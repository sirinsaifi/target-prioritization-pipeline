/* ─── Domain types ─────────────────────────────────────────────────────────── */
/*
 * Phase 10: these types used to describe a fully-fabricated, hardcoded
 * mock dataset (fictional sources, invented PMIDs like "LIT:20441",
 * fabricated study details like a "Sardinian ALS founder cohort" that does
 * not exist in any real ingested evidence). The static TARGETS array that
 * used to live in this file has been REMOVED — all data now comes from the
 * real FastAPI backend via api.ts (fetchTargetSummaries / fetchTargetDetail).
 *
 * The types below are adjusted from the original mock shape wherever the
 * real API genuinely doesn't have an equivalent field — see
 * docs/07_final_architecture_and_phases.md's Phase 10 section for the full
 * field-by-field comparison and the explicit decisions made for each gap
 * (gene full names: small static reference table, not fabricated; per-
 * dimension notes: real evidence counts, not narrative; EvidenceItem and
 * Contradiction.sourceA/B: restructured to real fields only).
 */

export type EvidenceLevel = 'Strong' | 'Moderate' | 'Limited'
export type GapType = 'Validation Gap' | 'Population Gap' | 'Modality Gap' | 'Mechanistic Gap' | 'Evidence-Consistency Gap'
export type ContraType =
  | 'Direct Contradiction'
  | 'Population Heterogeneity'
  | 'Methodological Disagreement'
  | 'Unclassified'
  // Real values the original mock's ContraType union was missing entirely
  // (see docs/07 Phase 10 field comparison) — both are real, logged
  // classifications the backend can return, not hypothetical additions.
  | 'Not Comparable (Cross-Type)'
  | 'Literature Contradiction'

export interface DimensionScore {
  label: string
  score: number        // 0-100 (backend's real dimension_breakdown is 0-1; scaled for display in api.ts)
  level: EvidenceLevel  // frontend-only bucketing of the real score — CONFIRMED no such category exists in the backend
  notes: string         // real, derived from actual evidence record counts — NOT a fabricated narrative
}

/*
 * Restructured from the original mock shape (which had `type`, `title`,
 * `year`, `effect`, `population`, `method` — mostly fabricated narrative
 * with no real backend equivalent). Real EvidenceRecordOut has no paper
 * title, publication year, or free-text "effect" description at all — the
 * DB doesn't store them. Fields below are exactly what GET
 * /evidence/target/{id} really returns.
 */
export interface EvidenceItem {
  id: string                       // real source_record_id (e.g. a PMID, ClinVar RCV id, Reactome pathway id)
  dimension: string                // "genetic" | "literature" | "pathway" | "human_clinical" | "experimental"
  source: string                   // real data_source (e.g. "eva", "europepmc", "reactome", "clinical_precedence")
  evidenceScore: number | null     // real evidence_score, 0-1
  directionOnTrait: string | null  // real direction_on_trait ("Risk" | "Protective" | null)
  detail: string | null            // whichever of tissue/population/assay_type/endpoint is real and non-null
}

/*
 * sourceA/sourceB restructured: the original mock had {id, title, year,
 * finding} — entirely fabricated narrative. The real ContradictionLog row
 * only stores evidence_record_a_id/b_id (plain foreign keys); there is no
 * stored "finding" sentence. Each side below is the REAL EvidenceRecord
 * those ids point to (joined client-side in api.ts against GET
 * /evidence/target/{id}), shown by its real fields instead.
 */
export interface Contradiction {
  id: string
  type: ContraType
  summary: string  // for literature_contradiction: the real deterministic verifier reason; otherwise derived from real matched/mismatched field names — never LLM- or hand-invented prose
  sourceA: { id: string; dimension: string; dataSource: string; directionOnTrait: string | null }
  sourceB: { id: string; dimension: string; dataSource: string; directionOnTrait: string | null }
  matchedFields: string[]
  mismatchedFields: string[]
}

export interface ResearchGap {
  id: string
  type: GapType
  rationale: string    // real, from GapRecord.rationale (gap_taxonomy.py's deterministic templates)
  suggestion: string   // real, from GapRecord.investigation_suggestion
}

/*
 * Evidence Momentum — a real, purely factual trend computed from real
 * timestamped EvidenceRecord rows (publication years, trial-start years),
 * NOT an LLM prediction and NOT an evidence-quality signal (see
 * app/core/scoring/evidence_momentum.py's module docstring — deliberately
 * kept out of priorityScore/gaps). "insufficient_data" is a real, honest
 * state (this target has no dated evidence yet), not an error.
 */
export type MomentumTrend = 'accelerating' | 'stable' | 'declining' | 'emerging' | 'insufficient_data'

export interface Momentum {
  yearlyCounts: { year: string; count: number }[]  // real per-year totals, sorted ascending by year
  trend: MomentumTrend
  momentumScore: number | null  // real recent-vs-prior ratio; null for "emerging"/"insufficient_data" (no real ratio to report)
  recentWindowCount: number
  priorWindowCount: number
}

export interface Target {
  id: number  // real backend Target.id — needed to re-fetch full detail (incl. literature contradictions) when opened
  gene: string
  fullName: string
  priorityScore: number
  dimensions: DimensionScore[]
  hasGaps: boolean
  hasContradictions: boolean
  evidenceItems: EvidenceItem[]
  contradictions: Contradiction[]
  gaps: ResearchGap[]
  /*
   * Run-Analysis follow-up: these distinguish "really ran this stage and
   * found nothing" from "this stage has never been run for this target" —
   * real, derived in api.ts from GET 404 (never run) vs 200 (ran, even if
   * the result is an empty list), not inferred or guessed. Needed because
   * hasGaps/hasContradictions/priorityScore alone can't tell those two
   * states apart (both read as "false"/"0").
   */
  scoreComputed: boolean
  contradictionsChecked: boolean
  gapsChecked: boolean
  momentum: Momentum
}
