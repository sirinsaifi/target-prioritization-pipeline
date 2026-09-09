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
export type GapType =
  | 'Validation Gap' | 'Population Gap' | 'Modality Gap' | 'Mechanistic Gap' | 'Evidence-Consistency Gap'
  // Real values this union was missing entirely (both gap types exist and
  // fire on real ALS data today — SOD1/TARDBP show Essentiality Risk,
  // see CLAUDE.md) — added here rather than falling back to a raw
  // snake_case string in the UI.
  | 'Safety Signal Gap' | 'Essentiality Risk Gap'
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
  // Real, authoritative "does this gene have a real computed score for
  // this dimension at all" flag (Target De-risking Report addition) — set
  // directly from whether the real dimension_breakdown JSON has this key,
  // NOT inferred from score being 0 (a genuine real score of exactly 0.0
  // is possible and must not be shown as "no data").
  present: boolean
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
  /*
   * Real, clickable external source link (or null where no real
   * single-record page exists — e.g. orphanet/impc) — see GET
   * /evidence/target/{id}'s real source_url field
   * (app/core/presentation/source_links.py). Never fabricated: null means
   * "no real page for this exact record", not "not fetched yet".
   */
  sourceUrl: string | null
  // Real free-text provenance (backend EvidenceRecord.notes) — added for
  // the Evidence + Risk + Gap Matrix's Constraint/Essentiality drill-downs
  // (this task): those two signals' real gnomAD/DepMap values live ONLY
  // in this field (e.g. "prioritisation_geneticConstraint=0.6926 (scale:
  // ...); lof_oe=0.7799 (obs=6, exp=7.69...)"), which was fetched from the
  // backend all along but previously discarded here — `detail` above only
  // carries tissue/population/assay_type/endpoint, never notes.
  notes: string | null
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

/*
 * A gap as a complete, 5-part decision unit (decision-layer strategy
 * priority #2): type -> evidence -> whyItMatters -> suggestion (Next
 * investigation) -> decisionImpact. `evidence`/`suggestion` already
 * existed (GapRecord.rationale/.investigation_suggestion, unchanged in
 * shape — `rationale` is renamed to `evidence` only here in the frontend
 * type, since that's what it always represented); `whyItMatters`/
 * `decisionImpact` are new real, TEMPLATED fields (see
 * app/core/gaps/gap_taxonomy.py's WHY_IT_MATTERS/DECISION_IMPACT dicts) —
 * never LLM-generated, same deterministic-and-auditable discipline as
 * every other gap field.
 */
