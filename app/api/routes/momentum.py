import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Target, MomentumScore
from app.core.scoring.evidence_momentum import compute_momentum
from app.models.schemas import MomentumOut

router = APIRouter(prefix="/momentum", tags=["momentum"])


@router.get("/target/{target_id}", response_model=MomentumOut)
def get_momentum(target_id: int, db: Session = Depends(get_db)):
    """
    Real, purely factual Evidence Momentum trend — see
    app/core/scoring/evidence_momentum.py's module docstring for why this
    is deliberately independent of gap analysis and priority scoring.

    Unlike scoring/contradictions/gaps, this recomputes AND persists a
    fresh MomentumScore row on every call rather than reading a prior one
    — deliberately, not an oversight: computing momentum is a cheap,
    pure DB aggregation over already-ingested EvidenceRecord rows, with no
    external API/LLM cost to avoid re-paying (the exact concern that
    motivated the GET/POST separation for scoring/contradictions/gaps —
    see docs/07 Phase 10 follow-up). There is nothing to "recompute
    wastefully" here, so a single GET route that's always fresh is simpler
    than adding a POST endpoint nobody needs.

    Always returns 200 with a real result — including "insufficient_data"
    if this target has no real dated evidence yet — rather than 404,
    since (unlike scoring/contradictions/gaps) there is no multi-stage
    prerequisite this could be "waiting on"; it only 404s for a genuinely
    unknown target.
    """
    target = db.query(Target).filter_by(id=target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found.")

    result = compute_momentum(target_id, db)

    record = MomentumScore(
        target_id=target_id,
        yearly_counts=json.dumps(result.yearly_counts),
        yearly_counts_by_dimension=json.dumps(result.yearly_counts_by_dimension),
        trend=result.trend,
        momentum_score=result.momentum_score,
        recent_window_count=result.recent_window_count,
        prior_window_count=result.prior_window_count,
        reference_year=result.reference_year,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
