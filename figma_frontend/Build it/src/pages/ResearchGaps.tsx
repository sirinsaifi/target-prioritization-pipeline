import { useParams, Link } from "react-router-dom";
import { useTargets, useGapAnalysis } from "../api/hooks";

const priorityColor = (p: string) => p === "HIGH" ? "#ef4444" : p === "MEDIUM" ? "#f59e0b" : "#94a3b8";

export default function ResearchGaps() {
  const { id } = useParams<{ id: string }>();
  const { data: targets } = useTargets();
  const { data: gapAnalysis, loading } = useGapAnalysis(Number(id));
  const target = targets?.data?.find((t) => String(t.id) === id) ?? targets?.data?.[0];
  const gaps = gapAnalysis?.gaps ?? [];

  if (loading) {
    return (
      <div style={{ padding: "32px 40px", maxWidth: 860, textAlign: "center", color: "var(--text-muted)" }}>
        <div style={{ fontSize: 16 }}>Loading research gaps...</div>
      </div>
    );
  }

  return (
    <div style={{ padding: "32px 40px", maxWidth: 860 }}>
      <div style={{ marginBottom: 28 }}>
        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", color: "var(--text-muted)", marginBottom: 8 }}>
          LAYER 5 — GAP DIAGNOSIS
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 6 }}>
          <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: 0, letterSpacing: "-0.02em" }}>
            Research Gap Decision-Briefs
          </h1>
          <span style={{ fontSize: 18, fontFamily: "monospace", fontWeight: 700, color: "#8b7fd1" }}>{target?.gene_symbol ?? id}</span>
        </div>
        <p style={{ fontSize: 13.5, color: "var(--text-secondary)", margin: 0 }}>
          Gaps are actionable scientific findings — not warning cards. Each brief answers:
          what is missing, why it matters, and what to investigate next.
        </p>
      </div>

      {gaps.length === 0 ? (
        <div
          style={{
            padding: "40px",
            borderRadius: 12,
            border: "1px solid rgba(34,197,94,0.25)",
            background: "rgba(34,197,94,0.04)",
            textAlign: "center",
            color: "var(--text-muted)",
          }}
        >
          <div style={{ fontSize: 28, marginBottom: 10 }}>✓</div>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4, color: "#22c55e" }}>No critical gaps identified</div>
          <div style={{ fontSize: 13 }}>All assessed dimensions for {target?.gene_symbol ?? id} have adequate evidence coverage.</div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          {gaps.map((gap, i) => (
            <div
              key={gap.id}
              style={{
                borderRadius: 12,
                border: "1px solid var(--border)",
                background: "var(--surface)",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  padding: "16px 24px",
                  borderBottom: "1px solid var(--border)",
                  background: "var(--surface-subtle)",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)" }}>
                    GAP {i + 1}
                  </span>
                  <span style={{ width: 1, height: 12, background: "var(--border)", display: "inline-block" }} />
                  <span style={{ fontSize: 13.5, fontWeight: 700, color: "var(--text-primary)" }}>
                    {gap.gap_type}
                  </span>
                  <span
                    style={{
                      fontSize: 10,
                      fontWeight: 700,
                      letterSpacing: "0.08em",
                      color: "var(--text-muted)",
                      background: "rgba(139,127,209,0.08)",
                      borderRadius: 4,
                      padding: "2px 6px",
                    }}
                  >
                    GAP TYPE
                  </span>
                </div>
                <span
                  style={{
                    fontSize: 10.5,
                    fontWeight: 700,
                    letterSpacing: "0.08em",
                    color: "#8b7fd1",
                    background: "rgba(139,127,209,0.12)",
                    border: "1px solid rgba(139,127,209,0.3)",
                    borderRadius: 5,
                    padding: "3px 10px",
                  }}
                >
                  ACTION REQUIRED
                </span>
              </div>

              <div style={{ padding: "0 24px" }}>
                {[
                  { step: "EVIDENCE BEHIND IT", content: gap.rationale, icon: "◈" },
                  { step: "WHY IT MATTERS", content: gap.why_it_matters, icon: "↳" },
                  { step: "NEXT INVESTIGATION", content: gap.investigation_suggestion, icon: "→" },
                  { step: "DECISION IMPACT", content: gap.decision_impact, icon: "◉" },
                ].map(({ step, content, icon }, si) => (
                  <div
                    key={step}
                    style={{
                      padding: "16px 0",
                      borderBottom: si < 3 ? "1px solid var(--border)" : "none",
                      display: "flex",
                      gap: 16,
                    }}
                  >
                    <div
                      style={{
                        width: 28,
                        height: 28,
                        borderRadius: "50%",
                        background: "var(--surface-subtle)",
                        border: "1px solid var(--border)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: 11,
                        color: "#8b7fd1",
                        flexShrink: 0,
                        marginTop: 1,
                      }}
                    >
                      {icon}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 6 }}>
                        {step}
                      </div>
                      <p style={{ fontSize: 13, color: "var(--text-primary)", lineHeight: 1.65, margin: 0 }}>
                        {content}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <div style={{ marginTop: 24, display: "flex", gap: 10 }}>
        <Link to={`/network/${target?.id ?? id}`}>
          <button style={{ padding: "9px 18px", borderRadius: 8, border: "1px solid var(--border-strong)", background: "transparent", color: "var(--text-secondary)", fontSize: 12.5, cursor: "pointer" }}>
            Evidence Network →
          </button>
        </Link>
        <Link to={`/report/${target?.id ?? id}`}>
          <button style={{ padding: "9px 18px", borderRadius: 8, border: "1px solid #c9b6e4", background: "rgba(139,127,209,0.06)", color: "#8b7fd1", fontSize: 12.5, fontWeight: 600, cursor: "pointer" }}>
            Export Report
          </button>
        </Link>
      </div>
    </div>
  );
}
