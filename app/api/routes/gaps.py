import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Target, ContradictionLog, GapRecord, EvidenceRecord, PriorityScore, PipelineRunLog
from app.core.gaps.gap_taxonomy import identify_gaps, describe_investigation_coverage, TargetEvidenceSummary
from app.models.schemas import GapAnalysisOut
from app.config import EVIDENCE_CONSISTENCY_GAP_THRESHOLD, EVIDENCE_STRENGTH_HIGH_THRESHOLD, MVP_DIMENSIONS

router = APIRouter(prefix="/gaps", tags=["gaps"])


@router.post("/target/{target_id}/run", response_model=GapAnalysisOut)
def run_gap_analysis(target_id: int, db: Session = Depends(get_db)):
    """
    Build a TargetEvidenceSummary from stored scores + contradiction logs +
    real evidence records, run the gap taxonomy, and persist the results.

    Requires POST /scoring/target/{id}/compute to have already run for this
    target (see CLAUDE.md sequencing note) — dimension scores, strength,
    consistency, and maturity are all read from the latest stored
    PriorityScore rather than recomputed here.
    """
    target = db.query(Target).filter_by(id=target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found.")

    priority = (
        db.query(PriorityScore)
        .filter(PriorityScore.target_id == target_id)
        .order_by(PriorityScore.computed_at.desc())
        .first()
    )
    if not priority:
        raise HTTPException(
            status_code=400,
            detail="No scores computed for this target yet. Run POST /scoring/target/{id}/compute first.",
        )

    pop_count = db.query(ContradictionLog).filter_by(
        target_id=target_id, classification="population_heterogeneity"
    ).count()
    method_count = db.query(ContradictionLog).filter_by(
        target_id=target_id, classification="methodological_disagreement"
    ).count()
    # Phase 7 follow-up: verified literature contradictions
    # (app/core/verification/literature_contradiction_verifier.py) feed the
    # SAME evidence_consistency gap as structured ones — see
    # gap_taxonomy.TargetEvidenceSummary.literature_contradiction_count.
    literature_contradiction_count = db.query(ContradictionLog).filter_by(
        target_id=target_id, classification="literature_contradiction"
    ).count()

    has_pathway_evidence = db.query(EvidenceRecord).filter_by(
        target_id=target_id, dimension="pathway"
    ).first() is not None
    # Real drug_target evidence (this task) is disease-filtered before ever
    # being ingested (see open_targets_client.get_drug_target_evidence()) —
    # a row existing at all means a real drug/clinical program genuinely
    # indicated for THIS disease, so it counts as human/clinical evidence
    # in its own right, not just a compound-existence signal. This directly
    # targets the exact kind of gap docs/07's C9orf72 case study found:
    # clinical_precedence's small-molecule/ChEMBL bias missed 2 real
    # RNA-targeted ASO trials — drugAndClinicalCandidates confirmed live to
    # NOT share that specific bias (SOD1's tofersen shows drugType
    # "Oligonucleotide" there), though it did not recover those exact 2
    # programs either (see that function's docstring).
    has_human_clinical_evidence = db.query(EvidenceRecord).filter(
        EvidenceRecord.target_id == target_id,
        EvidenceRecord.dimension.in_(["human_clinical", "drug_target"]),
    ).first() is not None
    # Proxy for "known compound in ChEMBL/DrugBank": clinical_precedence's
    # drugFromSource (stored as `intervention`) is itself ChEMBL-derived —
    # see docs/06_evidence_heterogeneity_discovery.md. Now also checks
    # drug_target evidence's own `intervention` (this task) for the same
    # reason as above.
    has_known_compound = db.query(EvidenceRecord).filter(
        EvidenceRecord.target_id == target_id,
        EvidenceRecord.dimension.in_(["human_clinical", "drug_target"]),
        EvidenceRecord.intervention.isnot(None),
    ).first() is not None
    # NOTE, unlike every check above: a ppi_network row is inserted for
    # EVERY successfully-queried gene, even one with zero real
    # high-confidence STRING partners (see
    # scripts/ingest_evidence.py._build_ppi_network_fields()'s docstring —
    # this distinguishes "checked, confirmed isolated" from "STRING query
    # failed"). So "row exists" alone is NOT the right check here — must
    # require a real, positive hub score, not merely a queried-and-recorded
    # zero, to count as mechanistic-gap-suppressing evidence.
    has_ppi_evidence = db.query(EvidenceRecord).filter(
        EvidenceRecord.target_id == target_id,
        EvidenceRecord.dimension == "ppi_network",
        EvidenceRecord.evidence_score.isnot(None),
        EvidenceRecord.evidence_score > 0,
    ).first() is not None

    summary = TargetEvidenceSummary(
        gene_symbol=target.gene_symbol,
        dimension_scores=json.loads(priority.dimension_breakdown or "{}"),
        evidence_strength=priority.evidence_strength or 0.0,
        evidence_consistency=priority.evidence_consistency if priority.evidence_consistency is not None else 1.0,
        evidence_maturity=priority.evidence_maturity or 0.0,
        has_pathway_evidence=has_pathway_evidence,
        has_human_clinical_evidence=has_human_clinical_evidence,
        has_known_compound=has_known_compound,
        has_ppi_evidence=has_ppi_evidence,
        population_heterogeneity_count=pop_count,
        methodological_disagreement_count=method_count,
        literature_contradiction_count=literature_contradiction_count,
    )

    findings = identify_gaps(
        summary,
        consistency_gap_threshold=EVIDENCE_CONSISTENCY_GAP_THRESHOLD,
        strength_high_threshold=EVIDENCE_STRENGTH_HIGH_THRESHOLD,
    )

    # Re-running gap analysis replaces this target's prior findings rather
    # than accumulating duplicates — same prototype convention as
    # scripts/ingest_evidence.py's "clear before re-insert". Without this,
    # every re-run (e.g. after new evidence is ingested) doubles up the
    # same gap types, which is exactly what surfaced when verifying the
    # Streamlit UI live: 6 gap rows shown for a target that should have 3.
    db.query(GapRecord).filter(GapRecord.target_id == target_id).delete()

    records = []
    for f in findings:
        rec = GapRecord(
            target_id=target_id,
            gap_type=f.gap_type,
            rationale=f.rationale,
            investigation_suggestion=f.investigation_suggestion,
        )
        db.add(rec)
        records.append(rec)

    # Real marker that gap analysis has been run for this target — see
    # PipelineRunLog's docstring: a target can legitimately have ZERO real
    # gaps (e.g. SOD1), and GET /target/{id} below needs to tell that apart
    # from "gap analysis was never run".
    db.add(PipelineRunLog(target_id=target_id, stage="gaps"))

    db.commit()
    for rec in records:
        db.refresh(rec)

    # The fixed pipeline always queries all 4 MVP dimensions by design
    # (see scripts/ingest_evidence.py's DATASOURCE_TO_DIMENSION + pathway
    # ingestion) — coverage is always complete here, never computed from
    # what actually got ingested. Contrast with the investigation loop's
    # app.agent.pipeline_handoff.score_investigation_result(), which passes
    # only the dimensions the agent actually chose to explore this run.
    coverage_label, dimensions_not_explored = describe_investigation_coverage(MVP_DIMENSIONS, verb="queried")

    return {
        "gaps": records,
        "investigation_coverage": coverage_label,
        "dimensions_not_explored": dimensions_not_explored,
    }


@router.get("/target/{target_id}", response_model=GapAnalysisOut)
def get_gaps(target_id: int, db: Session = Depends(get_db)):
    """
    Read-only: the currently persisted GapRecord rows for this target,
    without running anything. Contrast with POST .../run above, which
    always recomputes and replaces them.

    Coverage is always "complete (4/4 dimensions queried)" here too — same
    as the POST route — since the fixed pipeline's coverage is a property
    of how ingestion always works (see scripts/ingest_evidence.py), not of
    when gap analysis last ran; it's real and correct to state regardless
    of whether this call is a fresh POST or a read of a prior one.

    An empty gap list is a valid, real answer (e.g. SOD1 genuinely has zero
    gaps) — distinguished from "never run" via PipelineRunLog, same
    principle as GET /contradictions/target/{id}.
    """
    target = db.query(Target).filter_by(id=target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found.")

    ever_run = db.query(PipelineRunLog).filter_by(target_id=target_id, stage="gaps").first() is not None
    if not ever_run:
        raise HTTPException(
            status_code=404,
            detail="Gap analysis has never been run for this target. Call POST /gaps/target/{id}/run first.",
        )

    records = db.query(GapRecord).filter(GapRecord.target_id == target_id).all()
    coverage_label, dimensions_not_explored = describe_investigation_coverage(MVP_DIMENSIONS, verb="queried")

    return {
        "gaps": records,
        "investigation_coverage": coverage_label,
        "dimensions_not_explored": dimensions_not_explored,
    }
