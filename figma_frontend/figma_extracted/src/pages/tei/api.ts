/**
 * Real data layer — replaces the static TARGETS mock in data.ts with live
 * fetch() calls to the FastAPI backend. Plain fetch, no state-management
 * library (matches the backend's own Streamlit UI convention, which is
 * also a thin client over the same API — see streamlit_app.py).
 *
 * REAL API SURFACE THIS RELIES ON:
 *   GET  /targets/
 *   GET  /evidence/target/{id}
 *   GET  /scoring/target/{id}          (read-only — added to fix the gap below)
 *   GET  /contradictions/target/{id}   (read-only — returns BOTH structured
 *                                        and literature_contradiction rows)
 *   GET  /gaps/target/{id}             (read-only)
 *
 * FIXED ARCHITECTURAL GAP (this file previously called the POST endpoints
 * below from passive page loads, which is exactly the bug being fixed):
 * the API used to have NO GET routes for scores/contradictions/gaps — only
 * POST .../run and .../compute, which actively (re)compute AND persist a
 * new result every time they're called. That meant "viewing" a target and
 * "recomputing" it were the same action. Real GET routes were added
 * (app/api/routes/{scoring,contradictions,gaps}.py) that read the latest
 * persisted result without recomputing anything — this file now uses ONLY
 * those for display. The POST endpoints still exist and still work exactly
 * as before, reserved for an explicit "recompute" action this UI doesn't
 * expose yet (no button calls them) — see docs/07 Phase 10 follow-up.
 *
 * REAL CONSEQUENCE OF THIS FIX, worth stating plainly: the previous version
 * of this file deliberately ran the structured contradiction check for
 * every target on every list load, and ADDITIONALLY ran the real,
 * LLM-backed literature check (POST .../run-literature) every time a
 * target's detail page was opened — a real, non-trivial Groq API cost paid
 * on a passive page view. Since GET reads are cheap DB lookups regardless
 * of which check (structured or literature) produced the persisted rows,
 * that asymmetry is gone: TargetList and TargetDetail now show the exact
 * same real, already-computed data — literature contradictions included in
 * BOTH, not just the detail page — and neither view triggers a real LLM
 * call anymore. Refreshing with a NEW literature check is future work (an
 * explicit "recompute" action, not built here).
 *
 * A GET read can 404 (never computed/checked yet) — every one of the 5
 * real candidate targets already has real persisted history from earlier
 * phases, so this shouldn't occur in practice, but is handled defensively
 * below by falling back to an honest "not yet computed" display rather
 * than silently calling POST to fill the gap (that would reintroduce
 * exactly the bug this fix closes).
 *
 * RUN FULL ANALYSIS (added after the fix above): the UI still needs an
 * explicit, user-triggered way to (re)compute a target — see
 * `runFullAnalysis()` below, the one function in this file that calls
 * POST. Wired to a real button on TargetDetail (see TargetDetail.tsx).
 */

import type {
  Target, DimensionScore, EvidenceItem, Contradiction, ResearchGap,
  ContraType, GapType, EvidenceLevel, Momentum, MomentumTrend, TargetGraph, CautionFlag, ParalogueInfo,
  WhyThisTarget,
} from './data'

const API_BASE = (import.meta as any).env?.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

/* ─── Static reference data (NOT fabricated findings — see report) ───────────
   Gene full names are an objective, publicly-documented biological fact
   (HGNC-style nomenclature), not a study result — kept as a small local
   lookup table since no backend field stores this. Confirmed with the user
   before adding (see docs/07 Phase 10 write-up). */
const GENE_FULL_NAMES: Record<string, string> = {
  SOD1: 'Superoxide Dismutase 1',
  C9orf72: 'Chromosome 9 Open Reading Frame 72',
  TARDBP: 'TAR DNA-Binding Protein (TDP-43)',
  FUS: 'Fused in Sarcoma',
  NEK1: 'NIMA-Related Kinase 1',
}

/* Real snake_case gap_type -> a display label. The original mock only had
   5 gap types; safety_signal/essentiality_risk (real, fire on real ALS
   data today — see CLAUDE.md) were added later and are included here so
   the Gaps tab never falls back to a raw snake_case string. */
const GAP_TYPE_LABELS: Record<string, GapType> = {
  mechanistic: 'Mechanistic Gap',
  population: 'Population Gap',
  modality: 'Modality Gap',
  validation: 'Validation Gap',
  evidence_consistency: 'Evidence-Consistency Gap',
  safety_signal: 'Safety Signal Gap',
  essentiality_risk: 'Essentiality Risk Gap',
}

