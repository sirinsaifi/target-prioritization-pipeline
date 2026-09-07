import { useState, useEffect } from 'react'
import type { Target, DimensionScore, Contradiction, ResearchGap, EvidenceItem, ContraType, GapType, Momentum, MomentumTrend } from './data'
import { fetchTargetDetail, runFullAnalysis } from './api'

/* ─── Mini helpers ─────────────────────────────────────────────────────────── */

function scoreColor(n: number) {
  if (n >= 85) return '#1c5cab'
  if (n >= 70) return '#256abf'
  if (n >= 55) return '#3987e5'
  if (n >= 40) return '#5598e7'
  return '#86b6ef'
}

function levelChip(level: string) {
  if (level === 'Strong')   return { bg: 'var(--status-good-bg)',    color: '#065f46' }
  if (level === 'Moderate') return { bg: 'var(--status-warn-bg)',    color: '#92400e' }
  return                           { bg: 'var(--status-neutral-bg)', color: '#374151' }
}

function contraStyle(type: ContraType) {
  switch (type) {
    case 'Direct Contradiction':       return { bg: 'var(--contra-direct-bg)',  color: 'var(--contra-direct)',  dot: '#dc2626' }
    case 'Population Heterogeneity':   return { bg: 'var(--contra-pop-bg)',     color: 'var(--contra-pop)',     dot: '#d97706' }
    case 'Methodological Disagreement':return { bg: 'var(--contra-method-bg)',  color: 'var(--contra-method)', dot: '#2563eb' }
    // Real value from Phase 7 (LLM-proposed, deterministically verified) —
    // reuses the "direct" styling since a confirmed literature
    // contradiction is full-severity, same tier as a structured direct
    // contradiction (see config.CONTRADICTION_SEVERITY_WEIGHTS).
    case 'Literature Contradiction':   return { bg: 'var(--contra-direct-bg)',  color: 'var(--contra-direct)',  dot: '#7c3aed' }
    default:                           return { bg: 'var(--contra-unclass-bg)', color: 'var(--contra-unclass)', dot: '#6b7280' }
  }
}

function gapStyle(type: GapType) {
  switch (type) {
    case 'Validation Gap':          return { bg: 'var(--gap-validation-bg)', color: 'var(--gap-validation)' }
    case 'Population Gap':          return { bg: 'var(--gap-population-bg)', color: 'var(--gap-population)' }
    case 'Modality Gap':            return { bg: 'var(--gap-modality-bg)',   color: 'var(--gap-modality)'   }
    case 'Mechanistic Gap':         return { bg: 'var(--gap-mechanistic-bg)',color: 'var(--gap-mechanistic)' }
    case 'Evidence-Consistency Gap':return { bg: 'var(--gap-consistency-bg)',color: 'var(--gap-consistency)' }
  }
}

function priorityLabel(score: number) {
  if (score >= 85) return 'High priority'
  if (score >= 65) return 'Moderate-high priority'
  if (score >= 45) return 'Moderate priority'
  return 'Lower priority'
}

/* ─── Evidence Momentum — real trend from real, timestamped evidence
   (see app/core/scoring/evidence_momentum.py). Purely informational: NOT
   a quality/priority signal — a declining trend does not mean weaker
   evidence, it might mean the question is settled (see that module's own
   docstring). Never described here as good/bad, only as a real trend. ── */

function momentumStyle(trend: MomentumTrend) {
  switch (trend) {
    case 'accelerating': return { color: '#059669', bg: '#ecfdf5', icon: '↗', label: 'Accelerating' }
    case 'emerging':     return { color: '#7c3aed', bg: '#f5f3ff', icon: '✦', label: 'Emerging' }
    case 'stable':       return { color: '#2563eb', bg: '#eff6ff', icon: '→', label: 'Stable' }
    case 'declining':    return { color: '#d97706', bg: '#fffbeb', icon: '↘', label: 'Declining' }
    default:             return { color: 'var(--ink-3)', bg: 'var(--status-neutral-bg)', icon: '—', label: 'Not enough data yet' }
  }
}

