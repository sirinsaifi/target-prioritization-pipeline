"""
Tool layer for the agentic/orchestration stage.

Per the project's core design principle (CLAUDE.md): the agentic/LLM layer
only retrieves, orchestrates, and explains — it must never originate a
score, weight, or threshold. Every function here is a thin, read-only
wrapper around already-computed, already-stored deterministic values.
None of them compute anything; they only fetch and reshape what the
scoring/verification/gap modules already wrote to the database.
"""

import json

from sqlalchemy.orm import Session

from app.db.models import Target, PriorityScore, ContradictionLog, GapRecord, EvidenceRecord


def get_target(db: Session, target_id: int) -> Target | None:
    return db.query(Target).filter_by(id=target_id).first()


def get_latest_priority_score(db: Session, target_id: int) -> PriorityScore | None:
    return (
        db.query(PriorityScore)
        .filter(PriorityScore.target_id == target_id)
        .order_by(PriorityScore.computed_at.desc())
        .first()
    )


def get_contradiction_summary(db: Session, target_id: int) -> dict:
    """Counts of logged contradictions by classification, plus a few examples for traceability."""
    logs = db.query(ContradictionLog).filter_by(target_id=target_id).all()
    counts: dict = {}
    for log in logs:
        counts[log.classification] = counts.get(log.classification, 0) + 1
    return {
        "counts": counts,
        "total_logged": len(logs),
        # Every claim must trace to a record (CLAUDE.md) — keep a bounded
        # sample of the actual logged pairs, not just aggregate counts.
        "examples": [
            {
                "classification": log.classification,
                "evidence_record_a_id": log.evidence_record_a_id,
                "evidence_record_b_id": log.evidence_record_b_id,
                "matched_fields": json.loads(log.matched_fields or "[]"),
                "mismatched_fields": json.loads(log.mismatched_fields or "[]"),
            }
            for log in logs[:5]
        ],
    }


def get_gaps(db: Session, target_id: int) -> list[dict]:
    records = db.query(GapRecord).filter_by(target_id=target_id).all()
    return [
        {
            "gap_type": r.gap_type,
            "rationale": r.rationale,
            "investigation_suggestion": r.investigation_suggestion,
        }
        for r in records
    ]


def get_evidence_dimension_counts(db: Session, target_id: int) -> dict:
    """Real evidence-record counts per dimension — for narrative traceability, not scoring."""
    records = db.query(EvidenceRecord).filter_by(target_id=target_id).all()
    counts: dict = {}
    for r in records:
        counts[r.dimension] = counts.get(r.dimension, 0) + 1
    return counts
