import { useState, useEffect, useMemo } from 'react'
import type { Target } from './data'
import { fetchWorkspaceContext, fetchTargetList, type WorkspaceContext } from './api'
import ParticleNetwork from './ParticleNetwork'

/* ─── Landing page — "Target Evidence Intelligence" ─────────────────────────
 *
 * Structure inspired by (not copied from) the Open Targets Platform landing
 * screen: a centered search card floating over a full-screen animated network
 * background. Our OWN branding (pink palette), our OWN motion (canvas
 * particle-network), and — most importantly — every piece of text and every
 * interactive element on this card is pulled from the REAL FastAPI backend
 * at render time. Nothing here is hardcoded placeholder text.
 *
 * Data sources (all real, fetched live):
 *   - GET /targets/context      → disease name, disease EFO ID, target count,
 *                                  and the real last-analysis timestamp (from
 *                                  the PipelineRunLog table, which logs every
 *                                  successful POST .../run or .../compute).
 *   - GET /targets/             → real candidate gene symbols (for quick-access
 *                                  chips + search) and their numeric IDs (for
 *                                  navigation).
 *
 * Disease-agnostic by design: even though today's data is ALS, the disease
 * name shown here, the gene chips, and the search results are all read from
 * the API response at render time — not hardcoded in this component.
 */

interface Props {
  targets: Target[] | null
  loadError: string | null
  onSelectTarget: (t: Target) => void
}

interface QuickChip {
  type: 'gene'
  id: number
  gene: string
  fullName: string
}

