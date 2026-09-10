import { useState, useEffect } from 'react'
import TargetList from './pages/tei/TargetList'
import TargetDetail, { type TabId } from './pages/tei/TargetDetail'
import PortfolioComparison from './pages/tei/PortfolioComparison'
import EvidenceRiskGapMatrix from './pages/tei/EvidenceRiskGapMatrix'
import HomePage from './pages/tei/HomePage'
import type { Target } from './pages/tei/data'
import { fetchTargetSummaries } from './pages/tei/api'

type Screen = 'home' | 'targets' | 'portfolio' | 'settings'

const NAV: { id: Screen; label: string; icon: string }[] = [
  { id: 'home',      label: 'Home',              icon: '⚡' },
  { id: 'targets',   label: 'Targets',           icon: 'M' },
  { id: 'portfolio', label: 'Portfolio Compare', icon: 'P' },
  { id: 'settings',  label: 'Disease Settings',  icon: 'S' },
]

export default function App() {
  const [screen, setScreen]         = useState<Screen>('home')
  const [selected, setSelected]     = useState<Target | null>(null)
  const [selectedTab, setSelectedTab] = useState<TabId | undefined>(undefined)
  const [targets, setTargets]       = useState<Target[] | null>(null)
  const [loadError, setLoadError]   = useState<string | null>(null)
  // Evidence + Risk + Gap Matrix is the new main portfolio view; the
  // original, more detailed Portfolio Comparison table (per-dimension
  // breakdown, momentum, translational opportunity, etc.) remains
  // available via a toggle rather than being removed — both show real
  // data, the matrix is just the new default entry point.
  const [portfolioView, setPortfolioView] = useState<'matrix' | 'detailed'>('matrix')

  useEffect(() => {
    let cancelled = false
    fetchTargetSummaries()
      .then(result => { if (!cancelled) setTargets(result) })
      .catch(err => { if (!cancelled) setLoadError(String(err)) })
    return () => { cancelled = true }
  }, [])

  const handleSelectTarget = (t: Target, tab?: TabId) => { setSelected(t); setSelectedTab(tab) }
  const handleBack          = ()          => { setSelected(null); setSelectedTab(undefined) }
  // Evidence Network tab: a PPI-partner node that is ALSO one of this
  // pipeline's own candidate targets (e.g. SOD1's real STRING partners
  // FUS/TARDBP) is clickable — resolve it against the already-fetched
  // target list rather than an extra fetch.
  const handleNavigateToTarget = (targetId: number) => {
    const found = targets?.find(x => x.id === targetId)
    if (found) { setScreen('targets'); handleSelectTarget(found) }
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--page-bg)' }}>
      {/* ── Sidebar ──────────────────────────────────────────────────── */}
      <aside style={{
        width: 216,
        minHeight: '100vh',
        background: 'var(--nav-bg)',
        display: 'flex',
        flexDirection: 'column',
        flexShrink: 0,
        position: 'fixed',
        top: 0, bottom: 0, left: 0,
        zIndex: 40,
      }}>
        {/* Wordmark */}
        <div style={{ padding: '22px 20px 18px', borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <div style={{
              width: 28, height: 28, borderRadius: 6,
              background: 'linear-gradient(135deg, #38a3d4, #1c7ab8)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0,
            }}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <circle cx="7" cy="7" r="2.5" fill="white" />
                <circle cx="7" cy="7" r="5.5" stroke="white" strokeWidth="1.2" fill="none" opacity="0.5" />
                <circle cx="7" cy="7" r="3.5" stroke="white" strokeWidth="0.8" fill="none" opacity="0.3" />
              </svg>
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 12.5, color: '#e8eef4', lineHeight: 1.2, letterSpacing: '-0.01em' }}>
                Target Evidence
              </div>
              <div style={{ fontWeight: 400, fontSize: 10.5, color: 'var(--nav-text)', lineHeight: 1.2, letterSpacing: '0.02em' }}>
                Intelligence
              </div>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav style={{ padding: '12px 10px', flex: 1 }}>
          <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.08em', color: 'rgba(184,200,219,0.5)', textTransform: 'uppercase', padding: '4px 8px 8px' }}>
            Workspace
          </div>
          <button
            className={`nav-item ${screen === 'home' && !selected ? 'home-active' : ''}`}
            onClick={() => { setScreen('home'); setSelected(null) }}
            style={{ color: 'var(--pink-500)' }}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4">
              <path d="M3 6l4-4 4 4" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M5 6V2h4v4" strokeLinecap="round" strokeLinejoin="round" />
              <rect x="2" y="6" width="10" height="7" rx="1.5" />
            </svg>
            Home
          </button>
          <button
            className={`nav-item ${screen === 'targets' && !selected ? 'active' : ''}`}
            onClick={() => { setScreen('targets'); setSelected(null) }}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4">
              <rect x="1" y="3" width="12" height="9" rx="1.5" />
              <path d="M1 6h12" />
              <path d="M5 6v6" />
            </svg>
            Targets
          </button>
          <button
            className={`nav-item ${screen === 'portfolio' ? 'active' : ''}`}
            onClick={() => { setScreen('portfolio'); setSelected(null) }}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4">
              <rect x="1" y="8" width="2.5" height="4" />
              <rect x="4.5" y="5" width="2.5" height="7" />
              <rect x="8" y="2" width="2.5" height="10" />
              <rect x="11.5" y="6" width="1.5" height="6" />
            </svg>
            Portfolio Compare
          </button>
          <button
            className={`nav-item ${screen === 'settings' ? 'active' : ''}`}
            onClick={() => { setScreen('settings'); setSelected(null) }}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4">
              <circle cx="7" cy="7" r="2" />
              <path d="M7 1v1M7 12v1M1 7h1M12 7h1M2.93 2.93l.7.7M10.37 10.37l.7.7M10.37 3.63l-.7.7M3.63 10.37l-.7.7" />
            </svg>
            Disease Settings
          </button>

          <div className="sep" style={{ marginTop: 16, marginBottom: 10 }} />

          <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.08em', color: 'rgba(184,200,219,0.5)', textTransform: 'uppercase', padding: '4px 8px 8px' }}>
            About
          </div>
          <button className="nav-item">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4">
              <circle cx="7" cy="7" r="6" />
              <path d="M7 6.5v4M7 4.5v.5" strokeLinecap="round" />
            </svg>
            Documentation
          </button>
        </nav>

        {/* Footer */}
        <div style={{ padding: '14px 16px', borderTop: '1px solid rgba(255,255,255,0.07)' }}>
          <div style={{ fontSize: 11, color: 'rgba(184,200,219,0.45)', lineHeight: 1.4 }}>
            TEI v0.9.2<br />
            Last sync: 2 min ago
          </div>
        </div>
      </aside>

      {/* ── Main ─────────────────────────────────────────────────────── */}
      <main style={{ flex: 1, marginLeft: 216, minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
        {/* Top bar */}
        <header style={{
          height: 52,
          background: 'var(--surface)',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          padding: '0 28px',
          gap: 12,
          flexShrink: 0,
          position: 'sticky',
          top: 0,
          zIndex: 30,
        }}>
          {selected && (
            <button
              onClick={handleBack}
              style={{
                display: 'flex', alignItems: 'center', gap: 5,
                padding: '4px 10px', borderRadius: 6,
                border: '1px solid var(--border)', background: 'var(--page-bg)',
                color: 'var(--ink-2)', fontSize: 12.5, fontWeight: 500, cursor: 'pointer',
                marginRight: 4,
              }}
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.6">
                <path d="M8 2L4 6l4 4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Targets
            </button>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--ink-3)', fontWeight: 400 }}>Disease context:</span>
            <select style={{
              fontSize: 13, fontWeight: 600, color: 'var(--ink-1)',
              border: '1px solid var(--border)', borderRadius: 6,
              padding: '4px 28px 4px 10px', background: 'var(--page-bg)',
              appearance: 'none', cursor: 'pointer', outline: 'none',
            }}>
              <option value="EFO_0000253">Amyotrophic Lateral Sclerosis (ALS)</option>
              <option value="EFO_0000508">Cystic Fibrosis</option>
              <option value="EFO_0000647">Parkinson's Disease</option>
              <option value="EFO_0000685">Rheumatoid Arthritis</option>
            </select>
          </div>
          <div style={{ flex: 1 }} />
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{ width: 7, height: 7, borderRadius: '50%', background: loadError ? '#dc2626' : targets ? '#22c55e' : '#d97706' }} />
            <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>
              {loadError ? 'Evidence DB unreachable' : targets ? 'Evidence DB connected' : 'Connecting to Evidence DB…'}
            </span>
          </div>
        </header>

        {/* Page content */}
        <div style={{ flex: 1, padding: '28px 28px 48px' }}>
          {screen === 'settings' ? (
            <SettingsPlaceholder />
          ) : screen === 'home' && !selected ? (
            /* Landing page: always renders (even on backend error) because
               the HomePage component has its own graceful error display and
               its own lightweight fetch fallback. Clicking a gene chip or
               search result navigates to that target's detail page and
               switches the sidebar to "Targets" so Back returns to the list. */
            <HomePage
              targets={targets}
              loadError={loadError}
              onSelectTarget={(t) => { setScreen('targets'); handleSelectTarget(t) }}
            />
          ) : loadError ? (
            <div style={{ maxWidth: 600 }}>
              <h1 style={{ fontSize: 20, fontWeight: 700, color: 'var(--ink-1)', margin: '0 0 6px' }}>Could not reach the backend</h1>
              <p style={{ color: 'var(--ink-2)', fontSize: 13.5, margin: '0 0 12px' }}>
                Make sure the FastAPI backend is running (<code>uvicorn app.main:app --reload</code>) and reachable at the
                configured API base URL (set <code>VITE_API_BASE_URL</code> if it isn't <code>http://127.0.0.1:8000</code>).
              </p>
              <div className="surface" style={{ padding: 16, fontSize: 12.5, color: 'var(--ink-3)', fontFamily: 'monospace' }}>
                {loadError}
              </div>
            </div>
          ) : !targets ? (
            <div style={{ padding: '64px 0', textAlign: 'center', color: 'var(--ink-3)', fontSize: 13.5 }}>
              Loading real target data from the backend (running contradictions → scoring → gaps for each gene)…
            </div>
          ) : selected ? (
            <TargetDetail targetId={selected.id} initial={selected} initialTab={selectedTab} onBack={handleBack} onNavigateToTarget={handleNavigateToTarget} />
          ) : screen === 'portfolio' ? (
            <div>
              <div style={{ display: 'flex', gap: 6, marginBottom: 16 }}>
                <button
                  className={`nav-item ${portfolioView === 'matrix' ? 'active' : ''}`}
                  style={{ width: 'auto', padding: '6px 14px' }}
                  onClick={() => setPortfolioView('matrix')}
                >
                  Evidence + Risk + Gap Matrix
                </button>
                <button
                  className={`nav-item ${portfolioView === 'detailed' ? 'active' : ''}`}
                  style={{ width: 'auto', padding: '6px 14px' }}
                  onClick={() => setPortfolioView('detailed')}
                >
                  Detailed Comparison
                </button>
              </div>
              {portfolioView === 'matrix' ? (
                <EvidenceRiskGapMatrix
                  targets={targets}
                  onSelectTarget={(t, tab) => { setScreen('targets'); handleSelectTarget(t, tab) }}
                />
              ) : (
                <PortfolioComparison
                  targets={targets}
                  onSelectTarget={(t) => { setScreen('targets'); handleSelectTarget(t) }}
                />
              )}
            </div>
          ) : (
            <TargetList targets={targets} onSelectTarget={handleSelectTarget} />
          )}
        </div>
      </main>
    </div>
  )
}

function SettingsPlaceholder() {
  return (
    <div style={{ maxWidth: 600 }}>
      <h1 style={{ fontSize: 20, fontWeight: 700, color: 'var(--ink-1)', margin: '0 0 6px' }}>Disease Settings</h1>
      <p style={{ color: 'var(--ink-2)', fontSize: 13.5, margin: '0 0 24px' }}>
        Configure evidence sources, scoring weights, and pipeline parameters for the active disease context.
      </p>
      <div className="surface" style={{ padding: 24 }}>
        <p style={{ color: 'var(--ink-3)', fontSize: 13, textAlign: 'center', padding: '32px 0', margin: 0 }}>
          Settings panel — in development
        </p>
      </div>
    </div>
  )
}
