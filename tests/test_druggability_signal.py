"""
Tests for the Pharos druggability signal (this task) — Signal 1.

Covers: the TDL scorer mapping, the Pharos client's ligandCounts parsing +
not-found handling (mocked HTTP, no real network), the _build_druggability_
fields EvidenceRecord builder (raw_value=evidence_score=None discipline),
the new "druggability" gap type's trigger/suppress logic, and the
translational_opportunity Tdark-override / Tclin-reinforcement rules.

REAL, LIVE-CONFIRMED STATUS (see app/config.py TDL_SCORES docstring): none
of the 5 real ALS genes are Tclin or Tdark (all Tchem/Tbio), so the
druggability gap and the Tdark/Tclin translational rules are exercised here
via constructed test inputs, not real-data fixtures — same "real but
currently unexercised by today's data" status documented for several other
features in this project.
"""

from unittest.mock import patch, MagicMock

from app.core.scoring.dimension_scoring import score_druggability_tdl
from app.core.gaps.gap_taxonomy import (
    TargetEvidenceSummary, identify_gaps, GAP_TEMPLATES, WHY_IT_MATTERS, DECISION_IMPACT,
)
from app.core.classification.translational_opportunity import (
    TranslationalOpportunityInput, classify_translational_opportunity,
)
from app.ingestion.pharos_client import get_druggability_evidence, _parse_ligand_counts
from app.config import (
    TDL_SCORES, EVIDENCE_STRENGTH_HIGH_THRESHOLD,
    family_druggability_heuristic,
    DRUGGABLE_FAMILIES_FAVORABLE, DRUGGABLE_FAMILIES_CHALLENGING,
)
from app.core.verification.pharos_cross_checks import (
    disease_association_cross_check, ppi_cross_check, _parse_notes, _parse_partner_list,
)
from scripts.ingest_evidence import _build_druggability_fields, _format_ligand_activities


# --- TDL scorer mapping (the prototype 0-1 scale) ---------------------------

def test_tdl_score_mapping_matches_prototype_spec():
    """Tclin=1.0, Tchem=0.7, Tbio=0.4, Tdark=0.1 — the exact prototype mapping
    this task specified, documented as a prototype not an external reference."""
    assert score_druggability_tdl("Tclin") == 1.0
    assert score_druggability_tdl("Tchem") == 0.7
    assert score_druggability_tdl("Tbio") == 0.4
    assert score_druggability_tdl("Tdark") == 0.1


def test_tdl_score_matches_config_constant():
    """The scorer reads from config.TDL_SCORES (single source of truth), not
    a hardcoded duplicate dict — so changing the config changes the scorer."""
    for tdl, expected in TDL_SCORES.items():
        assert score_druggability_tdl(tdl) == expected


def test_tdl_score_none_for_missing_or_unrecognized():
    """None (target not found in Pharos) or an unrecognized tier returns None —
    a real absence of signal, never a fabricated 0.0 or silent Tdark default."""
    assert score_druggability_tdl(None) is None
    assert score_druggability_tdl("") is None
    assert score_druggability_tdl("Tunknown") is None


def test_tdl_score_is_case_sensitive_real_tiers():
    """Pharos returns exact-case tier strings ("Tclin", not "tclin"). The
    scorer does not lowercase — a wrong-case input is a real upstream shape
    change worth surfacing as None, not silently normalized."""
    assert score_druggability_tdl("tclin") is None
    assert score_druggability_tdl("TDARK") is None


# --- Pharos client: ligandCounts parsing + not-found handling (mocked) -------

def test_parse_ligand_counts_real_sod1_shape():
    """Real SOD1 shape (confirmed live): [{value:8,name:'ligand'},{value:0,name:'drug'}]
    -> (8, 0). Handles the list-of-{value,name} structure Pharos actually returns."""
    counts = [{"value": 8, "name": "ligand"}, {"value": 0, "name": "drug"}]
    assert _parse_ligand_counts(counts) == (8, 0)


