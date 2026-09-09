import { useState } from 'react'
import type { Target, ResearchGap } from './data'
import { pickMainGap } from './api'
import { GapCard } from './TargetDetail'

/**
 * Evidence + Risk + Gap Matrix — the new main portfolio view.
 *
 * DESIGN INTENT (this task's own explicit requirement, stated directly):
 * this is meant to be ONE coherent workflow, not a collection of separate
 * screens — see the landscape at a glance (this matrix) -> click any dot
 * -> see the real evidence/risk/gap behind that specific signal (the
 * drawer below) -> for a gap specifically, see the FULL decision-ready
 * explanation (the exact same GapCard component TargetDetail's own
 * Research Gaps tab uses, reused here rather than rebuilt) -> click the
 * target's name to open the full Single-Target Report for deeper
 * investigation. Every step of that workflow is real, already-fetched
 * data — nothing here queries the backend again or invents anything.
 *
 * INSPIRED by Open Targets' own prioritization-matrix interaction pattern
 * (rows=targets, columns=factors, colored dots, click-to-drill-down) —
 * explicitly NOT a visual clone of OTP's real 19-column structural/
 * druggability layout (hasLigand, hasPocket, isInMembrane, etc. — a
 * different project's domain, same scope boundary this whole project has
 * maintained since the safety/genetic-constraint work). The interaction
 * PATTERN is borrowed; the columns and every piece of drill-down content
 * are this project's own real, already-computed signals.
 *
 * COLUMNS (9 total, all from data already fetched by api.ts's
 * buildTarget() — no new backend endpoint):
 *   Evidence:      Genetic, Literature, Clinical, Experimental
 *   Risk/Context:  Safety, Constraint, Essentiality, Paralogues
 *   Gap:           the single most significant open gap (pickMainGap(),
 *                  the SAME function already built for Portfolio
 *                  Comparison's own "Main Gap" column — reused, not
 *                  reimplemented)
 *
 * DOT COLORS reuse ALREADY-ESTABLISHED thresholds, never a new scale:
 * - Evidence columns: DimensionScore.level (Strong/Moderate/Limited),
 *   itself computed via api.ts's existing scoreToLevel() (75/45) — the
 *   SAME threshold already shown on DimCard and the legacy Portfolio
 *   Comparison table. A REAL confirmed contradiction touching that
 *   dimension overrides to red regardless of the score (see
 *   dimensionDotColor() below) — real, live case: NEK1 has one real
 *   confirmed `literature_contradiction`, so its Literature dot is red
 *   even though its real literature dimension score is 0.99 (Strong).
 * - Constraint: the real genetic-constraint evidence_score (already the
 *   project's own linear remap of OTP's -1..+1 factor to 0-1 — see
 *   scripts/ingest_evidence.py's _build_genetic_constraint_fields()),
 *   tiered with the SAME 0.8/0.5 boundary confidenceTier()/priorityTier()
 *   already use elsewhere in this app.
 * - Safety/Essentiality: real caution-flag presence (green=checked
 *   clean, red=real flag present, gray=never checked).
 * - Paralogues: green if no real paralogue crosses this project's own
 *   40% note-worthiness threshold (config.PARALOGUE_MODALITY_NOTE_
 *   IDENTITY_THRESHOLD — see app/core/gaps/gap_taxonomy.py), amber if one
 *   does — NEVER red, since this project has repeatedly documented
 *   paralogues as a genuinely two-sided signal, not a one-directional
 *   risk (see data.ts's own ParalogueInfo docstring).
 * - Gap: green=no gap, amber=an open evidence-completeness gap, red=a
 *   caution-flag-type gap (Safety Signal / Essentiality Risk), gray=gaps
 *   never run for this target.
 */

type EvidenceColumnKey = 'genetic' | 'literature' | 'human_clinical' | 'experimental'
type RiskColumnKey = 'safety' | 'constraint' | 'essentiality' | 'paralogues'
type ColumnKey = EvidenceColumnKey | RiskColumnKey | 'gap'

const EVIDENCE_COLUMNS: { key: EvidenceColumnKey; label: string; dimensionLabel: string }[] = [
  { key: 'genetic', label: 'Genetic', dimensionLabel: 'Genetic' },
  { key: 'literature', label: 'Literature', dimensionLabel: 'Literature' },
  { key: 'human_clinical', label: 'Clinical', dimensionLabel: 'Human / Clinical' },
  { key: 'experimental', label: 'Experimental', dimensionLabel: 'Experimental' },
]

