import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Target, ContradictionLog, GapRecord, EvidenceRecord, PriorityScore, PipelineRunLog
from app.core.gaps.gap_taxonomy import identify_gaps, describe_investigation_coverage, TargetEvidenceSummary
from app.models.schemas import GapAnalysisOut
from app.config import (
    EVIDENCE_CONSISTENCY_GAP_THRESHOLD, EVIDENCE_STRENGTH_HIGH_THRESHOLD, MVP_DIMENSIONS,
    PARALOGUE_MODALITY_NOTE_IDENTITY_THRESHOLD, WHY_THIS_TARGET_UNCERTAINTY_EXCLUDED_GAP_TYPES,
)
from app.core.classification.translational_opportunity import (
    TranslationalOpportunityInput, classify_translational_opportunity,
)

router = APIRouter(prefix="/gaps", tags=["gaps"])


def _gather_target_evidence_flags(db: Session, target_id: int) -> dict:
    """
    Real EvidenceRecord presence checks shared by BOTH routes below —
    extracted (this task, building Translational Opportunity) so GET
    /gaps/target/{id} can classify translational opportunity without
    re-querying gap-identification's own logic differently or duplicating
    it by hand. Previously this whole block lived inline only in the POST
    route (it originally only needed to feed identify_gaps()); GET now
    needs the same real has_known_compound/has_human_clinical_evidence/
    has_safety_signal/has_essentiality_risk facts to classify
    Translational Opportunity on a pure read, so this is the ONE place
    that computes them, called from both.
    """
    has_pathway_evidence = db.query(EvidenceRecord).filter_by(
        target_id=target_id, dimension="pathway"
    ).first() is not None
    # Real drug_target evidence is disease-filtered before ever being
    # ingested (see open_targets_client.get_drug_target_evidence()) — a
    # row existing at all means a real drug/clinical program genuinely
    # indicated for THIS disease, so it counts as human/clinical evidence
    # in its own right, not just a compound-existence signal.
    has_human_clinical_evidence = db.query(EvidenceRecord).filter(
        EvidenceRecord.target_id == target_id,
        EvidenceRecord.dimension.in_(["human_clinical", "drug_target"]),
    ).first() is not None
    # Proxy for "known compound in ChEMBL/DrugBank": clinical_precedence's
    # drugFromSource (stored as `intervention`) is itself ChEMBL-derived.
    has_known_compound = db.query(EvidenceRecord).filter(
        EvidenceRecord.target_id == target_id,
        EvidenceRecord.dimension.in_(["human_clinical", "drug_target"]),
        EvidenceRecord.intervention.isnot(None),
    ).first() is not None
    # A ppi_network row is inserted for EVERY successfully-queried gene,
    # even one with zero real high-confidence STRING partners — "row
    # exists" alone is NOT the right check; requires a real, positive hub
    # score to count as mechanistic-gap-suppressing evidence.
    has_ppi_evidence = db.query(EvidenceRecord).filter(
        EvidenceRecord.target_id == target_id,
        EvidenceRecord.dimension == "ppi_network",
        EvidenceRecord.evidence_score.isnot(None),
        EvidenceRecord.evidence_score > 0,
    ).first() is not None
    # Real Open Targets Known Safety Events — one real row per documented
    # event; evidence_score is always None here (never scored), so
    # presence of ANY row is itself the real signal.
    safety_signal_records = db.query(EvidenceRecord).filter(
        EvidenceRecord.target_id == target_id, EvidenceRecord.dimension == "safety_signal",
    ).all()
    safety_signal_events = [
        r.notes.split(";")[0].removeprefix("event=") for r in safety_signal_records if r.notes
    ]
    # Real Open Targets Gene Essentiality — ONE real row per gene, ALWAYS
    # present once ingested, so the row's own real isEssential value (not
    # mere row presence) is the signal.
    essentiality_record = db.query(EvidenceRecord).filter_by(
        target_id=target_id, dimension="essentiality_risk",
    ).first()
    has_essentiality_risk = bool(essentiality_record and essentiality_record.raw_value is not None
                                  and essentiality_record.raw_value < 0)
    essentiality_risk_note = essentiality_record.notes if (has_essentiality_risk and essentiality_record) else None
    # Real Open Targets Paralogues — only rows at or above this project's
    # own note-worthiness threshold surface as a Modality-gap enrichment.
    paralogy_records = db.query(EvidenceRecord).filter(
        EvidenceRecord.target_id == target_id,
        EvidenceRecord.dimension == "paralogy",
        EvidenceRecord.raw_value >= PARALOGUE_MODALITY_NOTE_IDENTITY_THRESHOLD,
    ).all()
    paralogue_high_identity_matches = [
        f"{r.notes.split('paralog_gene=')[1].split(';')[0]} ({r.raw_value:.1f}% identity)"
        for r in paralogy_records if r.notes and "paralog_gene=" in r.notes
    ]
    # Real Pharos Target Development Level (TDL) — read from the
    # druggability row's notes (format "tdl=Tchem; name=...; ..." — see
    # scripts/ingest_evidence.py's _build_druggability_fields()). None if
    # Pharos had no target for this gene (a real absence, never defaulted
    # to Tdark). Same notes-parsing convention already used above for
    # safety_signal_events ("event=...") and paralogue_high_identity_matches
    # ("paralog_gene=...").
    druggability_record = db.query(EvidenceRecord).filter_by(
        target_id=target_id, dimension="druggability",
    ).first()
    tdl = None
    if druggability_record and druggability_record.notes:
        for part in druggability_record.notes.split(";"):
            part = part.strip()
            if part.startswith("tdl="):
                tdl = part.removeprefix("tdl=") or None
                break

    return dict(
        has_pathway_evidence=has_pathway_evidence,
        has_human_clinical_evidence=has_human_clinical_evidence,
        has_known_compound=has_known_compound,
        has_ppi_evidence=has_ppi_evidence,
        has_safety_signal=len(safety_signal_records) > 0,
        safety_signal_events=safety_signal_events,
        has_essentiality_risk=has_essentiality_risk,
        essentiality_risk_note=essentiality_risk_note,
        paralogue_high_identity_matches=paralogue_high_identity_matches,
        tdl=tdl,
    )


