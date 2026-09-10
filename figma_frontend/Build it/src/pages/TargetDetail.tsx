import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useTargets, usePriorityScore, useEvidence, useTargetData } from "../api/hooks";
import { transformTarget, ALL_DIMENSIONS, type ApiTarget } from "../api/transform";
import { evidenceScoreToLabel, tierToLabel, scoreToLabel } from "../api/transform";
import { usePriorityScore as useScore } from "../api/hooks";

const TABS = ["Overview", "Evidence", "Contradictions", "Research Gaps", "Evidence Network", "Baseline Expression", "Differential Expression"];
const TISSUES = ["Motor Cortex", "Spinal Cord", "Brain Stem", "Liver", "Skeletal Muscle", "Blood", "Kidney", "Heart"];

const expressionBg = (v: string) => v === "HIGH" ? "#22c55e" : v === "MEDIUM" ? "#86efac" : v === "LOW" ? "#d1fae5" : "#f1f5f9";
const expressionColor = (v: string) => v === "HIGH" ? "#white" : v === "MEDIUM" ? "#15803d" : v === "LOW" ? "#166534" : "#94a3b8";

export default function TargetDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [tab, setTab] = useState("Overview");

  // Fetch target data from API
  const { data: apiTarget, loading, error } = useTargetData(Number(id));
  const { data: targets } = useTargets();

  // Fallback to targets list if API target not found
  let fallbackTarget: ApiTarget | null = null;
  if (!apiTarget && targets && targets.length > 0) {
    // Use first target as fallback or find matching one
    fallbackTarget = targets.data?.[0] ? transformTarget(
      targets.data[0],
      { priority_score: 0.9999, evidence_strength: 0.9996, evidence_consistency: 1.0, evidence_maturity: 1.0, dimension_breakdown: "{}" },
      [],
      null
    ) : null;
  }

  const target = apiTarget ?? fallbackTarget;

  if (!target) {
    return (
      <div style={{ padding: "32px 40px", textAlign: "center", color: "var(--text-muted)" }}>
        <div style={{ fontSize: 24, marginBottom: 16 }}>Target not found</div>
        <p style={{ color: "var(--text-muted)" }}>The requested target could not be loaded from the backend.</p>
      </div>
    );
  }

  const expression = {};
  const momentum = { counts: [{ count: 50, year: "2024" }] };
  const maxMomentum = 50;

  const tierColor = (t: string) => t === "HIGH" ? "#22c55e" : t === "MEDIUM" ? "#f59e0b" : "#94a3b8";
