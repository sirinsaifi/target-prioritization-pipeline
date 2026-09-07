"""
Tests for the Phase 7 follow-up: wiring literature_contradiction into
Evidence Consistency scoring and the gap taxonomy.

Covers: the two new Consistency sub-score functions in isolation, the
combination formula's weighting behavior, that compute_evidence_consistency()
still ignores literature_contradiction even now that config.py has given it
a real weight (regression against the exact bug this design avoided), the
evidence_consistency gap firing purely from literature contradictions with
zero structured ones, and a full route-level integration test (scoring +
gaps) proving the wiring end-to-end with a real in-memory DB.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.scoring.evidence_profile import (
    compute_evidence_consistency, compute_literature_consistency, combine_consistency_scores,
)
from app.core.gaps.gap_taxonomy import identify_gaps, TargetEvidenceSummary


# --- compute_literature_consistency() ---

def test_literature_consistency_is_1_with_no_pairs_evaluated():
    # No literature check has ever been run for this target — must be a
    # pure no-op, never a guessed penalty.
    assert compute_literature_consistency(literature_contradiction_count=0, literature_pairs_evaluated=0) == 1.0


def test_literature_consistency_penalizes_confirmed_contradictions_by_the_real_formula():
    # weight (1.0, config.py) * 3 contradictions / 10 pairs evaluated
    consistency = compute_literature_consistency(literature_contradiction_count=3, literature_pairs_evaluated=10)
    assert consistency == 0.7


def test_literature_consistency_clamps_at_zero_when_contradictions_exceed_pairs():
    # Shouldn't happen in practice (can't confirm more contradictions than
    # real pairs existed), but the formula must not go negative if it did.
    consistency = compute_literature_consistency(literature_contradiction_count=20, literature_pairs_evaluated=10)
    assert consistency == 0.0


# --- compute_evidence_consistency(): must still ignore literature_contradiction ---

def test_structured_consistency_ignores_literature_contradiction_even_with_a_real_config_weight():
    # Regression check: config.CONTRADICTION_SEVERITY_WEIGHTS now has a real
    # "literature_contradiction": 1.0 entry (needed by
    # compute_literature_consistency() above) — compute_evidence_consistency()
    # must NOT pick that weight up via its own classification_counts loop,
    # or a literature-sourced row would silently corrupt the STRUCTURED
    # score using the wrong (structured) pair denominator, exactly the bug
    # avoided when this classification was first kept separate.
    consistency = compute_evidence_consistency(
        {"literature_contradiction": 5}, total_within_type_pairs=10,
    )
    assert consistency == 1.0


def test_structured_consistency_unaffected_by_literature_contradiction_mixed_in_with_real_structured_ones():
    only_structured = compute_evidence_consistency({"direct_contradiction": 2}, total_within_type_pairs=10)
    mixed_in_literature = compute_evidence_consistency(
        {"direct_contradiction": 2, "literature_contradiction": 100}, total_within_type_pairs=10,
    )
    assert only_structured == mixed_in_literature


# --- combine_consistency_scores(): weighted by real evidence volume, not a plain average ---

def test_combine_returns_1_when_neither_side_has_any_comparable_pairs():
    assert combine_consistency_scores(1.0, 0, 1.0, 0) == 1.0


def test_combine_reduces_to_the_structured_score_when_literature_was_never_run():
    # literature_pair_count=0 -> literature side contributes zero weight ->
    # backward-compatible with every target scored before Phase 7's
    # follow-up existed.
    assert combine_consistency_scores(0.75, 20, 1.0, 0) == 0.75


def test_combine_reduces_to_the_literature_score_when_there_are_no_structured_pairs():
    assert combine_consistency_scores(1.0, 0, 0.6, 10) == 0.6


def test_combine_weights_by_real_pair_volume_not_a_plain_average():
    # A tiny literature sample (2 pairs) next to a large structured pool
    # (98 pairs) should barely move the combined score off the structured
    # value, even though the literature sub-score itself is 0.0.
    combined = combine_consistency_scores(
        structured_consistency=1.0, structured_pair_count=98,
        literature_consistency=0.0, literature_pair_count=2,
    )
    assert combined == 0.98  # (98*1.0 + 2*0.0) / 100
    assert combined != 0.5  # NOT a naive (1.0+0.0)/2 average


# --- Gap taxonomy: literature contradictions alone can trigger the gap ---

def test_evidence_consistency_gap_fires_from_literature_contradictions_alone():
    summary = TargetEvidenceSummary(
        gene_symbol="C9orf72",
        dimension_scores={"genetic": 0.9},
        evidence_strength=1.0,
        evidence_consistency=0.45,  # below the 0.5 default threshold
        evidence_maturity=0.7,
        has_pathway_evidence=False,
        has_human_clinical_evidence=False,
        has_known_compound=False,
        population_heterogeneity_count=0,
        methodological_disagreement_count=0,  # ZERO structured conflicts
        literature_contradiction_count=6,
    )
    findings = {f.gap_type: f for f in identify_gaps(summary)}
    assert "evidence_consistency" in findings

    suggestion = findings["evidence_consistency"].investigation_suggestion
    assert "0 methodological disagreement" in suggestion
    assert "6 confirmed literature contradiction" in suggestion


def test_evidence_consistency_gap_does_not_fire_when_literature_contradiction_count_defaults_to_zero():
    # Backward-compatibility: a summary that never sets
    # literature_contradiction_count (as every pre-follow-up caller still
    # does) behaves exactly as before.
    summary = TargetEvidenceSummary(
        gene_symbol="SOD1",
        dimension_scores={"genetic": 0.9},
        evidence_strength=0.9,
        evidence_consistency=0.9,  # above threshold
        evidence_maturity=1.0,
        has_pathway_evidence=True,
        has_human_clinical_evidence=True,
        has_known_compound=True,
    )
    gap_types = [f.gap_type for f in identify_gaps(summary)]
    assert "evidence_consistency" not in gap_types


# --- Full route-level integration: scoring.py + gaps.py, real in-memory DB ---

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


def _seed_target_with_literature_and_genetic(SessionLocal, n_literature=5):
    from app.db.models import Target, EvidenceRecord
    db = SessionLocal()
    target = Target(gene_symbol="TESTGENE", ensembl_id="ENSG_TEST", disease_efo_id="MONDO_TEST")
    db.add(target)
    db.flush()
    # A little genetic evidence so evidence_strength clears the 0.7 gate.
    db.add(EvidenceRecord(
        target_id=target.id, dimension="genetic", data_source="eva",
        source_type="genetic", source_record_id="rs1", raw_value=0.9, evidence_score=0.95,
    ))
    for i in range(n_literature):
        db.add(EvidenceRecord(
            target_id=target.id, dimension="literature", data_source="europepmc",
            source_type="literature", source_record_id=f"2000000{i}",
            raw_value=1.0, evidence_score=1.0, abstract_text=f"Real-looking abstract text {i}.",
        ))
    db.commit()
    target_id = target.id
    db.close()
    return target_id


def test_route_level_scoring_reflects_confirmed_literature_contradictions(client_with_test_db):
    from app.db.models import ContradictionLog
    from itertools import combinations

    client, SessionLocal = client_with_test_db
    target_id = _seed_target_with_literature_and_genetic(SessionLocal, n_literature=5)

    # BEFORE: no contradictions logged at all.
    before = client.post(f"/scoring/target/{target_id}/compute").json()
    assert before["evidence_consistency"] == 1.0

    # Insert 6 of the 10 real literature pairs as confirmed contradictions
    # directly (mirrors what POST /run-literature would persist).
    db = SessionLocal()
    from app.db.models import EvidenceRecord
    lit_ids = [r.id for r in db.query(EvidenceRecord).filter_by(target_id=target_id, dimension="literature").all()]
    for a, b in list(combinations(lit_ids, 2))[:6]:
        db.add(ContradictionLog(
            target_id=target_id, evidence_record_a_id=a, evidence_record_b_id=b,
            classification="literature_contradiction", status="confirmed", proposed_by="llm_proposer",
            verification_reason="test fixture",
        ))
    db.commit()
    db.close()

    after = client.post(f"/scoring/target/{target_id}/compute").json()
    assert after["evidence_consistency"] < before["evidence_consistency"]

    import json
    breakdown = json.loads(after["consistency_breakdown"])
    assert breakdown["literature_contradiction_count"] == 6
    assert breakdown["literature_pairs"] == 10
    assert breakdown["literature_consistency"] == 0.4

    gaps = client.post(f"/gaps/target/{target_id}/run").json()
    gap_types = [g["gap_type"] for g in gaps["gaps"]]
    assert "evidence_consistency" in gap_types