function MomentumChart({ momentum, gene }: { momentum: Momentum; gene: string }) {
  const s = momentumStyle(momentum.trend)

  if (momentum.trend === 'insufficient_data' || momentum.yearlyCounts.length === 0) {
    return (
      <div className="surface" style={{ padding: '18px 22px', marginBottom: 20 }}>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-3)', marginBottom: 6 }}>
          Evidence Momentum
        </div>
        <p style={{ margin: 0, fontSize: 12.5, color: 'var(--ink-3)' }}>
          Not enough real, dated evidence for {gene} yet to compute a trend.
        </p>
      </div>
    )
  }

  // Real history can span 20+ years for a well-studied gene (e.g. real
  // SOD1 data goes back to 1999) — showing all of it as bars makes the
  // chart illegible rather than "a line going up tells a story instantly".
  // Display-only slice to the most recent years; the real full history
  // (and the real momentum_score/trend, both computed from ALL of it, not
  // just this slice) remains available via the API regardless.
  const displayedYears = momentum.yearlyCounts.slice(-8)
  const maxCount = Math.max(...displayedYears.map(y => y.count), 1)
  const barAreaHeight = 80

  return (
    <div className="surface" style={{ padding: '18px 22px', marginBottom: 20 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-3)', marginBottom: 4 }}>
            Evidence Momentum
          </div>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--ink-3)' }}>
            Real publication/study-year counts — a factual trend, not an evidence-quality signal.
          </p>
        </div>
        <span
          className="badge"
          style={{ background: s.bg, color: s.color, fontSize: 12, flexShrink: 0, whiteSpace: 'nowrap' }}
        >
          {s.icon} {s.label}
          {momentum.momentumScore !== null && ` · ${momentum.momentumScore.toFixed(1)}x`}
        </span>
      </div>

      {/* Bar chart — plain inline SVG, no charting library */}
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, height: barAreaHeight + 24, paddingTop: 8 }}>
        {displayedYears.map(({ year, count }) => {
          const h = Math.max((count / maxCount) * barAreaHeight, count > 0 ? 3 : 0)
          return (
            <div key={year} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--ink-2)', marginBottom: 3 }}>{count}</div>
              <div style={{
                width: '100%', maxWidth: 34, height: h,
                background: s.color, borderRadius: '3px 3px 0 0',
                opacity: 0.85,
              }} />
              <div style={{ fontSize: 10.5, color: 'var(--ink-3)', marginTop: 5 }}>{year}</div>
            </div>
          )
        })}
      </div>

      <p style={{ margin: '12px 0 0', fontSize: 11.5, color: 'var(--ink-3)' }}>
        {momentum.priorWindowCount} record{momentum.priorWindowCount === 1 ? '' : 's'} in the prior 2-year window →{' '}
        {momentum.recentWindowCount} record{momentum.recentWindowCount === 1 ? '' : 's'} in the most recent 2-year window.
      </p>
      {displayedYears.length > 0 && Number(displayedYears[displayedYears.length - 1].year) === new Date().getFullYear() && (
        <p style={{ margin: '4px 0 0', fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic' }}>
          Note: {displayedYears[displayedYears.length - 1].year} is still in progress — its real count so far is
          naturally lower than a completed year's, which can make a genuinely accelerating trend read as merely
          "stable" until the year is complete.
        </p>
      )}
    </div>
  )
}

/* ─── Dimension score arc (SVG mini gauge) ─────────────────────────────────── */

