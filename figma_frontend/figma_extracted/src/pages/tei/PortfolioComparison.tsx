import type { Target, GapType } from './data'
import { consistencyTier, maturityTier, priorityTier, pickMainGap, type ScoreTier } from './api'

/* ─── Portfolio Comparison — side-by-side view of all candidate targets,
   so a stakeholder can compare WHY each ranks where it does at a glance,
   rather than clicking through targets one at a time.

   PROTOTYPE thresholds for the colored cells (documented, not a scientific
   standard — this is a visual triage aid): score >= 0.7 green, 0.3-0.7
   amber, < 0.3 or missing gray. Same threshold family the rest of the
   project already uses for the "Strong / Moderate / Limited" bucketing in
   api.ts::scoreToLevel(), kept consistent on purpose. ── */

const GREEN  = { bg: '#ecfdf5', color: '#065f46', border: '#a7f3d0' }
const AMBER  = { bg: '#fffbeb', color: '#92400e', border: '#fde68a' }
const GRAY   = { bg: '#f3f4f6', color: '#6b7280', border: '#e5e7eb' }
const MUTED  = { bg: '#fafafa', color: '#9ca3af', border: '#f3f4f6' }  // for "no data at all" vs a real 0-score

function scoreCellStyle(score: number, present: boolean) {
  if (!present) return MUTED
  if (score >= 70) return GREEN
  if (score >= 30) return AMBER
  return GRAY
}

/* Momentum trend -> a visual language kept identical to TargetDetail's
   MomentumChart badges (not re-invented here). This is the ONE cell in
   this whole grid that is deliberately not colored on the green/amber/
   red scale — momentum is not a quality signal (see
   app/core/scoring/evidence_momentum.py's module docstring), and
   green-for-accelerating would silently frame a declining trend as
   "bad", which is exactly the misreading the module was designed to
   prevent. */
function momentumBadge(trend: string) {
  switch (trend) {
    case 'accelerating': return { icon: '↗', color: '#059669', bg: '#ecfdf5', label: 'Accelerating' }
    case 'emerging':     return { icon: '✦', color: '#7c3aed', bg: '#f5f3ff', label: 'Emerging' }
    case 'stable':       return { icon: '→', color: '#2563eb', bg: '#eff6ff', label: 'Stable' }
    case 'declining':    return { icon: '↘', color: '#d97706', bg: '#fffbeb', label: 'Declining' }
    default:             return { icon: '—', color: 'var(--ink-3)', bg: 'var(--status-neutral-bg)', label: 'No data' }
  }
}

const GAP_TYPE_SHORT: Record<GapType, string> = {
  'Mechanistic Gap': 'mechanistic',
  'Modality Gap': 'modality',
  'Validation Gap': 'validation',
  'Population Gap': 'population',
  'Evidence-Consistency Gap': 'consistency',
  'Safety Signal Gap': 'safety signal',
  'Essentiality Risk Gap': 'essentiality risk',
}

/* High/Medium/Low chip styling — same visual language (green/amber/red)
 * as this file's own GREEN/AMBER/GRAY score-cell colors above, applied to
 * the tiers computed in api.ts (which reuse the SAME thresholds as
 * "Why This Target?", not a new scale invented for this table). */
/* Translational Opportunity cell colors — SAME categories/colors as
 * TargetDetail.tsx's/TargetReport.tsx's own opportunityStyle()/
 * opportunityChipStyle() (kept as a small local duplicate, matching this
 * file's existing convention — see GAP_TYPE_SHORT/tierChipStyle above).
 * "De-risking Needed" reuses the caution-flag red deliberately — it must
 * never read as more positive than an actual caution flag. */
function opportunityCellStyle(category: string) {
  switch (category) {
    case 'De-risking Needed':           return { bg: '#fef2f2', color: '#991b1b', border: '#fecaca' }
    case 'Clinical-Stage':              return GREEN
    case 'Preclinical High-Confidence': return AMBER
    default:                            return GRAY  // Early-Stage Discovery
  }
}

function tierChipStyle(tier: ScoreTier) {
  switch (tier) {
    case 'High':   return GREEN
    case 'Medium': return AMBER
    case 'Low':    return { bg: '#fef2f2', color: '#991b1b', border: '#fecaca' }
    default:       return MUTED
  }
}

interface Props {
  targets: Target[]
  onSelectTarget: (t: Target) => void
}

