"""
Tests for app/ingestion/clinicaltrials_gov_client.py — the real gap this
source was built to close (BIIB078/WVE-004 missing from clinical_precedence
for C9orf72) is verified live in this task's write-up, not re-verified here
(no real network call in unit tests, per this project's existing
convention — see open_targets_client tests for the same pattern). These
tests confirm the noise-filtering logic against a controlled, real-shaped
fixture built directly from the actual live API response structure.
"""

from unittest.mock import patch, MagicMock

from app.ingestion.clinicaltrials_gov_client import get_clinical_trials


def _fake_study(nct_id, brief_title, overall_status, why_stopped, phases, interventions, study_type="INTERVENTIONAL", start_date="2022-01-01"):
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct_id, "briefTitle": brief_title},
            "statusModule": {
                "overallStatus": overall_status,
                "whyStopped": why_stopped,
                "startDateStruct": {"date": start_date, "type": "ACTUAL"},
            },
            "designModule": {"phases": phases, "studyType": study_type},
            "armsInterventionsModule": {"interventions": interventions},
        }
    }


def _mock_response(studies):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"studies": studies}
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def test_recovers_a_real_shaped_drug_trial():
    """Mirrors the real BIIB078 trial exactly (NCT04288856) — the specific
    case this source exists to recover."""
    studies = [_fake_study(
        "NCT04288856",
        "Study to Assess the Safety... BIIB078...",
        "TERMINATED",
        "There was no evidence of benefit across efficacy endpoints in the randomized trial, 245AS101.",
        ["PHASE1"],
        [{"name": "BIIB078", "type": "DRUG"}],
    )]
    with patch("app.ingestion.clinicaltrials_gov_client.requests.get", return_value=_mock_response(studies)):
        rows = get_clinical_trials("C9orf72", "Amyotrophic Lateral Sclerosis")

    assert len(rows) == 1
    assert rows[0]["nct_id"] == "NCT04288856"
    assert rows[0]["intervention_name"] == "BIIB078"
    assert rows[0]["overall_status"] == "TERMINATED"
    assert "no evidence of benefit" in rows[0]["why_stopped"]
    assert rows[0]["phases"] == ["PHASE1"]
    assert rows[0]["start_date"] == "2022-01-01"


def test_filters_out_non_drug_intervention_types():
    studies = [_fake_study(
        "NCT05747937", "Longitudinal Assessment...", "RECRUITING", None, ["NA"],
        [{"name": "Skin biopsy", "type": "DIAGNOSTIC_TEST"}, {"name": "Transcranial Pulse Stimulation", "type": "DEVICE"}],
    )]
    with patch("app.ingestion.clinicaltrials_gov_client.requests.get", return_value=_mock_response(studies)):
        rows = get_clinical_trials("C9orf72", "Amyotrophic Lateral Sclerosis")
    assert rows == []


def test_filters_out_observational_studies_with_no_real_intervention():
    studies = [_fake_study(
        "NCT03865420", "ALS Families Project", "RECRUITING", None, [],
        [], study_type="OBSERVATIONAL",
    )]
    with patch("app.ingestion.clinicaltrials_gov_client.requests.get", return_value=_mock_response(studies)):
        rows = get_clinical_trials("C9orf72", "Amyotrophic Lateral Sclerosis")
    assert rows == []


def test_filters_out_placebo_arms():
    studies = [_fake_study(
        "NCT04931862", "Study of WVE-004...", "TERMINATED",
        "no clinical benefit was seen at 24 weeks", ["PHASE1", "PHASE2"],
        [{"name": "WVE-004", "type": "DRUG"}, {"name": "Placebo", "type": "DRUG"}],
    )]
    with patch("app.ingestion.clinicaltrials_gov_client.requests.get", return_value=_mock_response(studies)):
        rows = get_clinical_trials("C9orf72", "Amyotrophic Lateral Sclerosis")

    assert len(rows) == 1
    assert rows[0]["intervention_name"] == "WVE-004"


def test_keeps_biological_and_genetic_intervention_types():
    studies = [_fake_study(
        "NCT99999999", "Gene therapy trial", "RECRUITING", None, ["PHASE1"],
        [{"name": "AAV-gene-therapy", "type": "GENETIC"}, {"name": "Antibody-X", "type": "BIOLOGICAL"}],
    )]
    with patch("app.ingestion.clinicaltrials_gov_client.requests.get", return_value=_mock_response(studies)):
        rows = get_clinical_trials("SOD1", "Amyotrophic Lateral Sclerosis")
    assert {r["intervention_name"] for r in rows} == {"AAV-gene-therapy", "Antibody-X"}


def test_returns_empty_list_when_no_studies_found():
    with patch("app.ingestion.clinicaltrials_gov_client.requests.get", return_value=_mock_response([])):
        rows = get_clinical_trials("ZZZFAKE9", "Fictional Test Syndrome")
    assert rows == []


def test_sends_real_gene_and_disease_as_query_params():
    with patch("app.ingestion.clinicaltrials_gov_client.requests.get", return_value=_mock_response([])) as mock_get:
        get_clinical_trials("C9orf72", "Amyotrophic Lateral Sclerosis")
    _, kwargs = mock_get.call_args
    assert kwargs["params"]["query.cond"] == "Amyotrophic Lateral Sclerosis"
    assert kwargs["params"]["query.term"] == "C9orf72"