const RISK_COLUMNS: { key: RiskColumnKey; label: string }[] = [
  { key: 'safety', label: 'Safety' },
  { key: 'constraint', label: 'Constraint' },
  { key: 'essentiality', label: 'Essentiality' },
  { key: 'paralogues', label: 'Paralogues' },
]

const PARALOGUE_NOTE_THRESHOLD = 40 // mirrors config.PARALOGUE_MODALITY_NOTE_IDENTITY_THRESHOLD

type DotColor = 'green' | 'amber' | 'red' | 'gray'

const DOT_HEX: Record<DotColor, string> = {
  green: '#22c55e', amber: '#f59e0b', red: '#dc2626', gray: '#d1d5db',
}

function Dot({ color, onClick, title }: { color: DotColor; onClick: () => void; title: string }) {
  return (
    <button
      onClick={onClick}
      title={title}
      style={{
        width: 16, height: 16, borderRadius: '50%', border: 'none', cursor: 'pointer',
        background: DOT_HEX[color], padding: 0, display: 'inline-block',
        boxShadow: color === 'gray' ? 'inset 0 0 0 1px #b8bfc9' : 'none',
      }}
    />
  )
}

/* Real safety-checked proxy — mirrors app/core/narration/agent_narrator.py's
 * build_why_this_target_grounding_data(): the genetic-constraint evidence
 * row (source="ot_genetic_constraint") comes from the SAME real OTP query
 * as safety data, so its presence is the honest signal that "the safety
 * query for this gene was actually run" — zero safety_signal rows alone
 * can't distinguish "checked, clean" from "never checked". */
function safetyChecked(t: Target): boolean {
  return t.evidenceItems.some(e => e.source === 'ot_genetic_constraint')
}

function essentialityRecord(t: Target) {
  return t.evidenceItems.find(e => e.dimension === 'essentiality_risk')
}

function constraintRecord(t: Target) {
  return t.evidenceItems.find(e => e.dimension === 'genetic' && e.source === 'ot_genetic_constraint')
}

function dimensionDotColor(t: Target, col: typeof EVIDENCE_COLUMNS[number]): DotColor {
  const dim = t.dimensions.find(d => d.label === col.dimensionLabel)
  if (!dim || !dim.present) return 'gray'
  const hasContradiction = t.contradictions.some(
    c => c.sourceA.dimension === col.key || c.sourceB.dimension === col.key,
  )
  if (hasContradiction) return 'red'
  if (dim.level === 'Strong') return 'green'
  return 'amber' // Moderate or Limited — real but not strong, never red on score alone
}

function safetyDotColor(t: Target): DotColor {
  if (t.cautionFlags.some(f => f.kind === 'safety_event')) return 'red'
  return safetyChecked(t) ? 'green' : 'gray'
}

function constraintDotColor(t: Target): DotColor {
  const rec = constraintRecord(t)
  if (!rec || rec.evidenceScore === null) return 'gray'
  // Same 0.8/0.5 boundary as consistencyTier()/priorityTier() — see this
  // file's own module docstring for why, not a new scale.
  if (rec.evidenceScore >= 0.8) return 'green'
  if (rec.evidenceScore < 0.5) return 'red'
  return 'amber'
}

function essentialityDotColor(t: Target): DotColor {
  if (t.cautionFlags.some(f => f.kind === 'essentiality')) return 'red'
  return essentialityRecord(t) ? 'green' : 'gray'
}

function paralogueDotColor(t: Target): DotColor {
  if (t.paralogues.length === 0) return t.evidenceItems.length > 0 ? 'green' : 'gray'
  const maxIdentity = Math.max(...t.paralogues.map(p => p.identityPercent))
  return maxIdentity >= PARALOGUE_NOTE_THRESHOLD ? 'amber' : 'green'
}

function gapDotColor(t: Target): DotColor {
  if (!t.gapsChecked) return 'gray'
  const main = pickMainGap(t.gaps)
  if (!main) return 'green'
  if (main.type === 'Safety Signal Gap' || main.type === 'Essentiality Risk Gap') return 'red'
  return 'amber'
}