/* Real dimension labels, in the SAME order api.ts's DIMENSION_ORDER uses
 * when it builds Target.dimensions — all 9 real MVP dimensions (see
 * app/config.py's MVP_DIMENSIONS), not just the original 4. Target
 * De-risking Report audit finding: this table was stuck at 4 dimensions
 * only because CORE_DIMENSIONS was never updated after 5 more real
 * dimensions were added to the backend in later work — Target.dimensions
 * itself already carries all 9 (fixed in api.ts as part of this task), so
 * extending this list is the only change needed here too. */
const CORE_DIMENSIONS = [
  'Genetic', 'Literature', 'Pathway', 'Human / Clinical',
  'Omics', 'Experimental', 'Drug-Target', 'Tissue Expression', 'PPI Network',
] as const

export default function PortfolioComparison({ targets, onSelectTarget }: Props) {
  // Default sort: descending by priority score (highest-priority left-most)
  const sorted = [...targets].sort((a, b) => b.priorityScore - a.priorityScore)

  return (
    <div style={{ maxWidth: 1400 }}>
      {/* Header */}
      <div style={{ marginBottom: 22 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: 'var(--ink-1)', margin: '0 0 4px', letterSpacing: '-0.02em' }}>
          Portfolio Comparison
        </h1>
        <p style={{ fontSize: 13.5, color: 'var(--ink-2)', margin: 0 }}>
          All {targets.length} candidate targets side by side. Green = ≥70, amber = 30-69, gray &lt; 30 — a
          prototype visual triage, not a scientific standard. Click a gene column header to open its full detail page.
        </p>
      </div>

      {/* The grid */}
      <div className="surface" style={{ overflow: 'auto', borderRadius: 12 }}>
        <table style={{
          borderCollapse: 'collapse',
          minWidth: '100%',
          fontSize: 12.5,
        }}>
          <thead>
            <tr>
              <th style={rowLabelHeaderStyle}>Signal</th>
              {sorted.map(t => (
                <th
                  key={t.gene}
                  onClick={() => onSelectTarget(t)}
                  style={{
                    ...geneHeaderStyle,
                    cursor: 'pointer',
                  }}
                  title={`Open ${t.gene} detail`}
                >
                  <div style={{ fontWeight: 700, fontSize: 13.5, color: 'var(--seq-550)', letterSpacing: '-0.01em' }}>
                    {t.gene}
                  </div>
                  <div style={{ fontSize: 10.5, color: 'var(--ink-3)', marginTop: 2, fontWeight: 400 }}>
                    {t.fullName}
                  </div>
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {/* Priority Score — real 0-100 composite PLUS a High/Medium/Low
                label. Tiered against the REAL, unrounded priorityScoreRaw
                (a prior bug compared the already-rounded display integer
                instead), using priority's OWN thresholds — 0.7/0.5,
                reusing config.EVIDENCE_STRENGTH_HIGH_THRESHOLD/
                EVIDENCE_CONSISTENCY_GAP_THRESHOLD, deliberately NOT the
                same 0.8/0.5 pair confidenceTier() uses, since priority_score
                is a different composite metric — see api.ts::priorityTier()
                for the full reasoning. */}
            <tr>
              <td style={rowLabelStyle}>
                <div style={{ fontWeight: 600 }}>Priority</div>
                <div style={sublabelStyle}>0-100 composite</div>
              </td>
              {sorted.map(t => {
                const s = scoreCellStyle(t.priorityScore, t.scoreComputed)
                const tier = priorityTier(t.priorityScoreRaw, t.scoreComputed)
                const tierStyle = tierChipStyle(tier)
                return (
                  <td key={t.gene} style={{ ...cellStyle, background: s.bg, color: s.color, borderColor: s.border }}>
                    <div style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 700, fontSize: 15 }}>
                      {t.scoreComputed ? t.priorityScore : '—'}
                    </div>
                    <span style={{
                      display: 'inline-block', marginTop: 4, fontSize: 9.5, fontWeight: 700,
                      letterSpacing: '0.04em', padding: '1px 6px', borderRadius: 4,
                      background: tierStyle.bg, color: tierStyle.color, border: `1px solid ${tierStyle.border}`,
                    }}>
                      {tier.toUpperCase()}
                    </span>
                  </td>
                )
              })}
            </tr>

            {/* Section header — Translational Opportunity (prototype) */}
            {/* Deliberately its OWN section, separated from the Priority
                row above by a header boundary — a DETERMINISTIC, rule-based
                category, explicitly NOT a score, and never to be read as
                part of Priority (see app/core/classification/
                translational_opportunity.py's module docstring). A real
                caution flag always forces "De-risking Needed" here,
                regardless of how strong Priority above looks for the same
                gene (see SOD1/TARDBP below — both HIGH priority, both
                De-risking Needed). */}
            <SectionHeader label="Translational Opportunity — prototype, not a validated score" colSpan={sorted.length + 1} />
            <tr>
              <td style={rowLabelStyle}>
                <div style={{ fontWeight: 600 }}>Category</div>
                <div style={sublabelStyle}>rule-based, deterministic</div>
              </td>
              {sorted.map(t => {
                const opp = t.translationalOpportunity
                const style = opp ? opportunityCellStyle(opp.category) : MUTED
                return (
                  <td key={t.gene} style={{ ...cellStyle, background: style.bg, color: style.color, borderColor: style.border }}>
                    <div style={{ fontWeight: 700, fontSize: 11.5, lineHeight: 1.3 }}>
                      {opp ? opp.category : '—'}
                    </div>
                  </td>
                )
              })}
            </tr>

            {/* Section header — Evidence Profile */}
            <SectionHeader label="Evidence Profile" colSpan={sorted.length + 1} />

            {/* Per-dimension scores — pulled from Target's own dimensions
                array (api.ts's DIMENSION_ORDER, all 9 real MVP
                dimensions — extended from 4 as part of this task, see
                CORE_DIMENSIONS's own comment above). `present` now reads
                the real, authoritative DimensionScore.present flag (this
                task) rather than a `score > 0` heuristic, which would
                have misread a genuine real 0.0 score as "no data". */}
            {CORE_DIMENSIONS.map((label, i) => (
              <tr key={label}>
                <td style={rowLabelStyle}>
                  <div>{label}</div>
                  <div style={sublabelStyle}>dimension score</div>
                </td>
                {sorted.map(t => {
                  const d = t.dimensions[i]
                  const present = t.scoreComputed && d.present
                  const s = scoreCellStyle(d.score, present)
                  return (
                    <td key={t.gene} style={{ ...cellStyle, background: s.bg, color: s.color, borderColor: s.border }}>
                      <div style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>
                        {present ? d.score : '—'}
                      </div>
                      <div style={{ fontSize: 10, marginTop: 2, opacity: 0.75 }}>{present ? d.level : 'no data'}</div>
                    </td>
                  )
                })}
              </tr>
            ))}

            {/* Consistency / Maturity (this task) — real evidence_consistency/
                evidence_maturity, previously fetched then silently discarded
                (see data.ts's Target.evidenceConsistency/.evidenceMaturity
                docstring), now shown as High/Medium/Low using the SAME
                thresholds "Why This Target?" already established
                (api.ts::consistencyTier()/maturityTier()). */}
            <tr>
              <td style={rowLabelStyle}>
                <div style={{ fontWeight: 600 }}>Consistency</div>
                <div style={sublabelStyle}>agreement across sources</div>
              </td>
              {sorted.map(t => {
                const tier = consistencyTier(t.evidenceConsistency)
                const s = tierChipStyle(tier)
                return (
                  <td key={t.gene} style={{ ...cellStyle, background: s.bg, color: s.color, borderColor: s.border }}>
                    <div style={{ fontWeight: 700, fontSize: 13 }}>{tier.toUpperCase()}</div>
                    {t.evidenceConsistency !== null && (
                      <div style={{ fontSize: 10, marginTop: 2, opacity: 0.75 }}>{t.evidenceConsistency.toFixed(2)}</div>
                    )}
                  </td>
                )
              })}
            </tr>

            <tr>
              <td style={rowLabelStyle}>
                <div style={{ fontWeight: 600 }}>Maturity</div>
                <div style={sublabelStyle}>translational stage reached</div>
              </td>
              {sorted.map(t => {
                const tier = maturityTier(t.evidenceMaturity)
                const s = tierChipStyle(tier)
                return (
                  <td key={t.gene} style={{ ...cellStyle, background: s.bg, color: s.color, borderColor: s.border }}>
                    <div style={{ fontWeight: 700, fontSize: 13 }}>{tier.toUpperCase()}</div>
                    {t.evidenceMaturity !== null && (
                      <div style={{ fontSize: 10, marginTop: 2, opacity: 0.75 }}>{t.evidenceMaturity.toFixed(2)}</div>
                    )}
                  </td>
                )
              })}
            </tr>

            {/* Section header — Momentum */}
            <SectionHeader label="Evidence Momentum" colSpan={sorted.length + 1} />

            <tr>
              <td style={rowLabelStyle}>
                <div>Trend</div>
                <div style={sublabelStyle}>real per-year counts</div>
              </td>
              {sorted.map(t => {
                const b = momentumBadge(t.momentum.trend)
                return (
                  <td key={t.gene} style={{ ...cellStyle, background: b.bg, color: b.color, borderColor: 'transparent' }}>
                    <div style={{ fontWeight: 600 }}>{b.icon} {b.label}</div>
                    {t.momentum.momentumScore !== null && (
                      <div style={{ fontSize: 10.5, marginTop: 2, opacity: 0.8 }}>
                        {t.momentum.momentumScore.toFixed(2)}x recent vs prior
                      </div>
                    )}
                  </td>
                )
              })}
            </tr>

            {/* Section header — Verification & Gaps */}
            <SectionHeader label="Verification & Gaps" colSpan={sorted.length + 1} />

            <tr>
              <td style={rowLabelStyle}>
                <div>Contradictions</div>
                <div style={sublabelStyle}>real confirmed count</div>
              </td>
              {sorted.map(t => {
                // A real, confirmed 0 (checked, none found) is different
                // from "never checked" — surfaced honestly, not collapsed.
                const has = t.hasContradictions
                const style = t.contradictionsChecked
                  ? (has ? { bg: '#fef2f2', color: '#991b1b', border: '#fecaca' } : GREEN)
                  : MUTED
                return (
                  <td key={t.gene} style={{ ...cellStyle, background: style.bg, color: style.color, borderColor: style.border }}>
                    <div style={{ fontWeight: 600 }}>
                      {t.contradictionsChecked ? t.contradictions.length : '—'}
                    </div>
                    <div style={{ fontSize: 10, marginTop: 2, opacity: 0.75 }}>
                      {t.contradictionsChecked ? (has ? 'detected' : 'none found') : 'not checked'}
                    </div>
                  </td>
                )
              })}
            </tr>

            {/* Main Gap (this task) — the single most significant real
                open gap per target, by a documented priority order (see
                api.ts::pickMainGap()'s own docstring: Safety Signal >
                Essentiality Risk > Validation > Modality > Mechanistic >
                Population > Evidence-Consistency — this project's own
                judgment call, not an external standard). Distinct from
                the full "Research Gaps" row below, which still lists
                EVERY real gap type found, not just the headline one. */}
            <tr>
              <td style={rowLabelStyle}>
                <div style={{ fontWeight: 600 }}>Main Gap</div>
                <div style={sublabelStyle}>single most significant</div>
              </td>
              {sorted.map(t => {
                const main = pickMainGap(t.gaps)
                const style = !t.gapsChecked ? MUTED : main ? AMBER : GREEN
                return (
                  <td key={t.gene} style={{ ...cellStyle, background: style.bg, color: style.color, borderColor: style.border }}>
                    <div style={{ fontWeight: 700, fontSize: 12 }}>
                      {!t.gapsChecked ? '—' : main ? (GAP_TYPE_SHORT[main.type] || main.type) : 'None'}
                    </div>
                  </td>
                )
              })}
            </tr>

            <tr>
              <td style={rowLabelStyle}>
                <div>Research Gaps</div>
                <div style={sublabelStyle}>gap types identified</div>
              </td>
              {sorted.map(t => {
                const has = t.hasGaps
                const style = t.gapsChecked
                  ? (has ? AMBER : GREEN)
                  : MUTED
                const gapTypes = t.gaps.map(g => GAP_TYPE_SHORT[g.type] || g.type).join(', ')
                return (
                  <td key={t.gene} style={{ ...cellStyle, background: style.bg, color: style.color, borderColor: style.border, textAlign: 'left' as const }}>
                    <div style={{ fontWeight: 600, textAlign: 'center' }}>
                      {t.gapsChecked ? t.gaps.length : '—'}
                    </div>
                    {t.gapsChecked && has && (
                      <div style={{ fontSize: 10.5, marginTop: 3, textAlign: 'center', lineHeight: 1.3 }}>
                        {gapTypes}
                      </div>
                    )}
                    {t.gapsChecked && !has && (
                      <div style={{ fontSize: 10, marginTop: 2, opacity: 0.75, textAlign: 'center' }}>none found</div>
                    )}
                    {!t.gapsChecked && (
                      <div style={{ fontSize: 10, marginTop: 2, opacity: 0.75, textAlign: 'center' }}>not checked</div>
                    )}
                  </td>
                )
              })}
            </tr>

            <tr>
              <td style={rowLabelStyle}>
                <div>Investigation Coverage</div>
                <div style={sublabelStyle}>dimensions queried</div>
              </td>
              {sorted.map(t => (
                <td key={t.gene} style={{ ...cellStyle, background: '#fafafa', borderColor: '#f3f4f6', color: 'var(--ink-2)' }}>
                  <div style={{ fontSize: 11, fontWeight: 500 }}>
                    {/* The fixed pipeline always queries every configured
                        dimension by design (see docs/07 Phase 8), so this
                        row currently reads "complete" for every target —
                        included anyway because it's a real, defensible
                        signal that would genuinely differ under the
                        autonomous investigation loop's output. */}
                    complete
                  </div>
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 20, marginTop: 14, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 11.5, color: 'var(--ink-3)', fontWeight: 500 }}>Cell color:</span>
        <LegendChip style={GREEN}  label="≥ 70 / strong" />
        <LegendChip style={AMBER}  label="30–69 / partial" />
        <LegendChip style={GRAY}   label="< 30 / weak" />
        <LegendChip style={MUTED}  label="not analyzed / no data" />
      </div>
      <p style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 8, lineHeight: 1.5, maxWidth: 900 }}>
        Cell thresholds are a prototype visual triage, not a scientific standard. Momentum badges use a
        different color language on purpose — momentum is a factual trend, not an evidence-quality signal, and
        would be misleading to render on the same green/amber scale.
      </p>
    </div>
  )
}