def test_parse_ligand_counts_none_or_empty_is_zeros():
    """A null/empty ligandCounts (an undrugged target with no field at all) is
    a real (0, 0), not a parsing failure — confirmed: C9orf72 returns
    [{0,ligand},{0,drug}] but a truly missing field should also be (0, 0)."""
    assert _parse_ligand_counts(None) == (0, 0)
    assert _parse_ligand_counts([]) == (0, 0)


def test_get_druggability_evidence_returns_none_for_not_found_target():
    """Real not-found shape (confirmed live): {"data":{"target":null}} -> None.
    The client surfaces a real absence rather than fabricating a Tdark row."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": {"target": None}}
    mock_response.raise_for_status = MagicMock()
    with patch("app.ingestion.pharos_client.requests.post", return_value=mock_response):
        result = get_druggability_evidence("ZZZFAKEXX")
    assert result is None


def test_get_druggability_evidence_parses_real_found_target():
    """Real found-target shape: every field straight from the live API response,
    fam may be None (3 of 5 real ALS genes), ligand/drug counts parsed."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": {
            "target": {
                "name": "Guanine nucleotide exchange C9orf72",
                "tdl": "Tbio", "fam": None, "sym": "C9orf72",
                "description": "...", "novelty": 0.00096553,
                "publicationCount": 581,
                "ligandCounts": [{"value": 0, "name": "ligand"}, {"value": 0, "name": "drug"}],
            }
        }
    }
    mock_response.raise_for_status = MagicMock()
    with patch("app.ingestion.pharos_client.requests.post", return_value=mock_response):
        result = get_druggability_evidence("C9orf72")
    assert result is not None
    assert result["tdl"] == "Tbio"
    assert result["fam"] is None  # real null preserved, never defaulted
    assert result["novelty"] == 0.00096553
    assert result["ligand_count"] == 0
    assert result["drug_count"] == 0
    assert result["publication_count"] == 581


# --- Field builder: the raw_value/None discipline (kept out of priority) -----

def test_build_druggability_fields_stores_tdl_in_raw_value_not_evidence_score():
    """The core discipline: the TDL score lives in raw_value, evidence_score is
    None — so druggability can NEVER be silently averaged into evidence_strength
    or evidence_maturity (scoring.py only aggregates non-null evidence_score)."""
    row = {"sym": "SOD1", "name": "Superoxide dismutase", "tdl": "Tchem", "fam": "Enzyme",
           "description": "x", "novelty": 0.00039653, "publication_count": 1229,
           "ligand_count": 8, "drug_count": 0}
    fields = _build_druggability_fields(row)
    assert fields["dimension"] == "druggability"
    assert fields["data_source"] == "pharos"
    assert fields["source_type"] == "druggability"
    assert fields["raw_value"] == 0.7  # Tchem -> the real TDL score
    assert fields["evidence_score"] is None  # NEVER scored into priority
    assert "tdl=Tchem" in fields["notes"]
    assert "ligand_count=8" in fields["notes"]
    assert "novelty=0.00039653" in fields["notes"]


def test_build_druggability_fields_tdark_stores_low_score_still_none_evidence():
    """Tdark still stores its 0.1 score in raw_value (not 0.0, not None) — the
    real druggability signal is preserved for the gap/portfolio, just kept out
    of the priority composite."""
    row = {"sym": "X", "name": "X", "tdl": "Tdark", "fam": None, "description": None,
           "novelty": 0.5, "publication_count": 3, "ligand_count": 0, "drug_count": 0}
    fields = _build_druggability_fields(row)
    assert fields["raw_value"] == 0.1
    assert fields["evidence_score"] is None


# --- Druggability gap: trigger (Tdark + strong) / suppress (non-Tdark) -------

def _summary_with_tdl(tdl, **overrides) -> TargetEvidenceSummary:
    defaults = dict(
        gene_symbol="TESTGENE",
        dimension_scores={"genetic": 0.9},
        evidence_strength=0.9,
        evidence_consistency=1.0,
        evidence_maturity=0.4,
        has_pathway_evidence=True,
        has_human_clinical_evidence=True,
        has_known_compound=True,
        tdl=tdl,
    )
    defaults.update(overrides)
    return TargetEvidenceSummary(**defaults)


