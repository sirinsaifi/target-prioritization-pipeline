import { useState, useMemo } from 'react'
import type { Target } from './data'

/* ── Score → sequential-blue color (from palette.md ramp) ── */
function scoreColor(n: number): { fill: string; text: string } {
  if (n >= 85) return { fill: '#1c5cab', text: '#1c5cab' }
  if (n >= 70) return { fill: '#256abf', text: '#256abf' }
  if (n >= 55) return { fill: '#3987e5', text: '#3987e5' }
  if (n >= 40) return { fill: '#5598e7', text: '#5598e7' }
  return        { fill: '#86b6ef', text: '#2a78d6' }
}

function levelBadge(level: string) {
  if (level === 'Strong')   return { bg: 'var(--status-good-bg)',    color: '#065f46' }
  if (level === 'Moderate') return { bg: 'var(--status-warn-bg)',    color: '#92400e' }
  return                           { bg: 'var(--status-neutral-bg)', color: '#374151' }
}

function ScoreCell({ score }: { score: number }) {
  const { fill, text } = scoreColor(score)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
      <div style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 700, fontSize: 13.5, color: text, minWidth: 26, textAlign: 'right' }}>
        {score}
      </div>
      <div className="score-bar-track">
        <div className="score-bar-fill" style={{ width: `${score}%`, background: fill }} />
      </div>
    </div>
  )
}

type SortKey = 'priorityScore' | 'gene' | 'genetic' | 'literature' | 'pathway' | 'human'
type SortDir = 'asc' | 'desc'

interface Props { targets: Target[]; onSelectTarget: (t: Target) => void }