/* Real classification values (app/core/verification/contradiction_classifier.py
   + Phase 7's literature_contradiction) -> display label. The mock's
   ContraType union only had 4 of these 6 real values — extended in data.ts
   to add the 2 missing ones (not_comparable_cross_type, literature_contradiction)
   rather than silently dropping/miscategorizing real logged rows. */
const CONTRA_TYPE_LABELS: Record<string, ContraType> = {
  direct_contradiction: 'Direct Contradiction',
  population_heterogeneity: 'Population Heterogeneity',
  methodological_disagreement: 'Methodological Disagreement',
  unclassified: 'Unclassified',
  not_comparable_cross_type: 'Not Comparable (Cross-Type)',
  literature_contradiction: 'Literature Contradiction',
}

/* Real dimension_breakdown key -> display label. The original mock only
 * had 4 dimensions (kept FIRST, at indices 0-3, since several call sites —
 * TargetList.tsx's sort keys, TargetDetail.tsx's tagline — index into
 * Target.dimensions positionally and assume genetic/literature/pathway/
 * human_clinical are exactly there). The other 5 real MVP dimensions
 * (app/config.py's MVP_DIMENSIONS) were added to the backend across later
 * tasks this project but never added here — Target De-risking Report
 * audit finding: buildDimensions() below already handles an arbitrary
 * dimension list generically (a missing real score for a given gene
 * already renders as an honest "no real evidence ingested" state, not a
 * fabricated zero), so extending this list is the ONLY change needed to
 * surface all 9 real dimensions everywhere Target.dimensions is used —
 * no new fetch, no new backend work. "omics" is included even though it's
 * never had a real row for any of the 5 ALS candidates (confirmed
 * retired at the source, see docs/07 Phase 13) — shown honestly as "no
 * real evidence", not hidden. */
const DIMENSION_ORDER: { key: string; label: string }[] = [
  { key: 'genetic', label: 'Genetic' },
  { key: 'literature', label: 'Literature' },
  { key: 'pathway', label: 'Pathway' },
  { key: 'human_clinical', label: 'Human / Clinical' },
  { key: 'omics', label: 'Omics' },
  { key: 'experimental', label: 'Experimental' },
  { key: 'drug_target', label: 'Drug-Target' },
  { key: 'tissue_expression', label: 'Tissue Expression' },
  { key: 'ppi_network', label: 'PPI Network' },
]

/* ─── Shared High/Medium/Low labeling — reuses the SAME thresholds already
 * established server-side for "Why This Target?" (app/config.py's
 * CONFIDENCE_HIGH_THRESHOLD/CONFIDENCE_LOW_THRESHOLD =
 * agent_narrator._confidence_label(), MATURITY_HIGH_THRESHOLD/
 * MATURITY_LOW_THRESHOLD = agent_narrator._maturity_label()), not a new
 * threshold family invented for the Target De-risking Report / Portfolio
 * Comparison table. Kept here as pure functions (not a 6th fetch of
 * GET /narration/why-target/{id}, which makes a real, rate-limited LLM
 * call) — mirroring the real backend constant VALUES is enough to render
 * the same label without paying that cost on every list/table view. If
 * those backend constants ever change, these must be updated to match. */
export type ScoreTier = 'High' | 'Medium' | 'Low' | 'Unknown'

function tierFromThresholds(value: number | null, high: number, low: number): ScoreTier {
  if (value === null) return 'Unknown'
  if (value >= high) return 'High'
  if (value < low) return 'Low'
  return 'Medium'
}

/** Mirrors agent_narrator._confidence_label() (config.CONFIDENCE_HIGH_THRESHOLD=0.8 / CONFIDENCE_LOW_THRESHOLD=0.5). */
export function consistencyTier(evidenceConsistency: number | null): ScoreTier {
  return tierFromThresholds(evidenceConsistency, 0.8, 0.5)
}

/** Mirrors agent_narrator._maturity_label() (config.MATURITY_HIGH_THRESHOLD=0.9 / MATURITY_LOW_THRESHOLD=0.4). */
export function maturityTier(evidenceMaturity: number | null): ScoreTier {
  return tierFromThresholds(evidenceMaturity, 0.9, 0.4)
}