def test_druggability_gap_fires_for_tdark_with_strong_evidence():
    """The exact trigger: strong OTP evidence + Tdark. Biology says this target
    matters, but almost nothing is known about how to drug it."""
    findings = identify_gaps(_summary_with_tdl("Tdark"))
    types = [f.gap_type for f in findings]
    assert "druggability" in types
    druggability = next(f for f in findings if f.gap_type == "druggability")
    assert "Tdark" in druggability.rationale
    assert "druggability" in GAP_TEMPLATES["druggability"]  # template registered
    assert druggability.why_it_matters  # 5-part format populated
    assert druggability.decision_impact


def test_druggability_gap_suppressed_for_tchem_tbio_tclin():
    """Only Tdark triggers it — Tchem/Tbio/Tclin all have at least some
    druggability characterization and do NOT fire the gap. This is why none of
    the 5 real ALS genes (all Tchem/Tbio) trigger it today."""
    for tdl in ("Tchem", "Tbio", "Tclin"):
        findings = identify_gaps(_summary_with_tdl(tdl))
        assert "druggability" not in [f.gap_type for f in findings], (
            f"{tdl} should NOT trigger the druggability gap"
        )


def test_druggability_gap_suppressed_when_evidence_strength_below_threshold():
    """Same gate as safety_signal/essentiality_risk/modality: a target not being
    prioritized on its merits doesn't need a druggability-priority tension."""
    findings = identify_gaps(_summary_with_tdl("Tdark", evidence_strength=0.3))
    assert "druggability" not in [f.gap_type for f in findings]


def test_druggability_gap_suppressed_when_tdl_is_none():
    """None (Pharos had no target for this gene) does NOT default to Tdark —
    a real absence, not a fabricated gap."""
    findings = identify_gaps(_summary_with_tdl(None))
    assert "druggability" not in [f.gap_type for f in findings]


# --- Translational opportunity: Tdark override / Tclin reinforcement ---------

def _opp_input(**overrides) -> TranslationalOpportunityInput:
    defaults = dict(
        gene_symbol="TESTGENE", priority_score=0.9, evidence_maturity=0.9,
        has_known_compound=True, has_human_clinical_evidence=True,
        has_safety_signal=False, has_essentiality_risk=False,
    )
    defaults.update(overrides)
    return TranslationalOpportunityInput(**defaults)


def test_tdark_overrides_clinical_stage_to_early_stage_discovery():
    """The literal instruction: a Tdark target leans Early-Stage Discovery
    EVEN IF OTP evidence looks strong (here: would otherwise be Clinical-Stage
    with a known compound + clinical evidence). Druggability is a deeper
    obstacle than 'no compound found yet'."""
    inp = _opp_input(tdl="Tdark")
    result = classify_translational_opportunity(inp)
    assert result.category == "Early-Stage Discovery"
    assert "Tdark" in result.rationale
    assert "druggability" in result.rationale.lower() or "drug" in result.rationale.lower()


def test_tdark_does_not_override_de_risking_needed():
    """Safety first: a documented caution flag (safety/essentiality) is more
    urgent than druggability uncertainty, so De-risking Needed still wins."""
    inp = _opp_input(tdl="Tdark", has_essentiality_risk=True)
    result = classify_translational_opportunity(inp)
    assert result.category == "De-risking Needed"


def test_tclin_reinforces_clinical_stage_with_explicit_note():
    """A Tclin target (approved drugs already exist) reinforces the
    Clinical-Stage categorization — the rationale names Tclin explicitly."""
    inp = _opp_input(tdl="Tclin")
    result = classify_translational_opportunity(inp)
    assert result.category == "Clinical-Stage"
    assert "Tclin" in result.rationale


def test_tchem_tbio_tdl_does_not_change_category_from_clinical_stage():
    """Tchem/Tbio are mid-tier druggability — neither the Tdark override nor the
    Tclin reinforcement applies, so the category is unchanged by TDL. This is
    the real case for all 5 ALS genes today (all Clinical-Stage or De-risking)."""
    for tdl in ("Tchem", "Tbio"):
        inp = _opp_input(tdl=tdl)
        result = classify_translational_opportunity(inp)
        assert result.category == "Clinical-Stage"
        assert "Tclin" not in result.rationale
        assert "Tdark" not in result.rationale


