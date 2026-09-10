import { useParams, Link } from "react-router-dom";
import { useTargetData } from "../api/hooks";

const tierColor = (t: string) => t === "HIGH" ? "#22c55e" : t === "MEDIUM" ? "#f59e0b" : "#94a3b8";

export default function WhyTarget() {
  const { id } = useParams<{ id: string }>();
  const { data: target, loading, error } = useTargetData(Number(id));

  if (loading) {
    return (
      <div style={{ padding: "32px 40px", maxWidth: 860, textAlign: "center", color: "var(--text-muted)" }}>
        <div style={{ fontSize: 24, marginBottom: 16 }}>Loading target details...</div>
      </div>
    );
  }

  if (!target) {
    return (
      <div style={{ padding: "32px 40px", maxWidth: 860, textAlign: "center", color: "var(--text-muted)" }}>
        <div style={{ fontSize: 24, marginBottom: 16 }}>Target not found</div>
        <p>No target data found for ID: {id}</p>
      </div>
    );
  }

  const strongEvidence = Object.entries(target.evidence)
    .filter(([, v]) => v.score === "strong")
    .map(([k, v]) => ({ dim: k, ev: v }));

  const uncertainties = Object.entries(target.evidence)
    .filter(([, v]) => v.score === "none" || v.score === "unchecked" || v.score === "weak")
    .map(([k, v]) => ({ dim: k, ev: v }));

  return (
    <div style={{ padding: "32px 40px", maxWidth: 860 }}>
      <div style={{ marginBottom: 28 }}>
        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", color: "var(--text-muted)", marginBottom: 8 }}>
          LAYER 4 — EXPLAINABILITY
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 6 }}>
          <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: 0, letterSpacing: "-0.02em" }}>
            Why This Target?
          </h1>
          <span style={{ fontSize: 18, fontFamily: "monospace", fontWeight: 700, color: "#8b7fd1" }}>{target.symbol}</span>
        </div>
        <p style={{ fontSize: 13.5, color: "var(--text-secondary)", margin: 0 }}>
          Evidence rationale grounded in computed scores and source provenance — not AI-generated prose.
        </p>
      </div>

      {/* Score summary */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 12,
          marginBottom: 28,
        }}
      >
        {[
          { label: "Priority Score", value: `${target.priorityScore}`, sub: `${target.tier} TIER` },
          { label: "Ev. Strength", value: target.evidenceStrength, sub: "across dimensions" },
          { label: "Consistency", value: target.consistency, sub: "across sources" },
          { label: "Maturity", value: target.maturity, sub: "of evidence body" },
        ].map(({ label, value, sub }) => (
          <div
            key={label}
            style={{
              padding: "16px",
              borderRadius: 10,
              border: "1px solid var(--border)",
              background: "var(--surface-subtle)",
              textAlign: "center",
            }}
          >
            <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 6 }}>
              {label.toUpperCase()}
            </div>
            <div style={{ fontSize: 24, fontWeight: 800, color: tierColor(value), lineHeight: 1.1, marginBottom: 4 }}>
              {value}
            </div>
            <div style={{ fontSize: 10, color: "var(--text-muted)" }}>{sub}</div>
          </div>
        ))}
      </div>

      {/* Narrative */}
      <div
        style={{
          padding: "20px 24px",
          borderRadius: 12,
          border: "1px solid #d4cce8",
          background: "var(--brand-gradient-subtle)",
          marginBottom: 28,
        }}
      >
        <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em", color: "#8b7fd1", marginBottom: 10 }}>
          EVIDENCE RATIONALE
        </div>
        <p style={{ fontSize: 13.5, color: "var(--text-primary)", lineHeight: 1.75, margin: 0 }}>
          {target.whyRanked}
        </p>
      </div>

      {/* Strongest supporting evidence */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 12 }}>
          STRONGEST SUPPORTING EVIDENCE
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {strongEvidence.map(({ dim, ev }) => (
            <div
              key={dim}
              style={{
                padding: "14px 18px",
                borderRadius: 10,
                border: "1px solid rgba(34,197,94,0.2)",
                background: "rgba(34,197,94,0.04)",
                display: "flex",
                alignItems: "center",
                gap: 16,
              }}
            >
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#22c55e", flexShrink: 0, display: "inline-block" }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", marginBottom: 2 }}>{dim}</div>
                <div style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{ev.records} records · {ev.source}</div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 18, fontWeight: 800, color: "var(--text-primary)" }}>{ev.value}</div>
                <div style={{ fontSize: 9.5, color: "#22c55e", fontWeight: 700, letterSpacing: "0.08em" }}>STRONG</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Score decomposition */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 12 }}>
          SCORE DECOMPOSITION
        </div>
        {[
          { label: "Genetic Evidence", value: target.geneticContribution, color: "#8b7fd1", pct: Math.round((target.geneticContribution / target.priorityScore) * 100) },
          { label: "Literature Evidence", value: target.literatureContribution, color: "#a596d5", pct: Math.round((target.literatureContribution / target.priorityScore) * 100) },
          { label: "Clinical / Experimental", value: target.clinicalContribution, color: "#c9b6e4", pct: Math.round((target.clinicalContribution / target.priorityScore) * 100) },
          { label: "Other Dimensions", value: target.priorityScore - target.geneticContribution - target.literatureContribution - target.clinicalContribution, color: "#e8d6ee", pct: 0 },
        ].filter(d => d.value > 0).map(({ label, value, color, pct }) => (
          <div key={label} style={{ marginBottom: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5, fontSize: 12.5 }}>
              <span style={{ color: "var(--text-secondary)", fontWeight: 500 }}>{label}</span>
              <div style={{ display: "flex", gap: 8 }}>
                <span style={{ color: "var(--text-muted)", fontSize: 11 }}>{pct > 0 ? `${pct}%` : ""}</span>
                <span style={{ fontWeight: 700, color: "var(--text-primary)", fontFamily: "monospace" }}>{value} pts</span>
              </div>
            </div>
            <div style={{ height: 10, background: "var(--border)", borderRadius: 99, overflow: "hidden" }}>
              <div
                style={{
                  height: "100%",
                  width: `${(value / target.priorityScore) * 100}%`,
                  background: color,
                  borderRadius: 99,
                }}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Limitations */}
      {uncertainties.length > 0 && (
        <div style={{ marginBottom: 28 }}>
          <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 12 }}>
            LIMITATIONS & REMAINING UNCERTAINTY
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {uncertainties.map(({ dim, ev }) => (
              <div
                key={dim}
                style={{
                  padding: "12px 16px",
                  borderRadius: 8,
                  border: "1px solid var(--border)",
                  background: "var(--surface-subtle)",
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                }}
              >
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: ev.score === "unchecked" ? "#e2e8f0" : "#94a3b8",
                    flexShrink: 0,
                    display: "inline-block",
                    border: "1px solid #cbd5e1",
                  }}
                />
                <div style={{ flex: 1 }}>
                  <span style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-primary)" }}>{dim}</span>
                  <span
                    style={{
                      fontSize: 11,
                      color: "var(--text-muted)",
                      marginLeft: 8,
                    }}
                  >
                    {ev.score === "unchecked" ? "Not yet assessed" : ev.score === "none" ? "Checked — no evidence found" : "Weak evidence"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Main gap */}
      <div
        style={{
          padding: "16px 20px",
          borderRadius: 10,
          border: "1px solid rgba(245,158,11,0.25)",
          background: "rgba(245,158,11,0.05)",
        }}
      >
        <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em", color: "#d97706", marginBottom: 8 }}>
          MAIN REMAINING UNCERTAINTY
        </div>
        <p style={{ fontSize: 13, color: "var(--text-primary)", margin: 0, lineHeight: 1.6 }}>
          {target.mainGap}
        </p>
      </div>

      <div style={{ marginTop: 24, display: "flex", gap: 10 }}>
        <Link to={`/gaps/${target.id}`}>
          <button style={{ padding: "9px 18px", borderRadius: 8, border: "1px solid var(--border-strong)", background: "transparent", color: "var(--text-secondary)", fontSize: 12.5, cursor: "pointer" }}>
            Research Gaps →
          </button>
        </Link>
        <Link to={`/contradictions/${target.id}`}>
          <button style={{ padding: "9px 18px", borderRadius: 8, border: "1px solid rgba(239,68,68,0.25)", background: "transparent", color: "#ef4444", fontSize: 12.5, cursor: "pointer" }}>
            Contradictions →
          </button>
        </Link>
      </div>
    </div>
  );
}
