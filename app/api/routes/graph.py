from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.graph.knowledge_graph import build_target_graph

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/target/{target_id}")
def get_target_graph(target_id: int, db: Session = Depends(get_db)):
    """
    Real, in-memory knowledge graph for one target — pathways, PPI
    partners, gaps, disease, and (if any exist) confirmed contradictions —
    built fresh from already-persisted data every call. Read-only: never
    recomputes scores/contradictions/gaps, and the graph itself is never
    persisted (cheap enough to rebuild from a handful of already-indexed
    queries every time, same reasoning as GET /narrative and GET
    /momentum's read paths).
    """
    graph = build_target_graph(target_id, db)
    if graph is None:
        raise HTTPException(status_code=404, detail="Target not found.")
    return graph
