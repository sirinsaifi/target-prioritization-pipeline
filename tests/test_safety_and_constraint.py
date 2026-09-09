"""
Tests for the two new real Open Targets Target Prioritisation Factors —
Known Safety Events and Genetic Constraint (see
app/ingestion/open_targets_client.py's get_prioritisation_and_safety()
docstring for the real field semantics, confirmed live against
platform-docs.opentargets.org). Real finding for all 5 ALS genes: zero
documented safety events (see CLAUDE.md) — the safety_signal gap path is
real but unexercised by current data, covered here by construction
instead, same pattern as other real-but-unexercised branches in this
codebase.
"""

from unittest.mock import patch

from app.config import SOURCE_TYPE_BY_DATA_SOURCE, COMPARABILITY_FIELDS_BY_SOURCE_TYPE, DIMENSION_MATURITY_LADDER
from app.ingestion.open_targets_client import get_prioritisation_and_safety
from app.core.presentation.source_links import get_source_url
from scripts.ingest_evidence import _build_genetic_constraint_fields, _build_safety_signal_fields


# --- get_prioritisation_and_safety (mocked _run_query, no real network) ---

def test_get_prioritisation_and_safety_real_sod1_shape():
    """Mirrors real live SOD1 data confirmed during this task: empty
    safetyLiabilities, no hasSafetyEvent key at all (real "no information
    available", not "no events")."""
    fake_data = {
        "target": {
            "geneticConstraint": [
                {"constraintType": "syn", "score": -0.305, "exp": 57.74, "obs": 62, "oe": 1.074},
                {"constraintType": "mis", "score": 1.224, "exp": 146.57, "obs": 106, "oe": 0.723},
                {"constraintType": "lof", "score": 0.012, "exp": 7.69, "obs": 6, "oe": 0.78},
            ],
            "safetyLiabilities": [],
            "prioritisation": {"items": [
                {"key": "geneticConstraint", "value": "0.692553778268064"},
                {"key": "hasLigand", "value": "0"},
            ]},
        }
    }
    with patch("app.ingestion.open_targets_client._run_query", return_value=fake_data):
        result = get_prioritisation_and_safety("ENSG00000142168")

    assert result["genetic_constraint_prioritisation"] == "0.692553778268064"
    assert result["has_safety_event_flag"] is None  # key absent -> "no information available"
    assert result["safety_liabilities"] == []
    assert len(result["genetic_constraint_rows"]) == 3


def test_get_prioritisation_and_safety_real_kcnh2_shape():
    """Mirrors real live KCNH2/hERG data: hasSafetyEvent="-1" present
    alongside a real, non-empty safetyLiabilities list — the "-1 means HAS
    an event" semantics this task's own investigation confirmed via
    platform-docs.opentargets.org (not the OPPOSITE, more intuitive-looking
    "-1 = no data" reading that the raw values alone would suggest)."""
    fake_data = {
        "target": {
            "geneticConstraint": [],
            "safetyLiabilities": [{
                "event": "prolongation of QT interval of ECG", "eventId": "HP_0001657",
                "datasource": "Bowes et al. (2012)", "url": None,
                "biosamples": [{"tissueLabel": "cardiovascular system"}],
                "effects": [{"dosing": "general", "direction": "Inhibition/Decrease/Downregulation"}],
            }],
            "prioritisation": {"items": [{"key": "hasSafetyEvent", "value": "-1"}]},
        }
    }
    with patch("app.ingestion.open_targets_client._run_query", return_value=fake_data):
        result = get_prioritisation_and_safety("ENSG00000055118")

    assert result["has_safety_event_flag"] == "-1"
    assert len(result["safety_liabilities"]) == 1
    assert result["safety_liabilities"][0]["event"] == "prolongation of QT interval of ECG"


# --- _build_genetic_constraint_fields ---------------------------------------

def test_registered_as_genetic_not_a_new_dimension():
    assert SOURCE_TYPE_BY_DATA_SOURCE["ot_genetic_constraint"] == "genetic"


