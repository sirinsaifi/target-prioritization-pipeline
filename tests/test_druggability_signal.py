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
from app.config import TDL_SCORES, EVIDENCE_STRENGTH_HIGH_THRESHOLD
from scripts.ingest_evidence import _build_druggability_fields


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
