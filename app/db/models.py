from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.db.database import Base


class Target(Base):
    """A candidate target (gene/protein) for the configured disease."""
    __tablename__ = "targets"

    id = Column(Integer, primary_key=True)
    gene_symbol = Column(String, unique=True, nullable=False)
    ensembl_id = Column(String, unique=True, nullable=False)
    disease_efo_id = Column(String, nullable=False)

    evidence_records = relationship("EvidenceRecord", back_populates="target")


class EvidenceRecord(Base):
    """
    A single piece of evidence for a target-disease pair, normalized to the
    fields needed for scoring (Stage 4) and contradiction classification
    (Stage 5's comparability fields).
    """
    __tablename__ = "evidence_records"

    id = Column(Integer, primary_key=True)
    target_id = Column(Integer, ForeignKey("targets.id"), nullable=False)

    # Which evidence dimension this record belongs to
    dimension = Column(String, nullable=False)  # genetic | literature | pathway | human_clinical | ...
    data_source = Column(String, nullable=False)  # e.g. "open_targets_l2g", "europe_pmc", "clinvar"

    # Source traceability (required by design — every claim must trace to a record)
    source_record_id = Column(String, nullable=False)  # e.g. PubMed ID, GWAS study accession, ClinVar RCV ID
    retrieval_timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Raw + computed scores
    raw_value = Column(Float, nullable=True)  # e.g. L2G score, p-value, trial phase code
    evidence_score = Column(Float, nullable=True)  # normalized 0-1 score after dimension_scoring.py

    # Source-type group, used to select which comparability fields apply
    # (see app.config.COMPARABILITY_FIELDS_BY_SOURCE_TYPE). Discovered via
    # live OTP GraphQL introspection: a uniform field set does not work
    # across genetic / experimental / clinical / literature evidence.
    source_type = Column(String, nullable=True)  # "genetic" | "experimental" | "clinical" | "literature"

    # Generic comparability fields (populated where they genuinely apply —
    # mainly experimental/IMPC-style evidence)
    tissue = Column(String, nullable=True)
    disease_subtype = Column(String, nullable=True)
    population = Column(String, nullable=True)  # clinical trial population, where available
    assay_type = Column(String, nullable=True)
    endpoint = Column(String, nullable=True)  # clinical trial endpoint, where available
    phenotype = Column(String, nullable=True)  # IMPC-style phenotype
    intervention = Column(String, nullable=True)  # clinical trial intervention/drug

    # Genetic-evidence-specific comparability fields (eva/uniprot_variants/
    # gwas_credible_sets do not carry population/tissue/assay/endpoint —
    # these are the real fields available instead)
    variant_id = Column(String, nullable=True)
    clinical_significance = Column(String, nullable=True)  # ClinVar term, e.g. "pathogenic"
    inheritance_pattern = Column(String, nullable=True)  # from allelicRequirements, e.g. "Autosomal dominant"

    # Direction of Effect (reusing OTP's standardized concept)
    direction_on_target = Column(String, nullable=True)  # "GoF" | "LoF" | None
    direction_on_trait = Column(String, nullable=True)  # "Risk" | "Protective" | None

    notes = Column(Text, nullable=True)

    # Real PubMed abstract text, fetched on demand via
    # app/ingestion/literature_text_client.py::get_abstract_text() using
    # this row's own `source_record_id` as the PMID — only ever populated
    # for dimension="literature" rows. NULL means "not fetched yet" (or no
    # real abstract exists for this PMID), never a placeholder. Added for
    # Phase 7 (app/core/verification/literature_contradiction_proposer.py),
    # which needs real excerpt text to propose candidate contradictions
    # from literature — the one dimension with no structured comparability
    # fields for the deterministic classifier to use instead.
    abstract_text = Column(Text, nullable=True)

    # Real publication/study year, for Evidence Momentum (see
    # app/core/scoring/evidence_momentum.py). Confirmed via live
    # introspection which real sources actually populate this: OTP's
    # europepmc rows reliably carry `publicationYear` (5/5 real SOD1
    # sample rows populated); our own direct-PubMed rows get it via a
    # real NCBI esummary lookup (see literature_client.py); OTP's
    # clinical_precedence rows carry `studyStartDate`, but confirmed
    # MOSTLY NULL in this real dataset (4 of 5 SOD1 sample rows) — parsed
    # to a year where present, left NULL otherwise (a real, honest data
    # gap, not forced). NULL for every other dimension — not fetched,
    # not guessed.
    publication_year = Column(Integer, nullable=True)

    target = relationship("Target", back_populates="evidence_records")


