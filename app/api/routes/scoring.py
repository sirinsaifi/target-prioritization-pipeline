from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from collections import defaultdict, Counter
from math import comb

from app.db.database import get_db
from app.db.models import EvidenceRecord, PriorityScore, ContradictionLog
from app.core.scoring.harmonic_sum import harmonic_sum_score_scaled_for_type
from app.core.scoring.evidence_profile import (
    comparable_pair_count, compute_evidence_consistency, compute_evidence_maturity,
    compute_literature_consistency, combine_consistency_scores,
)
from app.models.schemas import PriorityScoreOut
from app.config import LITERATURE_CONTRADICTION_MAX_RECORDS
import json

router = APIRouter(prefix="/scoring", tags=["scoring"])


@router.get("/target/{target_id}", response_model=PriorityScoreOut)
def get_latest_score(target_id: int, db: Session = Depends(get_db)):
    """
    Read-only: the most recently computed PriorityScore for this target —
    does NOT recompute anything (contrast with POST .../compute below,
    which always inserts a fresh row). Added to fix a real architectural
    gap found in Phase 10: before this, "view a target's score" and
    "recompute it" were the same action, which is wrong for a UI that just
    wants to display already-computed data.

    A score is never legitimately "empty" the way contradictions/gaps can
    be (see PipelineRunLog's docstring) — if no row exists yet, that's an
    unambiguous "never computed", so this returns 404, not a fabricated
    zero-valued result.
    """
    priority = (
        db.query(PriorityScore)
        .filter(PriorityScore.target_id == target_id)
        .order_by(PriorityScore.computed_at.desc())
        .first()
    )
    if not priority:
        raise HTTPException(
            status_code=404,
            detail="No score computed yet for this target. Call POST /scoring/target/{id}/compute first.",
        )
    return priority


@router.post("/target/{target_id}/compute", response_model=PriorityScoreOut)
def compute_scores(target_id: int, db: Session = Depends(get_db)):
    """
    Compute per-dimension scores (via harmonic sum) and a composite evidence
    profile for a target, using whatever evidence records are already stored.
    This is deterministic — no LLM involved in the numbers themselves.

    NOTE on sequencing (see CLAUDE.md): Consistency depends on the
    contradiction classifier having already been run for this target
    (POST /contradictions/target/{id}/run) — this endpoint reads whatever
    ContradictionLog rows already exist rather than running the classifier
    itself, so run contradictions first or Consistency will read as 1.0
    (no logged conflicts != no possible conflicts).
    """
    records = db.query(EvidenceRecord).filter(EvidenceRecord.target_id == target_id).all()
    if not records:
        raise HTTPException(status_code=404, detail="No evidence records found for this target.")

    scores_by_dimension = defaultdict(list)
    for r in records:
        if r.evidence_score is not None:
            scores_by_dimension[r.dimension].append(r.evidence_score)

    dimension_breakdown = {
        dim: harmonic_sum_score_scaled_for_type(scores)
        for dim, scores in scores_by_dimension.items()
    }

    all_scores = [s for scores in scores_by_dimension.values() for s in scores]
    evidence_strength = harmonic_sum_score_scaled_for_type(all_scores) if all_scores else 0.0

    # Consistency: STRUCTURED sub-score, from the contradiction classifier's
    # logged output for this target, weighted by severity and normalized
    # against how many evidence pairs were actually comparable (see
    # evidence_profile.py). Unchanged from before Phase 7's literature
    # follow-up — compute_evidence_consistency() ignores any
    # "literature_contradiction" rows in classification_counts internally.
    direction_labeled = [r for r in records if r.direction_on_trait is not None]
    total_pairs = comparable_pair_count([r.source_type for r in direction_labeled])
    classification_counts = dict(Counter(
        c.classification for c in
        db.query(ContradictionLog).filter(ContradictionLog.target_id == target_id).all()
    ))
    structured_consistency = compute_evidence_consistency(classification_counts, total_pairs)
    structured_contradiction_count = sum(
        count for classification, count in classification_counts.items() if classification != "literature_contradiction"
    )

    # Consistency: LITERATURE sub-score (Phase 7 follow-up). The real
    # denominator is NOT comparable_pair_count() — literature contradictions
    # come from a deliberately bounded SAMPLE (see
    # app.config.LITERATURE_CONTRADICTION_MAX_RECORDS), not an exhaustive
    # count of every real literature pair. Reproduced deterministically here
    # from stored EvidenceRecord.abstract_text rather than needing new
    # persistence: POST /contradictions/target/{id}/run-literature always
    # selects the first LITERATURE_CONTRADICTION_MAX_RECORDS literature
    # records (by id) that have real abstract text, so re-deriving that same
    # selection here reconstructs exactly how many pairs the last real run
    # would have (or did) examine. If the literature route was never run for
    # this target, this is 0 and the literature sub-score is a no-op 1.0 —
    # see combine_consistency_scores()'s docstring for why this makes the
    # whole change backward-compatible by construction.
    literature_records_considered = (
        db.query(EvidenceRecord.id)
        .filter(
            EvidenceRecord.target_id == target_id,
            EvidenceRecord.dimension == "literature",
            EvidenceRecord.abstract_text.isnot(None),
        )
        .order_by(EvidenceRecord.id)
        .limit(LITERATURE_CONTRADICTION_MAX_RECORDS)
        .count()
    )
    literature_pairs_evaluated = comb(literature_records_considered, 2)
    literature_contradiction_count = classification_counts.get("literature_contradiction", 0)
    literature_consistency = compute_literature_consistency(literature_contradiction_count, literature_pairs_evaluated)

    evidence_consistency = combine_consistency_scores(
        structured_consistency, total_pairs, literature_consistency, literature_pairs_evaluated,
    )
    consistency_breakdown = {
        "structured_consistency": structured_consistency,
        "structured_pairs": total_pairs,
        "structured_contradiction_count": structured_contradiction_count,
        "literature_consistency": literature_consistency,
        "literature_pairs": literature_pairs_evaluated,
        "literature_contradiction_count": literature_contradiction_count,
    }

    # Maturity: from dimension coverage — the most advanced rung reached on
    # the translational-evidence ladder (see evidence_profile.py).
    dimensions_with_evidence = {r.dimension for r in records}
    evidence_maturity = compute_evidence_maturity(dimensions_with_evidence)

    # Composite priority score: an unweighted average of the three
    # components, for relative ranking convenience only. This is our own
    # explainable layer, not an OTP formula — Strength/Consistency/Maturity
    # are still reported separately above (see CLAUDE.md "Original
    # contributions": kept non-collapsed) so this composite never has to be
    # the only number a user sees.
    priority_score = round((evidence_strength + evidence_consistency + evidence_maturity) / 3, 4)

    priority = PriorityScore(
        target_id=target_id,
        evidence_strength=evidence_strength,
        evidence_consistency=evidence_consistency,
        evidence_maturity=evidence_maturity,
        dimension_breakdown=json.dumps(dimension_breakdown),
        consistency_breakdown=json.dumps(consistency_breakdown),
        priority_score=priority_score,
    )
    db.add(priority)
    db.commit()
    db.refresh(priority)
    return priority
