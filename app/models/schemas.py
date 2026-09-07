from pydantic import BaseModel
from datetime import datetime


class TargetOut(BaseModel):
    id: int
    gene_symbol: str
    ensembl_id: str
    disease_efo_id: str

    class Config:
        from_attributes = True


class EvidenceRecordOut(BaseModel):
    id: int
    target_id: int
    dimension: str
    data_source: str
    source_record_id: str
    evidence_score: float | None
    tissue: str | None
    population: str | None
    assay_type: str | None
    endpoint: str | None
    direction_on_trait: str | None

    class Config:
        from_attributes = True


class ContradictionOut(BaseModel):
    id: int
    target_id: int
    evidence_record_a_id: int
    evidence_record_b_id: int
    classification: str
    matched_fields: str | None
    mismatched_fields: str | None
    created_at: datetime
    # Phase 7 additions — always populated (status defaults to "confirmed",
    # proposed_by is backfilled to "structured_classifier" for every
    # pre-Phase-7 row, see scripts/migrate_add_literature_columns.py), so
    # both the structured-classifier route and the new literature route
    # return this same shape, self-describing either way.
    status: str
    proposed_by: str | None
    verification_reason: str | None

    class Config:
        from_attributes = True


class LiteratureContradictionRunOut(BaseModel):
    """
    Response for POST /contradictions/target/{id}/run-literature. Wraps
    confirmed contradictions with the same transparency principle as
    GapAnalysisOut's investigation_coverage: report exactly what was
    checked, not just what was found, so a small "0 contradictions found"
    result can't be misread as "nothing to check" when it might really mean
    "not enough real literature text was available to check."
    """
    contradictions: list[ContradictionOut]
    records_considered: int  # real literature records with usable abstract text, actually compared
    pairs_evaluated: int  # real LLM proposal calls made
    records_missing_abstract: int  # candidates tried where no real abstract text could be fetched
    proposals_rejected_by_verifier: int  # proposed CONTRADICT that failed deterministic verification (not logged)


class GapOut(BaseModel):
    id: int
    target_id: int
    gap_type: str
    rationale: str | None
    investigation_suggestion: str | None

    class Config:
        from_attributes = True


class GapAnalysisOut(BaseModel):
    """
    Wraps GapOut findings with a coverage label, so a gap result can never
    be read as equally authoritative regardless of which evidence-gathering
    path produced it — the fixed pipeline is always "complete" (it queries
    all 4 MVP dimensions by design); the autonomous investigation loop is
    labeled "partial" whenever the agent didn't explore every dimension
    this run. See app.core.gaps.gap_taxonomy.describe_investigation_coverage().
    """
    gaps: list[GapOut]
    investigation_coverage: str
    dimensions_not_explored: list[str]


class PriorityScoreOut(BaseModel):
    target_id: int
    evidence_strength: float | None
    evidence_consistency: float | None
    evidence_maturity: float | None
    dimension_breakdown: str | None
    # JSON-encoded {structured_consistency, structured_pairs,
    # structured_contradiction_count, literature_consistency,
    # literature_pairs, literature_contradiction_count} — kept visible and
    # separate from the single combined evidence_consistency number above,
    # same "don't collapse dimensions" principle as dimension_breakdown.
    # See app.core.scoring.evidence_profile.combine_consistency_scores().
    consistency_breakdown: str | None
    priority_score: float | None

    class Config:
        from_attributes = True


class MomentumOut(BaseModel):
    """
    Evidence Momentum / Trend Signal — see
    app.core.scoring.evidence_momentum's module docstring. Deliberately
    has no relationship to PriorityScoreOut above — an independent,
    purely informational signal, not a quality/priority metric.
    """
    target_id: int
    yearly_counts: str  # JSON-encoded {"2021": 5, "2022": 12, ...}
    yearly_counts_by_dimension: str  # JSON-encoded {"literature": {...}, ...}
    trend: str  # "accelerating" | "stable" | "declining" | "emerging" | "insufficient_data"
    momentum_score: float | None
    recent_window_count: int
    prior_window_count: int
    reference_year: int | None

    class Config:
        from_attributes = True
