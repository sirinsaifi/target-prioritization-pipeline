import type { ReactNode } from 'react'
import type { Target } from './data'
import { consistencyTier, maturityTier, priorityTier, pickMainGap, type ScoreTier } from './api'

/**
 * Target De-risking Report (decision-layer strategy, priority #3, Part A).
 *
 * AUDIT FINDING (this task): this view requires ZERO new backend work —
 * every real value it renders was already fetched by api.ts's buildTarget()
 * via existing endpoints (GET /scoring, /gaps, /narration/why-target). The
 * only genuinely missing piece was that Target.dimensions only carried 4
 * of the real 9 MVP dimensions (api.ts's DIMENSION_ORDER was never
 * extended after later dimensions were added) and evidence_consistency/
 * evidence_maturity were being fetched then silently discarded — both
 * fixed in api.ts/data.ts as part of this task, not new backend surface.
 *
 * Confidence/Maturity tiers reuse the SAME thresholds already established
 * for "Why This Target?" (api.ts's consistencyTier()/maturityTier() —
 * mirroring app/config.py's CONFIDENCE_HIGH/LOW_THRESHOLD and
 * MATURITY_HIGH/LOW_THRESHOLD). Priority does NOT reuse those — it's a
 * different composite metric (evidence_strength + evidence_consistency +
 * evidence_maturity, averaged — see app/api/routes/scoring.py), so
 * priorityTier() uses its own, still-existing pair instead
 * (EVIDENCE_STRENGTH_HIGH_THRESHOLD/EVIDENCE_CONSISTENCY_GAP_THRESHOLD =
 * 0.7/0.5) — a real bug (comparing an already-rounded display value
 * against a threshold) and this threshold decision were both found and
 * fixed after a direct request to verify priorityTier(); see that
 * function's own docstring for the full reasoning.
 */

function tierChip(tier: ScoreTier) {
  switch (tier) {
    case 'High':   return { bg: 'var(--status-good-bg)', color: '#065f46', label: 'High' }
    case 'Medium': return { bg: 'var(--status-warn-bg)', color: '#92400e', label: 'Medium' }
    case 'Low':    return { bg: '#fef2f2',                color: '#991b1b', label: 'Low' }
    default:       return { bg: 'var(--status-neutral-bg)', color: 'var(--ink-3)', label: 'Not yet scored' }
  }
}

function barColor(score: number) {
  if (score >= 70) return '#1c5cab'
  if (score >= 40) return '#5598e7'
  return '#86b6ef'
}

/* Reuses the same category colors as TargetDetail.tsx's opportunityStyle()
 * (kept as a small local duplicate, matching this project's existing
 * convention of duplicating small visual helpers per file rather than
 * cross-importing — e.g. gapStyle/momentumBadge are already separately
 * defined in both TargetDetail.tsx and PortfolioComparison.tsx). */
function opportunityChipStyle(category: string) {
  switch (category) {
    case 'De-risking Needed':           return { bg: 'var(--status-crit-bg)', color: 'var(--status-crit)' }
    case 'Clinical-Stage':              return { bg: 'var(--status-good-bg)', color: '#065f46' }
    case 'Preclinical High-Confidence': return { bg: 'var(--status-warn-bg)', color: '#92400e' }
    default:                            return { bg: 'var(--status-neutral-bg)', color: '#374151' }  // Early-Stage Discovery
  }
}

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div style={{
      fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase',
      color: 'var(--ink-3)', marginBottom: 8, marginTop: 22,
    }}>
      {children}
    </div>
  )
}

function ReportBar({ label, score, present }: { label: string; score: number; present: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '5px 0' }}>
      <div style={{ width: 150, fontSize: 12.5, color: 'var(--ink-1)', fontWeight: 500, flexShrink: 0 }}>{label}</div>
      <div style={{ flex: 1, height: 8, borderRadius: 99, background: '#e9ecf3', overflow: 'hidden' }}>
        {present && <div style={{ width: `${score}%`, height: '100%', borderRadius: 99, background: barColor(score) }} />}
      </div>
      <div style={{
        width: 30, textAlign: 'right', fontSize: 12.5, fontWeight: 700, fontVariantNumeric: 'tabular-nums',
        color: present ? 'var(--ink-1)' : 'var(--ink-3)', flexShrink: 0,
      }}>
        {present ? score : '—'}
      </div>
    </div>
  )
}

