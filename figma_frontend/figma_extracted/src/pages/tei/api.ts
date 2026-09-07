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
  ContraType, GapType, EvidenceLevel, Momentum, MomentumTrend,
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

/* Real snake_case gap_type -> the mock's existing display label. All 5 real
   values have a 1:1 mock counterpart already — no extension needed here. */
const GAP_TYPE_LABELS: Record<string, GapType> = {
  mechanistic: 'Mechanistic Gap',
  population: 'Population Gap',
  modality: 'Modality Gap',
  validation: 'Validation Gap',
  evidence_consistency: 'Evidence-Consistency Gap',
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

/* Real dimension_breakdown key -> the mock's existing 4 dimension labels/order. */
const DIMENSION_ORDER: { key: string; label: string }[] = [
  { key: 'genetic', label: 'Genetic' },
  { key: 'literature', label: 'Literature' },
  { key: 'pathway', label: 'Pathway' },
  { key: 'human_clinical', label: 'Human / Clinical' },
]

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
}

interface ApiGapAnalysis {
  gaps: ApiGap[]
  investigation_coverage: string
  dimensions_not_explored: string[]
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
        label, score: 0, level: 'Limited' as EvidenceLevel,
        notes: count > 0
          ? `${count} real evidence record(s) in this dimension, but none carry a computed score yet.`
          : 'No real evidence ingested for this dimension.',
      }
    }
    return {
      label,
      score: Math.round(raw * 100),
      level: scoreToLevel(raw),
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
    }
  })
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
    rationale: g.rationale || '',
    suggestion: g.investigation_suggestion || '',
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

  return {
    id: t.id,
    gene: t.gene_symbol,
    fullName: GENE_FULL_NAMES[t.gene_symbol] || t.gene_symbol,
    priorityScore: score ? Math.round((score.priority_score ?? 0) * 100) : 0,
    dimensions: score
      ? buildDimensions(score.dimension_breakdown, evidenceCounts)
      : DIMENSION_ORDER.map(({ label }) => ({
          label, score: 0, level: 'Limited' as EvidenceLevel, notes: 'Not yet scored — click "Run Full Analysis" above.',
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
 * TargetDetail. Identical GET-only reads; kept as a separate named export
 * since TargetDetail fetches by id rather than iterating the full list. */
export async function fetchTargetDetail(targetId: number): Promise<Target> {
  const targetsList = await apiGet<ApiTarget[]>('/targets/')
  const t = targetsList.find(x => x.id === targetId)
  if (!t) throw new Error(`Target id ${targetId} not found`)
  return buildTarget(t)
}
