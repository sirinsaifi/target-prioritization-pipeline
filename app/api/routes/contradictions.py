import json
from itertools import combinations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import EvidenceRecord, ContradictionLog, Target, PipelineRunLog
from app.core.verification.contradiction_classifier import (
    classify_contradiction, EvidenceForComparison,
)
from app.core.verification.literature_contradiction_proposer import propose_literature_contradiction
from app.core.verification.literature_contradiction_verifier import verify_literature_contradiction
from app.ingestion.literature_text_client import get_abstract_text
from app.models.schemas import ContradictionOut, LiteratureContradictionRunOut
from app.config import (
    DISEASE_NAME, LITERATURE_CONTRADICTION_MAX_RECORDS, LITERATURE_CONTRADICTION_MAX_CANDIDATES,
)

router = APIRouter(prefix="/contradictions", tags=["contradictions"])


def _to_comparison(record: EvidenceRecord) -> EvidenceForComparison:
    return EvidenceForComparison(
        record_id=record.id,
        source_record_id=record.source_record_id,
        source_type=record.source_type,
        direction_on_trait=record.direction_on_trait,
        tissue=record.tissue,
        population=record.population,
        assay_type=record.assay_type,
        endpoint=record.endpoint,
        phenotype=record.phenotype,
        intervention=record.intervention,
        variant_id=record.variant_id,
        clinical_significance=record.clinical_significance,
        inheritance_pattern=record.inheritance_pattern,
    )


@router.post("/target/{target_id}/run", response_model=list[ContradictionOut])
def run_contradiction_check(target_id: int, db: Session = Depends(get_db)):
    """
    Run the contradiction classifier over every pair of evidence records for
    a target that have a Direction of Effect recorded. Logs every
    non-"no_contradiction" result, including "unclassified", for full
    traceability.
    """
    records = (
        db.query(EvidenceRecord)
        .filter(EvidenceRecord.target_id == target_id, EvidenceRecord.direction_on_trait.isnot(None))
        .all()
    )
    if len(records) < 2:
        raise HTTPException(status_code=404, detail="Need at least 2 direction-labeled evidence records.")

    logged = []
    for rec_a, rec_b in combinations(records, 2):
        result = classify_contradiction(_to_comparison(rec_a), _to_comparison(rec_b))
        if result.classification == "no_contradiction":
            continue

        log = ContradictionLog(
            target_id=target_id,
            evidence_record_a_id=rec_a.id,
            evidence_record_b_id=rec_b.id,
            classification=result.classification,
            matched_fields=json.dumps(result.matched_fields),
            mismatched_fields=json.dumps(result.mismatched_fields),
            # Explicit rather than relying only on the column default —
            # see app/db/models.py's ContradictionLog docstring: every row
            # is self-describing about which stage produced it.
            status="confirmed",
            proposed_by="structured_classifier",
        )
        db.add(log)
        logged.append(log)

    # Real marker that this stage has been run for this target — see
    # PipelineRunLog's docstring: without this, GET /target/{id} below
    # couldn't tell "zero real contradictions found" apart from "never
    # checked" from an empty ContradictionLog query alone.
    db.add(PipelineRunLog(target_id=target_id, stage="contradictions"))

    db.commit()
    for log in logged:
        db.refresh(log)
    return logged