function DimGauge({ score }: { score: number }) {
  const r = 22
  const cx = 26, cy = 26
  const circ = 2 * Math.PI * r
  const arc  = circ * 0.75  // 270° sweep
  const fill = arc * (score / 100)
  const dash = `${fill} ${circ - fill}`
  const color = scoreColor(score)

  return (
    <svg width="52" height="52" viewBox="0 0 52 52" className="dim-score-ring">
      {/* Track */}
      <circle
        cx={cx} cy={cy} r={r}
        fill="none" stroke="#e9ecf3" strokeWidth="5"
        strokeDasharray={`${arc} ${circ - arc}`}
        strokeDashoffset={circ * 0.125}
        strokeLinecap="round"
        transform={`rotate(135 ${cx} ${cy})`}
      />
      {/* Fill */}
      <circle
        cx={cx} cy={cy} r={r}
        fill="none" stroke={color} strokeWidth="5"
        strokeDasharray={dash}
        strokeDashoffset={circ * 0.125}
        strokeLinecap="round"
        transform={`rotate(135 ${cx} ${cy})`}
      />
      <text x={cx} y={cy + 1} textAnchor="middle" dominantBaseline="middle" fontSize="12" fontWeight="700" fill={color} fontFamily="Inter, sans-serif">
        {score}
      </text>
    </svg>
  )
}

/* ─── Dimension card ───────────────────────────────────────────────────────── */

function DimCard({ d }: { d: DimensionScore }) {
  const { bg, color } = levelChip(d.level)
  return (
    <div className="dim-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-3)', marginBottom: 4 }}>
            {d.label}
          </div>
          <span className="badge" style={{ background: bg, color, fontSize: 11 }}>{d.level}</span>
        </div>
        <DimGauge score={d.score} />
      </div>
      <p style={{ margin: 0, fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.6 }}>{d.notes}</p>
    </div>
  )
}

/* ─── Evidence tab ─────────────────────────────────────────────────────────── */