export interface ResearchGap {
  id: string
  type: GapType
  evidence: string        // real, from GapRecord.rationale (gap_taxonomy.py's deterministic templates)
  whyItMatters: string     // real, from GapRecord.why_it_matters (templated per gap type)
  suggestion: string       // real, from GapRecord.investigation_suggestion ("Next investigation")
  decisionImpact: string   // real, from GapRecord.decision_impact (templated per gap type)
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

/*
 * Translational Opportunity — a lightweight, DETERMINISTIC, rule-based
 * category (GET /gaps/target/{id}'s `translational_opportunity` field —
 * see app/core/classification/translational_opportunity.py's module
 * docstring for the full rule set). EXPLICITLY A PROTOTYPE FRAMEWORK, NOT
 * A VALIDATED BUSINESS SCORE — `isPrototype` is always true, real, and
 * meant to be rendered visibly, not just carried silently. NEVER to be
 * merged into or confused with `priorityScore` — kept as its own,
 * separately-typed, separately-rendered field everywhere it appears
 * (TargetDetail, TargetReport, PortfolioComparison all show it as its own
 * clearly-labeled section/row, never folded into the Priority section).
 * A real caution flag (safety_signal/essentiality_risk) ALWAYS forces
 * category="De-risking Needed" server-side, regardless of how strong
 * priority/maturity/clinical evidence otherwise look — see that module's
 * own design requirement: a caution-flagged target can never land in a
 * purely positive category here.
 */
export interface TranslationalOpportunity {
  category: string
  rationale: string
  isPrototype: boolean
}

/*
 * Caution Flags — a UNIFIED, single visual pattern for every "this is a
 * real risk/caution fact, not a strength score" signal this pipeline
 * surfaces, per this task's own explicit instruction to reuse one
 * consistent pattern rather than inventing a different style per signal.
 * Two real kinds currently populate this array:
 *
 * - 'safety_event': real Open Targets Known Safety Events
 *   (Target.safetyLiabilities, dimension="safety_signal", data_source=
 *   "ot_safety"). Real finding across all 5 ALS candidate genes: zero
 *   documented events for any of them (see CLAUDE.md) — this kind is real
 *   but has never been non-empty in this project's actual data yet.
 * - 'essentiality': real Open Targets/DepMap Gene Essentiality
 *   (Target.isEssential, dimension="essentiality_risk", data_source=
 *   "ot_essentiality" — see app/ingestion/open_targets_client.py's
 *   get_essentiality_and_paralogues() docstring). Real finding: SOD1 and
 *   TARDBP are both flagged essential; C9orf72/FUS/NEK1 are not.
 *
 * Both are deliberately NOT folded into any dimension score (see
 * scripts/ingest_evidence.py's _build_safety_signal_fields()/
 * _build_essentiality_fields()) — surfaced here so TargetDetail.tsx can
 * render ONE shared warning banner, independent of gap-taxonomy's own
 * (stricter, high-evidence-only) "Safety Signal"/"Essentiality Risk" gap
 * triggers, kept as two distinctly-labeled kinds within that one banner
 * (never conflated — an observed clinical event and a predictive
 * cell-line-derived risk score carry different real confidence levels).
 */
export type CautionFlagKind = 'safety_event' | 'essentiality'

export interface CautionFlag {
  kind: CautionFlagKind
  title: string
  detail: string
  sourceUrl: string | null
}

/*
 * Paralogues — real Open Targets homologue data (Target.homologues,
 * filtered to real human paralogues; dimension="paralogy", data_source=
 * "ot_paralogy" — see app/ingestion/open_targets_client.py's
 * get_essentiality_and_paralogues() docstring). Deliberately NOT a caution
 * flag: a paralogue relationship is genuinely two-sided (see
 * scripts/ingest_evidence.py's _build_paralogy_fields() docstring for the
 * full reasoning — no paralogue can mean either "specific" or "no
 * biological backup"; many high-identity paralogues can mean either
 * "redundancy risk" or "a validated, druggable family"), so this renders
 * as a separate, neutral informational card, not the warning banner above.
 */
export interface ParalogueInfo {
  gene: string
  identityPercent: number
  sourceUrl: string | null
}

/*
 * "Why This Target?" — the decision-layer strategy's priority #1
 * structured narrative (GET /narration/why-target/{id},
 * app/core/narration/agent_narrator.py). Meant to be the FIRST thing a
 * reviewer reads on this page, more prominent than raw dimension scores.
 *
 * IMPORTANT design fact, carried through from the backend: `confidence`,
 * `evidenceMaturity`, and `mainRemainingUncertainty` are decided
 * DETERMINISTICALLY in Python from real thresholds (see
 * build_why_this_target_grounding_data()'s docstring) — the LLM is only
 * ever asked to phrase the 3 `bullets` strings from facts already decided;
 * it never sets these three fields. `null` (the whole object, not empty
 * fields) means the real backend call failed or hasn't been made yet
 * (e.g. no GROQ_API_KEY, or a real Groq rate limit — confirmed hit live
 * while building this feature) — never fabricated as an empty-but-present
 * result, and rendered as an honest "unavailable" state, not silently
 * hidden.
 */
export interface WhyThisTarget {
  bullets: string[]
  confidence: 'High' | 'Medium' | 'Low'
  evidenceMaturity: 'High' | 'Medium' | 'Low'
  mainRemainingUncertainty: string
}

/*
 * Evidence Network — real in-memory graph over already-persisted data for
 * one target (GET /graph/target/{id}, app/core/graph/knowledge_graph.py).
 * `data` genuinely differs by node type (see that module's docstring),
 * so it's kept loosely typed here rather than forced into one shape;
 * GraphTab.tsx narrows it per-type where it needs specific fields
 * (is_candidate_target/target_id for ppi_partner, gap_type/rationale for
 * gap, etc.).
 */
export type GraphNodeType = 'target' | 'disease' | 'pathway' | 'ppi_partner' | 'gap' | 'evidence_record'
export type GraphEdgeType = 'associated_with_disease' | 'belongs_to_pathway' | 'interacts_with' | 'has_gap' | 'contradicts'

export interface GraphNode {
  id: string
  type: GraphNodeType
  label: string
  data: Record<string, unknown>
}

export interface GraphEdge {
  source: string
  target: string
  type: GraphEdgeType
  label: string
}

export interface TargetGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface Target {
  id: number  // real backend Target.id — needed to re-fetch full detail (incl. literature contradictions) when opened
  gene: string
  fullName: string
  priorityScore: number
  /*
   * Real evidence_consistency/evidence_maturity (0-1) from the latest
   * PriorityScore row — ALREADY fetched by buildTarget() via GET
   * /scoring/target/{id} (Target De-risking Report audit finding: this
   * data was being fetched and then silently discarded, only
   * priority_score and dimension_breakdown were kept). null means never
   * scored yet (Target.scoreComputed is false), not a real 0.
   */
  evidenceConsistency: number | null
  evidenceMaturity: number | null
  /*
   * Real, UNROUNDED priority_score (0-1) — added alongside priorityScore
   * (the rounded 0-100 display integer) after a real, confirmed bug: the
   * old priorityTier() derived its tier by dividing the ALREADY-ROUNDED
   * priorityScore integer back down (e.g. 0.7955 -> rounds to 80 ->
   * 80/100 = 0.80 -> incorrectly reads as ">= 0.8"). Threshold comparisons
   * must run against the real, unrounded value — see api.ts::priorityTier().
   */
  priorityScoreRaw: number | null
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
  graph: TargetGraph
  cautionFlags: CautionFlag[]
  paralogues: ParalogueInfo[]
  whyThisTarget: WhyThisTarget | null
  // null only if gaps have never been run for this target (see
  // gapsChecked) — once gaps have run, the backend always returns a real
  // translational_opportunity alongside them (never optional there).
  translationalOpportunity: TranslationalOpportunity | null
}
