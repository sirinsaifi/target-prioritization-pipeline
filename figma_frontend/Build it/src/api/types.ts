/**
 * TypeScript interfaces mirroring the FastAPI backend schemas.
 * These correspond to the pydantic models in app/models/schemas.py
 * and the SQLAlchemy models in app/db/models.py.
 *
 * All endpoint functions in src/api/client.ts return data shaped to match
 * these interfaces (via JSON parsing of API responses).
 */

// ---------------------------------------------------------------------------
// Root / Context
// ---------------------------------------------------------------------------

export interface RootResponse {
  project: string;
  disease: string;
  disease_efo_id: string;
  docs: string;
}

export interface ContextResponse {
  disease: string;
  disease_efo_id: string;
  target_count: number;
  last_analysis: string | null;
  target_summary: TargetSummary;
}

export interface TargetSummary {
  gene_symbol: string;
  ensembl_id: string;
  priority_score: number | null;
  evidence_strength: number | null;
  evidence_consistency: number | null;
  evidence_maturity: number | null;
}

// ---------------------------------------------------------------------------
// Targets
// ---------------------------------------------------------------------------

export interface TargetOut {
  id: number;
  gene_symbol: string;
  ensembl_id: string;
  disease_efo_id: string;
}

// Seeding
export interface SeedResponse {
  created: TargetOut[];
}

// ---------------------------------------------------------------------------
// PriorityScore
// ---------------------------------------------------------------------------

export interface PriorityScoreOut {
  target_id: number;
  evidence_strength: number | null;
  evidence_consistency: number | null;
  evidence_maturity: number | null;
  dimension_breakdown: string | null; // JSON-encoded: {"genetic": 0.99, ...}
  consistency_breakdown: string | null; // JSON-encoded dict
  priority_score: number | null;
  computed_at: string;
}

// ---------------------------------------------------------------------------
// EvidenceRecord
// ---------------------------------------------------------------------------

export interface EvidenceRecordOut {
  id: number;
  target_id: number;
  dimension: string;
  data_source: string;
  source_record_id: string;
  evidence_score: number | null;
  tissue: string | null;
  population: string | null;
  assay_type: string | null;
  endpoint: string | null;
  direction_on_trait: string | null;
  source_url: string | null;
  notes: string | null;
  abstract_text: string | null;
  publication_year: number | null;
  external_id: string | null;
}

// ---------------------------------------------------------------------------
// GapRecord
// ---------------------------------------------------------------------------

export interface GapRecordOut {
  id: number;
  target_id: number;
  gap_type: string;
  rationale: string | null;
  investigation_suggestion: string | null;
  why_it_matters: string | null;
  decision_impact: string | null;
  created_at: string;
}

// GapAnalysisOut (POST /gaps/target/{id}/run response)
export interface GapAnalysisOut {
  gaps: GapRecordOut[];
  investigation_coverage: string;
  dimensions_not_explored: string[];
  translational_opportunity: TranslationalOpportunityOut;
}

export interface TranslationalOpportunityOut {
  category: string;
  rationale: string;
  is_prototype: boolean;
}

// ---------------------------------------------------------------------------
// ContradictionLog
// ---------------------------------------------------------------------------

export interface ContradictionOut {
  id: number;
  target_id: number;
  evidence_record_a_id: number;
  evidence_record_b_id: number;
  classification: string;
  matched_fields: string | null;
  mismatched_fields: string | null;
  created_at: string;
  status: string;
  proposed_by: string | null;
  verification_reason: string | null;
}

// ContradictionRunResponse (POST /contradictions/target/{id}/run response)
export interface ContradictionRunResponse {
  contradictions: ContradictionOut[];
}

// LiteratureContradictionRunOut (POST /contradictions/target/{id}/run-literature response)
export interface LiteratureContradictionRunOut {
  contradictions: ContradictionOut[];
  records_considered: number;
  pairs_evaluated: number;
  records_missing_abstract: number;
  proposals_rejected_by_verifier: number;
}

// ---------------------------------------------------------------------------
// Knowledge Graph
// ---------------------------------------------------------------------------

export interface GraphNode {
  id: string;
  type: string;
  label: string;
  data?: Record<string, any>;
}

export interface GraphEdge {
  source: string;
  target: string;
  type?: string;
  label?: string;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// ---------------------------------------------------------------------------
// MomentumScore
// ---------------------------------------------------------------------------

export interface MomentumOut {
  target_id: number;
  yearly_counts: Record<string, number>;
  yearly_counts_by_dimension: Record<string, Record<string, number>>;
  trend: string;
  momentum_score: number | null;
  recent_window_count: number;
  prior_window_count: number;
  reference_year: number | null;
  computed_at: string;
}

// ---------------------------------------------------------------------------
// Pharos Cross-Checks
// ---------------------------------------------------------------------------

export interface CrossCheckOut {
  check_type: string;
  gene_symbol: string;
  verdict: string;
  pharos_value: string;
  pipeline_value: string;
  rationale: string;
  details: Record<string, any>;
}

export interface PharosCrossChecksOut {
  target_id: number;
  gene_symbol: string;
  cross_checks: CrossCheckOut[];
}

// ---------------------------------------------------------------------------
// Narrative / Narration
// ---------------------------------------------------------------------------

export interface NarrativeResponse {
  narrative: string;
  grounding: {
    priority_score: number;
    evidence_consistency: number;
    evidence_maturity: number;
    gap_types: string[];
  } | null;
}

export interface KeyFreeNarrativeResponse {
  narrative: string;
  priority_score: number;
  evidence_consistency: number;
  evidence_maturity: number;
  gap_types: string[];
  contradiction_count: number;
  gap_count: number;
}

// ---------------------------------------------------------------------------
// Pipeline / Run status
// ---------------------------------------------------------------------------

export interface PipelineRunLogOut {
  id: number;
  target_id: number;
  stage: string;
  run_at: string;
}

export interface PipelineStatusResponse {
  contradictions_run: boolean;
  scoring_computed: boolean;
  gaps_run: boolean;
}