function EvidenceTab({ items }: { items: EvidenceItem[] }) {
  if (items.length === 0) {
    return (
      <div style={{ padding: '48px 0', textAlign: 'center', color: 'var(--ink-3)', fontSize: 13 }}>
        No individual evidence records indexed for this target yet.
      </div>
    )
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {items.map(item => (
        <div key={item.id} className="ev-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 5, flexWrap: 'wrap' }}>
                <code style={{ fontSize: 11, color: 'var(--seq-550)', fontFamily: 'monospace', background: '#eff6ff', padding: '2px 6px', borderRadius: 4 }}>
                  {item.id}
                </code>
                <span className="tag" style={{ background: '#f1f5f9', color: 'var(--ink-2)', border: '1px solid var(--border)' }}>
                  {item.dimension}
                </span>
                {item.directionOnTrait && (
                  <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{item.directionOnTrait}</span>
                )}
              </div>
              <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
                <div style={{ fontSize: 12 }}>
                  <span style={{ color: 'var(--ink-3)', marginRight: 4 }}>Evidence score:</span>
                  <span style={{ color: 'var(--ink-1)', fontWeight: 500 }}>
                    {item.evidenceScore !== null ? item.evidenceScore.toFixed(2) : '—'}
                  </span>
                </div>
                {item.detail && (
                  <div style={{ fontSize: 12 }}>
                    <span style={{ color: 'var(--ink-1)', fontWeight: 500 }}>{item.detail}</span>
                  </div>
                )}
              </div>
            </div>
            <div style={{ flexShrink: 0, fontSize: 11, color: 'var(--seq-450)', fontWeight: 600 }}>
              {item.source}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

/* ─── Contradictions tab ───────────────────────────────────────────────────── */

function ContraCard({ c }: { c: Contradiction }) {
  const [expanded, setExpanded] = useState(false)
  const { bg, color, dot } = contraStyle(c.type)

  return (
    <div className="ev-card" style={{ borderLeft: `3px solid ${dot}` }}>
      {/* Classification badge + summary */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 12, flexWrap: 'wrap' }}>
        <span className="badge" style={{ background: bg, color }}>
          {c.type}
        </span>
      </div>
      <p style={{ margin: '0 0 14px', fontSize: 13, color: 'var(--ink-1)', lineHeight: 1.55, fontStyle: 'italic' }}>
        {c.summary}
      </p>

      {/* Source pair — the real EvidenceRecord each side of the contradiction
          points to (joined client-side against GET /evidence/target/{id}),
          shown by its real fields. No stored "finding" sentence exists for
          either record, so none is shown (see docs/07 Phase 10). */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 12 }}>
        {[c.sourceA, c.sourceB].map((src, i) => (
          <div key={i} className="src-block">
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 5 }}>
              <code style={{ fontSize: 10.5, color: 'var(--seq-550)', fontFamily: 'monospace', background: '#eff6ff', padding: '1px 5px', borderRadius: 3 }}>
                {src.id}
              </code>
              <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>{src.dataSource}</span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--ink-2)', fontWeight: 500, marginBottom: 4, lineHeight: 1.35 }}>{src.dimension}</div>
            {src.directionOnTrait && (
              <div style={{ fontSize: 12, color: 'var(--ink-1)', lineHeight: 1.5 }}>Direction on trait: {src.directionOnTrait}</div>
            )}
          </div>
        ))}
      </div>

      {/* Expand / collapse */}
      <button className="expand-toggle" onClick={() => setExpanded(e => !e)}>
        {expanded ? '▾ Hide field comparison' : '▸ Show matched and mismatched fields'}
      </button>

      {expanded && (
        <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <div style={{ background: 'var(--status-good-bg)', borderRadius: 6, padding: '10px 12px' }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#065f46', marginBottom: 6, letterSpacing: '0.04em', textTransform: 'uppercase' }}>
              ✓ Matched fields
            </div>
            <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 3 }}>
              {c.matchedFields.map(f => (
                <li key={f} style={{ fontSize: 12, color: '#064e3b', display: 'flex', gap: 6, alignItems: 'center' }}>
                  <span style={{ color: '#059669' }}>·</span> {f}
                </li>
              ))}
            </ul>
          </div>
          <div style={{ background: 'var(--status-crit-bg)', borderRadius: 6, padding: '10px 12px' }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#991b1b', marginBottom: 6, letterSpacing: '0.04em', textTransform: 'uppercase' }}>
              ✕ Mismatched fields
            </div>
            <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 3 }}>
              {c.mismatchedFields.map(f => (
                <li key={f} style={{ fontSize: 12, color: '#7f1d1d', display: 'flex', gap: 6, alignItems: 'center' }}>
                  <span style={{ color: '#dc2626' }}>·</span> {f}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  )
}

function ContradictionsTab({ items, checked }: { items: Contradiction[]; checked: boolean }) {
  if (items.length === 0) {
    if (!checked) {
      // Real, honest "never run" state (see data.ts's contradictionsChecked)
      // — distinct from "checked, none found" below. Do not collapse these.
      return (
        <div style={{ padding: '48px 0', textAlign: 'center' }}>
          <div style={{ fontSize: 13, color: 'var(--ink-3)', marginBottom: 4 }}>Contradictions have not been checked yet for this target.</div>
          <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>Click "Run Full Analysis" above to check.</div>
        </div>
      )
    }
    return (
      <div style={{ padding: '48px 0', textAlign: 'center' }}>
        <div style={{ fontSize: 13, color: 'var(--ink-3)', marginBottom: 4 }}>No contradictions detected for this target.</div>
        <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>Evidence records are internally consistent.</div>
      </div>
    )
  }
  return (
    <div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        {([
          'Direct Contradiction', 'Population Heterogeneity', 'Methodological Disagreement',
          'Literature Contradiction', 'Not Comparable (Cross-Type)', 'Unclassified',
        ] as ContraType[]).map(type => {
          const s = contraStyle(type)
          const count = items.filter(c => c.type === type).length
          if (!count) return null
          return (
            <span key={type} className="badge" style={{ background: s.bg, color: s.color }}>
              {type} · {count}
            </span>
          )
        })}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {items.map(c => <ContraCard key={c.id} c={c} />)}
      </div>
    </div>
  )
}

/* ─── Research Gaps tab ────────────────────────────────────────────────────── */

function GapCard({ g }: { g: ResearchGap }) {
  const { bg, color } = gapStyle(g.type)
  return (
    <div className="ev-card">
      <div style={{ marginBottom: 8 }}>
        <span className="tag" style={{ background: bg, color, border: '1px solid transparent' }}>
          {g.type}
        </span>
      </div>
      <p style={{ margin: '0 0 12px', fontSize: 13, color: 'var(--ink-1)', lineHeight: 1.6 }}>
        {g.rationale}
      </p>
      <div className="suggestion-box">
        <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: '#3b82f6', marginBottom: 5 }}>
          Suggested next step
        </div>
        <div style={{ fontSize: 12.5, lineHeight: 1.6 }}>{g.suggestion}</div>
      </div>
    </div>
  )
}

function GapsTab({ items, checked }: { items: ResearchGap[]; checked: boolean }) {
  if (items.length === 0) {
    if (!checked) {
      // Real, honest "never run" state (see data.ts's gapsChecked) —
      // distinct from "checked, genuinely zero gaps" (e.g. SOD1) below.
      return (
        <div style={{ padding: '48px 0', textAlign: 'center' }}>
          <div style={{ fontSize: 13, color: 'var(--ink-3)', marginBottom: 4 }}>Gap analysis has not been run yet for this target.</div>
          <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>Click "Run Full Analysis" above to check.</div>
        </div>
      )
    }
    return (
      <div style={{ padding: '48px 0', textAlign: 'center', color: 'var(--ink-3)', fontSize: 13 }}>
        No research gaps identified for this target.
      </div>
    )
  }
  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        {(['Validation Gap', 'Population Gap', 'Modality Gap', 'Mechanistic Gap', 'Evidence-Consistency Gap'] as GapType[]).map(type => {
          const s = gapStyle(type)
          const count = items.filter(g => g.type === type).length
          if (!count) return null
          return (
            <span key={type} className="tag" style={{ background: s.bg, color: s.color, border: '1px solid transparent' }}>
              {type} · {count}
            </span>
          )
        })}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {items.map(g => <GapCard key={g.id} g={g} />)}
      </div>
    </div>
  )
}

