"""
Tests for scripts/ingest_evidence.py's ClinicalTrials.gov field-derivation
(_map_ctgov_phases_to_clinical_stage(), _build_ctgov_clinical_fields()) —
the second, independent human_clinical source added to recover real trials
OTP's clinical_precedence datasource misses entirely (BIIB078/WVE-004 for
C9orf72 — see app/ingestion/clinicaltrials_gov_client.py's module
docstring). Real trial shapes used below are the actual live API data for
these two trials, not constructed fixtures.
"""

from app.config import SOURCE_TYPE_BY_DATA_SOURCE, COMPARABILITY_FIELDS_BY_SOURCE_TYPE
from scripts.ingest_evidence import _map_ctgov_phases_to_clinical_stage, _build_ctgov_clinical_fields


# --- _map_ctgov_phases_to_clinical_stage ------------------------------------

def test_maps_single_phase():
    assert _map_ctgov_phases_to_clinical_stage(["PHASE1"]) == "phase_1"
    assert _map_ctgov_phases_to_clinical_stage(["PHASE4"]) == "phase_4"


def test_maps_combined_phases():
    assert _map_ctgov_phases_to_clinical_stage(["PHASE1", "PHASE2"]) == "phase_1_2"
    assert _map_ctgov_phases_to_clinical_stage(["PHASE2", "PHASE3"]) == "phase_2_3"


def test_maps_early_phase1():
    assert _map_ctgov_phases_to_clinical_stage(["EARLY_PHASE1"]) == "early_phase_1"


def test_maps_na_or_empty_to_unknown():
    assert _map_ctgov_phases_to_clinical_stage(["NA"]) == "unknown"
    assert _map_ctgov_phases_to_clinical_stage([]) == "unknown"


# --- _build_ctgov_clinical_fields -------------------------------------------

def test_registered_as_its_own_data_source_in_the_clinical_group():
    # Distinct from clinical_precedence — same comparability group (real
    # fields: population/endpoint/intervention all still apply), but a
    # different, separately-visible data_source (this task's own requirement).
    assert SOURCE_TYPE_BY_DATA_SOURCE["clinicaltrials_gov"] == "clinical"
    assert COMPARABILITY_FIELDS_BY_SOURCE_TYPE["clinical"] == ["population", "endpoint", "intervention"]


def test_build_ctgov_fields_for_real_biib078_trial():
    """Real live data: NCT04288856, the BIIB078 trial this source exists
    to recover for C9orf72."""
    row = {
        "nct_id": "NCT04288856",
        "brief_title": "Study to Assess the Safety, Tolerability, Pharmacokinetics, and Effect on Disease Progression of BIIB078...",
        "overall_status": "TERMINATED",
        "why_stopped": (
            "There was no evidence of benefit across efficacy endpoints in the randomized trial, 245AS101. "
            "Accordingly, Biogen has made the difficult decision to discontinue the BIIB078 program."
        ),
        "phases": ["PHASE1"],
        "start_date": "2020-03-10",
        "intervention_name": "BIIB078",
        "intervention_type": "DRUG",
    }
    fields = _build_ctgov_clinical_fields(row)

    assert fields["source_type"] == "clinical"
    assert fields["source_record_id"] == "NCT04288856"
    assert fields["external_id"] == "NCT04288856"
    assert fields["intervention"] == "biib078"
    assert fields["publication_year"] == 2020
    assert "no evidence of benefit" in fields["notes"]
    # Real, honest finding (this task): "no evidence of benefit" trips none
    # of the 3 existing TRIAL_STOP_NEGATIVE_KEYWORDS ("negative"/"safety"/
    # "adverse"), so stopped_early is False and this scores on clinical_stage
    # (phase_1) alone, without the 0.5x early-stop down-weight.
    assert fields["evidence_score"] == 0.1  # CLINICAL_STAGE_SCORES["phase_1"], no down-weight applied


def test_build_ctgov_fields_for_real_wve004_trial():
    """Real live data: NCT04931862, the WVE-004 trial this source exists
    to recover for C9orf72."""
    row = {
        "nct_id": "NCT04931862",
        "brief_title": "Study of WVE-004 in Patients With C9orf72-associated Amyotrophic Lateral Sclerosis (ALS) or Frontotemporal Dementia (FTD)",
        "overall_status": "TERMINATED",
        "why_stopped": (
            "Despite robust, sustained reductions in poly(GP), no clinical benefit was seen at 24 weeks, and "
            "reductions in poly(GP) were not associated with stabilization in functional outcomes. Based on these "
            "data, Wave decided to stop development of WVE-004."
        ),
        "phases": ["PHASE1", "PHASE2"],
        "start_date": "2021-08-01",
        "intervention_name": "WVE-004",
        "intervention_type": "DRUG",
    }
    fields = _build_ctgov_clinical_fields(row)

    assert fields["source_record_id"] == "NCT04931862"
    assert fields["intervention"] == "wve-004"
    assert fields["publication_year"] == 2021
    # Same real, honest finding as BIIB078 above — neither real trial's
    # whyStopped text trips the existing negative/safety/adverse keywords.
    assert fields["evidence_score"] == 0.15  # CLINICAL_STAGE_SCORES["phase_1_2"], no down-weight applied


def test_build_ctgov_fields_applies_down_weight_when_keyword_present():
    """Constructed case proving the down-weight logic IS reachable via this
    source when real text happens to use one of the 3 existing keywords —
    contrasts with BIIB078/WVE-004 above, whose real text doesn't."""
    row = {
        "nct_id": "NCT00000000",
        "brief_title": "Some trial",
        "overall_status": "TERMINATED",
        "why_stopped": "Stopped early due to a safety signal in the treatment arm.",
        "phases": ["PHASE2"],
        "start_date": "2019-01-01",
        "intervention_name": "SomeDrug",
        "intervention_type": "DRUG",
    }
    fields = _build_ctgov_clinical_fields(row)
    assert fields["evidence_score"] == 0.1  # 0.2 (phase_2) * 0.5 (TRIAL_STOPPED_EARLY_WEIGHT)


def test_build_ctgov_fields_handles_missing_why_stopped():
    row = {
        "nct_id": "NCT11111111", "brief_title": "Active trial", "overall_status": "RECRUITING",
        "why_stopped": None, "phases": ["PHASE3"], "start_date": None,
        "intervention_name": "ActiveDrug", "intervention_type": "DRUG",
    }
    fields = _build_ctgov_clinical_fields(row)
    assert fields["evidence_score"] == 0.7  # CLINICAL_STAGE_SCORES["phase_3"]
    assert fields["publication_year"] is None
