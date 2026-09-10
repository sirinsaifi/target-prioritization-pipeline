import { useParams } from "react-router-dom";
import { useTargetData } from "../api/hooks";

const scoreColor = (s: string) =>
  s === "strong" ? "#22c55e" : s === "moderate" ? "#f59e0b" : s === "weak" ? "#f97316" : "#94a3b8";

const tierColor = (t: string) => t === "HIGH" ? "#22c55e" : t === "MEDIUM" ? "#f59e0b" : "#94a3b8";

export default function Report() {
  const { id } = useParams<{ id: string }>();
  const { data: target, loading, error } = useTargetData(Number(id));

  if (loading) {
    return (
      <div style={{ padding: "32px 40px", textAlign: "center", color: "var(--text-muted)" }}>
        <div style={{ fontSize: 24, marginBottom: 16 }}>Loading report...</div>
      </div>
    );
  }

  if (!target) {
    return (
      <div style={{ padding: "32px 40px", textAlign: "center", color: "var(--text-muted)" }}>
        <div style={{ fontSize: 24, marginBottom: 16 }}>Report not found</div>
        <p>No target data found for ID: {id}</p>
      </div>
    );
  }

  const strongEvidence = Object.entries(target.evidence)
    .filter(([, v]) => v.score === "strong")
    .map(([k, v]) => ({ dim: k, ev: v }));

  return (
    <div style={{ padding: "32px 40px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 28 }}>
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", color: "var(--text-muted)", marginBottom: 4 }}>
            LAYER 6 — DE-RISKING REPORT
          </div>
          <div style={{ fontSize: 14, color: "var(--text-secondary)" }}>
            Print-ready single-target report — {target.symbol}
          </div>
        </div>
        <button
          onClick={() => window.print()}
          style={{
            padding: "9px 20px",
            borderRadius: 8,
            background: "linear-gradient(135deg, #a596d5, #8b7fd1)",
            border: "none",
            color: "white",
            fontSize: 13,
            fontWeight: 600,
            cursor: "pointer",
            letterSpacing: "0.04em",
          }}
        >
          EXPORT / PRINT
        </button>
      </div>

      <div
        style={{
        maxWidth: 800,
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: 14,
        overflow: "hidden",
      }}
    >
        <div style={{ background: "var(--brand-gradient)", padding: "28px 32px" }}>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.15em", color: "rgba(255,255,255,0.6)", marginBottom: 8 }}>
            EVIDENS · ALS TARGET DE-RISKING REPORT · 2026-09-10
          </div>
          <div
            style={{
              fontFamily: "'DM Serif Display', serif",
              fontSize: 28,
              fontWeight: 400,
              color: "white",
              marginBottom: 4,
            }}
          >
            {target.fullName}
          </div>
          <div style={{ fontSize: 14, color: "rgba(255,255,255,0.7)", fontFamily: "monospace" }}>
            {target.symbol} · {target.selectionSource}
          </div>
        </div>

        <div style={{ padding: "32px" }}>
          <section style={{ marginBottom: 28, paddingBottom: 28, borderBottom: "1px solid var(--border)" }}>
            <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 16px", letterSpacing: "0.02em" }}>
              Priority Assessment
            </h2>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
              {[
                { label: "Priority Score", value: `${target.priorityScore}`, color: "#8b7fd1" },
                { label: "Evidence Strength", value: target.evidenceStrength, color: tierColor(target.evidenceStrength) },
                { label: "Consistency", value: target.consistency, color: tierColor(target.consistency) },
                { label: "Maturity", value: target.maturity, color: tierColor(target.maturity) },
              ].map(({ label, value, color }) => (
                <div
                  key={label}
                  style={{
                    padding: "12px 14px",
                    borderRadius: 8,
                    border: "1px solid var(--border)",
                    background: "var(--surface-subtle)",
                    textAlign: "center",
                  }}
                >
                  <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 4 }}>
                    {label.toUpperCase()}
                  </div>
                  <div style={{ fontSize: 22, fontWeight: 800, color, lineHeight: 1.1 }}>{value}</div>
                </div>
              ))}
            </div>
          </section>

          <section style={{ marginBottom: 28, paddingBottom: 28, borderBottom: "1px solid var(--border)" }}>
            <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 12px" }}>
              Evidence Rationale
            </h2>
            <p style={{ fontSize: 13, color: "var(--text-primary)", lineHeight: 1.75, margin: 0 }}>
              {target.whyRanked}
            </p>
          </section>

          <section style={{ marginBottom: 28, paddingBottom: 28, borderBottom: "1px solid var(--border)" }}>
            <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 14px" }}>
              Score Decomposition
            </h2>
            {[
              { label: "Genetic Evidence", value: target.geneticContribution, color: "#8b7fd1" },
              { label: "Literature Evidence", value: target.literatureContribution, color: "#a596d5" },
              { label: "Clinical / Experimental", value: target.clinicalContribution, color: "#c9b6e4" },
            ].map(({ label, value, color }) => (
              <div key={label} style={{ marginBottom: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
                  <span style={{ color: "var(--text-secondary)" }}>{label}</span>
                  <span style={{ fontWeight: 700, fontFamily: "monospace" }}>{value} pts</span>
                </div>
                <div style={{ height: 6, background: "var(--border)", borderRadius: 99, overflow: "hidden" }}>
                  <div style={{ height: "100%", width: `${(value / target.priorityScore) * 100}%`, background: color, borderRadius: 99 }} />
                </div>
              </div>
            ))}
          </section>

          <section style={{ marginBottom: 28, paddingBottom: 28, borderBottom: "1px solid var(--border)" }}>
            <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 14px" }}>
              Strongest Supporting Evidence
            </h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {strongEvidence.map(({ dim, ev }) => (
                <div
                  key={dim}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "8px 12px",
                    borderRadius: 6,
                    background: "rgba(34,197,94,0.05)",
                    border: "1px solid rgba(34,197,94,0.15)",
                  }}
                >
                  <div>
                    <span style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-primary)" }}>{dim}</span>
                    <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 8 }}>{ev.records} records · {ev.source}</span>
                  </div>
                  <span style={{ fontSize: 10, fontWeight: 700, color: "#22c55e", letterSpacing: "0.08em" }}>STRONG</span>
                </div>
              ))}
            </div>
          </section>

          <section style={{ marginBottom: 28, paddingBottom: 28, borderBottom: "1px solid var(--border)" }}>
            <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 14px" }}>
              Research Gaps
            </h2>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
              {target.mainGap}
            </div>
            <div style={{ fontSize: 11.5, color: "#8b7fd1", lineHeight: 1.5, marginTop: 8 }}>
              Next: Review the gap analysis page for investigation suggestions.
            </div>
          </section>

          <section style={{ marginBottom: 28, paddingBottom: 28, borderBottom: "1px solid var(--border)" }}>
            <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 12px" }}>
              Final Assessment
            </h2>
            <div
              style={{
                padding: "14px 16px",
                borderRadius: 8,
                border: "1px solid var(--border)",
                background: "var(--surface-subtle)",
              }}
            >
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6, fontStyle: "italic" }}>
                Translational opportunity categorization
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
                {target.translationalOpportunity}
              </div>
            </div>
          </section>

          <div
            style={{
              marginTop: 28,
              paddingTop: 20,
              borderTop: "1px solid var(--border)",
              fontSize: 11,
              color: "var(--text-muted)",
              lineHeight: 1.6,
            }}
          >
            <strong>Evidence Provenance:</strong> ClinVar · ClinicalTrials.gov · PubMed · Reactome · STRING v12 · GTEx · Pharos · ChEMBL · MGI · gnomAD · OMIM
            <br />
            Generated by the Evidence-Guided Target Prioritization Pipeline · Prototype
          </div>
        </div>
      </div>
    </div>
  );
}
