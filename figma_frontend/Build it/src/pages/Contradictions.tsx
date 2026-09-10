import { useParams, Link } from "react-router-dom";
import { useTargets, useContradictions } from "../api/hooks";
import { transformContradictions, type ApiContradiction } from "../api/transform";

export default function Contradictions() {
  const { id } = useParams<{ id: string }>();
  const { data: targets } = useTargets();
  const { data: contradictions, loading } = useContradictions(Number(id));
  const apiContradictions = transformContradictions(contradictions ?? []);
  const target = targets?.data?.find((t) => String(t.id) === id) ?? targets?.data?.[0];

  if (loading) {
    return (
      <div style={{ padding: "32px 40px", maxWidth: 860, textAlign: "center", color: "var(--text-muted)" }}>
        <div style={{ fontSize: 16 }}>Loading contradiction analysis...</div>
      </div>
    );
  }

  return (
    <div style={{ padding: "32px 40px", maxWidth: 860 }}>
      <div style={{ marginBottom: 28 }}>
        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", color: "var(--text-muted)", marginBottom: 8 }}>
          LAYER 4 — EXPLAINABILITY · CONTRADICTIONS
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 6 }}>
          <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: 0, letterSpacing: "-0.02em" }}>
            Contradiction Analysis
          </h1>
          <span style={{ fontSize: 18, fontFamily: "monospace", fontWeight: 700, color: "#8b7fd1" }}>{target?.gene_symbol ?? id}</span>
        </div>
        <p style={{ fontSize: 13.5, color: "var(--text-secondary)", margin: 0 }}>
          Identified evidential conflicts where independent sources support opposing mechanisms.
          A high priority score does not eliminate these contradictions.
        </p>
      </div>

      {apiContradictions.length === 0 ? (
        <div
          style={{
            padding: "40px",
            borderRadius: 12,
            border: "1px solid var(--border)",
            background: "var(--surface-subtle)",
            textAlign: "center",
            color: "var(--text-muted)",
          }}
        >
          <div style={{ fontSize: 28, marginBottom: 10 }}>✓</div>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>No contradictions identified</div>
          <div style={{ fontSize: 13 }}>Evidence for {target?.gene_symbol ?? id} is directionally consistent across reviewed sources.</div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {apiContradictions.map((c) => (
            <div
              key={c.id}
              style={{
                padding: "24px",
                borderRadius: 12,
                border: "1.5px solid rgba(239,68,68,0.25)",
                background: "rgba(239,68,68,0.03)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16, flexWrap: "wrap", gap: 8 }}>
                <div>
                  <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: "#ef4444", marginBottom: 4 }}>
                    {c.dimension.toUpperCase()} CONTRADICTION
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)" }}>
                    {c.classification}
                  </div>
                </div>
                <div
                  style={{
                    fontSize: 10.5,
                    fontWeight: 700,
                    letterSpacing: "0.08em",
                    color: "#d97706",
                    background: "rgba(245,158,11,0.1)",
                    border: "1px solid rgba(245,158,11,0.25)",
                    borderRadius: 5,
                    padding: "3px 10px",
                  }}
                >
                  {c.impact.split(" — ")[0]} IMPACT
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: 12, alignItems: "center", marginBottom: 16 }}>
                <div
                  style={{
                    padding: "14px 16px",
                    borderRadius: 10,
                    border: "1px solid rgba(34,197,94,0.3)",
                    background: "rgba(34,197,94,0.06)",
                  }}
                >
                  <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "#22c55e", marginBottom: 6 }}>
                    SOURCE A
                  </div>
                  <div style={{ fontSize: 11.5, color: "var(--text-muted)", fontStyle: "italic", marginBottom: 8 }}>{c.sourceA.ref}</div>
                  <div style={{ fontSize: 12.5, color: "var(--text-primary)", lineHeight: 1.5, marginBottom: 8 }}>{c.sourceA.claim}</div>
                  <div
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                      fontSize: 10,
                      fontWeight: 600,
                      color: "#22c55e",
                      background: "rgba(34,197,94,0.1)",
                      borderRadius: 99,
                      padding: "2px 8px",
                    }}
                  >
                    ↑ {c.sourceA.direction}
                  </div>
                </div>

                <div
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: "50%",
                    background: "rgba(239,68,68,0.1)",
                    border: "1px solid rgba(239,68,68,0.25)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 11,
                    fontWeight: 700,
                    color: "#ef4444",
                    flexShrink: 0,
                  }}
                >
                  vs
                </div>

                <div
                  style={{
                    padding: "14px 16px",
                    borderRadius: 10,
                    border: "1px solid rgba(239,68,68,0.3)",
                    background: "rgba(239,68,68,0.06)",
                  }}
                >
                  <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "#ef4444", marginBottom: 6 }}>
                    SOURCE B
                  </div>
                  <div style={{ fontSize: 11.5, color: "var(--text-muted)", fontStyle: "italic", marginBottom: 8 }}>{c.sourceB.ref}</div>
                  <div style={{ fontSize: 12.5, color: "var(--text-primary)", lineHeight: 1.5, marginBottom: 8 }}>{c.sourceB.claim}</div>
                  <div
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                      fontSize: 10,
                      fontWeight: 600,
                      color: "#ef4444",
                      background: "rgba(239,68,68,0.1)",
                      borderRadius: 99,
                      padding: "2px 8px",
                    }}
                  >
                    ↓ {c.sourceB.direction}
                  </div>
                </div>
              </div>

              <div
                style={{
                  padding: "12px 16px",
                  borderRadius: 8,
                  border: "1px solid var(--border)",
                  background: "var(--surface)",
                  display: "flex",
                  gap: 12,
                }}
              >
                <div style={{ flexShrink: 0 }}>
                  <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-muted)", marginBottom: 4 }}>VERIFICATION</div>
                  <div style={{ fontSize: 11.5, color: "var(--text-secondary)", lineHeight: 1.5 }}>{c.verificationStatus}</div>
                </div>
                <div style={{ width: 1, background: "var(--border)", flexShrink: 0 }} />
                <div>
                  <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-muted)", marginBottom: 4 }}>DECISION IMPACT</div>
                  <div style={{ fontSize: 11.5, color: "var(--text-secondary)", lineHeight: 1.5 }}>{c.impact.split(" — ")[1]}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <div style={{ marginTop: 24, display: "flex", gap: 10 }}>
        <Link to={`/gaps/${target?.id ?? id}`}>
          <button style={{ padding: "9px 18px", borderRadius: 8, border: "1px solid var(--border-strong)", background: "transparent", color: "var(--text-secondary)", fontSize: 12.5, cursor: "pointer" }}>
            Research Gaps →
          </button>
        </Link>
      </div>
    </div>
  );
}
