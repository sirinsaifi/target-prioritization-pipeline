import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Target, InvestigationTrace
from app.agent.investigation_loop import investigate_target
from app.agent.pipeline_handoff import score_investigation_result
from app.config import DISEASE_NAME

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/investigate/{target_id}")
def run_investigation(target_id: int, max_iterations: int = 6, db: Session = Depends(get_db)):
    """
    Runs the autonomous investigation loop (app/agent/investigation_loop.py)
    for this target, persists every tool-call step to InvestigationTrace for
    audit, then hands the agent-gathered evidence to the UNMODIFIED
    deterministic pipeline (app/agent/pipeline_handoff.py) for scoring.

    This is a NEW, separate path alongside the existing fixed pipeline
    (scripts/ingest_evidence.py + POST /scoring, /contradictions, /gaps) —
    not a replacement. The resulting evidence profile is NOT written into
    the shared PriorityScore/ContradictionLog/GapRecord tables (see
    pipeline_handoff.py's module docstring for why); only the
    InvestigationTrace steps are persisted.
    """
    target = db.query(Target).filter_by(id=target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found.")

    result = investigate_target(target.gene_symbol, DISEASE_NAME, max_iterations=max_iterations)

    run_id = str(uuid.uuid4())
    trace_rows = []
    for step in result.steps:
        trace = InvestigationTrace(
            target_id=target_id,
            run_id=run_id,
            step_number=step.step_number,
            tool_called=step.tool_called,
            tool_input=json.dumps(step.tool_input),
            tool_result_summary=step.tool_result_summary,
            agent_reasoning=step.agent_reasoning,
        )
        db.add(trace)
        trace_rows.append(trace)
    db.commit()
    for t in trace_rows:
        db.refresh(t)

    evidence_profile = score_investigation_result(result)

    return {
        "run_id": run_id,
        "gene": result.gene,
        "disease": result.disease,
        "stopped_reason": result.stopped_reason,
        "final_message": result.final_message,
        "trace": [
            {
                "step_number": t.step_number,
                "tool_called": t.tool_called,
                "tool_input": json.loads(t.tool_input or "{}"),
                "tool_result_summary": t.tool_result_summary,
                "agent_reasoning": t.agent_reasoning,
                "timestamp": t.timestamp.isoformat(),
            }
            for t in trace_rows
        ],
        "evidence_profile": evidence_profile,
    }