/* ─── Main TargetDetail ────────────────────────────────────────────────────── */

type TabId = 'evidence' | 'contradictions' | 'gaps'

interface Props {
  targetId: number
  initial: Target   // the summary already fetched by TargetList — rendered immediately; re-fetched below to reflect the latest persisted state (real GET reads only, no recomputation — see api.ts)
  onBack: () => void
}

export default function TargetDetail({ targetId, initial, onBack }: Props) {
  const [tab, setTab] = useState<TabId>('evidence')
  const [t, setT] = useState<Target>(initial)
  const [refreshing, setRefreshing] = useState(true)
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisError, setAnalysisError] = useState<string | null>(null)
  const [literatureWarning, setLiteratureWarning] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setT(initial)
    setRefreshing(true)
    setAnalysisError(null)
    setLiteratureWarning(null)
    // Real GET-only re-read (no recomputation) — refreshes in case the
    // persisted data changed since TargetList's own fetch (e.g. someone
    // else ran POST .../run in the meantime). No LLM call happens here.
    fetchTargetDetail(targetId)
      .then(full => { if (!cancelled) { setT(full); setRefreshing(false) } })
      .catch(() => { if (!cancelled) setRefreshing(false) })  // real failure (e.g. backend unreachable) — keep showing the already-loaded summary rather than an error
    return () => { cancelled = true }
  }, [targetId])

  // The one place this page calls POST — see api.ts's runFullAnalysis()
  // docstring for the real call order and why it differs from how the
  // 4 stages were first requested.
  async function handleRunAnalysis() {
    if (analyzing) return
    setAnalyzing(true)
    setAnalysisError(null)
    setLiteratureWarning(null)
    try {
      const { literatureCheckError } = await runFullAnalysis(targetId)
      if (literatureCheckError) setLiteratureWarning(literatureCheckError)
      const full = await fetchTargetDetail(targetId)
      setT(full)
    } catch (err) {
      // A failure in contradictions/scoring/gaps (not the literature step,
      // which is handled separately above) is a real problem — e.g. the
      // backend went down mid-run. Shown honestly rather than silently
      // discarded; whatever structured results DID get persisted before
      // the failure remain visible after the re-fetch below already ran
      // (or, if the very first call failed, the previously-displayed data
      // stays as-is).
      setAnalysisError(err instanceof Error ? err.message : String(err))
    } finally {
      setAnalyzing(false)
    }
  }

  const sc = scoreColor(t.priorityScore)

  // One-line summary for the header
  const summaryParts: string[] = []
  const geneticLevel = t.dimensions[0].level
  const humanLevel   = t.dimensions[3].level
  if (geneticLevel === 'Strong') summaryParts.push('strong genetic evidence')
  else if (geneticLevel === 'Moderate') summaryParts.push('moderate genetic evidence')
  else summaryParts.push('limited genetic evidence')
  if (humanLevel === 'Strong') summaryParts.push('robust human validation')
  else if (humanLevel === 'Moderate') summaryParts.push('partial human validation')
  else summaryParts.push('limited human validation')
  if (t.hasContradictions) summaryParts.push(`${t.contradictions.length} evidence conflict${t.contradictions.length > 1 ? 's' : ''} detected`)

  const tagLine = `${priorityLabel(t.priorityScore)} — ${summaryParts.join(', ')}.`

  return (
    <div style={{ maxWidth: 1000 }}>
      {/* ── Header ───────────────────────────────────────────────────── */}
      <div className="surface" style={{ padding: '24px 28px', marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 24 }}>
          {/* Score callout */}
          <div style={{ textAlign: 'center', flexShrink: 0 }}>
            <div style={{
              width: 72, height: 72,
              borderRadius: 14,
              background: `${sc}14`,
              border: `2px solid ${sc}30`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexDirection: 'column',
            }}>
              <div style={{ fontSize: t.scoreComputed ? 26 : 20, fontWeight: 800, color: t.scoreComputed ? sc : 'var(--ink-3)', lineHeight: 1, letterSpacing: '-0.03em' }}>
                {t.scoreComputed ? t.priorityScore : '—'}
              </div>
              <div style={{ fontSize: 9, fontWeight: 600, color: t.scoreComputed ? sc : 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginTop: 2 }}>
                {t.scoreComputed ? 'Score' : 'Not analyzed'}
              </div>
            </div>
          </div>

          {/* Gene info */}
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 4 }}>
              <h1 style={{ fontSize: 24, fontWeight: 800, color: 'var(--ink-1)', margin: 0, letterSpacing: '-0.03em' }}>
                {t.gene}
              </h1>
              <span style={{ fontSize: 14, color: 'var(--ink-3)', fontWeight: 400 }}>{t.fullName}</span>
              {refreshing && (
                <span style={{ fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic' }}>
                  Refreshing…
                </span>
              )}
            </div>
            <p style={{ margin: '0 0 14px', fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.5 }}>
              {t.scoreComputed ? tagLine : 'Not yet analyzed — click "Run Full Analysis" to compute a priority score, check for contradictions, and identify research gaps.'}
            </p>
            {/* Flag badges */}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {!t.scoreComputed && (
                <span className="badge" style={{ background: 'var(--status-neutral-bg)', color: '#374151' }}>
                  Not yet analyzed
                </span>
              )}
              {t.hasContradictions && (
                <span className="badge" style={{ background: 'var(--contra-direct-bg)', color: 'var(--contra-direct)' }}>
                  ⚡ {t.contradictions.length} Contradiction{t.contradictions.length > 1 ? 's' : ''}
                </span>
              )}
              {t.hasGaps && (
                <span className="badge" style={{ background: 'var(--status-warn-bg)', color: '#92400e' }}>
                  ◎ {t.gaps.length} Research Gap{t.gaps.length > 1 ? 's' : ''}
                </span>
              )}
              {t.evidenceItems.length > 0 && (
                <span className="badge" style={{ background: '#eff6ff', color: 'var(--seq-550)' }}>
                  {t.evidenceItems.length} Evidence Records
                </span>
              )}
            </div>
          </div>

          {/* Run Full Analysis — the one button in this app that triggers
              real compute (POST endpoints); everything else on this page
              is a read-only display of already-persisted results. */}
          <div style={{ flexShrink: 0 }}>
            <button
              onClick={handleRunAnalysis}
              disabled={analyzing}
              style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '10px 18px',
                borderRadius: 8,
                border: 'none',
                background: analyzing ? 'var(--seq-250)' : 'var(--seq-550)',
                color: 'white',
                fontSize: 13, fontWeight: 600,
                cursor: analyzing ? 'not-allowed' : 'pointer',
                whiteSpace: 'nowrap',
              }}
            >
              {analyzing && (
                <span style={{
                  width: 12, height: 12, borderRadius: '50%',
                  border: '2px solid rgba(255,255,255,0.4)',
                  borderTopColor: 'white',
                  display: 'inline-block',
                  animation: 'spin 0.7s linear infinite',
                }} />
              )}
              {analyzing ? 'Running Analysis…' : 'Run Full Analysis'}
            </button>
            <p style={{ margin: '6px 0 0', fontSize: 10.5, color: 'var(--ink-3)', maxWidth: 150, lineHeight: 1.4, textAlign: 'right' }}>
              Recomputes score, contradictions (incl. literature), and gaps for {t.gene}.
            </p>
          </div>
        </div>

        {literatureWarning && (
          <div style={{ marginTop: 16, padding: '10px 14px', borderRadius: 7, background: 'var(--status-warn-bg)', color: '#92400e', fontSize: 12.5, lineHeight: 1.5 }}>
            Structured-evidence analysis (contradictions, scoring, gaps) completed successfully, but the literature
            contradiction check (real LLM call) failed: <strong>{literatureWarning}</strong>. The results below reflect
            everything that DID succeed.
          </div>
        )}
        {analysisError && (
          <div style={{ marginTop: 16, padding: '10px 14px', borderRadius: 7, background: 'var(--status-crit-bg)', color: 'var(--status-crit)', fontSize: 12.5, lineHeight: 1.5 }}>
            Analysis failed: <strong>{analysisError}</strong>
          </div>
        )}
      </div>

      {/* ── Evidence Momentum ────────────────────────────────────────── */}
      <MomentumChart momentum={t.momentum} gene={t.gene} />

      {/* ── Dimension cards ──────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 14, marginBottom: 24 }}>
        {t.dimensions.map(d => <DimCard key={d.label} d={d} />)}
      </div>

      {/* ── Tabs ─────────────────────────────────────────────────────── */}
      <div className="surface" style={{ overflow: 'hidden' }}>
        {/* Tab bar */}
        <div style={{
          display: 'flex',
          borderBottom: '1px solid var(--border)',
          padding: '0 20px',
          gap: 4,
        }}>
          {([
            { id: 'evidence',        label: 'Evidence',        count: t.evidenceItems.length    },
            { id: 'contradictions',  label: 'Contradictions',  count: t.contradictions.length   },
            { id: 'gaps',            label: 'Research Gaps',   count: t.gaps.length             },
          ] as { id: TabId; label: string; count: number }[]).map(({ id, label, count }) => (
            <button
              key={id}
              className={`tab-btn${tab === id ? ' active' : ''}`}
              onClick={() => setTab(id)}
            >
              {label}
              {count > 0 && (
                <span style={{
                  marginLeft: 5, fontSize: 10, fontWeight: 700,
                  padding: '1px 6px', borderRadius: 99,
                  background: tab === id ? 'var(--seq-550)' : 'var(--page-bg)',
                  color: tab === id ? 'white' : 'var(--ink-3)',
                }}>
                  {count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div style={{ padding: '22px 24px' }}>
          {tab === 'evidence'       && <EvidenceTab       items={t.evidenceItems}  />}
          {tab === 'contradictions' && <ContradictionsTab items={t.contradictions} checked={t.contradictionsChecked} />}
          {tab === 'gaps'           && <GapsTab           items={t.gaps}           checked={t.gapsChecked}           />}
        </div>
      </div>
    </div>
  )
}
