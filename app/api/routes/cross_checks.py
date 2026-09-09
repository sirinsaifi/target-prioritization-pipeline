"""
Pharos cross-checks route — surfaces the two deterministic Pharos-vs-pipeline
comparisons (items D and E of the Pharos expansion). See
app/core/verification/pharos_cross_checks.py for the comparison logic.

Recomputed on every GET (same "always fresh" convention as /momentum — these
are cheap, pure reads of already-stored values plus a deterministic
comparison, with no external API/LLM cost to avoid re-paying). Requires the
druggability EvidenceRecord to exist (POST /gaps or ingestion must have run),
and for the disease-association cross-check specifically, a PriorityScore to
exist (POST /scoring/.../compute must have run) — returns "incomparable"
otherwise rather than 404, since a real "one source not yet available" state
is meaningful to report, not an error.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Target, EvidenceRecord, PriorityScore
from app.core.verification.pharos_cross_checks import (
    disease_association_cross_check, ppi_cross_check,
)
from app.models.schemas import CrossCheckOut, PharosCrossChecksOut

router = APIRouter(prefix="/cross-checks", tags=["cross-checks"])


@router.get("/pharos/target/{target_id}", response_model=PharosCrossChecksOut)
def get_pharos_cross_checks(target_id: int, db: Session = Depends(get_db)):
    """
    Both Pharos cross-checks for one target:
    - disease_association: Pharos ALS DisGeNET score vs OTP Genetic/Literature.
    - ppi: Pharos STRINGDB partners vs this project's STRING high-confidence partners.
    Deterministic, no LLM, recomputed on every call from stored values.
    """
    target = db.query(Target).filter_by(id=target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found.")

    pharos_row = db.query(EvidenceRecord).filter_by(
        target_id=target_id, dimension="druggability",
    ).first()
    if not pharos_row:
        raise HTTPException(
            status_code=400,
            detail="No Pharos druggability record for this target. Run ingestion first.",
        )
    string_row = db.query(EvidenceRecord).filter_by(
        target_id=target_id, dimension="ppi_network",
    ).first()
    priority = (
        db.query(PriorityScore)
        .filter(PriorityScore.target_id == target_id)
        .order_by(PriorityScore.computed_at.desc())
        .first()
    )

    disease_result = disease_association_cross_check(
        target.gene_symbol,
        pharos_row.notes,
        priority.dimension_breakdown if priority else None,
    )
    ppi_result = ppi_cross_check(
        target.gene_symbol,
        pharos_row.notes,
        string_row.notes if string_row else None,
    )
    return {
        "target_id": target_id,
        "gene_symbol": target.gene_symbol,
        "cross_checks": [disease_result, ppi_result],
    }