/**
 * CORRECTED (real bug found and fixed): this used to take the ALREADY-
 * ROUNDED 0-100 display integer and divide it back down before comparing
 * to a threshold — e.g. a real raw score of 0.7955 rounds to 80 for
 * display, then 80/100 = 0.80 incorrectly reads as ">= 0.8". Thresholds
 * must be compared against the real, unrounded value, so this now takes
 * `priorityScoreRaw` (0-1) directly, never the rounded display integer.
 *
 * THRESHOLD DECISION, made explicitly rather than assumed: priority_score
 * is NOT the same metric confidenceTier()/maturityTier() were calibrated
 * for — it's `(evidence_strength + evidence_consistency + evidence_maturity) / 3`
 * (see app/api/routes/scoring.py), a broader composite, not evidence_consistency
 * alone. Reusing CONFIDENCE_HIGH/LOW_THRESHOLD (0.8/0.5) here was an
 * unverified assumption, not a real reuse of an equivalent metric's own
 * threshold. Uses a DIFFERENT, still-existing pair instead:
 * EVIDENCE_STRENGTH_HIGH_THRESHOLD (0.7) and EVIDENCE_CONSISTENCY_GAP_
 * THRESHOLD (0.5) from app/config.py — this codebase's own already-
 * established "strong enough" / "concerning" bars, used throughout
 * gap_taxonomy.py for exactly this kind of judgment, and semantically
 * closer to "is this target worth prioritizing" than the consistency-
 * specific 0.8 cutoff. `computed` distinguishes a real score from "never
 * scored yet" (see Target.scoreComputed).
 */
export function priorityTier(priorityScoreRaw: number | null, computed: boolean): ScoreTier {
  if (!computed) return 'Unknown'
  return tierFromThresholds(priorityScoreRaw, 0.7, 0.5)
}

/* Main Gap selection (this task) — the single most significant real open
 * gap, by a documented priority order. EXPLICIT JUDGMENT CALL: safety/
 * essentiality risk flags first (they fire because a real, concerning
 * fact EXISTS, not because evidence is missing — see
 * app/core/gaps/gap_taxonomy.py), then Validation (no proof of benefit in
 * humans at all) > Modality (no compound yet, a narrower problem) >
 * Mechanistic (mechanism unclear, but disease link itself not in doubt) >
 * Population (a real finding exists, just not yet replicated broadly) >
 * Evidence-Consistency (a prompt to double-check existing evidence, not a
 * coverage gap). This is this project's OWN chosen order, not an external
 * standard — documented here rather than left implicit. */
const MAIN_GAP_PRIORITY: GapType[] = [
  'Safety Signal Gap', 'Essentiality Risk Gap', 'Validation Gap', 'Modality Gap',
  'Mechanistic Gap', 'Population Gap', 'Evidence-Consistency Gap',
]

export function pickMainGap(gaps: ResearchGap[]): ResearchGap | null {
  for (const gapType of MAIN_GAP_PRIORITY) {
    const found = gaps.find(g => g.type === gapType)
    if (found) return found
  }
  return gaps[0] ?? null
}

/* Score -> level bucketing. CONFIRMED this categorical mapping does not
   exist anywhere in the backend (checked dimension_scoring.py,
   evidence_profile.py, gap_taxonomy.py) — this is a frontend-only
   presentational bucketing of the real 0-1 score, not a backend-computed
   category. Thresholds chosen to roughly match the mock data's own
   score-to-level assignments (e.g. mock: 82->Strong, 71->Moderate,
   58->Moderate, 45->Limited). */
function scoreToLevel(score0to1: number): EvidenceLevel {
  const pct = score0to1 * 100
  if (pct >= 75) return 'Strong'
  if (pct >= 45) return 'Moderate'
  return 'Limited'
}

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status} ${await res.text()}`)
  return res.json()
}

async function apiGetOrNull<T>(path: string): Promise<T | null> {
  const res = await fetch(`${API_BASE}${path}`)
  if (res.status === 404) return null  // real, honest "never computed/checked yet" — not an error
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status} ${await res.text()}`)
  return res.json()
}

/**
 * POST is reserved for an explicit "recompute" action — not called from
 * any passive load in this file (see module docstring). Exported for a
 * future "Recompute" UI action; unused today is intentional, not dead code.
 */