def test_none_tdl_does_not_trigger_override():
    """None TDL (Pharos had no target) is treated as 'no druggability signal' —
    no Tdark override, no Tclin reinforcement, never a Tdark default."""
    inp = _opp_input(tdl=None)
    result = classify_translational_opportunity(inp)
    assert result.category == "Clinical-Stage"  # unchanged by None TDL
    assert "Tdark" not in result.rationale
    assert "Tclin" not in result.rationale


# --- Signal A: novelty stored as its own field, separate from TDL -----------

def test_novelty_stored_separate_from_tdl_score_in_notes():
    """Novelty is its own field in notes (novelty=...), NOT merged into the
    TDL-derived raw_value. TDL score (0.7 for Tchem) is in raw_value;
    novelty (0.00039653) is in notes — two distinct signals, never conflated."""
    row = {"sym": "SOD1", "name": "SOD1", "tdl": "Tchem", "fam": "Enzyme",
           "description": None, "novelty": 0.00039653, "publication_count": 1229,
           "ligand_count": 8, "drug_count": 0, "ligands": [], "als_association": None,
           "ppi": {"stringdb_count": 485, "total_count": 485, "partner_symbols": []}}
    fields = _build_druggability_fields(row)
    assert fields["raw_value"] == 0.7  # TDL-derived, not novelty
    parsed = _parse_notes(fields["notes"])
    assert parsed["novelty"] == "0.00039653"
    assert parsed["tdl"] == "Tchem"
    # Novelty and TDL are distinct: a target can be low-novelty yet Tdark.
    assert parsed["novelty"] != parsed["tdl"]


def test_novelty_documented_as_understudied_not_same_as_tdl():
    """The field-builder docstring must document that novelty represents
    under-studied-relative-to-importance, NOT the same as TDL. Checked via
    the module docstring of pharos_client (the canonical documentation point)."""
    import app.ingestion.pharos_client as pc
    assert "under-studied" in pc.__doc__.lower()
    assert "not the same as tdl" in pc.__doc__.lower() or "distinct from tdl" in pc.__doc__.lower()


# --- Signal B: protein family + prototype druggability heuristic ------------

def test_family_heuristic_favorable_for_kinase_and_enzyme():
    """Real ALS-gene families: SOD1=Enzyme, NEK1=Kinase — both favorable
    (historically strong small-molecule druggability track record)."""
    assert family_druggability_heuristic("Enzyme") == "favorable"
    assert family_druggability_heuristic("Kinase") == "favorable"


def test_family_heuristic_challenging_for_transcription_factor():
    assert family_druggability_heuristic("Transcription Factor") == "challenging"


def test_family_heuristic_neutral_for_null_and_unknown():
    """3 of 5 real ALS genes (C9orf72/TARDBP/FUS) have fam=null -> neutral.
    A real absence, not 'challenging'. Unknown families are also neutral."""
    assert family_druggability_heuristic(None) == "neutral"
    assert family_druggability_heuristic("Some Unknown Family") == "neutral"


def test_family_heuristic_case_insensitive():
    assert family_druggability_heuristic("kinase") == "favorable"
    assert family_druggability_heuristic("KINASE") == "favorable"


def test_family_heuristic_label_stored_in_notes():
    """The heuristic label is stored in notes as family_druggability_heuristic=...,
    visible context alongside the raw family name — never overrides TDL."""
    row = {"sym": "NEK1", "name": "Nek1", "tdl": "Tchem", "fam": "Kinase",
           "description": None, "novelty": 0.016, "publication_count": 62,
           "ligand_count": 165, "drug_count": 0, "ligands": [], "als_association": None,
           "ppi": {"stringdb_count": 83, "total_count": 88, "partner_symbols": []}}
    fields = _build_druggability_fields(row)
    parsed = _parse_notes(fields["notes"])
    assert parsed["family"] == "Kinase"
    assert parsed["family_druggability_heuristic"] == "favorable"
    assert fields["raw_value"] == 0.7  # TDL still drives raw_value, not the family heuristic


# --- Signal C: ligand activity detail (isdrug + activity type/value) --------