export default function TargetReport({ t }: { t: Target }) {
  const priorityLevel = priorityTier(t.priorityScoreRaw, t.scoreComputed)
  const consistencyLevel = consistencyTier(t.evidenceConsistency)
  const maturityLevel = maturityTier(t.evidenceMaturity)
  const mainGap = pickMainGap(t.gaps)
  const pChip = tierChip(priorityLevel)
  const cChip = tierChip(consistencyLevel)
  const mChip = tierChip(maturityLevel)

  return (
    <div className="report-view" style={{ maxWidth: 760 }}>
      <div className="no-print" style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 10 }}>
        <button
          onClick={() => window.print()}
          style={{
            fontSize: 12, fontWeight: 600, padding: '7px 14px', borderRadius: 7,
            border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--ink-1)', cursor: 'pointer',
          }}
        >
          Print / Export
        </button>
      </div>

      <div className="surface" style={{ padding: '30px 34px' }}>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--ink-3)' }}>
          Target De-risking Report
        </div>
        <h1 style={{ fontSize: 26, fontWeight: 700, margin: '4px 0 24px', color: 'var(--ink-1)', letterSpacing: '-0.02em' }}>
          {t.gene} <span style={{ fontSize: 14, fontWeight: 400, color: 'var(--ink-3)' }}>— {t.fullName}</span>
        </h1>

        {/* ── Priority ─────────────────────────────────────────────────── */}
        <SectionLabel>Priority</SectionLabel>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ flex: 1, height: 14, borderRadius: 99, background: '#e9ecf3', overflow: 'hidden' }}>
            {t.scoreComputed && (
              <div style={{ width: `${t.priorityScore}%`, height: '100%', borderRadius: 99, background: barColor(t.priorityScore) }} />
            )}
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: 'var(--ink-1)', width: 44, textAlign: 'right' }}>
            {t.scoreComputed ? t.priorityScore : '—'}
          </div>
          <span className="badge" style={{ background: pChip.bg, color: pChip.color, fontSize: 11.5, fontWeight: 700 }}>
            {pChip.label.toUpperCase()}
          </span>
        </div>

        {/* ── Evidence ─────────────────────────────────────────────────── */}
        <SectionLabel>Evidence</SectionLabel>
        <div>
          {t.dimensions.map(d => <ReportBar key={d.label} label={d.label} score={d.score} present={d.present} />)}
        </div>

        {/* ── Consistency ──────────────────────────────────────────────── */}
        <SectionLabel>Consistency</SectionLabel>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="badge" style={{ background: cChip.bg, color: cChip.color, fontSize: 11.5, fontWeight: 700 }}>
            {cChip.label.toUpperCase()}
          </span>
          <span style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>
            {!t.contradictionsChecked
              ? 'Contradiction check has not been run for this target yet.'
              : t.contradictions.length === 0
                ? '✓ No same-type contradictions detected.'
                : `${t.contradictions.length} real contradiction(s) found: ${[...new Set(t.contradictions.map(c => c.type))].join(', ')}.`}
          </span>
        </div>

        {/* ── Maturity ─────────────────────────────────────────────────── */}
        <SectionLabel>Maturity</SectionLabel>
        <span className="badge" style={{ background: mChip.bg, color: mChip.color, fontSize: 11.5, fontWeight: 700 }}>
          {mChip.label.toUpperCase()}
        </span>

        {/* ── Translational Opportunity ────────────────────────────────── */}
        {/* A lightweight, DETERMINISTIC, rule-based category — explicitly a
            PROTOTYPE FRAMEWORK, NOT a validated business score, and kept
            deliberately far from the Priority section above (separate
            label, separate row, own section header) so it can never read
            as the same thing. Real requirement enforced server-side: a
            real caution flag always forces "De-risking Needed", regardless
            of how strong Priority/Maturity above look — see
            app/core/classification/translational_opportunity.py. */}
        {t.translationalOpportunity && (
          <>
            <SectionLabel>Translational Opportunity <span style={{ textTransform: 'none', fontWeight: 400, color: 'var(--ink-3)' }}>(prototype — not a validated score)</span></SectionLabel>
            <span className="badge" style={{
              background: opportunityChipStyle(t.translationalOpportunity.category).bg,
              color: opportunityChipStyle(t.translationalOpportunity.category).color,
              fontSize: 11.5, fontWeight: 700,
            }}>
              {t.translationalOpportunity.category}
            </span>
            <p style={{ margin: '6px 0 0', fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.55 }}>
              {t.translationalOpportunity.rationale}
            </p>
          </>
        )}

        {/* ── Caution Flags ────────────────────────────────────────────── */}
        {/* Real Known Safety Events / Gene Essentiality flags ONLY — never
            fabricated (see data.ts's own CautionFlag docstring). Section
            is entirely omitted, not shown empty, when none are real. */}
        {t.cautionFlags.length > 0 && (
          <>
            <SectionLabel>Caution Flags</SectionLabel>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {t.cautionFlags.map((f, i) => (
                <div key={i} style={{
                  fontSize: 12.5, padding: '8px 12px', borderRadius: 7,
                  background: 'var(--status-crit-bg)', color: 'var(--ink-1)',
                }}>
                  <strong style={{ color: 'var(--status-crit)' }}>
                    {f.kind === 'safety_event' ? 'Safety Signal' : 'Essentiality Risk'}:
                  </strong> {f.title} — {f.detail}
                </div>
              ))}
            </div>
          </>
        )}

        {/* ── Key Gap / Next Investigation ─────────────────────────────── */}
        <SectionLabel>Key Gap</SectionLabel>
        {mainGap ? (
          <>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink-1)', marginBottom: 4 }}>{mainGap.type}</div>
            <p style={{ margin: '0 0 14px', fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.55 }}>{mainGap.evidence}</p>

            <SectionLabel>Next Investigation</SectionLabel>
            <p style={{ margin: 0, fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.55 }}>{mainGap.suggestion}</p>
          </>
        ) : (
          <p style={{ margin: 0, fontSize: 12.5, color: 'var(--ink-2)' }}>
            {t.gapsChecked ? 'No real open gaps for this target.' : 'Gap analysis has not been run for this target yet.'}
          </p>
        )}

        {/* ── Decision Summary ─────────────────────────────────────────── */}
        {/* Reuses "Why This Target?"'s own confidence/maturity/bullets
            output directly (per this task's own instruction) rather than
            building a new summary generator — see agent_narrator.py's
            generate_why_this_target_narrative(). */}
        <SectionLabel>Decision Summary</SectionLabel>
        {t.whyThisTarget ? (
          <div>
            <ul style={{ margin: '0 0 10px', paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 4 }}>
              {t.whyThisTarget.bullets.map((b, i) => (
                <li key={i} style={{ fontSize: 12.5, color: 'var(--ink-1)', lineHeight: 1.5 }}>{b}</li>
              ))}
            </ul>
            <p style={{ margin: 0, fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.5 }}>
              Confidence: <strong style={{ color: 'var(--ink-1)' }}>{t.whyThisTarget.confidence}</strong> · Evidence
              maturity: <strong style={{ color: 'var(--ink-1)' }}>{t.whyThisTarget.evidenceMaturity}</strong> · Main
              remaining uncertainty: {t.whyThisTarget.mainRemainingUncertainty}
            </p>
          </div>
        ) : (
          <p style={{ margin: 0, fontSize: 12.5, color: 'var(--ink-3)' }}>
            "Why This Target?" narrative unavailable right now (the real LLM call may be rate-limited or the API key
            unconfigured) — the sections above are unaffected, all real and derived independently of it.
          </p>
        )}
      </div>
    </div>
  )
}