export async function apiPost<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: 'POST' })
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status} ${await res.text()}`)
  return res.json()
}

/* ─── Real backend response shapes (subset of fields actually used) ───────── */

interface ApiTarget {
  id: number
  gene_symbol: string
  ensembl_id: string
  disease_efo_id: string
}

interface ApiEvidenceRecord {
  id: number
  target_id: number
  dimension: string
  data_source: string
  source_record_id: string
  evidence_score: number | null
  tissue: string | null
  population: string | null
  assay_type: string | null
  endpoint: string | null
  direction_on_trait: string | null
  source_url: string | null
  notes: string | null
}

interface ApiContradiction {
  id: number
  target_id: number
  evidence_record_a_id: number
  evidence_record_b_id: number
  classification: string
  matched_fields: string | null
  mismatched_fields: string | null
  status: string
  proposed_by: string | null
  verification_reason: string | null
}

interface ApiGap {
  id: number
  target_id: number
  gap_type: string
  rationale: string | null
  investigation_suggestion: string | null
  why_it_matters: string | null
  decision_impact: string | null
}

interface ApiTranslationalOpportunity {
  category: string
  rationale: string
  is_prototype: boolean
}

interface ApiGapAnalysis {
  gaps: ApiGap[]
  investigation_coverage: string
  dimensions_not_explored: string[]
  translational_opportunity: ApiTranslationalOpportunity
}

interface ApiMomentum {
  target_id: number
  yearly_counts: string  // JSON-encoded {"2021": 5, ...}
  yearly_counts_by_dimension: string
  trend: string
  momentum_score: number | null
  recent_window_count: number
  prior_window_count: number
  reference_year: number | null
}

interface ApiWhyThisTargetResponse {
  error: string | null
  why_this_target: {
    gene_symbol: string
    bullets: string[]
    confidence: 'High' | 'Medium' | 'Low'
    evidence_maturity: 'High' | 'Medium' | 'Low'
    main_remaining_uncertainty: Record<string, unknown> | null
  } | null
}

interface ApiPriorityScore {
  target_id: number
  evidence_strength: number | null
  evidence_consistency: number | null
  evidence_maturity: number | null
  dimension_breakdown: string | null
  consistency_breakdown: string | null
  priority_score: number | null
}

/* ─── Transform helpers ────────────────────────────────────────────────── */

function buildDimensions(dimensionBreakdownJson: string | null, evidenceCounts: Record<string, number>): DimensionScore[] {
  const breakdown: Record<string, number> = dimensionBreakdownJson ? JSON.parse(dimensionBreakdownJson) : {}
  return DIMENSION_ORDER.map(({ key, label }) => {
    const raw = breakdown[key]
    const count = evidenceCounts[key] || 0
    if (raw === undefined) {
      // Real, honest state: no evidence_score exists for this dimension at
      // all for this gene (not a zero score — a real absence of data, see
      // docs/07 Phase 10 field-comparison report).
      return {
        label, score: 0, level: 'Limited' as EvidenceLevel, present: false,
        notes: count > 0
          ? `${count} real evidence record(s) in this dimension, but none carry a computed score yet.`
          : 'No real evidence ingested for this dimension.',
      }
    }
    return {
      label,
      score: Math.round(raw * 100),
      level: scoreToLevel(raw),
      present: true,
      // Real, derived from actual evidence counts (see confirmed decision
      // in docs/07) — NOT a fabricated narrative like the old mock data.
      notes: `${count} real evidence record(s) in this dimension.`,
    }
  })
}

function buildEvidenceItems(records: ApiEvidenceRecord[]): EvidenceItem[] {
  return records.map(r => {
    const detail = [
      r.tissue && `tissue: ${r.tissue}`,
      r.population && `population: ${r.population}`,
      r.assay_type && `assay: ${r.assay_type}`,
      r.endpoint && `endpoint: ${r.endpoint}`,
    ].filter(Boolean).join(', ')
    return {
      id: r.source_record_id,
      dimension: r.dimension,
      source: r.data_source,
      evidenceScore: r.evidence_score,
      directionOnTrait: r.direction_on_trait,
      detail: detail || null,
      sourceUrl: r.source_url,
      notes: r.notes,
    }
  })
}

/* Real Known Safety Events (dimension="safety_signal", data_source=
 * "ot_safety" — see app/ingestion/open_targets_client.py). `notes` is the
 * only place the real event name/datasource live (no dedicated structured
 * field), stored server-side as "event=X; direction=Y; datasource=Z" —
 * parsed back out here rather than adding a new backend field for what's
 * fundamentally free-text provenance the same way pathway/ppi_partner
 * notes already are (see the graph feature's own _parse_note_field()
 * precedent, mirrored here client-side since this is the one place that
 * needs it parsed). */
function parseNoteField(notes: string | null, key: string): string | null {
  if (!notes) return null
  const marker = `${key}=`
  const idx = notes.indexOf(marker)
  if (idx === -1) return null
  const start = idx + marker.length
  const end = notes.indexOf(';', start)
  const value = (end === -1 ? notes.slice(start) : notes.slice(start, end)).trim()
  return value || null
}

/* Real Known Safety Events (dimension="safety_signal") -> the unified
 * CautionFlag shape (see data.ts's own docstring for why these two real
 * signals share one banner, kept distinctly labeled within it). */
function buildSafetyEventFlags(records: ApiEvidenceRecord[]): CautionFlag[] {
  return records
    .filter(r => r.dimension === 'safety_signal')
    .map(r => ({
      kind: 'safety_event' as const,
      title: parseNoteField(r.notes, 'event') || r.source_record_id,
      detail: parseNoteField(r.notes, 'datasource') || r.data_source,
      sourceUrl: r.source_url,
    }))
}

/* Real Open Targets/DepMap Gene Essentiality (dimension="essentiality_risk").
 * ONE real row per gene, always present (see scripts/ingest_evidence.py's
 * _build_essentiality_fields()) — only rendered as a caution flag when the
 * record's own real `raw_value` (OTP's -1/0 prioritisation factor) is
 * negative, i.e. genuinely "reported essential" per that function's
 * confirmed real semantics; `raw_value` is not exposed on
 * ApiEvidenceRecord today, so `isEssential=True` is parsed out of `notes`
 * instead — the same real text the backend's own gap-taxonomy wiring
 * reads (see app/api/routes/gaps.py). */
function buildEssentialityFlags(records: ApiEvidenceRecord[]): CautionFlag[] {
  return records
    .filter(r => r.dimension === 'essentiality_risk' && parseNoteField(r.notes, 'isEssential') === 'True')
    .map(r => ({
      kind: 'essentiality' as const,
      title: 'Flagged essential (Open Targets / DepMap)',
      detail: r.notes || 'Reported essential by Open Targets/DepMap.',
      sourceUrl: r.source_url,
    }))
}

function buildCautionFlags(records: ApiEvidenceRecord[]): CautionFlag[] {
  return [...buildSafetyEventFlags(records), ...buildEssentialityFlags(records)]
}

/* Real Open Targets Paralogues (dimension="paralogy", one real row per
 * real human paralogue found — see scripts/ingest_evidence.py's
 * _build_paralogy_fields()). Deliberately NOT filtered by any
 * note-worthiness threshold here (unlike the backend's Modality-gap
 * enrichment) — every real paralogue found is shown in this informational
 * card, since the two-sided interpretation belongs to the reader, not a
 * cutoff baked into what's displayed. */
function buildParalogues(records: ApiEvidenceRecord[]): ParalogueInfo[] {
  return records
    .filter(r => r.dimension === 'paralogy')
    .map(r => ({
      gene: parseNoteField(r.notes, 'paralog_gene') || r.source_record_id,
      identityPercent: Number(parseNoteField(r.notes, 'query_pct_identity')) || 0,
      sourceUrl: r.source_url,
    }))
    .sort((a, b) => b.identityPercent - a.identityPercent)
}

function describeContradiction(classification: string, matchedFieldsJson: string | null, mismatchedFieldsJson: string | null, verificationReason: string | null): string {
  const matched: string[] = matchedFieldsJson ? JSON.parse(matchedFieldsJson) : []
  const mismatched: string[] = mismatchedFieldsJson ? JSON.parse(mismatchedFieldsJson) : []
  const label = CONTRA_TYPE_LABELS[classification] || classification
  if (classification === 'literature_contradiction') {
    // Real, deterministic verifier text (see literature_contradiction_verifier.py)
    // — not an LLM-invented sentence.
    return verificationReason || `${label} (literature-sourced, LLM-proposed and deterministically verified).`
  }
  const parts = [`${label}.`]
  if (matched.length) parts.push(`Matched: ${matched.join(', ')}.`)
  if (mismatched.length) parts.push(`Mismatched: ${mismatched.join(', ')}.`)
  return parts.join(' ')
}

function buildContradictions(apiContradictions: ApiContradiction[], evidenceById: Map<number, ApiEvidenceRecord>): Contradiction[] {
  return apiContradictions.map(c => {
    const recA = evidenceById.get(c.evidence_record_a_id)
    const recB = evidenceById.get(c.evidence_record_b_id)
    const describeSource = (rec: ApiEvidenceRecord | undefined, id: number) => rec
      ? { id: rec.source_record_id, dimension: rec.dimension, dataSource: rec.data_source, directionOnTrait: rec.direction_on_trait }
      : { id: String(id), dimension: 'unknown', dataSource: 'unknown', directionOnTrait: null }
    return {
      id: String(c.id),
      type: CONTRA_TYPE_LABELS[c.classification] || (c.classification as ContraType),
      summary: describeContradiction(c.classification, c.matched_fields, c.mismatched_fields, c.verification_reason),
      sourceA: describeSource(recA, c.evidence_record_a_id),
      sourceB: describeSource(recB, c.evidence_record_b_id),
      matchedFields: c.matched_fields ? JSON.parse(c.matched_fields) : [],
      mismatchedFields: c.mismatched_fields ? JSON.parse(c.mismatched_fields) : [],
    }
  })
}

function buildGaps(gaps: ApiGap[]): ResearchGap[] {
  return gaps.map(g => ({
    id: String(g.id),
    type: GAP_TYPE_LABELS[g.gap_type] || (g.gap_type as GapType),
    evidence: g.rationale || '',
    whyItMatters: g.why_it_matters || '',
    suggestion: g.investigation_suggestion || '',
    decisionImpact: g.decision_impact || '',
  }))
}

function countByDimension(records: ApiEvidenceRecord[]): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const r of records) counts[r.dimension] = (counts[r.dimension] || 0) + 1
  return counts
}

const VALID_MOMENTUM_TRENDS: MomentumTrend[] = ['accelerating', 'stable', 'declining', 'emerging', 'insufficient_data']

function buildMomentum(m: ApiMomentum): Momentum {
  const yearlyCountsObj: Record<string, number> = JSON.parse(m.yearly_counts)
  return {
    yearlyCounts: Object.entries(yearlyCountsObj)
      .map(([year, count]) => ({ year, count }))
      .sort((a, b) => a.year.localeCompare(b.year)),
    trend: (VALID_MOMENTUM_TRENDS as string[]).includes(m.trend) ? (m.trend as MomentumTrend) : 'insufficient_data',
    momentumScore: m.momentum_score,
    recentWindowCount: m.recent_window_count,
    priorWindowCount: m.prior_window_count,
  }
}

/* Real "main_remaining_uncertainty" dict from the backend (see
 * build_why_this_target_grounding_data()'s docstring) -> a readable
 * sentence. Two real shapes, both handled, nothing else fabricated: a real
 * open gap ({source:"gap", gap_type, rationale}) or, when no
 * evidence-completeness gap is open, the real lowest-scoring dimension
 * ({source:"lowest_dimension", label, score}). */
function describeMainRemainingUncertainty(u: Record<string, unknown> | null): string {
  if (!u) return 'Not available.'
  if (u.source === 'gap') {
    return String(u.rationale || `Open ${u.gap_type} gap.`)
  }
  if (u.source === 'lowest_dimension') {
    const score = typeof u.score === 'number' ? Math.round(u.score * 100) : u.score
    return `No open evidence-completeness gap — the lowest-scoring dimension is ${u.label} (${score}).`
  }
  // Real edge case: every scored dimension this target has is one with a
  // known scoring-formula limitation (see the backend's
  // config.DIMENSIONS_WITH_SCORING_FORMULA_LIMITATIONS docstring) — stated
  // plainly rather than forcing a misleading pick.
  if (u.source === 'none') {
    return 'No clear remaining uncertainty in scored dimensions.'
  }
  return 'Not available.'
}

/* GET /narration/why-target/{id} — a real LLM call with a real, disclosed
 * failure mode (no GROQ_API_KEY, or a real Groq rate/token limit,
 * confirmed hit live while building this feature). Fetched eagerly since
 * this is meant to be the FIRST thing a reviewer reads (per this
 * feature's own design goal), but failure is caught here and returns
 * null rather than breaking the rest of the page — same graceful-
 * degradation convention as momentum/graph above. */
async function buildWhyThisTarget(targetId: number): Promise<WhyThisTarget | null> {
  try {
    const res = await fetch(`${API_BASE}/narration/why-target/${targetId}`)
    if (!res.ok) return null
    const body: ApiWhyThisTargetResponse = await res.json()
    if (body.error || !body.why_this_target) return null
    const w = body.why_this_target
    return {
      bullets: w.bullets,
      confidence: w.confidence,
      evidenceMaturity: w.evidence_maturity,
      mainRemainingUncertainty: describeMainRemainingUncertainty(w.main_remaining_uncertainty),
    }
  } catch {
    return null
  }
}

/* ─── Public API ───────────────────────────────────────────────────────── */

export async function fetchTargetList(): Promise<{ id: number; gene: string }[]> {
  const targets = await apiGet<ApiTarget[]>('/targets/')
  return targets.map(t => ({ id: t.id, gene: t.gene_symbol }))
}

/**
 * Builds one real Target from GET-only reads — no POST, no recomputation
 * of scoring/contradictions/gaps. Shared by both fetchTargetSummaries()
 * (all 5 genes, for TargetList) and fetchTargetDetail() (one gene, for
 * TargetDetail) — now that reads don't recompute anything, there's no
 * cost reason to treat "list" and "detail" differently the way the
 * previous POST-based version did (see module docstring for what changed
 * and why).
 *
 * ONE DELIBERATE EXCEPTION, stated plainly rather than silently
 * contradicting the paragraph above: GET /momentum/target/{id} DOES
 * recompute and persist a fresh MomentumScore row on every call — by
 * design (see that route's own docstring), because momentum is a cheap,
 * pure DB aggregation over already-ingested data with no external
 * API/LLM cost to avoid re-paying, unlike scoring/contradictions/gaps.
 * Calling it from this passive load is therefore NOT the same
 * "viewing == recomputing" bug Phase 10 fixed for the other three.
 */
async function buildTarget(t: ApiTarget): Promise<Target> {
  const evidenceRecords = await apiGet<ApiEvidenceRecord[]>(`/evidence/target/${t.id}`).catch(() => [] as ApiEvidenceRecord[])
  const evidenceCounts = countByDimension(evidenceRecords)
  const evidenceById = new Map(evidenceRecords.map(r => [r.id, r]))
  const momentum = await apiGet<ApiMomentum>(`/momentum/target/${t.id}`)
    .then(buildMomentum)
    .catch((): Momentum => ({
      yearlyCounts: [], trend: 'insufficient_data', momentumScore: null, recentWindowCount: 0, priorWindowCount: 0,
    }))

  const score = await apiGetOrNull<ApiPriorityScore>(`/scoring/target/${t.id}`)
  // Real, honest "never checked"/"never run" states — an empty array from
  // apiGet (200 OK) means "checked, zero found"; null from apiGetOrNull
  // (404) means "never checked at all". The raw nullness is preserved below
  // as scoreComputed/contradictionsChecked/gapsChecked so the UI (the new
  // Run Full Analysis feature) can show an honest "not yet analyzed"
  // indicator instead of silently reading an unrun stage as "zero found".
  const contradictionsRaw = await apiGetOrNull<ApiContradiction[]>(`/contradictions/target/${t.id}`)
  const gapAnalysisRaw = await apiGetOrNull<ApiGapAnalysis>(`/gaps/target/${t.id}`)
  const contradictions = contradictionsRaw ?? []
  const gapAnalysis = gapAnalysisRaw ?? { gaps: [], investigation_coverage: '', dimensions_not_explored: [] }
  // Real, read-only knowledge graph (GET /graph/target/{id}) — cheap to
  // rebuild from already-persisted rows every call (see that route's own
  // docstring), so it's fetched eagerly here like every other tab's data
  // rather than lazily on tab-open, matching this file's existing pattern.
  const graph = await apiGet<TargetGraph>(`/graph/target/${t.id}`).catch((): TargetGraph => ({ nodes: [], edges: [] }))

  return {
    id: t.id,
    gene: t.gene_symbol,
    fullName: GENE_FULL_NAMES[t.gene_symbol] || t.gene_symbol,
    priorityScore: score ? Math.round((score.priority_score ?? 0) * 100) : 0,
    priorityScoreRaw: score?.priority_score ?? null,
    evidenceConsistency: score?.evidence_consistency ?? null,
    evidenceMaturity: score?.evidence_maturity ?? null,
    dimensions: score
      ? buildDimensions(score.dimension_breakdown, evidenceCounts)
      : DIMENSION_ORDER.map(({ label }) => ({
          label, score: 0, level: 'Limited' as EvidenceLevel, present: false,
          notes: 'Not yet scored — click "Run Full Analysis" above.',
        })),
    hasGaps: gapAnalysis.gaps.length > 0,
    hasContradictions: contradictions.length > 0,
    evidenceItems: buildEvidenceItems(evidenceRecords),
    contradictions: buildContradictions(contradictions, evidenceById),
    gaps: buildGaps(gapAnalysis.gaps),
    scoreComputed: score !== null,
    contradictionsChecked: contradictionsRaw !== null,
    gapsChecked: gapAnalysisRaw !== null,
    momentum,
    graph,
    cautionFlags: buildCautionFlags(evidenceRecords),
    paralogues: buildParalogues(evidenceRecords),
    translationalOpportunity: gapAnalysisRaw
      ? {
          category: gapAnalysisRaw.translational_opportunity.category,
          rationale: gapAnalysisRaw.translational_opportunity.rationale,
          isPrototype: gapAnalysisRaw.translational_opportunity.is_prototype,
        }
      : null,
    // Deliberately NOT fetched here — see fetchTargetDetail() below. Every
    // real target this project has (5 ALS genes) would otherwise pay a
    // real LLM cost just from opening the LIST page (fetchTargetSummaries
    // calls buildTarget() once per target) — exactly the "viewing == an
    // expensive real cost" anti-pattern Phase 10 already fixed once for
    // the literature-contradiction check. Kept scoped to the detail view
    // only, same real precedent.
    whyThisTarget: null,
  }
}

/**
 * The ONE place in this app that calls POST endpoints (every other
 * function in this file is GET-only — see module docstring). Explicitly
 * triggered by the "Run Full Analysis" button on TargetDetail; never
 * called from a passive page load.
 *
 * Real stages run, in this ORDER (deliberately reordered from how this was
 * first requested — scoring, then contradictions — see docs/07 Phase 10
 * follow-up for why): structured contradictions -> literature
 * contradictions -> scoring -> gaps. Reason: app/api/routes/scoring.py's
 * own docstring states Consistency is computed from whatever ContradictionLog
 * rows ALREADY exist at the time scoring runs, not recomputed live — running
 * scoring before contradictions would silently score against stale/prior
 * contradiction data instead of this run's real findings. Gaps must run
 * last because POST /gaps/target/{id}/run reads the latest PriorityScore
 * (400s if none exists yet).
 *
 * The literature check is a real Groq LLM call and can fail for reasons
 * outside this app's control (no API key configured, rate limit, too few
 * literature records with fetchable abstracts). That failure is caught
 * here and reported back rather than aborting the other 3 (real,
 * deterministic) stages or swallowing the failure silently.
 */
export async function runFullAnalysis(targetId: number): Promise<{ literatureCheckError: string | null }> {
  await apiPost(`/contradictions/target/${targetId}/run`)

  let literatureCheckError: string | null = null
  try {
    await apiPost(`/contradictions/target/${targetId}/run-literature`)
  } catch (err) {
    literatureCheckError = err instanceof Error ? err.message : String(err)
  }

  await apiPost(`/scoring/target/${targetId}/compute`)
  await apiPost(`/gaps/target/${targetId}/run`)

  return { literatureCheckError }
}

/** Real priority score, dimensions, and gap/contradiction data for every
 * target — used by TargetList. Pure GET reads (see module docstring). */
export async function fetchTargetSummaries(): Promise<Target[]> {
  const targets = await apiGet<ApiTarget[]>('/targets/')
  return Promise.all(targets.map(buildTarget))
}

/** Same real data as fetchTargetSummaries(), for one target — used by
 * TargetDetail. Identical GET-only reads, PLUS the real "Why This
 * Target?" LLM call (see buildTarget()'s own note on why that call is
 * scoped to the detail view only, not the list) — the one real, bounded
 * LLM cost paid here, matching the existing precedent this file already
 * established for the literature-contradiction check. Kept as a separate
 * named export since TargetDetail fetches by id rather than iterating the
 * full list. */
export async function fetchTargetDetail(targetId: number): Promise<Target> {
  const targetsList = await apiGet<ApiTarget[]>('/targets/')
  const t = targetsList.find(x => x.id === targetId)
  if (!t) throw new Error(`Target id ${targetId} not found`)
  const target = await buildTarget(t)
  target.whyThisTarget = await buildWhyThisTarget(targetId)
  return target
}