class ContradictionLog(Base):
    """
    A confirmed (or explicitly unclassified) pair of evidence records that
    disagree in direction of effect. This is the traceable record required
    by the finalized contradiction-classification spec.
    """
    __tablename__ = "contradiction_log"

    id = Column(Integer, primary_key=True)
    target_id = Column(Integer, ForeignKey("targets.id"), nullable=False)

    evidence_record_a_id = Column(Integer, ForeignKey("evidence_records.id"), nullable=False)
    evidence_record_b_id = Column(Integer, ForeignKey("evidence_records.id"), nullable=False)

    classification = Column(String, nullable=False)
    # one of: "direct_contradiction" | "population_heterogeneity"
    #         | "methodological_disagreement" | "unclassified"

    matched_fields = Column(Text, nullable=True)  # JSON-encoded list of fields that matched
    mismatched_fields = Column(Text, nullable=True)  # JSON-encoded list of fields that differed

    # Added for Phase 7 (literature contradiction proposer/verifier — see
    # app/core/verification/literature_contradiction_proposer.py and
    # _verifier.py). Rows logged by the EXISTING structured classifier
    # (app/api/routes/contradictions.py's POST /run) are unaffected in
    # meaning — they were always deterministically confirmed, never
    # LLM-proposed — and are backfilled to status="confirmed",
    # proposed_by="structured_classifier" (see the migration script) so
    # every row in this table is self-describing regardless of which path
    # produced it.
    status = Column(String, nullable=False, default="confirmed")
    # "pending_verification" | "confirmed" | "rejected" — literature-path
    # rows start "pending_verification" then the deterministic verifier
    # flips them; structured-classifier rows are "confirmed" from the start
    # (no separate verification stage exists for them, by design).
    proposed_by = Column(String, nullable=True)
    # "structured_classifier" | "llm_proposer" — which stage produced this
    # row's initial classification. NULL only for legacy rows predating
    # this column that a migration failed to backfill (should not occur).
    verification_reason = Column(Text, nullable=True)
    # Deterministic verifier's real reason for confirming/rejecting an
    # LLM-proposed contradiction (e.g. "same target/gene/disease, real
    # abstract text on both sides, classification=CONTRADICT"). NULL for
    # structured-classifier rows — they were never "verified" in this
    # sense, the classifier's own output was already the confirmed result.

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class GapRecord(Base):
    """A research gap identified for a target, with its linked investigation suggestion."""
    __tablename__ = "gap_records"

    id = Column(Integer, primary_key=True)
    target_id = Column(Integer, ForeignKey("targets.id"), nullable=False)

    gap_type = Column(String, nullable=False)
    # one of: "mechanistic" | "population" | "modality" | "validation" | "evidence_consistency"

    rationale = Column(Text, nullable=True)  # why this gap was triggered (rule + values)
    investigation_suggestion = Column(Text, nullable=True)  # templated, not free-generated

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PriorityScore(Base):
    """
    The explainable prioritization output for a target — kept explicitly
    separate from any single OTP association score, per the finalized
    architecture (evidence profile != priority score).
    """
    __tablename__ = "priority_scores"

    id = Column(Integer, primary_key=True)
    target_id = Column(Integer, ForeignKey("targets.id"), nullable=False)

    evidence_strength = Column(Float, nullable=True)
    evidence_consistency = Column(Float, nullable=True)
    evidence_maturity = Column(Float, nullable=True)

    # Per-dimension breakdown (JSON-encoded dict), e.g. {"genetic": 0.82, "literature": 0.41, ...}
    dimension_breakdown = Column(Text, nullable=True)

    # Consistency breakdown (JSON-encoded dict) — kept separate/visible per
    # this project's "don't collapse dimensions" principle, same rationale
    # as dimension_breakdown above. Added when literature_contradiction was
    # wired into Consistency scoring (Phase 7 follow-up): structured and
    # literature-sourced contradictions come from genuinely different
    # evidence populations (an exhaustive structured-pair count vs. a
    # small, deliberately bounded literature sample — see
    # evidence_profile.compute_evidence_consistency()'s docstring), so
    # `evidence_consistency` above is a single weighted-combined number,
    # but this column keeps both real sub-scores and their real pair
    # counts visible: {"structured_consistency", "structured_pairs",
    # "literature_consistency", "literature_pairs",
    # "structured_contradiction_count", "literature_contradiction_count"}.
    consistency_breakdown = Column(Text, nullable=True)

    priority_score = Column(Float, nullable=True)
    computed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PipelineRunLog(Base):
    """
    Real, explicit marker answering ONE question: "has this stage's POST
    .../run (or .../compute) endpoint ever been called for this target" —
    added specifically to fix a real ambiguity found in Phase 10 (frontend):
    both ContradictionLog and GapRecord can legitimately have ZERO rows for
    a real reason (zero real contradictions/gaps found for that target),
    which is meaningfully different from "never checked at all". Without
    this marker, GET /contradictions/target/{id} and GET /gaps/target/{id}
    (read-only routes — see app/api/routes/contradictions.py and gaps.py)
    could not honestly tell those two states apart from an empty result
    alone. PriorityScore doesn't need this: it's never legitimately "empty"
    the way the other two are — a computed score always has some numeric
    value, so 404-when-no-row-exists is sufficient there.

    One row is inserted every time the corresponding POST endpoint runs
    (not deduplicated — multiple rows for the same target/stage just means
    it was checked more than once, which is real and fine; GET routes only
    care whether AT LEAST ONE row exists).
    """
    __tablename__ = "pipeline_run_log"

    id = Column(Integer, primary_key=True)
    target_id = Column(Integer, ForeignKey("targets.id"), nullable=False)
    stage = Column(String, nullable=False)  # "contradictions" | "gaps"
    run_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class InvestigationTrace(Base):
    """
    Auditable, ordered log of every tool call the autonomous investigation
    agent made during one investigate_target() run (see
    app/agent/investigation_loop.py) — the evidence that the agent made
    real, traceable sequencing decisions rather than being a black box.

    `run_id` groups the steps of one investigate_target() call together
    (added beyond the originally requested column list — without it,
    running the same target twice would collide on
    target_id+step_number and make separate runs impossible to tell apart,
    which defeats the point of comparing repeated runs against each other).

    NOT wired into the fixed pipeline's tables (EvidenceRecord,
    ContradictionLog, GapRecord, PriorityScore) — this is a purely
    additive, separate audit trail for the agent path. See
    app/agent/pipeline_handoff.py's module docstring for why agent-gathered
    evidence itself is scored in memory rather than persisted alongside the
    fixed pipeline's data for the same targets.
    """
    __tablename__ = "investigation_traces"

    id = Column(Integer, primary_key=True)
    target_id = Column(Integer, ForeignKey("targets.id"), nullable=False)
    run_id = Column(String, nullable=False)

    step_number = Column(Integer, nullable=False)
    tool_called = Column(String, nullable=False)
    tool_input = Column(Text, nullable=True)  # JSON-encoded
    tool_result_summary = Column(Text, nullable=True)
    agent_reasoning = Column(Text, nullable=True)  # frequently empty in practice — see CLAUDE.md

    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class MomentumScore(Base):
    """
    Evidence Momentum / Trend Signal — a real, purely factual trend
    computed from real timestamped EvidenceRecord rows already in this
    database (see app/core/scoring/evidence_momentum.py). No LLM
    involvement, no prediction — a deterministic, re-derivable summary of
    real publication/study-year counts.

    A SEPARATE table, not a PriorityScore column, precisely because this
    signal is deliberately kept OUT of PriorityScore/gap-taxonomy (see
    evidence_momentum.py's module docstring) — a target's evidence
    quality/priority does not change based on whether interest in it is
    rising or falling; keeping momentum in its own table makes that
    architectural separation structural, not just a convention that could
    be silently violated later.

    One row per compute_momentum() call (not deduplicated — same
    real-history-preserving convention as PipelineRunLog/PriorityScore;
    GET /momentum/target/{id} recomputes and persists a fresh row on every
    call, since this is a cheap, pure DB aggregation over already-ingested
    data with no external cost to avoid re-running, unlike scoring/
    contradictions/gaps — see that route's docstring for why the Phase 10
    GET/POST separation concern does not apply here the same way).
    """
    __tablename__ = "momentum_scores"

    id = Column(Integer, primary_key=True)
    target_id = Column(Integer, ForeignKey("targets.id"), nullable=False)

    yearly_counts = Column(Text, nullable=False)  # JSON-encoded {"2021": 5, "2022": 12, ...}
    yearly_counts_by_dimension = Column(Text, nullable=False)  # JSON-encoded {"literature": {"2021": 5, ...}, ...}

    trend = Column(String, nullable=False)  # "accelerating" | "stable" | "declining" | "emerging" | "insufficient_data"
    momentum_score = Column(Float, nullable=True)  # None for "emerging"/"insufficient_data" — no real ratio to report

    recent_window_count = Column(Integer, nullable=False)
    prior_window_count = Column(Integer, nullable=False)
    reference_year = Column(Integer, nullable=True)  # the real max year found in this target's own dated evidence

    computed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
