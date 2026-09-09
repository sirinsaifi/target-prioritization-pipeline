"""
Tests for the two remaining real Open Targets Target Prioritisation
Factors from this task — Gene Essentiality and Paralogues (see
app/ingestion/open_targets_client.py's get_essentiality_and_paralogues()
docstring for the real field semantics, confirmed live against
platform-docs.opentargets.org and via live GraphQL introspection).

Real finding across all 5 ALS genes (see CLAUDE.md): SOD1 and TARDBP are
both flagged essential by OTP/DepMap; C9orf72/FUS/NEK1 are not. None of the
5 genes' real paralogues cross OTP's own official 60% redundancy-flagging
threshold, but FUS's real EWSR1 match (~56%) crosses this project's own,
more inclusive 40% note-worthiness threshold — so the Modality-gap
enrichment path is real and tested here via construction, same
"real mechanism, currently unexercised by live gap output" pattern as
safety_signal.
"""

from unittest.mock import patch

from app.config import (
    SOURCE_TYPE_BY_DATA_SOURCE, COMPARABILITY_FIELDS_BY_SOURCE_TYPE, DIMENSION_MATURITY_LADDER,
    MVP_DIMENSIONS, PARALOGUE_MODALITY_NOTE_IDENTITY_THRESHOLD,
)
from app.ingestion.open_targets_client import get_essentiality_and_paralogues
from app.core.presentation.source_links import get_source_url
from app.core.gaps.gap_taxonomy import TargetEvidenceSummary, identify_gaps
from scripts.ingest_evidence import _build_essentiality_fields, _build_paralogy_fields


# --- get_essentiality_and_paralogues (mocked _run_query, no real network) --

def test_get_essentiality_and_paralogues_real_sod1_shape():
    """Mirrors real live SOD1 data confirmed during this task: isEssential
    True, geneEssentiality=-1, 2 real human paralogues (CCS, SOD3), 12
    real cross-species orthologues correctly excluded."""
    fake_data = {
        "target": {
            "isEssential": True,
            "depMapEssentiality": [
                {"tissueId": "UBERON_0003975", "tissueName": "internal female genitalia",
                 "screens": [{"geneEffect": -2.2168540954589844}, {"geneEffect": -1.120680332183838}]},
            ],
            "homologues": [
                {"speciesId": "9606", "speciesName": "Human", "homologyType": "other_paralog",
                 "targetGeneId": "ENSG00000173992", "targetGeneSymbol": "CCS",
                 "queryPercentageIdentity": 47.4026, "targetPercentageIdentity": 26.6423},
                {"speciesId": "9606", "speciesName": "Human", "homologyType": "other_paralog",
                 "targetGeneId": "ENSG00000109610", "targetGeneSymbol": "SOD3",
                 "queryPercentageIdentity": 39.6104, "targetPercentageIdentity": 25.4167},
                {"speciesId": "9598", "speciesName": "Chimpanzee", "homologyType": "ortholog_one2one",
                 "targetGeneId": "ENSPTRG00000000001", "targetGeneSymbol": "SOD1",
                 "queryPercentageIdentity": 100.0, "targetPercentageIdentity": 100.0},
            ],
            "prioritisation": {"items": [
                {"key": "geneEssentiality", "value": "-1"},
                {"key": "paralogMaxIdentityPercentage", "value": "0"},
            ]},
        }
    }
    with patch("app.ingestion.open_targets_client._run_query", return_value=fake_data):
        result = get_essentiality_and_paralogues("ENSG00000142168")

    assert result["is_essential"] is True
    assert result["gene_essentiality_prioritisation"] == "-1"
    assert result["paralog_max_identity_prioritisation"] == "0"
    assert len(result["depmap_essentiality_rows"]) == 1
    # The real cross-species ortholog (chimp SOD1) must NOT be counted as a
    # real human paralogue.
    assert len(result["human_paralogues"]) == 2
    symbols = {h["targetGeneSymbol"] for h in result["human_paralogues"]}
    assert symbols == {"CCS", "SOD3"}


def test_get_essentiality_and_paralogues_real_c9orf72_shape_no_paralogues():
    """Mirrors real live C9orf72 data: not essential, and genuinely zero
    real human paralogues (paralogMaxIdentityPercentage absent = NA, not 0)."""
    fake_data = {
        "target": {
            "isEssential": False,
            "depMapEssentiality": [],
            "homologues": [],
            "prioritisation": {"items": [{"key": "geneEssentiality", "value": "0"}]},
        }
    }
    with patch("app.ingestion.open_targets_client._run_query", return_value=fake_data):
        result = get_essentiality_and_paralogues("ENSG00000147894")

    assert result["is_essential"] is False
    assert result["human_paralogues"] == []
    assert result["paralog_max_identity_prioritisation"] is None


# --- _build_essentiality_fields ---------------------------------------------