/* ─── Drawer content, one real, non-fabricated view per column type ────── */

function EvidenceDrawerContent({ t, col, onOpenEvidenceTab }: {
  t: Target; col: typeof EVIDENCE_COLUMNS[number]; onOpenEvidenceTab: () => void
}) {
  const dim = t.dimensions.find(d => d.label === col.dimensionLabel)
  const items = t.evidenceItems.filter(e => e.dimension === col.key)
  const sources = [...new Set(items.map(e => e.source))]
  const relatedContradictions = t.contradictions.filter(
    c => c.sourceA.dimension === col.key || c.sourceB.dimension === col.key,
  )
  return (
    <div>
      <DrawerStat label="Real record count" value={String(items.length)} />
      <DrawerStat label="Real sources" value={sources.length ? sources.join(', ') : 'none'} />
      <DrawerStat label="Dimension score" value={dim && dim.present ? `${dim.score} (${dim.level})` : 'No real evidence ingested'} />
      {relatedContradictions.length > 0 && (
        <div style={{ marginTop: 10, padding: '8px 12px', borderRadius: 7, background: '#fef2f2', color: '#991b1b', fontSize: 12.5 }}>
          <strong>{relatedContradictions.length} real confirmed contradiction(s) in this dimension:</strong>
          <ul style={{ margin: '4px 0 0', paddingLeft: 16 }}>
            {relatedContradictions.map(c => <li key={c.id}>{c.summary}</li>)}
          </ul>
        </div>
      )}
      <button onClick={onOpenEvidenceTab} style={drawerButtonStyle}>
        View full Evidence tab →
      </button>
    </div>
  )
}

function SafetyDrawerContent({ t }: { t: Target }) {
  const events = t.cautionFlags.filter(f => f.kind === 'safety_event')
  if (events.length > 0) {
    return (
      <div>
        {events.map((f, i) => (
          <div key={i} style={{ marginBottom: 8, padding: '8px 12px', borderRadius: 7, background: 'var(--status-crit-bg)', fontSize: 12.5 }}>
            <strong style={{ color: 'var(--status-crit)' }}>{f.title}</strong> — {f.detail}
            {f.sourceUrl && <> · <a href={f.sourceUrl} target="_blank" rel="noopener noreferrer">source ↗</a></>}
          </div>
        ))}
      </div>
    )
  }
  return (
    <p style={{ fontSize: 12.5, color: 'var(--ink-2)', margin: 0 }}>
      {safetyChecked(t)
        ? 'No documented safety events found in current data sources (checked, clean — not "never checked").'
        : 'Safety has not been checked for this target yet.'}
    </p>
  )
}

function ConstraintDrawerContent({ t }: { t: Target }) {
  const rec = constraintRecord(t)
  if (!rec) return <p style={{ fontSize: 12.5, color: 'var(--ink-3)', margin: 0 }}>Genetic constraint has not been checked for this target yet.</p>
  return (
    <div>
      <DrawerStat label="Remapped evidence score (0-1)" value={rec.evidenceScore !== null ? rec.evidenceScore.toFixed(4) : '—'} />
      <p style={{ margin: '8px 0 0', fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.55 }}>{rec.notes}</p>
    </div>
  )
}

function EssentialityDrawerContent({ t }: { t: Target }) {
  const rec = essentialityRecord(t)
  if (!rec) return <p style={{ fontSize: 12.5, color: 'var(--ink-3)', margin: 0 }}>Gene essentiality has not been checked for this target yet.</p>
  return (
    <div>
      <p style={{ margin: 0, fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.55 }}>{rec.notes}</p>
    </div>
  )
}

