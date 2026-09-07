from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Target
from app.agent.orchestrator import generate_target_narrative

router = APIRouter(prefix="/narrative", tags=["narrative"])


@router.get("/target/{target_id}")
def get_target_narrative(target_id: int, db: Session = Depends(get_db)):
    """
    Explainable narrative for one target, grounded strictly in already-
    computed values (scores, contradictions, gaps) — see
    app/agent/orchestrator.py for the "explain, don't compute" guarantee.
    Run /scoring and /gaps for this target first; without them this still
    returns a response, but says so explicitly rather than fabricating.
    """
    target = db.query(Target).filter_by(id=target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found.")

    return generate_target_narrative(db, target_id)