def test_registered_as_its_own_source_type_excluded_from_contradictions_and_maturity():
    assert SOURCE_TYPE_BY_DATA_SOURCE["ot_essentiality"] == "essentiality_risk"
    assert COMPARABILITY_FIELDS_BY_SOURCE_TYPE["essentiality_risk"] == []
    assert "essentiality_risk" not in DIMENSION_MATURITY_LADDER
    assert "essentiality_risk" not in MVP_DIMENSIONS


def test_build_essentiality_fields_real_sod1_essential():
    depmap_rows = [
        {"screens": [{"geneEffect": -2.2168540954589844}, {"geneEffect": -1.120680332183838}]},
    ]
    fields = _build_essentiality_fields("SOD1", True, "-1", depmap_rows)

    assert fields["dimension"] == "essentiality_risk"
    assert fields["data_source"] == "ot_essentiality"
    assert fields["source_record_id"] == "ot_essentiality:SOD1"
    # Deliberately unscored — see the docstring's reasoning.
    assert fields["evidence_score"] is None
    assert fields["raw_value"] == -1.0
    assert "isEssential=True" in fields["notes"]
    assert "depmap_screens_n=2" in fields["notes"]
    assert "mean_geneEffect=-1.6688" in fields["notes"]


def test_build_essentiality_fields_real_c9orf72_not_essential():
    fields = _build_essentiality_fields("C9orf72", False, "0", [])
    assert fields["raw_value"] == 0.0
    assert "isEssential=False" in fields["notes"]
    assert "no real DepMap screen rows available" in fields["notes"]


def test_build_essentiality_fields_handles_missing_prioritisation_value():
    fields = _build_essentiality_fields("TESTGENE", None, None, [])
    assert fields["raw_value"] is None
    assert fields["evidence_score"] is None


# --- _build_paralogy_fields --------------------------------------------------

def test_registered_as_its_own_source_type_two_sided_not_a_gap_trigger():
    assert SOURCE_TYPE_BY_DATA_SOURCE["ot_paralogy"] == "paralogy"
    assert COMPARABILITY_FIELDS_BY_SOURCE_TYPE["paralogy"] == []
    assert "paralogy" not in DIMENSION_MATURITY_LADDER
    assert "paralogy" not in MVP_DIMENSIONS


def test_build_paralogy_fields_real_fus_ewsr1_crosses_project_note_threshold():
    """Real live FUS data: EWSR1 at ~56% identity — below OTP's own 60%
    redundancy cutoff, but above this project's own, more inclusive 40%
    note-worthiness threshold (see config.PARALOGUE_MODALITY_NOTE_IDENTITY_
    THRESHOLD's docstring for why these are deliberately different numbers)."""
    row = {
        "targetGeneId": "ENSG00000182944", "targetGeneSymbol": "EWSR1",
        "queryPercentageIdentity": 56.2738, "targetPercentageIdentity": 45.122,
    }
    fields = _build_paralogy_fields("FUS", row)

    assert fields["dimension"] == "paralogy"
    assert fields["data_source"] == "ot_paralogy"
    assert fields["source_record_id"] == "ot_paralogy:FUS:EWSR1"
    assert fields["evidence_score"] is None  # deliberately two-sided, never scored
    assert fields["raw_value"] == 56.2738
    assert fields["external_id"] == "ENSG00000182944"
    assert "paralog_gene=EWSR1" in fields["notes"]
    assert f"above_project_note_threshold_{PARALOGUE_MODALITY_NOTE_IDENTITY_THRESHOLD:.0f}pct=yes" in fields["notes"]


def test_build_paralogy_fields_real_tardbp_low_identity_below_threshold():
    """Real live TARDBP data: many real paralogue hits, but at LOW
    identity (e.g. RBM38 ~16%) — correctly below this project's own 40%
    note-worthiness threshold, distinguishing a loose RRM-domain-sharing
    superfamily from a genuinely close paralogue like FUS/EWSR1 above."""
    row = {
        "targetGeneId": "ENSG00000132819", "targetGeneSymbol": "RBM38",
        "queryPercentageIdentity": 9.42029, "targetPercentageIdentity": 16.318,
    }
    fields = _build_paralogy_fields("TARDBP", row)
    assert fields["raw_value"] == 16.318
    assert "above_project_note_threshold_40pct=no" in fields["notes"]


# --- gap_taxonomy: essentiality_risk gap + modality-gap paralogue enrichment

def test_no_gaps_when_everything_covered_including_essentiality_and_paralogy():
    summary = TargetEvidenceSummary(
        gene_symbol="SOD1",
        dimension_scores={"genetic": 0.9, "literature": 0.9, "pathway": 0.9, "human_clinical": 0.9},
        evidence_strength=0.9, evidence_consistency=1.0, evidence_maturity=1.0,
        has_pathway_evidence=True, has_human_clinical_evidence=True, has_known_compound=True,
        has_essentiality_risk=False, paralogue_high_identity_matches=[],
    )
    assert identify_gaps(summary) == []


