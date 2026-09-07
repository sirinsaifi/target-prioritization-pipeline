"""
Tests for the investigation_coverage labeling distinction: gap findings from
the exhaustive fixed pipeline vs. the (possibly incomplete) autonomous
investigation loop must never be presented as equally authoritative. See
app.core.gaps.gap_taxonomy.describe_investigation_coverage() and its two
callers (app/api/routes/gaps.py, app/agent/pipeline_handoff.py).
"""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import MVP_DIMENSIONS
from app.core.gaps.gap_taxonomy import describe_investigation_coverage
from app.agent.investigation_loop import InvestigationResult
from app.agent.pipeline_handoff import score_investigation_result
from app.core.narration.agent_narrator import (
    build_investigation_grounding_data, generate_investigation_narrative,
)


# --- describe_investigation_coverage() itself ---

def test_describe_investigation_coverage_all_dimensions_is_complete():
    label, not_explored = describe_investigation_coverage(MVP_DIMENSIONS, verb="queried")
    assert label == f"complete ({len(MVP_DIMENSIONS)}/{len(MVP_DIMENSIONS)} dimensions queried)"
    assert not_explored == []


def test_describe_investigation_coverage_partial_lists_explored_and_not_explored():
    label, not_explored = describe_investigation_coverage({"genetic", "literature", "pathway"}, verb="explored")
    assert label == f"partial (3/{len(MVP_DIMENSIONS)} dimensions explored: genetic, literature, pathway)"
    assert not_explored == [d for d in MVP_DIMENSIONS if d not in {"genetic", "literature", "pathway"}]


# --- Fixed pipeline: always "complete", via the real /gaps route ---

@pytest.fixture
def client_with_test_db():
    from app.db.database import Base, get_db
    from app.main import app

    # StaticPool is required here (not just check_same_thread=False):
    # FastAPI's TestClient runs the route handler via run_in_threadpool, so
    # a plain sqlite:///:memory: engine would hand out a fresh, empty
    # in-memory database to each new worker thread's connection.
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app), TestingSessionLocal
    app.dependency_overrides.clear()


def test_fixed_pipeline_gaps_route_always_reports_complete_coverage(client_with_test_db):
    from app.db.models import Target, PriorityScore

    client, SessionLocal = client_with_test_db
    db = SessionLocal()
    target = Target(gene_symbol="SOD1", ensembl_id="ENSG00000142168", disease_efo_id="MONDO_0004976")
    db.add(target)
    db.flush()
    db.add(PriorityScore(
        target_id=target.id,
        evidence_strength=0.9,
        evidence_consistency=1.0,
        evidence_maturity=1.0,
        priority_score=0.95,
        dimension_breakdown=json.dumps({"genetic": 0.9}),
    ))
    db.commit()
    target_id = target.id
    db.close()

    response = client.post(f"/gaps/target/{target_id}/run")
    assert response.status_code == 200
    body = response.json()
    assert body["investigation_coverage"] == f"complete ({len(MVP_DIMENSIONS)}/{len(MVP_DIMENSIONS)} dimensions queried)"
    assert body["dimensions_not_explored"] == []
    assert isinstance(body["gaps"], list)


# --- Investigation loop: partial, derived from real tool calls ---

def test_score_investigation_result_reports_partial_coverage_from_actual_tool_calls():
    # Only 3 of the 7 tools were actually called this run (mirrors the real
    # SOD1 re-run: genetic -> literature -> pathway, clinical never called).
    # Zero-row results are enough — a tool called with zero rows is still
    # "explored", unlike one never called at all.
    result = InvestigationResult(
        gene="SOD1",
        disease="Amyotrophic Lateral Sclerosis",
        gathered_evidence={
            "search_genetic_evidence": [{"rows": []}],
            "search_literature_evidence": [{"rows": []}],
            "search_pathway_evidence": [{"rows": []}],
        },
    )

    profile = score_investigation_result(result)

    assert profile["investigation_coverage"] == (
        f"partial (3/{len(MVP_DIMENSIONS)} dimensions explored: genetic, literature, pathway)"
    )
    assert profile["dimensions_not_explored"] == [
        d for d in MVP_DIMENSIONS if d not in {"genetic", "literature", "pathway"}
    ]