def test_ligand_detail_stores_isdrug_and_activity_type_value():
    """Per-compound isdrug (approved vs research) + activity type/value, not
    just a count. Real SOD1 shape: 8 research ligands, all EC50 pChEMBL values."""
    row = {"sym": "SOD1", "name": "SOD1", "tdl": "Tchem", "fam": "Enzyme",
           "description": None, "novelty": 0.0004, "publication_count": 1229,
           "ligand_count": 8, "drug_count": 0,
           "ligands": [{"name": "compound A", "isdrug": False, "actcnt": 1,
                        "activities": [{"type": "EC50", "value": 7.17, "moa": None}]},
                       {"name": "compound B", "isdrug": False, "actcnt": 1,
                        "activities": [{"type": "EC50", "value": 6.77, "moa": None}]}],
           "als_association": None,
           "ppi": {"stringdb_count": 485, "total_count": 485, "partner_symbols": []}}
    fields = _build_druggability_fields(row)
    notes = fields["notes"]
    assert "isdrug=False" in notes
    assert "EC50=7.17" in notes
    assert "EC50=6.77" in notes
    assert "compound A" in notes


def test_format_ligand_activities_handles_multiple_types():
    """A ligand with multiple activities (e.g. staurosporine: IC50 + IC50) is
    formatted compactly as 'IC50=8.04, IC50=7.74'."""
    activities = [{"type": "IC50", "value": 8.04, "moa": None},
                  {"type": "IC50", "value": 7.74, "moa": None}]
    assert _format_ligand_activities(activities) == "IC50=8.04, IC50=7.74"
    assert _format_ligand_activities([]) == "none"


def test_ligand_detail_none_when_no_ligands():
    """C9orf72/FUS have zero ligands -> ligand_detail=none (real absence,
    not a parse error). The aggregate count (ligand_count=0) is still stored."""
    row = {"sym": "C9orf72", "name": "C9orf72", "tdl": "Tbio", "fam": None,
           "description": None, "novelty": 0.0009, "publication_count": 581,
           "ligand_count": 0, "drug_count": 0, "ligands": [], "als_association": None,
           "ppi": {"stringdb_count": 111, "total_count": 111, "partner_symbols": []}}
    fields = _build_druggability_fields(row)
    parsed = _parse_notes(fields["notes"])
    assert parsed["ligand_count"] == "0"
    assert parsed["ligand_detail"] == "none"


# --- Signal D (PRIORITY): disease-association cross-check vs OTP -------------

def test_parse_notes_extracts_structured_fields():
    notes = "tdl=Tchem; novelty=0.0004; als_disgenet_score=0.7; als_evidence=24 PubMed IDs"
    parsed = _parse_notes(notes)
    assert parsed["tdl"] == "Tchem"
    assert parsed["novelty"] == "0.0004"
    assert parsed["als_disgenet_score"] == "0.7"


def test_disease_cross_check_agree_when_tiers_match():
    """Real SOD1-shaped case: Pharos DisGeNET=0.7 (High) vs OTP Genetic=0.99
    (High) -> AGREE. Both sources place SOD1's ALS evidence in the High band."""
    pharos_notes = "als_disgenet_score=0.7; als_evidence=24 PubMed IDs"
    breakdown = '{"genetic": 0.99, "literature": 1.0}'
    result = disease_association_cross_check("SOD1", pharos_notes, breakdown)
    assert result.check_type == "disease_association"
    assert result.verdict == "agree"
    assert "0.7" in result.pharos_value
    assert "0.99" in result.pipeline_value


def test_disease_cross_check_disagree_when_tiers_far_apart():
    """Pharos Low (0.2) vs OTP High (0.9) -> DISAGREE (2-tier gap). A real,
    surprising finding worth flagging — the two sources disagree on whether
    this target has strong ALS evidence."""
    pharos_notes = "als_disgenet_score=0.2"
    breakdown = '{"genetic": 0.9}'
    result = disease_association_cross_check("GENE", pharos_notes, breakdown)
    assert result.verdict == "disagree"