def test_essentiality_risk_gap_fires_with_strong_evidence_and_real_essential_flag():
    """Constructed KCNH2-shaped fixture (real ALS data has never fired this
    combination — see module docstring): a strong target flagged essential."""
    summary = TargetEvidenceSummary(
        gene_symbol="KCNH2",
        dimension_scores={"genetic": 0.9, "literature": 0.9, "pathway": 0.9, "human_clinical": 0.9},
        evidence_strength=0.9, evidence_consistency=1.0, evidence_maturity=1.0,
        has_pathway_evidence=True, has_human_clinical_evidence=True, has_known_compound=True,
        has_essentiality_risk=True,
        essentiality_risk_note="isEssential=True; prioritisation_geneEssentiality=-1",
    )
    findings = identify_gaps(summary)
    types = [f.gap_type for f in findings]
    assert "essentiality_risk" in types
    finding = next(f for f in findings if f.gap_type == "essentiality_risk")
    assert "KCNH2" in finding.investigation_suggestion
    assert "does not automatically disqualify" in finding.investigation_suggestion
    # The real SOD1/tofersen counter-example must be named so a reader
    # doesn't over-read a flag here as definitive.
    assert "tofersen" in finding.investigation_suggestion


def test_essentiality_risk_gap_suppressed_when_evidence_strength_is_low():
    summary = TargetEvidenceSummary(
        gene_symbol="WEAKGENE",
        dimension_scores={}, evidence_strength=0.3, evidence_consistency=1.0, evidence_maturity=0.2,
        has_pathway_evidence=False, has_human_clinical_evidence=False, has_known_compound=False,
        has_essentiality_risk=True, essentiality_risk_note="isEssential=True",
    )
    types = [f.gap_type for f in identify_gaps(summary)]
    assert "essentiality_risk" not in types


def test_modality_gap_enriched_with_real_paralogue_note_when_present():
    """Real FUS-shaped scenario: strong evidence, no known compound, and a
    real high-identity paralogue (EWSR1) present."""
    summary = TargetEvidenceSummary(
        gene_symbol="FUS",
        dimension_scores={"genetic": 0.9, "literature": 0.9}, evidence_strength=0.9,
        evidence_consistency=1.0, evidence_maturity=0.5,
        has_pathway_evidence=True, has_human_clinical_evidence=False, has_known_compound=False,
        paralogue_high_identity_matches=["EWSR1 (56.3% identity)"],
    )
    findings = identify_gaps(summary)
    modality = next(f for f in findings if f.gap_type == "modality")
    assert "EWSR1 (56.3% identity)" in modality.investigation_suggestion
    assert "redundancy" in modality.investigation_suggestion


def test_modality_gap_not_enriched_when_no_high_identity_paralogue():
    """Real TARDBP-shaped scenario: same modality gap trigger, but no
    paralogue crosses this project's own note-worthiness threshold — the
    gap still fires (unrelated trigger condition), just without the note."""
    summary = TargetEvidenceSummary(
        gene_symbol="TARDBP",
        dimension_scores={"genetic": 0.9}, evidence_strength=0.9,
        evidence_consistency=1.0, evidence_maturity=0.5,
        has_pathway_evidence=True, has_human_clinical_evidence=False, has_known_compound=False,
        paralogue_high_identity_matches=[],
    )
    modality = next(f for f in identify_gaps(summary) if f.gap_type == "modality")
    assert "redundancy" not in modality.investigation_suggestion


def test_modality_gap_trigger_condition_unaffected_by_paralogue_matches():
    """The paralogue note must NEVER be the reason the gap fires or doesn't
    — only has_known_compound controls that."""
    summary = TargetEvidenceSummary(
        gene_symbol="HASCOMPOUND",
        dimension_scores={}, evidence_strength=0.9, evidence_consistency=1.0, evidence_maturity=0.5,
        has_pathway_evidence=True, has_human_clinical_evidence=True, has_known_compound=True,
        paralogue_high_identity_matches=["SOMEGENE (90% identity)"],
    )
    types = [f.gap_type for f in identify_gaps(summary)]
    assert "modality" not in types


# --- source_links.py: ot_essentiality / ot_paralogy -------------------------

def test_ot_essentiality_links_to_the_real_target_page():
    url = get_source_url("ot_essentiality", "ot_essentiality:SOD1", None, None, "ENSG00000142168")
    assert url == "https://platform.opentargets.org/target/ENSG00000142168"


def test_ot_paralogy_links_to_the_real_paralogue_gene_page_not_the_current_gene():
    url = get_source_url("ot_paralogy", "ot_paralogy:SOD1:CCS", None, "ENSG00000173992", "ENSG00000142168")
    assert url == "https://www.ensembl.org/Homo_sapiens/Gene/Summary?g=ENSG00000173992"


def test_ot_paralogy_returns_none_without_real_external_id():
    assert get_source_url("ot_paralogy", "ot_paralogy:SOD1:CCS", None, None, "ENSG00000142168") is None
