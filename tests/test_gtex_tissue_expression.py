"""
Tests for the GTEx tissue-expression integration: the real tau statistic
(app/core/scoring/dimension_scoring.py's compute_tau_specificity()) and
the field-derivation + HPA cross-check
(scripts/ingest_evidence.py's _build_gtex_fields()) — see
app/ingestion/gtex_client.py's module docstring for the design decision
(second tissue_expression source, not a new "omics" dimension).
"""

from app.config import SOURCE_TYPE_BY_DATA_SOURCE
from app.core.scoring.dimension_scoring import compute_tau_specificity
from scripts.ingest_evidence import _build_gtex_fields, _tau_to_hpa_like_category


# --- compute_tau_specificity ------------------------------------------------

def test_tau_is_zero_for_perfectly_uniform_expression():
    assert compute_tau_specificity({"Liver": 100.0, "Brain": 100.0, "Muscle": 100.0}) == 0.0


def test_tau_is_high_for_a_single_specific_tissue():
    tau = compute_tau_specificity({"Liver": 1000.0, "Brain": 1.0, "Muscle": 1.0, "Skin": 1.0})
    assert tau > 0.9


def test_tau_uses_real_sod1_shaped_data():
    """Real, broadly-expressed housekeeping-like profile (SOD1's actual
    shape: hundreds of TPM across most tissues, no extreme outlier) should
    score LOW (broad expression), not high."""
    real_shaped = {
        "Liver": 378.478, "Adrenal_Gland": 377.499, "Brain_Frontal_Cortex_BA9": 347.651,
        "Brain_Hypothalamus": 301.111, "Brain_Spinal_cord_cervical_c-1": 289.02,
        "Artery_Aorta": 276.404, "Pancreas": 33.4015, "Whole_Blood": 33.0538,
    }
    tau = compute_tau_specificity(real_shaped)
    assert tau is not None
    assert tau < 0.7  # broadly expressed, not tissue-specific


def test_tau_returns_none_for_fewer_than_two_tissues():
    assert compute_tau_specificity({"Liver": 100.0}) is None
    assert compute_tau_specificity({}) is None


def test_tau_returns_none_when_never_expressed():
    assert compute_tau_specificity({"Liver": 0.0, "Brain": 0.0}) is None


# --- _tau_to_hpa_like_category ----------------------------------------------

def test_tau_bucket_boundaries_match_hpa_real_tiers():
    assert _tau_to_hpa_like_category(0.9) == "tissue enriched"
    assert _tau_to_hpa_like_category(0.6) == "group enriched"
    assert _tau_to_hpa_like_category(0.3) == "tissue enhanced"
    assert _tau_to_hpa_like_category(0.1) == "low tissue specificity"


# --- _build_gtex_fields ------------------------------------------------------

def test_registered_as_tissue_expression_not_omics():
    assert SOURCE_TYPE_BY_DATA_SOURCE["gtex"] == "tissue_expression"


def test_build_gtex_fields_real_sod1_shaped_data_with_agreeing_hpa_category():
    median_by_tissue = {
        "Liver": 378.478, "Adrenal_Gland": 377.499, "Pancreas": 33.4015, "Whole_Blood": 33.0538,
    }
    # HPA's real historical category for SOD1 this session was "Tissue enhanced" —
    # a broad-ish category, roughly consistent with a low/mid tau.
    fields = _build_gtex_fields(median_by_tissue, "SOD1", hpa_category="Tissue enhanced")

    assert fields["dimension"] == "tissue_expression"
    assert fields["data_source"] == "gtex"
    assert fields["source_record_id"] == "gtex:SOD1"
    assert fields["tissue"] == "Liver"  # highest real median
    assert fields["evidence_score"] == fields["raw_value"]  # tau used directly as the score
    assert "tau_specificity=" in fields["notes"]
    assert "top_tissues=" in fields["notes"]
    assert "HPA='Tissue enhanced'" in fields["notes"]


def test_build_gtex_fields_notes_disagreement_honestly():
    # Highly tissue-specific real shape (one dominant tissue) vs HPA saying broad.
    median_by_tissue = {"Brain_Cortex": 5000.0, "Liver": 1.0, "Muscle": 1.0, "Skin": 1.0}
    fields = _build_gtex_fields(median_by_tissue, "TESTGENE", hpa_category="Low tissue specificity")
    assert "DISAGREE" in fields["notes"]


def test_build_gtex_fields_handles_missing_hpa_category():
    fields = _build_gtex_fields({"Liver": 100.0, "Brain": 50.0}, "TESTGENE", hpa_category=None)
    assert "HPA category not available for comparison" in fields["notes"]
