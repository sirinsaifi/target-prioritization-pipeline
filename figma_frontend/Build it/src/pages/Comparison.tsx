import { useNavigate } from "react-router-dom";
import { useTargets } from "../api/hooks";
import { tierColor, scoreColor, scoreLabel } from "../api/transform";

const scoreBg = (score: string) =>
  score === "strong" ? "rgba(34,197,94,0.1)" : score === "moderate" ? "rgba(245,158,11,0.1)" : score === "weak" ? "rgba(249,115,22,0.1)" : "#94a3b8";

export default function Comparison() {
  const navigate = useNavigate();
  const { data: targets, loading } = useTargets();
  const showComparison = targets?.data?.slice(0, 3) ?? [];
  const DIMENSIONS = ["genetic", "literature", "human_clinical", "experimental", "pathway", "drug_target", "tissue_expression", "ppi_network"];

  if (loading) {
    return (
      <div style={{ padding: "32px 40px", textAlign: "center", color: "var(--text-muted)" }}>
        <div style={{ fontSize: 24, marginBottom: 16 }}>Loading comparison data...</div>
      </div>
    );
  }

  return (
    <div style={{ padding: "32px 40px" }}>
      <div style={{ marginBottom: 28 }}>
        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", color: "var(--text-muted)", marginBottom: 8 }}>
          LAYER 6 — DECISION & OUTPUT
        </div>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 5px", letterSpacing: "-0.02em" }}>
          Portfolio Comparison
        </h1>
        <p style={{ fontSize: 13.5, color: "var(--text-secondary)", margin: 0 }}>
          Side-by-side evidence profile comparison. Visual differences highlight why targets rank differently.
        </p>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${showComparison.length}, 1fr)`,
          gap: 16,
          marginBottom: 28,
        }}
      >
        {showComparison.map((t, i) => (
          <div
            key={t.id}
            style={{
              borderRadius: 12,
              border: i === 0 ? "1.5px solid #8b7fd1" : "1px solid var(--border)",
              background: "var(--surface)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                padding: "16px 20px",
                background: i === 0 ? "linear-gradient(135deg, #f0eaf8, #e4ddf4)" : "var(--surface-subtle)",
                borderBottom: "1px solid var(--border)",
              }}
            >
              <button
                onClick={() => navigate(`/target/${t.id}`)}
                style={{ background: "none", border: "none", cursor: "pointer", padding: 0, textAlign: "left" }}
              >
                <div style={{ fontSize: 18, fontWeight: 800, color: i === 0 ? "#8b7fd1" : "var(--text-primary)", fontFamily: "monospace", marginBottom: 2 }}>
                  {t.symbol}
                </div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.4 }}>
                  {t.fullName.substring(0, 26)}...
                </div>
              </button>
            </div>

            <div
              style={{
                padding: "16px 20px",
                borderBottom: "1px solid var(--border)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-muted)", marginBottom: 2 }}>
                  PRIORITY
                </div>
                <div style={{ fontSize: 28, fontWeight: 800, color: "var(--text-primary)", lineHeight: 1 }}>
                  {t.priorityScore}
                </div>
              </div>
              <span
                style={{
                  fontSize: 10.5,
                  fontWeight: 700,
                  letterSpacing: "0.08em",
                  color: tierColor(t.tier),
                  background: `${tierColor(t.tier)}15`,
                  borderRadius: 5,
                  padding: "4px 10px",
                }}
              >
                {t.tier}
              </span>
            </div>

            <div style={{ padding: "12px 20px", borderBottom: "1px solid var(--border)" }}>
              {[
                { label: "Ev. Strength", value: t.evidenceStrength },
                { label: "Consistency", value: t.consistency },
                { label: "Maturity", value: t.maturity },
              ].map(({ label, value }) => (
                <div key={label} style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", fontSize: 12 }}>
                  <span style={{ color: "var(--text-muted)" }}>{label}</span>
                  <span style={{ fontWeight: 700, color: tierColor(value) }}>{value}</span>
                </div>
              ))}
            </div>

            <div style={{ padding: "12px 20px" }}>
              <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-muted)", marginBottom: 5 }}>
                MAIN GAP
              </div>
              <div style={{ fontSize: 11.5, color: "var(--text-secondary)", lineHeight: 1.5 }}>
                {t.mainGap.substring(0, 70)}...
              </div>
            </div>
          </div>
        ))}
      </div>

      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 14 }}>
          EVIDENCE DIMENSION COMPARISON
        </div>
        <div
          style={{
            borderRadius: 12,
            border: "1px solid var(--border)",
            overflow: "hidden",
            background: "var(--surface)",
          }}
        >
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr style={{ background: "var(--surface-subtle)" }}>
                <th
                  style={{
                    padding: "10px 16px",
                    textAlign: "left",
                    fontSize: 10,
                    fontWeight: 700,
                    letterSpacing: "0.1em",
                    color: "var(--text-muted)",
                    borderBottom: "1px solid var(--border)",
                    minWidth: 140,
                  }}
                >
                  DIMENSION
                </th>
                {showComparison.map((t) => (
                  <th
                    key={t.id}
                    style={{
                      padding: "10px 16px",
                      textAlign: "center",
                      fontSize: 11.5,
                      fontWeight: 700,
                      color: "var(--text-primary)",
                      borderBottom: "1px solid var(--border)",
                      fontFamily: "monospace",
                    }}
                  >
                    {t.symbol}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {DIMENSIONS.map((dim, ri) => (
                <tr
                  key={dim}
                  style={{ background: ri % 2 === 0 ? "var(--surface)" : "var(--surface-subtle)", borderBottom: "1px solid var(--border)" }}
                >
                  <td style={{ padding: "10px 16px", fontSize: 12.5, color: "var(--text-secondary)", fontWeight: 500 }}>
                    {dim.replace("_", " ").toUpperCase()}
                  </td>
                  {showComparison.map((t) => {
                    const ev = t.evidence[dim] || { score: "unchecked", value: 0 };
                    const isWinner = ev.score === "strong" && showComparison.some((x) => x.evidence[dim].score !== "strong");
                    return (
                      <td key={t.id} style={{ padding: "10px 16px", textAlign: "center" }}>
                        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                          <span
                            style={{
                              fontSize: 11,
                              fontWeight: 700,
                              color: scoreColor(ev.score),
                              background: `${scoreColor(ev.score)}12`,
                              border: isWinner ? `1.5px solid ${scoreColor(ev.score)}50` : `1px solid ${scoreColor(ev.score)}25`,
                              borderRadius: 5,
                              padding: "2px 9px",
                              letterSpacing: "0.06em",
                            }}
                          >
                            {ev.score === "unchecked" ? "?" : ev.score === "none" ? "—" : ev.score.toUpperCase()}
                          </span>
                          {ev.value > 0 && (
                            <div style={{ fontSize: 10, fontFamily: "monospace", color: "var(--text-muted)" }}>
                              {ev.value}
                            </div>
                          )}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 14 }}>
          SCORE DECOMPOSITION
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {[
            { label: "Genetic", key: "geneticContribution" as const, color: "#8b7fd1" },
            { label: "Literature", key: "literatureContribution" as const, color: "#a596d5" },
            { label: "Clinical", key: "clinicalContribution" as const, color: "#c9b6e4" },
          ].map(({ label, key, color }) => (
            <div key={label}>
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6, fontWeight: 500 }}>{label}</div>
              <div style={{ display: "flex", gap: 8 }}>
                {showComparison.map((t) => (
                  <div key={t.id} style={{ flex: 1 }}>
                    <div style={{ height: 8, background: "var(--border)", borderRadius: 99, overflow: "hidden", marginBottom: 3 }}>
                      <div
                        style={{
                          height: "100%",
                          width: `${(t[key] / t.priorityScore) * 100}%`,
                          background: color,
                          borderRadius: 99,
                        }}
                      />
                    </div>
                    <div style={{ fontSize: 10, color: "var(--text-muted)", fontFamily: "monospace", textAlign: "center" }}>
                      {t[key]} pts
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