function ParaloguesDrawerContent({ t }: { t: Target }) {
  if (t.paralogues.length === 0) {
    return <p style={{ fontSize: 12.5, color: 'var(--ink-2)', margin: 0 }}>No real human paralogues found for this gene.</p>
  }
  return (
    <div>
      <DrawerStat label="Real human paralogues" value={String(t.paralogues.length)} />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
        {t.paralogues.map((p, i) => (
          <span key={i} style={{ fontSize: 12, padding: '3px 8px', borderRadius: 5, background: 'var(--status-neutral-bg)' }}>
            {p.sourceUrl ? <a href={p.sourceUrl} target="_blank" rel="noopener noreferrer">{p.gene}</a> : p.gene}
            {' '}<span style={{ color: 'var(--ink-3)' }}>{p.identityPercent.toFixed(1)}%</span>
          </span>
        ))}
      </div>
      <p style={{ margin: '10px 0 0', fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>
        A two-sided signal, not a risk score: a close paralogue could provide functional backup (risk-reducing) or
        reduce a knockdown/knockout drug's effectiveness through redundancy (a modality risk). Amber above means at
        least one real paralogue crosses this project's own {PARALOGUE_NOTE_THRESHOLD}% note-worthiness threshold.
      </p>
    </div>
  )
}

function GapDrawerContent({ t }: { t: Target }) {
  const main = pickMainGap(t.gaps)
  if (!t.gapsChecked) return <p style={{ fontSize: 12.5, color: 'var(--ink-3)', margin: 0 }}>Gap analysis has not been run for this target yet.</p>
  if (!main) return <p style={{ fontSize: 12.5, color: 'var(--ink-2)', margin: 0 }}>No real open gaps for this target.</p>
  return <GapCard g={main as ResearchGap} />
}

function DrawerStat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ marginBottom: 6, fontSize: 12.5 }}>
      <span style={{ color: 'var(--ink-3)' }}>{label}: </span>
      <span style={{ color: 'var(--ink-1)', fontWeight: 600 }}>{value}</span>
    </div>
  )
}

const drawerButtonStyle: React.CSSProperties = {
  marginTop: 14, fontSize: 12, fontWeight: 600, padding: '7px 14px', borderRadius: 7,
  border: '1px solid var(--border)', background: 'var(--page-bg)', color: 'var(--ink-1)', cursor: 'pointer',
}

/* ─── Main component ─────────────────────────────────────────────────── */

interface Props {
  targets: Target[]
  onSelectTarget: (t: Target, tab?: 'report' | 'evidence') => void
}