export default function TargetList({ targets, onSelectTarget }: Props) {
  const [query,   setQuery]   = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('priorityScore')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const sortedFiltered = useMemo(() => {
    const q = query.toLowerCase()
    const filtered = targets.filter(t =>
      t.gene.toLowerCase().includes(q) ||
      t.fullName.toLowerCase().includes(q)
    )
    return [...filtered].sort((a, b) => {
      let va = 0, vb = 0
      if (sortKey === 'gene') {
        return sortDir === 'asc' ? a.gene.localeCompare(b.gene) : b.gene.localeCompare(a.gene)
      }
      if (sortKey === 'priorityScore') { va = a.priorityScore; vb = b.priorityScore }
      else if (sortKey === 'genetic')   { va = a.dimensions[0].score; vb = b.dimensions[0].score }
      else if (sortKey === 'literature'){ va = a.dimensions[1].score; vb = b.dimensions[1].score }
      else if (sortKey === 'pathway')   { va = a.dimensions[2].score; vb = b.dimensions[2].score }
      else if (sortKey === 'human')     { va = a.dimensions[3].score; vb = b.dimensions[3].score }
      return sortDir === 'asc' ? va - vb : vb - va
    })
  }, [targets, query, sortKey, sortDir])

  function handleSort(key: SortKey) {
    if (key === sortKey) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('desc') }
  }

  function SortBtn({ k, label }: { k: SortKey; label: string }) {
    const active = sortKey === k
    return (
      <button className="sort-btn" onClick={() => handleSort(k)} style={{ color: active ? 'var(--ink-1)' : undefined }}>
        {label}
        <span style={{ color: active ? 'var(--seq-450)' : 'var(--ink-3)', fontSize: 10 }}>
          {active ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ' ↕'}
        </span>
      </button>
    )
  }

  return (
    <div style={{ maxWidth: 1100 }}>
      {/* Page header */}
      <div style={{ marginBottom: 22 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: 'var(--ink-1)', margin: '0 0 4px', letterSpacing: '-0.02em' }}>
          Candidate Targets
        </h1>
        <p style={{ fontSize: 13.5, color: 'var(--ink-2)', margin: 0 }}>
          {targets.length} targets evaluated for current disease indication. Click a row to open Target Detail.
        </p>
      </div>

      {/* Search + filter bar */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 18 }}>
        <div style={{ position: 'relative', flex: 1, maxWidth: 360 }}>
          <svg
            width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="var(--ink-3)" strokeWidth="1.4"
            style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }}
          >
            <circle cx="6" cy="6" r="4.5" />
            <path d="M10 10l2.5 2.5" strokeLinecap="round" />
          </svg>
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search gene symbol or name…"
            style={{
              width: '100%',
              padding: '8px 12px 8px 34px',
              borderRadius: 7,
              border: '1px solid var(--border)',
              background: 'var(--surface)',
              fontSize: 13,
              color: 'var(--ink-1)',
              outline: 'none',
              fontFamily: 'inherit',
            }}
            onFocus={e  => { (e.target as HTMLInputElement).style.borderColor = 'var(--seq-400)'; (e.target as HTMLInputElement).style.boxShadow = '0 0 0 3px rgba(57,135,229,0.12)' }}
            onBlur={e   => { (e.target as HTMLInputElement).style.borderColor = 'var(--border)';  (e.target as HTMLInputElement).style.boxShadow = 'none' }}
          />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>
            {sortedFiltered.length} result{sortedFiltered.length !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      {/* Table */}
      <div className="surface" style={{ overflow: 'hidden', borderRadius: 12 }}>
        {/* Table header */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: '140px 160px 1fr 1fr 1fr 1fr 80px',
          padding: '10px 20px',
          background: 'var(--page-bg)',
          borderBottom: '1px solid var(--border)',
          gap: 12,
          alignItems: 'center',
        }}>
          <SortBtn k="gene"          label="Gene" />
          <SortBtn k="priorityScore" label="Priority Score" />
          <SortBtn k="genetic"       label="Genetic" />
          <SortBtn k="literature"    label="Literature" />
          <SortBtn k="pathway"       label="Pathway" />
          <SortBtn k="human"         label="Human/Clinical" />
          <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
            Flags
          </span>
        </div>

        {/* Rows */}
        {sortedFiltered.map((t, i) => (
          <div
            key={t.gene}
            className="tbl-row"
            onClick={() => onSelectTarget(t)}
            style={{
              display: 'grid',
              gridTemplateColumns: '140px 160px 1fr 1fr 1fr 1fr 80px',
              padding: '14px 20px',
              gap: 12,
              alignItems: 'center',
              background: i % 2 === 0 ? 'var(--surface)' : '#fcfcfc',
            }}
          >
            {/* Gene */}
            <div>
              <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--seq-550)', letterSpacing: '-0.01em' }}>{t.gene}</div>
              <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 1, lineHeight: 1.35, maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.fullName}</div>
            </div>

            {/* Priority */}
            <ScoreCell score={t.priorityScore} />

            {/* Dimensions */}
            {t.dimensions.map(d => {
              const { bg, color } = levelBadge(d.level)
              return (
                <div key={d.label} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <div style={{ fontVariantNumeric: 'tabular-nums', fontSize: 13, fontWeight: 600, color: 'var(--ink-1)' }}>
                    {d.score}
                  </div>
                  <span className="badge" style={{ background: bg, color, fontSize: 10, padding: '1px 7px', width: 'fit-content' }}>
                    {d.level}
                  </span>
                </div>
              )
            })}

            {/* Flags */}
            <div style={{ display: 'flex', gap: 6 }}>
              {t.hasContradictions && (
                <span title="Contradictions detected" style={{
                  width: 22, height: 22, borderRadius: 5,
                  background: 'var(--status-crit-bg)', color: 'var(--status-crit)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 12, fontWeight: 700,
                }}>
                  ⚡
                </span>
              )}
              {t.hasGaps && (
                <span title="Research gaps detected" style={{
                  width: 22, height: 22, borderRadius: 5,
                  background: 'var(--status-warn-bg)', color: 'var(--status-warn)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 12,
                }}>
                  ◎
                </span>
              )}
              {!t.hasContradictions && !t.hasGaps && (
                <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>—</span>
              )}
            </div>
          </div>
        ))}

        {sortedFiltered.length === 0 && (
          <div style={{ padding: '48px 24px', textAlign: 'center', color: 'var(--ink-3)', fontSize: 13 }}>
            No targets match "{query}"
          </div>
        )}
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 20, marginTop: 14, alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <span style={{ fontSize: 11.5, color: 'var(--ink-3)', fontWeight: 500 }}>Evidence level:</span>
          {[
            { label: 'Strong',   ...levelBadge('Strong') },
            { label: 'Moderate', ...levelBadge('Moderate') },
            { label: 'Limited',  ...levelBadge('Limited') },
          ].map(({ label, bg, color }) => (
            <span key={label} className="badge" style={{ background: bg, color, fontSize: 11 }}>{label}</span>
          ))}
        </div>
        <div style={{ width: 1, height: 14, background: 'var(--border)' }} />
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11.5, color: 'var(--ink-3)' }}>
            <span style={{ fontSize: 12, color: 'var(--status-crit)' }}>⚡</span> Contradictions
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11.5, color: 'var(--ink-3)' }}>
            <span style={{ fontSize: 12, color: 'var(--status-warn)' }}>◎</span> Research gaps
          </span>
        </div>
      </div>

      {/* Honest-uncertainty footnote — real backend behavior, not just
          documented in project docs (see docs/07 Phase 10 follow-up). */}
      <p style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 10, lineHeight: 1.5, maxWidth: 720 }}>
        Contradiction and gap flags show each target's most recently checked/computed results (including any
        literature-based contradictions already found) — they are read-only here and are not automatically
        re-checked on every visit. If a target hasn't been checked yet, its flags read as "none" rather than
        re-running the check silently.
      </p>
    </div>
  )
}
