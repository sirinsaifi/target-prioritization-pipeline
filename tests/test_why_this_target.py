"""
Tests for the "Why This Target?" structured narrative (decision-layer
strategy, priority #1) — app/core/narration/agent_narrator.py's
build_why_this_target_grounding_data() / generate_why_this_target_narrative().

Same discipline as test_agent_narrator.py: mock `_call_llm` so no real
network call or API key is needed. What's under test is (a) grounding-data
assembly from real DB rows, and (b) that confidence/evidence_maturity/
main_remaining_uncertainty are decided deterministically in Python, NEVER
by the (mocked) LLM — the LLM is only ever asked for the 3 bullet strings.
"""

import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import Target, PriorityScore, GapRecord, EvidenceRecord, ContradictionLog, PipelineRunLog
from app.core.narration.agent_narrator import (
    build_why_this_target_grounding_data, generate_why_this_target_narrative,
    _parse_why_this_target_bullets, _confidence_label, _maturity_label,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed_target(db, gene_symbol="SOD1"):
    target = Target(gene_symbol=gene_symbol, ensembl_id=f"ENSG_{gene_symbol}", disease_efo_id="MONDO_0004976")
    db.add(target)
    db.flush()
    return target


# --- _confidence_label / _maturity_label (pure deterministic lookups) ------

def test_confidence_label_thresholds():
    assert _confidence_label(0.95) == "High"
    assert _confidence_label(0.8) == "High"   # boundary, >= is High
    assert _confidence_label(0.6) == "Medium"
    assert _confidence_label(0.5) == "Medium"  # boundary, >= 0.5 is not Low
    assert _confidence_label(0.49) == "Low"
    assert _confidence_label(None) == "Low"


def test_maturity_label_thresholds():
    assert _maturity_label(1.0) == "High"
    assert _maturity_label(0.9) == "High"
    assert _maturity_label(0.5) == "Medium"
    assert _maturity_label(0.4) == "Medium"
    assert _maturity_label(0.39) == "Low"
    assert _maturity_label(None) == "Low"


# --- build_why_this_target_grounding_data -----------------------------------

def test_grounding_data_returns_none_for_missing_target(db_session):
    assert build_why_this_target_grounding_data(db_session, target_id=999) is None


def test_grounding_data_reports_no_score_without_fabricating_dimensions(db_session):
    target = _seed_target(db_session)
    db_session.commit()
    data = build_why_this_target_grounding_data(db_session, target.id)
    assert data["gene_symbol"] == "SOD1"
    assert data["priority_score"] is None


def test_top_dimensions_are_real_and_sorted_descending(db_session):
    target = _seed_target(db_session)
    db_session.add(PriorityScore(
        target_id=target.id, evidence_strength=0.9, evidence_consistency=1.0, evidence_maturity=1.0,
        priority_score=0.95,
        dimension_breakdown=json.dumps({
            "genetic": 0.99, "literature": 0.95, "pathway": 1.0, "human_clinical": 0.96, "ppi_network": 0.1,
        }),
    ))
    db_session.commit()

    data = build_why_this_target_grounding_data(db_session, target.id)
    top = data["top_dimensions"]
    assert len(top) == 3
    assert [d["dimension"] for d in top] == ["pathway", "genetic", "human_clinical"]
    assert top[0]["label"] == "Pathway"
    assert top[0]["score"] == 1.0


def test_main_remaining_uncertainty_falls_back_to_real_lowest_dimension_when_no_gaps(db_session):
    """Real SOD1-shaped case: zero evidence-completeness gaps -> the real
    lowest-scoring dimension is named, not a fabricated gap. ppi_network
    (0.1) is numerically the lowest here but is EXCLUDED (known
    scoring-formula limitation — see config.DIMENSIONS_WITH_SCORING_
    FORMULA_LIMITATIONS), so tissue_expression (0.4694) is correctly named
    instead — a real, live-confirmed fix: this fallback previously named
    ppi_network for a gene with 10 real high-confidence STRING partners,
    which is a formula artifact, not a genuine weakness."""
    target = _seed_target(db_session)
    db_session.add(PriorityScore(
        target_id=target.id, evidence_strength=0.9996, evidence_consistency=1.0, evidence_maturity=1.0,
        priority_score=0.9999,
        dimension_breakdown=json.dumps({
            "genetic": 0.9991, "literature": 0.9995, "human_clinical": 0.9639, "pathway": 1.0,
            "drug_target": 1.0, "experimental": 0.5726, "tissue_expression": 0.4694, "ppi_network": 0.1,
        }),
    ))
    db_session.commit()

    data = build_why_this_target_grounding_data(db_session, target.id)
    uncertainty = data["main_remaining_uncertainty"]
    assert uncertainty["source"] == "lowest_dimension"
    assert uncertainty["dimension"] == "tissue_expression"
    assert uncertainty["score"] == 0.4694


def test_main_remaining_uncertainty_skips_ppi_network_even_when_numerically_lowest(db_session):
    """Direct regression test for the fix: a real gene with a meaningful
    interactome (10 real high-confidence STRING partners) scores
    ppi_network=0.10 purely because of the /100 ceiling artifact — this
    must never be picked as the 'uncertainty', even though it's the
    numerically lowest real score present."""
    target = _seed_target(db_session, "TESTGENE2")
    db_session.add(PriorityScore(
        target_id=target.id, evidence_strength=0.9, evidence_consistency=1.0, evidence_maturity=0.5,
        priority_score=0.85,
        dimension_breakdown=json.dumps({"genetic": 0.9, "pathway": 1.0, "ppi_network": 0.1}),
    ))
    db_session.commit()

    data = build_why_this_target_grounding_data(db_session, target.id)
    uncertainty = data["main_remaining_uncertainty"]
    assert uncertainty["dimension"] != "ppi_network"
    assert uncertainty["dimension"] == "genetic"
    assert uncertainty["score"] == 0.9


def test_main_remaining_uncertainty_reports_none_when_every_dimension_is_excluded(db_session):
    """Edge case: the ONLY scored dimension this target has is one with a
    known scoring-formula limitation — forcing a pick would repeat exactly
    the misleading behavior this fix removes, so this states plainly that
    there's no clear pick rather than guessing."""
    target = _seed_target(db_session, "TESTGENE3")
    db_session.add(PriorityScore(
        target_id=target.id, evidence_strength=0.1, evidence_consistency=1.0, evidence_maturity=0.45,
        priority_score=0.1,
        dimension_breakdown=json.dumps({"ppi_network": 0.1}),
    ))
    db_session.commit()

    data = build_why_this_target_grounding_data(db_session, target.id)
    assert data["main_remaining_uncertainty"] == {"source": "none"}


def test_main_remaining_uncertainty_excludes_risk_flag_gap_types(db_session):
    """A target whose ONLY open gap is essentiality_risk (a risk flag, not
    a missing-evidence gap) must still fall back to the lowest dimension,
    not name essentiality_risk as the 'uncertainty' — it's already
    reported via the caution-flags bullet."""
    target = _seed_target(db_session)
    db_session.add(PriorityScore(
        target_id=target.id, evidence_strength=0.9, evidence_consistency=1.0, evidence_maturity=1.0,
        priority_score=0.95,
        dimension_breakdown=json.dumps({"genetic": 0.99, "pathway": 0.2}),
    ))
    db_session.add(GapRecord(target_id=target.id, gap_type="essentiality_risk", rationale="flagged essential"))
    db_session.commit()

    data = build_why_this_target_grounding_data(db_session, target.id)
    uncertainty = data["main_remaining_uncertainty"]
    assert uncertainty["source"] == "lowest_dimension"
    assert uncertainty["dimension"] == "pathway"


def test_main_remaining_uncertainty_picks_highest_priority_real_gap(db_session):
    """Real NEK1-shaped case: both modality and validation gaps open ->
    validation (earlier in the documented priority order) is picked."""
    target = _seed_target(db_session, "NEK1")
    db_session.add(PriorityScore(
        target_id=target.id, evidence_strength=0.99, evidence_consistency=0.9, evidence_maturity=0.5,
        priority_score=0.8, dimension_breakdown=json.dumps({"genetic": 0.44, "literature": 0.98}),
    ))
    db_session.add(GapRecord(target_id=target.id, gap_type="modality", rationale="no known compound"))
    db_session.add(GapRecord(target_id=target.id, gap_type="validation", rationale="no human/clinical evidence"))
    db_session.commit()

    data = build_why_this_target_grounding_data(db_session, target.id)
    uncertainty = data["main_remaining_uncertainty"]
    assert uncertainty["source"] == "gap"
    assert uncertainty["gap_type"] == "validation"


def test_caution_flags_real_essentiality_and_safety_present(db_session):
    target = _seed_target(db_session)
    db_session.add(PriorityScore(
        target_id=target.id, evidence_strength=0.9, evidence_consistency=1.0, evidence_maturity=1.0,
        priority_score=0.95, dimension_breakdown=json.dumps({"genetic": 0.9}),
    ))
    db_session.add(EvidenceRecord(
        target_id=target.id, dimension="genetic", data_source="ot_genetic_constraint",
        source_type="genetic", source_record_id="ot_genetic_constraint:SOD1",
    ))
    db_session.add(EvidenceRecord(
        target_id=target.id, dimension="essentiality_risk", data_source="ot_essentiality",
        source_type="essentiality_risk", source_record_id="ot_essentiality:SOD1",
        raw_value=-1.0, notes="isEssential=True; prioritisation_geneEssentiality=-1",
    ))
    db_session.add(EvidenceRecord(
        target_id=target.id, dimension="safety_signal", data_source="ot_safety",
        source_type="safety_signal", source_record_id="HP_0001657",
        notes="event=prolongation of QT interval of ECG; direction=Inhibition; datasource=Bowes et al. (2012)",
    ))
    db_session.commit()

    data = build_why_this_target_grounding_data(db_session, target.id)
    flags = data["caution_flags"]
    assert flags["safety_checked"] is True
    assert flags["safety_events"] == ["prolongation of QT interval of ECG"]
    assert flags["essentiality_checked"] is True
    assert flags["is_essential"] is True


def test_caution_flags_checked_and_clean_not_confused_with_never_checked(db_session):
    """Real C9orf72-shaped case: essentiality WAS checked (isEssential=False)
    and safety WAS checked (genetic_constraint row exists) — both real,
    clean results, correctly distinguished from 'never checked'."""
    target = _seed_target(db_session, "C9orf72")
    db_session.add(PriorityScore(
        target_id=target.id, evidence_strength=0.9, evidence_consistency=1.0, evidence_maturity=1.0,
        priority_score=0.9, dimension_breakdown=json.dumps({"genetic": 0.9}),
    ))
    db_session.add(EvidenceRecord(
        target_id=target.id, dimension="genetic", data_source="ot_genetic_constraint",
        source_type="genetic", source_record_id="ot_genetic_constraint:C9orf72",
    ))
    db_session.add(EvidenceRecord(
        target_id=target.id, dimension="essentiality_risk", data_source="ot_essentiality",
        source_type="essentiality_risk", source_record_id="ot_essentiality:C9orf72",
        raw_value=0.0, notes="isEssential=False",
    ))
    db_session.commit()

    data = build_why_this_target_grounding_data(db_session, target.id)
    flags = data["caution_flags"]
    assert flags["safety_checked"] is True
    assert flags["safety_events"] == []
    assert flags["essentiality_checked"] is True
    assert flags["is_essential"] is False


def test_caution_flags_never_checked_when_no_prioritisation_data_exists(db_session):
    target = _seed_target(db_session, "TESTGENE")
    db_session.add(PriorityScore(
        target_id=target.id, evidence_strength=0.5, evidence_consistency=1.0, evidence_maturity=0.2,
        priority_score=0.5, dimension_breakdown=json.dumps({"literature": 0.5}),
    ))
    db_session.commit()

    data = build_why_this_target_grounding_data(db_session, target.id)
    flags = data["caution_flags"]
    assert flags["safety_checked"] is False
    assert flags["essentiality_checked"] is False


def test_contradiction_status_never_checked_vs_checked_and_clean_vs_checked_and_found(db_session):
    target = _seed_target(db_session)
    db_session.add(PriorityScore(
        target_id=target.id, evidence_strength=0.9, evidence_consistency=1.0, evidence_maturity=1.0,
        priority_score=0.9, dimension_breakdown=json.dumps({"genetic": 0.9}),
    ))
    db_session.commit()

    # Never checked.
    data = build_why_this_target_grounding_data(db_session, target.id)
    assert data["contradiction_status"]["checked"] is False
    assert data["contradiction_status"]["count"] == 0

    # Checked, zero found.
    db_session.add(PipelineRunLog(target_id=target.id, stage="contradictions"))
    db_session.commit()
    data = build_why_this_target_grounding_data(db_session, target.id)
    assert data["contradiction_status"]["checked"] is True
    assert data["contradiction_status"]["count"] == 0

    # Checked, real contradiction found.
    ev_a = EvidenceRecord(target_id=target.id, dimension="genetic", data_source="eva", source_record_id="a")
    ev_b = EvidenceRecord(target_id=target.id, dimension="genetic", data_source="eva", source_record_id="b")
    db_session.add_all([ev_a, ev_b])
    db_session.flush()
    db_session.add(ContradictionLog(
        target_id=target.id, evidence_record_a_id=ev_a.id, evidence_record_b_id=ev_b.id,
        classification="direct_contradiction",
    ))
    db_session.commit()
    data = build_why_this_target_grounding_data(db_session, target.id)
    assert data["contradiction_status"]["checked"] is True
    assert data["contradiction_status"]["count"] == 1
    assert data["contradiction_status"]["classifications"] == ["direct_contradiction"]


# --- _parse_why_this_target_bullets (real, resilient parsing) --------------

def test_parse_bullets_well_formed_json():
    raw = '{"bullets": ["a", "b", "c"]}'
    assert _parse_why_this_target_bullets(raw) == ["a", "b", "c"]


def test_parse_bullets_extracts_json_block_from_stray_prose():
    raw = 'Sure, here you go:\n{"bullets": ["a", "b", "c"]}\nHope that helps!'
    assert _parse_why_this_target_bullets(raw) == ["a", "b", "c"]


def test_parse_bullets_falls_back_to_raw_text_when_unparseable():
    raw = "This model just wrote a paragraph instead of JSON."
    assert _parse_why_this_target_bullets(raw) == [raw]


def test_parse_bullets_recovers_from_real_confirmed_missing_bracket_bug():
    """Real, confirmed-live failure shape from openai/gpt-oss-20b while
    building this feature: a missing `]` before the closing `}`. Both the
    direct json.loads() and the {...}-block regex fail on this (it's not
    valid JSON), but every individual bullet string inside is well-formed
    and should still be recovered rather than degrading to one raw blob."""
    raw = ('{"bullets":["Strongest evidence comes from Pathway (score 1.0), Drug-Target '
           '(score 1.0), and Literature (score 0.9995).","Caution flags: Gene is essential.",'
           '"No same-type contradictions detected."}')
    bullets = _parse_why_this_target_bullets(raw)
    assert bullets == [
        "Strongest evidence comes from Pathway (score 1.0), Drug-Target (score 1.0), and Literature (score 0.9995).",
        "Caution flags: Gene is essential.",
        "No same-type contradictions detected.",
    ]


# --- generate_why_this_target_narrative (mocked _call_llm) ------------------

def test_generate_why_this_target_narrative_never_lets_llm_set_confidence_or_maturity(db_session):
    target = _seed_target(db_session)
    db_session.add(PriorityScore(
        target_id=target.id, evidence_strength=0.9996, evidence_consistency=1.0, evidence_maturity=1.0,
        priority_score=0.9999,
        dimension_breakdown=json.dumps({"genetic": 0.9991, "pathway": 1.0, "ppi_network": 0.1}),
    ))
    db_session.commit()

    with patch("app.core.narration.agent_narrator._call_llm") as mock_call:
        mock_call.return_value = json.dumps({"bullets": [
            "Strongest support: Pathway (1.00) and Genetic (1.00).",
            "No real caution flags found in the checked data.",
            "No same-type contradictions detected.",
        ]})
        result = generate_why_this_target_narrative(target.id, db_session)

    assert result["error"] is None
    wtt = result["why_this_target"]
    assert len(wtt["bullets"]) == 3
    # Deterministic, NOT from the (mocked) LLM response.
    assert wtt["confidence"] == "High"
    assert wtt["evidence_maturity"] == "High"
    # ppi_network (0.1) is numerically lowest but excluded (known
    # scoring-formula limitation) — genetic (0.9991) is the real,
    # meaningful lowest of what remains.
    assert wtt["main_remaining_uncertainty"]["dimension"] == "genetic"

    system_prompt, user_prompt = mock_call.call_args[0]
    assert "0.9991" in user_prompt
    assert "ONLY a JSON object" in system_prompt
    # Real regression guard: a higher max_tokens budget than the default
    # 400 is required here — see _call_llm()'s own docstring for the real,
    # confirmed-live SOD1 truncation bug (a reasoning model spending its
    # whole budget on hidden reasoning tokens before any real content).
    assert mock_call.call_args.kwargs.get("max_tokens", 400) > 400


def test_generate_why_this_target_narrative_reports_missing_scores_without_calling_llm(db_session):
    target = _seed_target(db_session, "TESTGENE")
    db_session.commit()

    with patch("app.core.narration.agent_narrator._call_llm") as mock_call:
        result = generate_why_this_target_narrative(target.id, db_session)

    assert result["why_this_target"] is None
    assert "No scores computed" in result["error"]
    mock_call.assert_not_called()


def test_generate_why_this_target_narrative_reports_missing_target_without_calling_llm(db_session):
    with patch("app.core.narration.agent_narrator._call_llm") as mock_call:
        result = generate_why_this_target_narrative(999, db_session)

    assert result["error"] == "Target not found."
    mock_call.assert_not_called()
