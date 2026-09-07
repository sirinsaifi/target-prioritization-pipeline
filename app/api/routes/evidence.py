from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import EvidenceRecord
from app.models.schemas import EvidenceRecordOut

router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.get("/target/{target_id}", response_model=list[EvidenceRecordOut])
def get_evidence_for_target(target_id: int, dimension: str | None = None, db: Session = Depends(get_db)):
    """
    Return all evidence records for a target, optionally filtered by
    dimension (genetic | literature | pathway | human_clinical).
    """
    query = db.query(EvidenceRecord).filter(EvidenceRecord.target_id == target_id)
    if dimension:
        query = query.filter(EvidenceRecord.dimension == dimension)
    records = query.all()
    if not records:
        raise HTTPException(status_code=404, detail="No evidence found for this target/dimension.")
    return records
