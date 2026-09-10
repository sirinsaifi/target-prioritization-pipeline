from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import PipelineRunLog, Target
from app.models.schemas import TargetOut
from app.config import CANDIDATE_TARGETS, DISEASE_EFO_ID, DISEASE_NAME

router = APIRouter(prefix="/targets", tags=["targets"])


@router.get("/", response_model=list[TargetOut])
def list_targets(db: Session = Depends(get_db)):
    """Return all candidate targets currently loaded for the configured disease."""
    return db.query(Target).all()


@router.get("/context")
def get_context(db: Session = Depends(get_db)):
    """Return the active disease context and latest persisted analysis timestamp."""
    latest_analysis = db.query(func.max(PipelineRunLog.run_at)).scalar_one_or_none()
    return {
        "disease": DISEASE_NAME,
        "disease_efo_id": DISEASE_EFO_ID,
        "target_count": db.query(Target).count(),
        "last_analysis": latest_analysis.isoformat() if latest_analysis else None,
    }


@router.post("/seed", response_model=list[TargetOut])
def seed_targets(db: Session = Depends(get_db)):
    """
    Convenience endpoint: populate the targets table from app.config's
    CANDIDATE_TARGETS list. Run once before ingesting evidence.
    """
    created = []
    for gene_symbol, ensembl_id in CANDIDATE_TARGETS.items():
        existing = db.query(Target).filter_by(ensembl_id=ensembl_id).first()
        if existing:
            created.append(existing)
            continue
        target = Target(gene_symbol=gene_symbol, ensembl_id=ensembl_id, disease_efo_id=DISEASE_EFO_ID)
        db.add(target)
        db.flush()
        created.append(target)
    db.commit()
    return created