def test_disease_cross_check_partial_one_tier_gap():
    """Pharos Medium (0.5) vs OTP High (0.9) -> PARTIAL (1-tier gap). A real
    but milder disagreement, not a contradiction."""
    pharos_notes = "als_disgenet_score=0.5"
    breakdown = '{"genetic": 0.9}'
    result = disease_association_cross_check("FUS", pharos_notes, breakdown)
    assert result.verdict == "partial"


def test_disease_cross_check_incomparable_when_pharos_has_no_als_score():
    """None / missing als_disgenet_score -> incomparable, not a fabricated
    verdict. Real for a gene Pharos has no ALS entry for."""
    result = disease_association_cross_check("GENE", "tdl=Tchem", '{"genetic": 0.9}')
    assert result.verdict == "incomparable"


def test_disease_cross_check_incomparable_when_no_otp_scores():
    """No PriorityScore yet (scoring hasn't run) -> incomparable."""
    pharos_notes = "als_disgenet_score=0.7"
    result = disease_association_cross_check("GENE", pharos_notes, None)
    assert result.verdict == "incomparable"


def test_disease_cross_check_never_merges_values():
    """Both pharos_value and pipeline_value are always separate strings —
    never silently merged into a single number."""
    result = disease_association_cross_check("SOD1", "als_disgenet_score=0.7",
                                             '{"genetic": 0.99, "literature": 1.0}')
    assert result.pharos_value != result.pipeline_value
    assert "DisGeNET" in result.pharos_value
    assert "Genetic" in result.pipeline_value


# --- Signal E (PRIORITY): PPI cross-check vs STRING -------------------------

def test_parse_partner_list_extracts_symbols():
    notes = "high_confidence_partner_count=10; partners=SOD1, TARDBP, FUS"
    partners = _parse_partner_list(notes, "partners")
    assert partners == {"SOD1", "TARDBP", "FUS"}


def test_ppi_cross_check_agree_when_high_overlap():
    """Real expected case: STRING high-confidence partners are a subset of
    Pharos's full STRINGDB set -> high overlap -> AGREE (reassuring)."""
    pharos_notes = "ppi_stringdb_count=485; ppi_partners=TARDBP, C9orf72, FUS, CCS, SOD2"
    string_notes = "high_confidence_partner_count=3; partners=TARDBP, C9orf72, FUS"
    result = ppi_cross_check("SOD1", pharos_notes, string_notes)
    assert result.check_type == "ppi"
    assert result.verdict == "agree"
    assert result.details["overlap"] == 3


def test_ppi_cross_check_disagree_when_low_overlap():
    """Low overlap (<20%) -> DISAGREE — a real, surprising divergence worth
    flagging (the two STRINGDB-derived lists disagree on which partners exist)."""
    pharos_notes = "ppi_stringdb_count=100; ppi_partners=AAA, BBB, CCC"
    string_notes = "high_confidence_partner_count=10; partners=DDD, EEE, FFF, GGG, HHH, III, JJJ, KKK, LLL, MMM"
    result = ppi_cross_check("GENE", pharos_notes, string_notes)
    assert result.verdict == "disagree"


def test_ppi_cross_check_partial_moderate_overlap():
    pharos_notes = "ppi_stringdb_count=50; ppi_partners=AAA, BBB, CCC"
    string_notes = "high_confidence_partner_count=10; partners=AAA, BBB, X1, X2, X3, X4, X5, X6, X7, X8"
    result = ppi_cross_check("GENE", pharos_notes, string_notes)
    assert result.verdict == "partial"  # 2/10 = 20%


def test_ppi_cross_check_incomparable_when_either_source_empty():
    """No partners in either source -> incomparable, not a fabricated verdict."""
    result = ppi_cross_check("GENE", "ppi_stringdb_count=0; ppi_partners=none", None)
    assert result.verdict == "incomparable"


def test_ppi_cross_check_never_merges_values():
    result = ppi_cross_check("SOD1",
                             "ppi_stringdb_count=485; ppi_partners=TARDBP, FUS",
                             "high_confidence_partner_count=2; partners=TARDBP, FUS")
    assert "485" in result.pharos_value
    assert "high-confidence" in result.pipeline_value
    assert result.pharos_value != result.pipeline_value
