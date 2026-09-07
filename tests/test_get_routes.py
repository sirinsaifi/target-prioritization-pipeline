"""
Tests for the read-only GET routes added to fix the real architectural gap
found in Phase 10: previously the API had only POST endpoints for
scores/contradictions/gaps, each of which actively recomputes AND persists
every time it's called — there was no way to "just read" already-computed
data. These GET routes read the latest persisted result without
recomputing anything.

Covers all three states named in the task: found-result, no-result-yet
(404), and empty-but-checked (200 with []) — the last one only applies to
contradictions/gaps (a score is never legitimately "empty" the way an
empty contradiction/gap list can be, so scoring only has two states).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def client_with_test_db():
    from app.db.database import Base, get_db
    from app.main import app

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


def _seed_target_with_genetic_evidence(SessionLocal):
    from app.db.models import Target, EvidenceRecord
    db = SessionLocal()
    target = Target(gene_symbol="TESTGENE", ensembl_id="ENSG_TEST", disease_efo_id="MONDO_TEST")
    db.add(target)
    db.flush()
    db.add(EvidenceRecord(
        target_id=target.id, dimension="genetic", data_source="eva",
        source_type="genetic", source_record_id="rs1", raw_value=0.9, evidence_score=0.9,
        direction_on_trait="Risk",
    ))
    db.add(EvidenceRecord(
        target_id=target.id, dimension="genetic", data_source="eva",
        source_type="genetic", source_record_id="rs2", raw_value=0.8, evidence_score=0.8,
        direction_on_trait="Risk",
    ))
    db.commit()
    target_id = target.id
    db.close()
    return target_id


# --- GET /scoring/target/{id} ---

def test_get_score_404s_when_never_computed(client_with_test_db):
    client, SessionLocal = client_with_test_db
    target_id = _seed_target_with_genetic_evidence(SessionLocal)

    resp = client.get(f"/scoring/target/{target_id}")
    assert resp.status_code == 404
    assert "never" in resp.json()["detail"].lower() or "no score" in resp.json()["detail"].lower()


def test_get_score_returns_the_latest_persisted_result_without_recomputing(client_with_test_db):
    client, SessionLocal = client_with_test_db
    target_id = _seed_target_with_genetic_evidence(SessionLocal)

    computed = client.post(f"/scoring/target/{target_id}/compute").json()

    # Mutate evidence AFTER computing — if GET recomputed, it would see this
    # and produce a different result; it must not.
    db = SessionLocal()
    from app.db.models import EvidenceRecord
    db.query(EvidenceRecord).filter_by(target_id=target_id).delete()
    db.commit()
    db.close()

    read = client.get(f"/scoring/target/{target_id}").json()
    assert read["priority_score"] == computed["priority_score"]
    assert read["evidence_strength"] == computed["evidence_strength"]
    assert read["dimension_breakdown"] == computed["dimension_breakdown"]


def test_get_score_404s_for_unknown_target(client_with_test_db):
    client, _ = client_with_test_db
    resp = client.get("/scoring/target/999")
    assert resp.status_code == 404


# --- GET /contradictions/target/{id} ---

def test_get_contradictions_404s_when_never_checked(client_with_test_db):
    client, SessionLocal = client_with_test_db
    target_id = _seed_target_with_genetic_evidence(SessionLocal)

    resp = client.get(f"/contradictions/target/{target_id}")
    assert resp.status_code == 404
    assert "never" in resp.json()["detail"].lower()


def test_get_contradictions_returns_empty_list_when_checked_and_none_found(client_with_test_db):
    client, SessionLocal = client_with_test_db
    target_id = _seed_target_with_genetic_evidence(SessionLocal)  # both records same direction -> no_contradiction

    post_result = client.post(f"/contradictions/target/{target_id}/run").json()
    assert post_result == []  # real: no contradiction between two same-direction records

    get_result = client.get(f"/contradictions/target/{target_id}")
    assert get_result.status_code == 200
    assert get_result.json() == []  # checked, genuinely zero found — NOT a 404


def test_get_contradictions_returns_real_logged_rows_without_recomputing(client_with_test_db):
    client, SessionLocal = client_with_test_db
    target_id = _seed_target_with_genetic_evidence(SessionLocal)

    from app.db.models import ContradictionLog
    db = SessionLocal()
    db.add(ContradictionLog(
        target_id=target_id, evidence_record_a_id=1, evidence_record_b_id=2,
        classification="direct_contradiction", status="confirmed", proposed_by="structured_classifier",
    ))
    from app.db.models import PipelineRunLog
    db.add(PipelineRunLog(target_id=target_id, stage="contradictions"))
    db.commit()
    db.close()

    resp = client.get(f"/contradictions/target/{target_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["classification"] == "direct_contradiction"


def test_get_contradictions_404s_for_unknown_target(client_with_test_db):
    client, _ = client_with_test_db
    resp = client.get("/contradictions/target/999")
    assert resp.status_code == 404


# --- GET /gaps/target/{id} ---

def test_get_gaps_404s_when_never_run(client_with_test_db):
    client, SessionLocal = client_with_test_db
    target_id = _seed_target_with_genetic_evidence(SessionLocal)
    client.post(f"/scoring/target/{target_id}/compute")  # scores exist, but gaps never run

    resp = client.get(f"/gaps/target/{target_id}")
    assert resp.status_code == 404
    assert "never" in resp.json()["detail"].lower()


def _seed_target_with_no_real_gaps(SessionLocal):
    """
    A target with real evidence in all 4 dimensions, a known compound, and
    human/clinical evidence — genuinely clears every one of gap_taxonomy's
    5 trigger conditions (mirrors SOD1's real all-4-dimensions-covered
    profile), so POST .../run is expected to find zero real gaps.
    """
    from app.db.models import Target, EvidenceRecord
    db = SessionLocal()
    target = Target(gene_symbol="CLEANGENE", ensembl_id="ENSG_CLEAN", disease_efo_id="MONDO_TEST")
    db.add(target)
    db.flush()
    for dim, source_type, score, extra in [
        ("genetic", "genetic", 0.9, {"direction_on_trait": "Risk"}),
        ("literature", "literature", 0.9, {}),
        ("pathway", "pathway", 1.0, {}),
        ("human_clinical", "clinical", 0.9, {"intervention": "testdrug"}),
    ]:
        db.add(EvidenceRecord(
            target_id=target.id, dimension=dim, data_source="test", source_type=source_type,
            source_record_id=f"{dim}-1", raw_value=score, evidence_score=score, **extra,
        ))
    db.commit()
    target_id = target.id
    db.close()
    return target_id


def test_get_gaps_returns_empty_list_when_run_and_none_found(client_with_test_db):
    client, SessionLocal = client_with_test_db
    target_id = _seed_target_with_no_real_gaps(SessionLocal)
    client.post(f"/contradictions/target/{target_id}/run")
    client.post(f"/scoring/target/{target_id}/compute")

    post_result = client.post(f"/gaps/target/{target_id}/run").json()
    assert post_result["gaps"] == []  # real: all 4 dimensions covered, known compound, human/clinical present

    get_result = client.get(f"/gaps/target/{target_id}")
    assert get_result.status_code == 200
    body = get_result.json()
    assert body["gaps"] == []
    from app.config import MVP_DIMENSIONS
    assert body["investigation_coverage"] == f"complete ({len(MVP_DIMENSIONS)}/{len(MVP_DIMENSIONS)} dimensions queried)"


def test_get_gaps_reflects_real_persisted_gaps_without_recomputing(client_with_test_db):
    client, SessionLocal = client_with_test_db
    target_id = _seed_target_with_genetic_evidence(SessionLocal)
    client.post(f"/contradictions/target/{target_id}/run")
    client.post(f"/scoring/target/{target_id}/compute")
    run_result = client.post(f"/gaps/target/{target_id}/run").json()

    read_result = client.get(f"/gaps/target/{target_id}").json()
    assert [g["gap_type"] for g in read_result["gaps"]] == [g["gap_type"] for g in run_result["gaps"]]


def test_get_gaps_404s_for_unknown_target(client_with_test_db):
    client, _ = client_with_test_db
    resp = client.get("/gaps/target/999")
    assert resp.status_code == 404
