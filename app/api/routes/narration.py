from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.narration.agent_narrator import generate_target_narrative

router = APIRouter(prefix="/narration", tags=["narration"])


@router.get("/target/{target_id}")
def get_target_narration(target_id: int, db: Session = Depends(get_db)):
    """
    LLM-generated explainable narrative for one target, grounded strictly in
    already-computed values (see app/core/narration/agent_narrator.py) — the
    response includes both the narrative and the raw grounding data it was
    produced from, for traceability/audit back to specific database records.

    Requires GROQ_API_KEY to be set in the environment (interim model
    choice, see agent_narrator.py module docstring). For a fully
    deterministic narrative that needs no API key, see GET /narrative/target/{id}.
    """
    try:
        return generate_target_narrative(target_id, db)
    except RuntimeError as e:
        # _call_llm() raises this specifically when GROQ_API_KEY is
        # missing — surface it as a clean 503 with the actionable message,
        # not a bare 500 with a stack trace.
        raise HTTPException(status_code=503, detail=str(e))