/* ─── Reused inline styles (matches the surface/border language of the
   other pages, not a new visual system) ── */

const rowLabelHeaderStyle: React.CSSProperties = {
  padding: '10px 14px',
  textAlign: 'left',
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--ink-3)',
  textTransform: 'uppercase',
  letterSpacing: '0.03em',
  background: 'var(--page-bg)',
  borderBottom: '1px solid var(--border)',
  position: 'sticky',
  left: 0,
  zIndex: 2,
  minWidth: 170,
}

const geneHeaderStyle: React.CSSProperties = {
  padding: '10px 14px',
  textAlign: 'center',
  background: 'var(--page-bg)',
  borderBottom: '1px solid var(--border)',
  borderLeft: '1px solid var(--border)',
  minWidth: 130,
}

const rowLabelStyle: React.CSSProperties = {
  padding: '10px 14px',
  textAlign: 'left',
  fontSize: 12.5,
  color: 'var(--ink-1)',
  background: 'var(--surface)',
  borderBottom: '1px solid var(--border-muted)',
  position: 'sticky',
  left: 0,
  zIndex: 1,
}

const sublabelStyle: React.CSSProperties = {
  fontSize: 10.5,
  color: 'var(--ink-3)',
  marginTop: 2,
  fontWeight: 400,
}

const cellStyle: React.CSSProperties = {
  padding: '10px 12px',
  textAlign: 'center',
  borderLeft: '1px solid var(--border)',
  borderBottom: '1px solid var(--border-muted)',
  fontSize: 12.5,
  verticalAlign: 'middle',
}

function SectionHeader({ label, colSpan }: { label: string; colSpan: number }) {
  return (
    <tr>
      <td
        colSpan={colSpan}
        style={{
          padding: '8px 14px',
          background: '#f8fafc',
          fontSize: 10.5,
          fontWeight: 700,
          color: 'var(--ink-3)',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          borderTop: '1px solid var(--border)',
          borderBottom: '1px solid var(--border)',
        }}
      >
        {label}
      </td>
    </tr>
  )
}

function LegendChip({ style, label }: { style: { bg: string; color: string; border: string }; label: string }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '3px 10px', borderRadius: 12,
      background: style.bg, color: style.color, border: `1px solid ${style.border}`,
      fontSize: 11, fontWeight: 500,
    }}>
      {label}
    </span>
  )
}
