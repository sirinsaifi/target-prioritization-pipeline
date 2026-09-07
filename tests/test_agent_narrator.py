"""
Tests for app/core/narration/agent_narrator.py.

These tests mock `_call_llm` — the single function that talks to the
Groq API — so no real network call or API key is needed. What's
actually under test is the part that matters for the "never invent a
score" guarantee: that grounding data is assembled correctly from the
database, and that the exact real values end up in the prompt sent to the
model.
"""

import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import Target, PriorityScore, GapRecord
from app.core.narration.agent_narrator import (
    fetch_grounding_data, build_prompt, generate_target_narrative,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed_scored_target(db):
    target = Target(gene_symbol="SOD1", ensembl_id="ENSG00000142168", disease_efo_id="MONDO_0004976")
    db.add(target)
    db.flush()

    db.add(PriorityScore(
        target_id=target.id,
        evidence_strength=0.9996,
        evidence_consistency=1.0,
        evidence_maturity=1.0,
        priority_score=0.9999,
        dimension_breakdown=json.dumps({"genetic": 0.9992, "literature": 0.9993}),
    ))
    db.add(GapRecord(
        target_id=target.id,
        gap_type="mechanistic",
        rationale="Genetic score 1.00 >= 0.7 but no pathway evidence present.",
        investigation_suggestion="Suggest a pathway/mechanistic study to clarify mode of action.",
    ))
    db.commit()
    return target


def test_fetch_grounding_data_pulls_real_stored_values_only(db_session):
    target = _seed_scored_target(db_session)
    data = fetch_grounding_data(db_session, target.id)

    assert data["gene_symbol"] == "SOD1"
    assert data["priority_score"]["evidence_strength"] == 0.9996
    assert data["priority_score"]["dimension_breakdown"] == {"genetic": 0.9992, "literature": 0.9993}
    assert data["contradictions"] == []
    assert len(data["gaps"]) == 1
    assert data["gaps"][0]["gap_type"] == "mechanistic"


def test_fetch_grounding_data_returns_none_for_missing_target(db_session):
    assert fetch_grounding_data(db_session, target_id=999) is None


def test_build_prompt_embeds_grounding_data_verbatim_and_states_the_constraint():
    data = {"gene_symbol": "SOD1", "priority_score": {"evidence_strength": 0.9996}}
    prompt = build_prompt(data)
    assert "0.9996" in prompt
    assert "SOD1" in prompt
    assert "Do not invent evidence" in prompt


def test_generate_target_narrative_grounds_the_llm_call_in_real_stored_values(db_session):
    target = _seed_scored_target(db_session)

    with patch("app.core.narration.agent_narrator._call_llm") as mock_call:
        mock_call.return_value = "SOD1 shows strong genetic evidence..."
        result = generate_target_narrative(target.id, db_session)

    assert result["error"] is None
    assert result["narrative"] == "SOD1 shows strong genetic evidence..."
    mock_call.assert_called_once()
    system_prompt, user_prompt = mock_call.call_args[0]
    assert "Do not invent evidence" in system_prompt
    # The real stored strength (not a guess or a rounded restatement) must
    # appear verbatim in what's sent to the model.
    assert "0.9996" in user_prompt
    assert "mechanistic" in user_prompt


def test_generate_target_narrative_reports_missing_scores_without_calling_llm(db_session):
    target = Target(gene_symbol="TEST1", ensembl_id="ENSG_TEST", disease_efo_id="MONDO_TEST")
    db_session.add(target)
    db_session.commit()

    with patch("app.core.narration.agent_narrator._call_llm") as mock_call:
        result = generate_target_narrative(target.id, db_session)

    assert result["narrative"] is None
    assert "No scores computed" in result["error"]
    mock_call.assert_not_called()


def test_generate_target_narrative_reports_missing_target_without_calling_llm(db_session):
    with patch("app.core.narration.agent_narrator._call_llm") as mock_call:
        result = generate_target_narrative(999, db_session)

    assert result["narrative"] is None
    assert result["error"] == "Target not found."
    mock_call.assert_not_called()