def _build_translational_opportunity(gene_symbol: str, priority, gap_types: list, flags: dict):
    """
    Assembles TranslationalOpportunityInput from already-real values (a
    PriorityScore row, a list of real gap_type strings, and the flags dict
    _gather_target_evidence_flags() returns) and classifies it. Shared by
    both routes below. `gap_types` is filtered here to EVIDENCE-COMPLETENESS
    gaps only (see config.WHY_THIS_TARGET_UNCERTAINTY_EXCLUDED_GAP_TYPES) —
    safety_signal/essentiality_risk are read from the dedicated flags dict
    instead, never double-counted as an "open gap" here.
    """
    open_evidence_gap_types = [g for g in gap_types if g not in WHY_THIS_TARGET_UNCERTAINTY_EXCLUDED_GAP_TYPES]
    opportunity_input = TranslationalOpportunityInput(
        gene_symbol=gene_symbol,
        priority_score=priority.priority_score if priority else None,
        evidence_maturity=priority.evidence_maturity if priority else None,
        has_known_compound=flags["has_known_compound"],
        has_human_clinical_evidence=flags["has_human_clinical_evidence"],
        has_safety_signal=flags["has_safety_signal"],
        safety_signal_events=flags["safety_signal_events"],
        has_essentiality_risk=flags["has_essentiality_risk"],
        essentiality_risk_note=flags["essentiality_risk_note"],
        open_evidence_gap_types=open_evidence_gap_types,
        tdl=flags["tdl"],
    )
    return classify_translational_opportunity(opportunity_input)


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

    population_records = db.query(ContradictionLog).filter_by(
        target_id=target_id, classification="population_heterogeneity"
    ).all()
    pop_count = len(population_records)
    # Real per-pair field-VALUE detail (this task — "fully actionable gap"
    # feature): for each real population_heterogeneity contradiction, look
    # up the two real EvidenceRecord rows it references and read the
    # actual mismatched field's real value on each side (population or
    # tissue — see contradiction_classifier.py's POPULATION_LIKE_FIELDS).
    # A bare count was a generic restatement of the gap type; this is the
    # specific real evidence that actually triggered it. Never fabricated
    # by an LLM or from mismatched_fields' field NAMES alone — read live
    # from the same EvidenceRecord rows already fetched everywhere else in
    # this route.
    population_heterogeneity_details = []
    for c in population_records:
        rec_a = db.query(EvidenceRecord).filter_by(id=c.evidence_record_a_id).first()
        rec_b = db.query(EvidenceRecord).filter_by(id=c.evidence_record_b_id).first()
        if rec_a is None or rec_b is None:
            continue
        for field_name in json.loads(c.mismatched_fields or "[]"):
            val_a, val_b = getattr(rec_a, field_name, None), getattr(rec_b, field_name, None)
            if val_a is not None and val_b is not None:
                population_heterogeneity_details.append(
                    f"{field_name}: '{val_a}' ({rec_a.data_source}) vs '{val_b}' ({rec_b.data_source})"
                )
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

    flags = _gather_target_evidence_flags(db, target_id)

    summary = TargetEvidenceSummary(
        gene_symbol=target.gene_symbol,
        dimension_scores=json.loads(priority.dimension_breakdown or "{}"),
        evidence_strength=priority.evidence_strength or 0.0,
        evidence_consistency=priority.evidence_consistency if priority.evidence_consistency is not None else 1.0,
        evidence_maturity=priority.evidence_maturity or 0.0,
        has_pathway_evidence=flags["has_pathway_evidence"],
        has_human_clinical_evidence=flags["has_human_clinical_evidence"],
        has_known_compound=flags["has_known_compound"],
        has_ppi_evidence=flags["has_ppi_evidence"],
        population_heterogeneity_count=pop_count,
        methodological_disagreement_count=method_count,
        literature_contradiction_count=literature_contradiction_count,
        has_safety_signal=flags["has_safety_signal"],
        safety_signal_events=flags["safety_signal_events"],
        has_essentiality_risk=flags["has_essentiality_risk"],
        essentiality_risk_note=flags["essentiality_risk_note"],
        paralogue_high_identity_matches=flags["paralogue_high_identity_matches"],
        population_heterogeneity_details=population_heterogeneity_details,
        tdl=flags["tdl"],
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
            why_it_matters=f.why_it_matters,
            decision_impact=f.decision_impact,
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

    # Translational Opportunity (this task) — folded into the existing
    # GapAnalysisOut response rather than a new endpoint: every real
    # ingredient it needs (priority, gaps just computed, and the evidence
    # flags already gathered above) is already assembled right here. See
    # app/core/classification/translational_opportunity.py's module
    # docstring for the full rule set and prototype disclaimer.
    opportunity = _build_translational_opportunity(
        target.gene_symbol, priority, [f.gap_type for f in findings], flags,
    )

    return {
        "gaps": records,
        "investigation_coverage": coverage_label,
        "dimensions_not_explored": dimensions_not_explored,
        "translational_opportunity": opportunity,
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

    # Translational Opportunity, computed fresh on this read too (this
    # task) — cheap and fully deterministic (no LLM, no new query beyond
    # what real-data presence checks already do), same "recompute on every
    # GET" convention already used for investigation_coverage above rather
    # than persisting a value that could silently go stale. Real
    # PriorityScore fetched here specifically for this (GET /gaps
    # previously never needed it, since it only reads already-persisted
    # GapRecord rows).
    priority = (
        db.query(PriorityScore)
        .filter(PriorityScore.target_id == target_id)
        .order_by(PriorityScore.computed_at.desc())
        .first()
    )
    flags = _gather_target_evidence_flags(db, target_id)
    opportunity = _build_translational_opportunity(
        target.gene_symbol, priority, [r.gap_type for r in records], flags,
    )

    return {
        "gaps": records,
        "investigation_coverage": coverage_label,
        "dimensions_not_explored": dimensions_not_explored,
        "translational_opportunity": opportunity,
    }