def test_build_genetic_constraint_fields_real_sod1_value():
    """Real live value: SOD1 prioritisation.geneticConstraint=0.6926 ->
    fairly tolerant to LoF, consistent with tofersen being an approved
    LoF-mimicking knockdown therapy for this gene."""
    raw_rows = [{"constraintType": "lof", "score": 0.012, "exp": 7.69, "obs": 6, "oe": 0.78}]
    fields = _build_genetic_constraint_fields("SOD1", "0.692553778268064", raw_rows)

    assert fields["dimension"] == "genetic"
    assert fields["data_source"] == "ot_genetic_constraint"
    assert fields["source_record_id"] == "ot_genetic_constraint:SOD1"
    assert fields["evidence_score"] == 0.8463  # (0.6926 + 1) / 2, this project's own linear remap
    assert "lof_oe=0.7800" in fields["notes"]


def test_build_genetic_constraint_fields_real_fus_value_highly_constrained():
    """Real live value: FUS prioritisation.geneticConstraint=-0.9933 ->
    extremely LoF-intolerant/essential — a genuinely different real
    finding from SOD1, worth being able to tell apart via the score."""
    raw_rows = [{"constraintType": "lof", "score": 1, "exp": 74.81, "obs": 3, "oe": 0.0401}]
    fields = _build_genetic_constraint_fields("FUS", "-0.9932708218422505", raw_rows)
    assert fields["evidence_score"] == 0.0034  # (−0.9933 + 1) / 2 — near zero, correctly the low end


def test_build_genetic_constraint_fields_handles_missing_prioritisation_value():
    fields = _build_genetic_constraint_fields("TESTGENE", None, [])
    assert fields["evidence_score"] is None
    assert fields["raw_value"] is None
    assert "real lof constraint row unavailable" in fields["notes"]


# --- _build_safety_signal_fields --------------------------------------------

def test_registered_as_its_own_source_type_excluded_from_contradictions_and_maturity():
    assert SOURCE_TYPE_BY_DATA_SOURCE["ot_safety"] == "safety_signal"
    assert COMPARABILITY_FIELDS_BY_SOURCE_TYPE["safety_signal"] == []
    # Deliberately NOT a key here — see _build_safety_signal_fields()'s
    # docstring: this guarantees safety_signal can never be the max rung
    # in compute_evidence_maturity() (DIMENSION_MATURITY_LADDER.get(d, 0.0)
    # always falls back to 0.0 for an unregistered dimension).
    assert "safety_signal" not in DIMENSION_MATURITY_LADDER


def test_build_safety_signal_fields_real_kcnh2_shaped_event():
    row = {
        "event": "prolongation of QT interval of ECG", "eventId": "HP_0001657",
        "datasource": "Bowes et al. (2012)", "url": None,
        "biosamples": [{"tissueLabel": "cardiovascular system"}],
        "effects": [{"dosing": "general", "direction": "Inhibition/Decrease/Downregulation"}],
    }
    fields = _build_safety_signal_fields(row)

    assert fields["dimension"] == "safety_signal"
    assert fields["data_source"] == "ot_safety"
    assert fields["source_record_id"] == "HP_0001657"
    # Deliberately unscored — see the docstring's reasoning on why this
    # must never be silently averaged into a composite score.
    assert fields["evidence_score"] is None
    assert fields["tissue"] == "cardiovascular system"
    assert "event=prolongation of QT interval of ECG" in fields["notes"]
    assert fields["external_id"] is None  # this real event's url is null


def test_build_safety_signal_fields_falls_back_to_event_name_when_no_event_id():
    row = {"event": "Torsades de Point", "eventId": "", "datasource": "ClinPGx", "url": "https://x.example/1"}
    fields = _build_safety_signal_fields(row)
    assert fields["source_record_id"] == "safety:Torsades de Point"
    assert fields["external_id"] == "https://x.example/1"


# --- source_links.py: ot_safety / ot_genetic_constraint ---------------------

def test_ot_safety_link_passes_through_the_real_url_as_is():
    url = get_source_url("ot_safety", "HP_0001657", None, "https://aopwiki.org/aops/104", None)
    assert url == "https://aopwiki.org/aops/104"


def test_ot_safety_link_none_when_no_real_url():
    assert get_source_url("ot_safety", "HP_0001657", None, None, None) is None


def test_ot_genetic_constraint_links_to_the_real_target_page():
    url = get_source_url("ot_genetic_constraint", "ot_genetic_constraint:SOD1", None, None, "ENSG00000142168")
    assert url == "https://platform.opentargets.org/target/ENSG00000142168"