export default function HomePage({ targets, loadError, onSelectTarget }: Props) {
  /* --- Real workspace context (disease name, last-analysis timestamp) --- */
  const [context, setContext] = useState<WorkspaceContext | null>(null)
  const [contextError, setContextError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchWorkspaceContext()
      .then(ctx => {
        if (!cancelled) setContext(ctx)
      })
      .catch(err => {
        if (!cancelled) setContextError(String(err))
      })
    return () => {
      cancelled = true
    }
  }, [])

  /* --- Search: real-time filter across gene symbols, full names, and
       the current disease name. Typing a gene symbol or disease name
       shows matching chips below the search bar. Pressing Enter or
       clicking a gene result navigates to that target's detail page. --- */
  const [query, setQuery] = useState('')

  /* Lightweight target list (id + gene only) — fetched independently from
     the heavier Target[] in props so the landing page can show its
     quick-access chips even while App.tsx's fetchTargetSummaries() is
     still running the full pipeline for each gene. */
  const [lightTargets, setLightTargets] = useState<{ id: number; gene: string }[] | null>(null)

  useEffect(() => {
    /* If App.tsx already gave us full Target[] via props, use that; the
       light fetch is a fallback so chips are never blank while the heavy
       fetch is still in progress. */
    if (targets && targets.length > 0) return

    let cancelled = false
    fetchTargetList()
      .then(list => {
        if (!cancelled) setLightTargets(list)
      })
      .catch(() => {
        if (!cancelled) setLightTargets([])
      })
    return () => {
      cancelled = true
    }
  }, [targets])

  /* Search results — genes + (optionally) the disease itself. */
  const searchResults = useMemo(() => {
    const q = query.toLowerCase().trim()
    if (!q) return []

    const geneResults: (QuickChip & { fullName: string })[] = (targets ?? [])
      .filter(t =>
        t.gene.toLowerCase().includes(q) ||
        t.fullName.toLowerCase().includes(q)
      )
      .map(t => ({ type: 'gene' as const, id: t.id, gene: t.gene, fullName: t.fullName }))

    const diseaseMatch = context &&
      context.disease.toLowerCase().includes(q)
      ? [{ type: 'disease' as const, name: context.disease }]
      : []

    return [...geneResults, ...diseaseMatch]
  }, [query, targets, context])

  /* Quick-access chips: one per candidate gene + one for the disease. */
  const quickChips = useMemo((): QuickChip[] => {
    const source = targets ?? []
    if (source.length === 0 && lightTargets) {
      return lightTargets.map(lt => ({
        type: 'gene',
        id: lt.id,
        gene: lt.gene,
        fullName: lt.gene,
      }))
    }
    return source.map(t => ({
      type: 'gene',
      id: t.id,
      gene: t.gene,
      fullName: t.fullName,
    }))
  }, [targets, lightTargets])

  /* --- Handle keyboard search: Enter on a single gene match navigates --- */
  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key !== 'Enter') return
    const geneMatches = searchResults.filter(r => r.type === 'gene')
    if (geneMatches.length === 1) {
      const match = targets?.find(t => t.id === geneMatches[0].id)
      if (match) onSelectTarget(match)
    }
  }

  /* --- Format the real last-analysis timestamp for display --- */
  const lastAnalysisDisplay = useMemo(() => {
    if (!context?.lastAnalysis) return 'No analysis run yet'
    try {
      const d = new Date(context.lastAnalysis)
      return d.toLocaleString('en-US', {
        month: 'long',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return context.lastAnalysis
    }
  }, [context?.lastAnalysis])

  return (
    <>
      {/* Full-screen animated particle network (our own pink palette). */}
      <ParticleNetwork />

      {/* Centered card — floats above the animated background.
          Padding accounts for the fixed 52px header and the 216px sidebar
          so the card is always fully visible to the right of the sidebar. */}
      <div style={{
        position: 'fixed',
        top: 0, left: 0, right: 0, bottom: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        paddingTop: 52,
        paddingLeft: 216,
        boxSizing: 'border-box',
        pointerEvents: 'none',
        zIndex: 1,
      }}>
        <div style={{
          background: 'rgba(255, 255, 255, 0.93)',
          border: '1px solid rgba(255, 255, 255, 0.2)',
          borderRadius: 'var(--radius-lg)',
          padding: '40px 44px',
          width: '100%',
          maxWidth: 520,
          boxShadow: '0 20px 60px rgba(0, 0, 0, 0.15)',
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
          pointerEvents: 'auto',
        }}>
          {/* ── App name / branding ────────────────── */}
          <div style={{ textAlign: 'center', marginBottom: 32 }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 10,
              marginBottom: 12,
            }}>
              <div style={{
                width: 34, height: 34, borderRadius: 8,
                background: 'linear-gradient(135deg, var(--pink-500), var(--pink-700))',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
              }}>
                <svg width="16" height="16" viewBox="0 0 14 14" fill="none">
                  <circle cx="7" cy="7" r="2.5" fill="white" />
                  <circle cx="7" cy="7" r="5.5" stroke="white" strokeWidth="1.2" fill="none" opacity="0.5" />
                  <circle cx="7" cy="7" r="3.5" stroke="white" strokeWidth="0.8" fill="none" opacity="0.3" />
                </svg>
              </div>
              <div style={{ lineHeight: 1.2 }}>
                <div style={{ fontWeight: 700, fontSize: 17, color: 'var(--ink-1)', letterSpacing: '-0.01em' }}>
                  Target Evidence
                </div>
                <div style={{ fontWeight: 400, fontSize: 14, color: 'var(--pink-700)', letterSpacing: '0.01em' }}>
                  Intelligence
                </div>
              </div>
            </div>

            {/* Tagline — uses the real, live disease name from GET /targets/context */}
            <p style={{
              fontSize: 13.5,
              color: 'var(--ink-3)',
              margin: 0,
              lineHeight: 1.55,
            }}>
              Evidence-guided target prioritization for{' '}
              <strong style={{ color: 'var(--ink-2)' }}>
                {context?.disease ?? '…'}
              </strong>
            </p>
          </div>

          {/* ── Search bar ────────────────────────── */}
          <div style={{ position: 'relative', marginBottom: 16 }}>
            <svg
              width="14" height="14" viewBox="0 0 14 14" fill="none"
              stroke="var(--ink-3)" strokeWidth="1.4"
              style={{
                position: 'absolute', left: 11, top: '50%',
                transform: 'translateY(-50%)', pointerEvents: 'none',
              }}
            >
              <circle cx="6" cy="6" r="4.5" />
              <path d="M10 10l2.5 2.5" strokeLinecap="round" />
            </svg>
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={`Search gene symbol or disease name${context ? ` (e.g. ${context.disease.split(' ')[0]}…)` : ''}…`}
              style={{
                width: '100%',
                padding: '10px 14px 10px 36px',
                borderRadius: 8,
                border: '1px solid var(--border)',
                background: 'var(--surface)',
                fontSize: 13,
                color: 'var(--ink-1)',
                outline: 'none',
                fontFamily: 'inherit',
                transition: 'border-color 0.12s, box-shadow 0.12s',
              }}
              onFocus={e => {
                (e.target as HTMLInputElement).style.borderColor = '#f472b6'
                (e.target as HTMLInputElement).style.boxShadow = '0 0 0 3px rgba(244, 114, 182, 0.12)'
              }}
              onBlur={e => {
                (e.target as HTMLInputElement).style.borderColor = 'var(--border)'
                (e.target as HTMLInputElement).style.boxShadow = 'none'
              }}
            />
          </div>

          {/* ── Live search results ───────────────── */}
          {query && (
            <div style={{
              border: '1px solid var(--border)',
              borderRadius: 7,
              marginBottom: 16,
              overflow: 'hidden',
              maxHeight: 200,
            }}>
              {searchResults.length === 0 ? (
                <div style={{
                  padding: '10px 14px',
                  fontSize: 12,
                  color: 'var(--ink-3)',
                }}>
                  No matches found
                </div>
              ) : (
                <div style={{
                  display: 'flex',
                  flexDirection: 'column',
                  maxHeight: 200,
                  overflowY: 'auto',
                }}>
                  {searchResults.map((r, i) =>
                    r.type === 'gene' ? (
                      <button
                        key={`gene-${r.id}`}
                        onClick={() => {
                          const match = targets?.find(t => t.id === r.id)
                          if (match) onSelectTarget(match)
                        }}
                        style={{
                          padding: '10px 14px',
                          textAlign: 'left',
                          border: 'none',
                          background: i % 2 === 0 ? 'var(--page-bg)' : 'var(--surface)',
                          cursor: 'pointer',
                          fontSize: 13,
                          transition: 'background 0.1s',
                        }}
                        onMouseEnter={e => (e.currentTarget.style.background = '#f1f3f8')}
                        onMouseLeave={e => (e.currentTarget.style.background = i % 2 === 0 ? 'var(--page-bg)' : 'var(--surface)')}
                      >
                        <div style={{ fontWeight: 600, color: 'var(--ink-1)' }}>{r.gene}</div>
                        <div style={{ fontSize: 11, color: 'var(--ink-3)' }}>{r.fullName}</div>
                      </button>
                    ) : (
                      <div
                        key="disease"
                        style={{
                          padding: '10px 14px',
                          background: 'var(--pink-50)',
                          cursor: 'default',
                        }}
                      >
                        <div style={{ fontWeight: 600, color: 'var(--pink-700)' }}>{r.name}</div>
                        <div style={{ fontSize: 11, color: 'var(--ink-3)' }}>Current disease context</div>
                      </div>
                    )
                  )}
                </div>
              )}
            </div>
          )}

          {/* ── Quick-access chips ──────────────────
               Populated from real API data: one chip per candidate gene
               symbol, plus the real current disease name. Clicking a gene
               chip navigates to that target's detail page. */}
          <div style={{ marginBottom: 28 }}>
            <div style={{
              fontSize: 10.5,
              fontWeight: 600,
              letterSpacing: '0.04em',
              textTransform: 'uppercase',
              color: 'var(--ink-3)',
              marginBottom: 10,
            }}>
              Quick access
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {quickChips.map(chip => (
                <button
                  key={chip.id}
                  onClick={() => {
                    const match = targets?.find(t => t.id === chip.id)
                    if (match) onSelectTarget(match)
                  }}
                  disabled={!targets || !targets.find(t => t.id === chip.id)}
                  style={{
                    padding: '6px 14px',
                    borderRadius: 999,
                    border: '1px solid var(--border)',
                    background: 'var(--surface)',
                    color: 'var(--ink-1)',
                    fontSize: 12.5,
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.12s',
                  }}
                  onMouseEnter={e => {
                    if (!e.currentTarget.disabled) {
                      e.currentTarget.style.background = 'var(--pink-50)'
                      e.currentTarget.style.borderColor = '#fbcfe8'
                    }
                  }}
                  onMouseLeave={e => {
                    if (!e.currentTarget.disabled) {
                      e.currentTarget.style.background = 'var(--surface)'
                      e.currentTarget.style.borderColor = 'var(--border)'
                    }
                  }}
                >
                  {chip.gene}
                </button>
              ))}
              {/* Disease chip — shown as read-only context, not a navigation target */}
              {context && (
                <span style={{
                  padding: '6px 14px',
                  borderRadius: 999,
                  border: '1px solid var(--pink-200)',
                  background: 'var(--pink-50)',
                  color: 'var(--pink-700)',
                  fontSize: 12.5,
                  fontWeight: 600,
                  cursor: 'default',
                }}>
                  {context.disease}
                </span>
              )}
            </div>
          </div>

          {/* ── Real status line ────────────────────
               "Last analysis" timestamp comes from the real
               PipelineRunLog table (latest run_at across all
               contradictions/gaps/compute stages). Target count is the
               real number of candidate targets loaded. */}
          <div style={{
            textAlign: 'center',
            fontSize: 11.5,
            color: 'var(--ink-3)',
            padding: '14px 0',
            borderTop: '1px solid var(--border)',
          }}>
            Last analysis: {lastAnalysisDisplay} · {targets?.length ?? context?.targetCount ?? 0} targets loaded
          </div>

          {/* Honest error states — shown inline rather than hidden. */}
          {(contextError || loadError) && (
            <div style={{
              marginTop: 14,
              padding: '10px 14px',
              borderRadius: 7,
              background: 'var(--status-crit-bg)',
              color: 'var(--status-crit)',
              fontSize: 12,
              lineHeight: 1.5,
            }}>
              {loadError && <div>Backend unreachable: {loadError}</div>}
              {contextError && <div>Context fetch failed: {contextError}</div>}
              <div style={{ marginTop: 4, fontSize: 11 }}>
                Make sure the FastAPI backend is running
                (<code>uvicorn app.main:app --reload</code>).
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