def test_score_investigation_result_reports_complete_when_all_nine_tools_called():
    result = InvestigationResult(
        gene="SOD1",
        disease="Amyotrophic Lateral Sclerosis",
        gathered_evidence={
            "search_genetic_evidence": [{"rows": []}],
            "search_literature_evidence": [{"rows": []}],
            "search_pathway_evidence": [{"rows": []}],
            "search_clinical_evidence": [{"rows": []}],
            "search_experimental_evidence": [{"rows": []}],
            "search_omics_evidence": [{"rows": []}],
            "search_drug_target_evidence": [{"rows": []}],
            "search_tissue_expression": [{"gene": "SOD1", "ensembl_id": "ENSG00000142168", "rows": []}],
            "search_ppi_network": [{"gene": "SOD1", "rows": []}],
        },
    )

    profile = score_investigation_result(result)

    assert profile["investigation_coverage"] == f"complete ({len(MVP_DIMENSIONS)}/{len(MVP_DIMENSIONS)} dimensions explored)"
    assert profile["dimensions_not_explored"] == []


# --- Narration layer: mentions the caveat only when grounded as partial ---

def test_investigation_grounding_data_carries_the_real_coverage_value_through():
    evidence_profile = {
        "gene": "SOD1", "disease": "ALS",
        "evidence_strength": 0.9, "evidence_consistency": 1.0, "evidence_maturity": 0.5,
        "priority_score": 0.8, "dimension_breakdown": {"genetic": 0.9},
        "contradiction_classification_counts": {},
        "gaps": [],
        "investigation_coverage": "partial (3/4 dimensions explored: genetic, literature, pathway)",
        "dimensions_not_explored": ["human_clinical"],
    }
    grounding_data = build_investigation_grounding_data(evidence_profile)
    assert grounding_data["investigation_coverage"] == evidence_profile["investigation_coverage"]
    assert grounding_data["dimensions_not_explored"] == ["human_clinical"]


def test_generate_investigation_narrative_grounds_the_partial_caveat_in_the_real_value():
    evidence_profile = {
        "gene": "SOD1", "disease": "ALS",
        "evidence_strength": 0.9993, "evidence_consistency": 1.0, "evidence_maturity": 0.5,
        "priority_score": 0.8331, "dimension_breakdown": {"genetic": 0.9992, "literature": 1.0, "pathway": 1.0},
        "contradiction_classification_counts": {},
        "gaps": [{"gap_type": "validation", "rationale": "...", "investigation_suggestion": "..."}],
        "investigation_coverage": "partial (3/4 dimensions explored: genetic, literature, pathway)",
        "dimensions_not_explored": ["human_clinical"],
    }

    with patch("app.core.narration.agent_narrator._call_llm") as mock_call:
        mock_call.return_value = (
            "SOD1 shows strong genetic and literature support... "
            "(based on a partial investigation; human_clinical evidence was not queried in this run)"
        )
        result = generate_investigation_narrative(evidence_profile)

    assert result["error"] is None
    mock_call.assert_called_once()
    system_prompt, user_prompt = mock_call.call_args[0]
    # The instruction to add the caveat is real and present in the system
    # prompt sent to the model...
    assert "partial" in system_prompt and "dimensions_not_explored" in system_prompt
    # ...and the real coverage value/not-explored dimension are what's
    # actually grounded in the data sent to the model, not invented by the
    # test or the narrator.
    assert "partial (3/4 dimensions explored: genetic, literature, pathway)" in user_prompt
    assert "human_clinical" in user_prompt
