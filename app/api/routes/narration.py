from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.narration.agent_narrator import generate_target_narrative, generate_why_this_target_narrative

router = APIRouter(prefix="/narration", tags=["narration"])


def _run_narrator(fn, *args):
    """
    Shared error handling for both routes below — a real, live-confirmed
    gap found while building "Why This Target?": `_call_llm()` can raise
    RuntimeError (no API key, already handled) but ALSO a real
    `groq.RateLimitError` (confirmed live: this project's free-tier Groq
    key genuinely hit its 200,000 token/day limit during real testing of
    this exact feature) — previously uncaught, surfacing as a bare 500
    with a stack trace instead of the same clean, actionable error pattern
    already used for the missing-key case. `groq` is imported lazily here,
    matching the existing lazy-import convention in agent_narrator.py
    (avoids a hard dependency for callers who never exercise the LLM path).
    """
    import groq

    try:
        return fn(*args)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except groq.RateLimitError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Groq API rate/token limit reached — try again later. Real error: {e}",
        )


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
    return _run_narrator(generate_target_narrative, target_id, db)


@router.get("/why-target/{target_id}")
def get_why_this_target(target_id: int, db: Session = Depends(get_db)):
    """
    "Why This Target?" structured narrative (decision-layer strategy,
    priority #1) — see app/core/narration/agent_narrator.py's
    generate_why_this_target_narrative(). Unlike GET /narration/target/{id}
    above, `confidence`/`evidence_maturity`/`main_remaining_uncertainty`
    are decided deterministically, not by the LLM — only the 3 narrative
    bullets are LLM-phrased, from facts already decided. Requires
    GROQ_API_KEY, same as the plain narrator above.
    """
    return _run_narrator(generate_why_this_target_narrative, target_id, db)