export default function EvidenceRiskGapMatrix({ targets, onSelectTarget }: Props) {
  const [open, setOpen] = useState<{ target: Target; column: ColumnKey; label: string } | null>(null)

  return (
    <div style={{ maxWidth: 1200 }}>
      <div style={{ marginBottom: 22 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: 'var(--ink-1)', margin: '0 0 4px', letterSpacing: '-0.02em' }}>
          Evidence + Risk + Gap Matrix
        </h1>
        <p style={{ fontSize: 13.5, color: 'var(--ink-2)', margin: 0, maxWidth: 780 }}>
          Click a target's name to open its full Single-Target Report. Click any dot to see the real data behind
          that signal. Green = strong/no concern, amber = moderate/minor concern, red = a real documented risk or
          confirmed contradiction, gray = no real evidence found for that signal yet.
        </p>
      </div>

      <div className="surface" style={{ overflow: 'auto', borderRadius: 12 }}>
        <table style={{ borderCollapse: 'collapse', minWidth: '100%', fontSize: 12.5 }}>
          <thead>
            <tr>
              <th style={rowLabelHeaderStyle}>Target</th>
              {EVIDENCE_COLUMNS.map(c => <th key={c.key} style={colHeaderStyle}>{c.label}</th>)}
              {RISK_COLUMNS.map(c => <th key={c.key} style={colHeaderStyle}>{c.label}</th>)}
              <th style={colHeaderStyle}>Gap</th>
            </tr>
          </thead>
          <tbody>
            {targets.map(t => (
              <tr key={t.gene}>
                <td style={targetCellStyle}>
                  <button onClick={() => onSelectTarget(t, 'report')} style={geneButtonStyle} title={`Open ${t.gene}'s full Single-Target Report`}>
                    {t.gene}
                  </button>
                </td>
                {EVIDENCE_COLUMNS.map(c => (
                  <td key={c.key} style={dotCellStyle}>
                    <Dot
                      color={dimensionDotColor(t, c)}
                      title={`${t.gene} — ${c.label}`}
                      onClick={() => setOpen({ target: t, column: c.key, label: c.label })}
                    />
                  </td>
                ))}
                {RISK_COLUMNS.map(c => (
                  <td key={c.key} style={dotCellStyle}>
                    <Dot
                      color={
                        c.key === 'safety' ? safetyDotColor(t)
                        : c.key === 'constraint' ? constraintDotColor(t)
                        : c.key === 'essentiality' ? essentialityDotColor(t)
                        : paralogueDotColor(t)
                      }
                      title={`${t.gene} — ${c.label}`}
                      onClick={() => setOpen({ target: t, column: c.key, label: c.label })}
                    />
                  </td>
                ))}
                <td style={dotCellStyle}>
                  <Dot color={gapDotColor(t)} title={`${t.gene} — Gap`} onClick={() => setOpen({ target: t, column: 'gap', label: 'Gap' })} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ display: 'flex', gap: 20, marginTop: 14, alignItems: 'center', flexWrap: 'wrap' }}>
        <LegendDot color="green" label="Strong / no concern" />
        <LegendDot color="amber" label="Moderate / minor concern" />
        <LegendDot color="red" label="Contradictory evidence / real documented risk" />
        <LegendDot color="gray" label="No real evidence found" />
      </div>

      {/* ── Drill-down drawer ─────────────────────────────────────────── */}
      {open && (
        <div
          onClick={() => setOpen(null)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.35)', zIndex: 100, display: 'flex', justifyContent: 'flex-end' }}
        >
          <div
            onClick={e => e.stopPropagation()}
            className="surface"
            style={{ width: 420, maxWidth: '90vw', height: '100%', overflowY: 'auto', padding: '24px 26px', borderRadius: 0 }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-3)' }}>
                  {open.target.gene}
                </div>
                <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--ink-1)' }}>{open.label}</div>
              </div>
              <button onClick={() => setOpen(null)} style={{ border: 'none', background: 'none', cursor: 'pointer', fontSize: 18, color: 'var(--ink-3)' }}>✕</button>
            </div>

            {EVIDENCE_COLUMNS.some(c => c.key === open.column) && (
              <EvidenceDrawerContent
                t={open.target}
                col={EVIDENCE_COLUMNS.find(c => c.key === open.column)!}
                onOpenEvidenceTab={() => { setOpen(null); onSelectTarget(open.target, 'evidence') }}
              />
            )}
            {open.column === 'safety' && <SafetyDrawerContent t={open.target} />}
            {open.column === 'constraint' && <ConstraintDrawerContent t={open.target} />}
            {open.column === 'essentiality' && <EssentialityDrawerContent t={open.target} />}
            {open.column === 'paralogues' && <ParaloguesDrawerContent t={open.target} />}
            {open.column === 'gap' && <GapDrawerContent t={open.target} />}
          </div>
        </div>
      )}
    </div>
  )
}

function LegendDot({ color, label }: { color: DotColor; label: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, color: 'var(--ink-3)' }}>
      <span style={{ width: 10, height: 10, borderRadius: '50%', background: DOT_HEX[color], display: 'inline-block' }} />
      {label}
    </span>
  )
}

const rowLabelHeaderStyle: React.CSSProperties = {
  padding: '10px 14px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: 'var(--ink-3)',
  textTransform: 'uppercase', letterSpacing: '0.03em', background: 'var(--page-bg)',
  borderBottom: '1px solid var(--border)', position: 'sticky', left: 0, zIndex: 2, minWidth: 110,
}

const colHeaderStyle: React.CSSProperties = {
  padding: '10px 12px', textAlign: 'center', fontSize: 11, fontWeight: 600, color: 'var(--ink-3)',
  textTransform: 'uppercase', letterSpacing: '0.03em', background: 'var(--page-bg)',
  borderBottom: '1px solid var(--border)', borderLeft: '1px solid var(--border)', minWidth: 90,
}

const targetCellStyle: React.CSSProperties = {
  padding: '8px 14px', background: 'var(--surface)', borderBottom: '1px solid var(--border-muted)',
  position: 'sticky', left: 0, zIndex: 1,
}

const dotCellStyle: React.CSSProperties = {
  padding: '8px 12px', textAlign: 'center', borderLeft: '1px solid var(--border)',
  borderBottom: '1px solid var(--border-muted)', verticalAlign: 'middle',
}

const geneButtonStyle: React.CSSProperties = {
  border: 'none', background: 'none', cursor: 'pointer', padding: 0,
  fontSize: 13.5, fontWeight: 700, color: 'var(--seq-550)',
}