@router.get("/target/{target_id}", response_model=list[ContradictionOut])
def get_contradictions(target_id: int, db: Session = Depends(get_db)):
    """
    Read-only: every persisted ContradictionLog row for this target — BOTH
    structured (POST .../run) and literature (POST .../run-literature)
    classifications — without running anything. Contrast with the two POST
    routes, which always (re)compute.

    An empty list is a valid, real answer here (unlike PriorityScore) — it
    means "checked, zero real contradictions found", which is a
    meaningfully different state from "never checked at all". Distinguished
    via PipelineRunLog: if this stage has never been run for this target,
    404 rather than a misleading empty list.
    """
    target = db.query(Target).filter_by(id=target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found.")

    ever_run = db.query(PipelineRunLog).filter_by(target_id=target_id, stage="contradictions").first() is not None
    if not ever_run:
        raise HTTPException(
            status_code=404,
            detail=(
                "Contradictions have never been checked for this target. Call "
                "POST /contradictions/target/{id}/run (and/or .../run-literature) first."
            ),
        )

    return db.query(ContradictionLog).filter(ContradictionLog.target_id == target_id).all()


@router.post("/target/{target_id}/run-literature", response_model=LiteratureContradictionRunOut)
def run_literature_contradiction_check(target_id: int, db: Session = Depends(get_db)):
    """
    Phase 7: the literature-specific "LLM proposes -> deterministic rule
    layer verifies" pipeline (Stage 5 of the architecture). Separate from
    POST /target/{id}/run above — that route's structured classifier
    never even sees literature records (they have no direction_on_trait,
    the only field it filters on) — and separate from the autonomous
    investigation loop (Phase 8, which decides WHAT to investigate; this
    decides whether two ALREADY-gathered literature excerpts conflict).

    Bounded deliberately (app.config.LITERATURE_CONTRADICTION_MAX_RECORDS/
    _MAX_CANDIDATES) — comparing every real literature-record pair for a
    target would mean thousands of LLM calls; see config.py for why.

    Every proposed "CONTRADICT" is run through the deterministic verifier
    before being logged; SUPPORT/UNRELATED proposals are not contradiction
    candidates and are never logged, matching the structured route's own
    "only log non-no_contradiction results" convention.

    Logged rows use `classification="literature_contradiction"` — a NEW,
    distinct taxonomy value, deliberately NOT `"direct_contradiction"`.
    Checked before wiring this in: app/api/routes/scoring.py's Consistency
    computation divides confirmed-contradiction counts by
    `comparable_pair_count()` over only `direction_on_trait`-labeled
    records, and literature EvidenceRecords never have `direction_on_trait`
    set (confirmed: `_build_literature_fields()` never sets it) — so
    literature pairs are NOT in that denominator today. Reusing
    "direct_contradiction" would have silently inflated the Consistency
    numerator with no matching denominator increase, corrupting the score.
    `CONTRADICTION_SEVERITY_WEIGHTS` has no entry for
    "literature_contradiction", so `.get(classification, 0.0)` gives it
    zero weight — these rows are logged, real, and queryable, but
    deliberately don't affect Consistency yet. Wiring literature
    contradictions into Consistency scoring (by also counting literature
    pairs in the denominator) is real follow-up work, named explicitly in
    docs/07, not silently done here.
    """
    target = db.query(Target).filter_by(id=target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found.")

    candidates = (
        db.query(EvidenceRecord)
        .filter(EvidenceRecord.target_id == target_id, EvidenceRecord.dimension == "literature")
        .order_by(EvidenceRecord.id)
        .limit(LITERATURE_CONTRADICTION_MAX_CANDIDATES)
        .all()
    )

    usable_records: list[EvidenceRecord] = []
    missing_abstract_count = 0
    for record in candidates:
        if len(usable_records) >= LITERATURE_CONTRADICTION_MAX_RECORDS:
            break
        if not record.abstract_text:
            fetched_text = get_abstract_text(record.source_record_id)
            record.abstract_text = fetched_text
            db.add(record)
        if record.abstract_text:
            usable_records.append(record)
        else:
            missing_abstract_count += 1
    db.commit()

    if len(usable_records) < 2:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Need at least 2 literature records with real, fetchable abstract text "
                f"(found {len(usable_records)} among {len(candidates)} candidate(s) checked)."
            ),
        )

    gene = target.gene_symbol
    logged: list[ContradictionLog] = []
    pairs_evaluated = 0
    rejected_count = 0
    for rec_a, rec_b in combinations(usable_records, 2):
        pairs_evaluated += 1
        proposal = propose_literature_contradiction(gene, DISEASE_NAME, rec_a.abstract_text, rec_b.abstract_text)
        if proposal["classification"] != "CONTRADICT":
            continue  # SUPPORT / UNRELATED / unparseable — not a contradiction candidate, not logged

        verification = verify_literature_contradiction(rec_a, rec_b, proposal["classification"])
        if not verification.verified:
            # Deliberately NOT persisted: app/api/routes/scoring.py's
            # Consistency computation reads every ContradictionLog row for
            # a target with no status filter, so a "rejected" row would be
            # silently double-counted as a real contradiction. Only ever
            # persist what the deterministic verifier actually confirmed —
            # same "only log real findings" convention the structured
            # route already follows for "no_contradiction". Counted here
            # instead, so a rejection is still visible in the response, not
            # silently dropped.
            rejected_count += 1
            continue

        log = ContradictionLog(
            target_id=target_id,
            evidence_record_a_id=rec_a.id,
            evidence_record_b_id=rec_b.id,
            classification="literature_contradiction",
            matched_fields=None,  # no structured fields exist for literature — nothing to name here
            mismatched_fields=None,
            status="confirmed",
            proposed_by="llm_proposer",
            verification_reason=verification.reason,
        )
        db.add(log)
        logged.append(log)

    # Same real "has this stage ever been run" marker as the structured
    # route above — a literature check with zero confirmed contradictions
    # is still a real, completed check, not "never looked".
    db.add(PipelineRunLog(target_id=target_id, stage="contradictions"))

    db.commit()
    for log in logged:
        db.refresh(log)

    return {
        "contradictions": logged,
        "records_considered": len(usable_records),
        "pairs_evaluated": pairs_evaluated,
        "records_missing_abstract": missing_abstract_count,
        "proposals_rejected_by_verifier": rejected_count,
    }