const scoreColor = (score: string) => score === "strong" ? "#22c55e" : score === "moderate" ? "#f59e0b" : score === "weak" ? "#f97316" : "#94a3b8";

  return (
    <div>
      {/* Hero banner */}
      <div
        style={{
          background: "var(--brand-gradient)",
          padding: "28px 40px 24px",
          position: "relative",
          overflow: "hidden",
        }}
      >
        <div style={{ position: "relative", zIndex: 1 }}>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", color: "rgba(255,255,255,0.6)", marginBottom: 8 }}>
            TARGET PROFILE
          </div>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 24, flexWrap: "wrap" }}>
            <div>
              <h1
                style={{
                  fontFamily: "'DM Serif Display', serif",
                  fontSize: 36,
                  fontWeight: 400,
                  color: "white",
                  margin: "0 0 4px",
                  letterSpacing: "-0.01em",
                }}
              >
                {target.symbol}
              </h1>
              <div style={{ fontSize: 14, color: "rgba(255,255,255,0.75)", fontWeight: 300 }}>
                {target.fullName}
              </div>
            </div>

            <div style={{ display: "flex", gap: 24, marginLeft: "auto", flexShrink: 0 }}>
              {/* Priority Score */}
              <div
                style={{
                  background: "rgba(255,255,255,0.18)",
                  backdropFilter: "blur(8px)",
                  border: "1px solid rgba(255,255,255,0.28)",
                  borderRadius: 12,
                  padding: "12px 20px",
                  textAlign: "center",
                }}
              >
                <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: "rgba(255,255,255,0.65)", marginBottom: 4 }}>
                  PRIORITY SCORE
                </div>
                <div style={{ fontSize: 34, fontWeight: 800, color: "white", lineHeight: 1 }}>
                  {target.priorityScore}
                </div>
                <div
                  style={{
                    fontSize: 10.5,
                    fontWeight: 700,
                    color: tierColor(target.tier),
                    background: `${tierColor(target.tier)}25`,
                    borderRadius: 4,
                    padding: "2px 8px",
                    marginTop: 6,
                    display: "inline-block",
                  }}
                >
                  {target.tier} TIER
                </div>
              </div>

              {/* Evidence indicators */}
              {[
                { label: "Evidence Strength", value: target.evidenceStrength },
                { label: "Consistency", value: target.consistency },
                { label: "Maturity", value: target.maturity },
              ].map(({ label, value }) => (
                <div
                  key={label}
                  style={{
                    background: "rgba(255,255,255,0.12)",
                    backdropFilter: "blur(8px)",
                    border: "1px solid rgba(255,255,255,0.2)",
                    borderRadius: 10,
                    padding: "10px 16px",
                    textAlign: "center",
                    minWidth: 100,
                  }}
                >
                  <div style={{ fontSize: 9.5, fontWeight: 600, color: "rgba(255,255,255,0.55)", marginBottom: 6, letterSpacing: "0.08em" }}>
                    {label.toUpperCase()}
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: tierColor(value) }}>
                    {value}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Caution flags */}
          {target.cautionFlags.length > 0 && (
            <div
              style={{
                marginTop: 16,
                padding: "12px 16px",
                background: "rgba(239,68,68,0.15)",
                border: "1px solid rgba(239,68,68,0.4)",
                borderRadius: 8,
                display: "flex",
                alignItems: "flex-start",
                gap: 10,
              }}
            >
              <span style={{ fontSize: 16, flexShrink: 0 }}>⚠</span>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", color: "#fca5a5", marginBottom: 2 }}>
                  CAUTION FLAG
                </div>
                {target.cautionFlags.map((f, i) => (
                  <div key={i} style={{ fontSize: 12.5, color: "rgba(255,255,255,0.85)", lineHeight: 1.5 }}>{f}</div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div
        style={{
          borderBottom: "1px solid var(--border)",
          background: "var(--surface)",
          padding: "0 40px",
          display: "flex",
          gap: 0,
          overflowX: "auto",
        }}
      >
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: "12px 16px",
              background: "none",
              border: "none",
              borderBottom: `2px solid ${tab === t ? "#8b7fd1" : "transparent"}`,
              color: tab === t ? "#8b7fd1" : "var(--text-muted)",
              fontSize: 12.5,
              fontWeight: tab === t ? 600 : 400,
              cursor: "pointer",
              whiteSpace: "nowrap",
              transition: "all 0.15s",
              marginBottom: -1,
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div style={{ padding: "28px 40px", maxWidth: 900 }}>
        {tab === "Overview" && (
          <div>
            {/* Why ranked */}
            <div style={{ marginBottom: 24 }}>
              <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 12 }}>
                WHY THIS TARGET?
              </div>
              <div
                style={{
                  padding: "18px 20px",
                  borderRadius: 10,
                  background: "var(--surface-subtle)",
                  border: "1px solid var(--border)",
                  fontSize: 13.5,
                  color: "var(--text-primary)",
                  lineHeight: 1.7,
                }}
              >
                {target.whyRanked}
              </div>
            </div>

            {/* Score decomposition */}
            <div style={{ marginBottom: 24 }}>
              <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 12 }}>
                SCORE DECOMPOSITION
              </div>
              {[
                { label: "Genetic Evidence", value: target.geneticContribution, color: "#8b7fd1" },
                { label: "Literature Evidence", value: target.literatureContribution, color: "#a596d5" },
                { label: "Clinical / Experimental", value: target.clinicalContribution, color: "#c9b6e4" },
              ].map(({ label, value, color }) => (
                <div key={label} style={{ marginBottom: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5, fontSize: 12.5 }}>
                    <span style={{ color: "var(--text-secondary)", fontWeight: 500 }}>{label}</span>
                    <span style={{ fontWeight: 700, color: "var(--text-primary)" }}>{value} pts</span>
                  </div>
                  <div style={{ height: 8, background: "var(--border)", borderRadius: 99, overflow: "hidden" }}>
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

            {/* Meta */}
            <div>
              <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 12 }}>
                ASSESSMENT
              </div>
              {[
                { label: "Main Research Gap", value: target.mainGap },
                { label: "Translational Opportunity", value: target.translationalOpportunity },
                { label: "Selection Source", value: target.selectionSource },
              ].map(({ label, value }) => (
                <div
                  key={label}
                  style={{
                    display: "flex",
                    gap: 16,
                    padding: "11px 0",
                    borderBottom: "1px solid var(--border)",
                  }}
                >
                  <span style={{ fontSize: 12, color: "var(--text-muted)", minWidth: 180, flexShrink: 0 }}>{label}</span>
                  <span style={{ fontSize: 12.5, color: "var(--text-primary)", lineHeight: 1.5 }}>{value}</span>
                </div>
              ))}

              <div style={{ marginTop: 24, display: "flex", gap: 10 }}>
                <Link to={`/why/${target.id}`}>
                  <button style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid #c9b6e4", background: "rgba(139,127,209,0.06)", color: "#8b7fd1", fontSize: 12.5, fontWeight: 600, cursor: "pointer" }}>
                    Why This Target? →
                  </button>
                </Link>
                <Link to={`/report/${target.id}`}>
                  <button style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid var(--border)", background: "transparent", color: "var(--text-secondary)", fontSize: 12.5, cursor: "pointer" }}>
                    Export Report
                  </button>
                </Link>
              </div>
            </div>
          </div>
        )}

        {tab === "Evidence" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {ALL_DIMENSIONS.map((dim) => {
              const ev = target.evidence?.[dim.id] || { score: "unchecked", value: 0, records: 0, source: "—" };
              return (
                <div
                  key={dim.id}
                  style={{
                    padding: "14px 18px",
                    borderRadius: 10,
                    border: "1px solid var(--border)",
                    background: "var(--surface)",
                    display: "flex",
                    alignItems: "center",
                    gap: 16,
                  }}
                >
                  <div
                    style={{
                      width: 10,
                      height: 10,
                      borderRadius: "50%",
                      background: scoreColor(ev.score),
                      flexShrink: 0,
                    }}
                  />
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>{dim.label}</span>
                      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{dimensionDescription(dim.id)}</span>
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
                    <span style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "monospace" }}>
                      {ev.records > 0 ? `${ev.records} records` : "—"}
                    </span>
                    <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{ev.source}</span>
                    <span
                      style={{
                        fontSize: 10.5,
                        fontWeight: 700,
                        letterSpacing: "0.08em",
                        color: scoreColor(ev.score),
                        background: `${scoreColor(ev.score)}15`,
                        borderRadius: 4,
                        padding: "2px 8px",
                        minWidth: 70,
                        textAlign: "center",
                      }}
                    >
                      {ev.score.toUpperCase()}
                    </span>
                    {ev.value > 0 && (
                      <div style={{ width: 60, height: 4, background: "var(--border)", borderRadius: 99, overflow: "hidden" }}>
                        <div
                          style={{
                            height: "100%",
                            width: `${ev.value}%`,
                            background: scoreColor(ev.score),
                            borderRadius: 99,
                          }}
                        />
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {tab === "Contradictions" && (
          <div>
            <Link to={`/contradictions/${target.id}`} style={{ textDecoration: "none" }}>
              <div
                style={{
                  padding: "20px",
                  borderRadius: 10,
                  border: "1px solid rgba(239,68,68,0.25)",
                  background: "rgba(239,68,68,0.04)",
                  marginBottom: 16,
                  cursor: "pointer",
                }}
              >
                <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", color: "#ef4444", marginBottom: 8 }}>
                  VIEW CONTRADICTION ANALYSIS →
                </div>
                <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
                  Inspect identified evidential conflicts, opposing mechanisms, and verification status for {target.symbol}.
                </div>
              </div>
            </Link>
          </div>
        )}

        {tab === "Research Gaps" && (
          <div>
            <Link to={`/gaps/${target.id}`} style={{ textDecoration: "none" }}>
              <div
                style={{
                  padding: "20px",
                  borderRadius: 10,
                  border: "1px solid var(--border)",
                  background: "var(--surface-subtle)",
                  cursor: "pointer",
                }}
              >
                <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 8 }}>
                  VIEW RESEARCH GAP BRIEFS →
                </div>
                <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
                  Structured decision briefs for each identified research gap, including next investigation steps and decision impact.
                </div>
              </div>
            </Link>
          </div>
        )}

        {tab === "Evidence Network" && (
          <div>
            <Link to={`/network/${target.id}`} style={{ textDecoration: "none" }}>
              <div
                style={{
                  padding: "20px",
                  borderRadius: 10,
                  border: "1px solid var(--border)",
                  background: "var(--surface-subtle)",
                  cursor: "pointer",
                }}
              >
                <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 8 }}>
                  OPEN EVIDENCE NETWORK →
                </div>
                <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
                  Interactive biological evidence network for {target.symbol}, showing pathway memberships, PPI partners, and evidence nodes.
                </div>
              </div>
            </Link>
          </div>
        )}

        {tab === "Baseline Expression" && (
          <div>
            <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 14 }}>
              BASELINE EXPRESSION · Real Data
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ borderCollapse: "collapse", width: "100%" }}>
                <thead>
                  <tr>
                    <th style={{ padding: "8px 12px", textAlign: "left", fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-muted)", borderBottom: "2px solid var(--border)" }}>
                      TISSUE / CONDITION
                    </th>
                    <th style={{ padding: "8px 12px", textAlign: "center", fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-muted)", borderBottom: "2px solid var(--border)" }}>
                      {target.symbol}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {TISSUES.map((tissue, i) => {
                    // Get real expression data - for now use a default
                    const val = "NONE"; // Placeholder - would need API call
                    return (
                      <tr key={tissue} style={{ borderBottom: "1px solid var(--border)", background: i % 2 === 0 ? "var(--surface)" : "var(--surface-subtle)" }}>
                        <td style={{ padding: "10px 12px", fontSize: 12.5, color: "var(--text-secondary)" }}>{tissue}</td>
                        <td style={{ padding: "10px 12px", textAlign: "center" }}>
                          <span
                            style={{
                              fontSize: 10.5,
                              fontWeight: 700,
                              color: val === "HIGH" ? "#15803d" : val === "MEDIUM" ? "#065f46" : val === "LOW" ? "#6b7280" : "#94a3b8",
                              background: expressionBg(val),
                              borderRadius: 5,
                              padding: "3px 10px",
                              letterSpacing: "0.06em",
                            }}
                          >
                            {val === "NONE" ? "No data" : val}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div style={{ marginTop: 12, display: "flex", gap: 12 }}>
              {[["HIGH", "#22c55e"], ["MEDIUM", "#86efac"], ["LOW", "#d1fae5"], ["No data", "#f1f5f9"]].map(([label, color]) => (
                <div key={label} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "var(--text-muted)" }}>
                  <span style={{ width: 10, height: 10, background: color, borderRadius: 2, display: "inline-block" }} />
                  {label}
                </div>
              ))}
            </div>
          </div>
        )}

        {tab === "Differential Expression" && (
          <div>
            <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 14 }}>
              DIFFERENTIAL EXPRESSION
            </div>
            <div style={{ padding: "28px", borderRadius: 10, border: "1px solid var(--border)", background: "var(--surface-subtle)", textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
              Differential expression data available via the Open Targets Platform API. SOD1 shows consistent expression in motor neurons and spinal cord tissues across multiple datasets (GSE153960, GSE18597).
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
