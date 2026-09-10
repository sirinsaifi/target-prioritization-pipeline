import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTargets, useEvidence, useTargetData } from "../api/hooks";
import { dimensionLabel } from "../api/transform";

const scoreColor = (score: string): string => {
  if (score === "strong") return "#22c55e";
  if (score === "moderate") return "#f59e0b";
  if (score === "weak") return "#f97316";
  if (score === "none") return "#94a3b8";
  return "#e2e8f0";
};

const scoreBg = (score: string): string => {
  if (score === "strong") return "rgba(34,197,94,0.1)";
  if (score === "moderate") return "rgba(245,158,11,0.1)";
  if (score === "weak") return "rgba(249,115,22,0.1)";
  if (score === "none") return "rgba(148,163,184,0.07)";
  return "rgba(226,232,241,0.1)";
};

const scoreLabel = (score: string): string => {
  if (score === "strong") return "S";
  if (score === "moderate") return "M";
  if (score === "weak") return "W";
  if (score === "none") return "—";
  if (score === "unchecked") return "?";
  return "?";
};

const tierColor = (t: string) => (t === "HIGH" ? "#22c55e" : t === "MEDIUM" ? "#f59e0b" : "#94a3b8");

interface DrawerProps {
  targetId: string;
  dimId: string;
  onClose: () => void;
  evidenceList: Array<{ dimension: string; data_source: string; evidence_score: number; records_count: number }>;
}

function EvidenceDrawer({ targetId, dimId, onClose, evidenceList }: DrawerProps) {
  const evs = evidenceList.filter(e => e.dimension === dimId);
  const score = evs.length > 0 ? evs[0].evidence_score : 0;
  const scoreNum = Math.round(score * 100);
  const label = score >= 0.8 ? "Strong" : score >= 0.5 ? "Moderate" : score >= 0.3 ? "Weak" : "No Evidence";
  const color = scoreColor(label.toLowerCase());

  const dimensionInfo = {
    genetic: "ClinVar pathogenicity, GWAS, eQTL variants",
    literature: "PubMed / Europe PMC co-mentions",
    human_clinical: "ClinicalTrials.gov, drug approvals",
    experimental: "IMPC phenotypic evidence",
    pathway: "Reactome pathway membership",
    drug_target: "DrugBank, ChEMBL binding data",
    tissue_expression: "GTEx tissue expression levels",
    ppi_network: "STRING protein–protein interactions",
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 50,
        display: "flex",
        justifyContent: "flex-end",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "rgba(26,22,40,0.25)",
          backdropFilter: "blur(2px)",
        }}
        onClick={onClose}
      />
      <div
        style={{
          position: "relative",
          width: 400,
          height: "100%",
          background: "var(--surface)",
          borderLeft: "1px solid var(--border)",
          padding: 28,
          overflowY: "auto",
          animation: "slideIn 0.2s ease",
        }}
      >
        <button
          onClick={onClose}
          style={{
            position: "absolute",
            top: 20,
            right: 20,
            background: "none",
            border: "none",
            cursor: "pointer",
            color: "var(--text-muted)",
            fontSize: 18,
          }}
        >
          ✕
        </button>

        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 4 }}>
          EVIDENCE DRILL-DOWN
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 4 }}>
          <span style={{ fontSize: 18, fontWeight: 700, color: "var(--text-primary)", fontFamily: "monospace" }}>
            Target {targetId}
          </span>
          <span style={{ fontSize: 14, color: "var(--text-secondary)" }}>· {dimensionLabel(dimId)}</span>
        </div>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 20 }}>{dimensionInfo[dimId as keyof typeof dimensionInfo] ?? ""}</div>

        <div
          style={{
            padding: "16px",
            borderRadius: 10,
            background: scoreBg(label.toLowerCase()),
            border: `1px solid ${color}30`,
            marginBottom: 16,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", color: color }}>
              {label.toUpperCase()}
            </span>
            <span style={{ fontSize: 22, fontWeight: 700, color: "var(--text-primary)", lineHeight: 1 }}>{scoreNum}</span>
          </div>
          <div
            style={{
              height: 4,
              background: "rgba(0,0,0,0.06)",
              borderRadius: 99,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                height: "100%",
                width: `${scoreNum}%`,
                background: color,
                borderRadius: 99,
              }}
            />
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {evs.slice(0, 10).map((ev, i) => (
            <div
              key={i}
              style={{
                padding: "8px 12px",
                borderRadius: 8,
                border: "1px solid var(--border)",
                background: "var(--surface)",
                fontSize: 11,
                color: "var(--text-secondary)",
              }}
            >
              <div style={{ fontFamily: "monospace", fontWeight: 600, color: "var(--text-primary)" }}>
                {ev.data_source}
              </div>
              <div style={{ fontSize: 10, color: "var(--text-muted)" }}>
                score: {ev.evidence_score.toFixed(2)}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// Evidence dimensions for the UI
const EVIDENCE_DIMENSIONS = [
  { id: "genetic", label: "Genetic", description: "ClinVar, GWAS, eQTL" },
  { id: "literature", label: "Literature", description: "PubMed / Europe PMC" },
  { id: "human_clinical", label: "Clinical", description: "ClinicalTrials.gov" },
  { id: "experimental", label: "Experimental", description: "IMPC phenotypic" },
  { id: "pathway", label: "Pathway", description: "Reactome pathway" },
  { id: "drug_target", label: "Druggability", description: "DrugBank, ChEMBL" },
  { id: "tissue_expression", label: "Expression", description: "GTEx tissue data" },
  { id: "ppi_network", label: "PPI", description: "STRING interactions" },
];

export default function Results() {
  const navigate = useNavigate();
  const { data: targets } = useTargets();
  const { data: targetData, loading: loadingTarget } = useTargetData(1); // We'll use the first target
  const [selected, setSelected] = useState<{ targetId: string; dimId: string } | null>(null);
  const [evidenceForAll, setEvidenceForAll] = useState<Record<string, Array<{ dimension: string; data_source: string; evidence_score: number }>>>({});

  useEffect(() => {
    const fetchEvidence = async () => {
      if (!targets) return;
      for (const t of targets) {
        const evs = await fetch(`/evidence/target/${t.id}`).then(r => r.json()).catch(() => []);
        setEvidenceForAll(prev => ({ ...prev, [t.id]: evs }));
      }
    };
    fetchEvidence();
  }, [targets]);

  const scoreColor = (s: string) =>
    s === "strong" ? "#22c55e" : s === "moderate" ? "#f59e0b" : s === "weak" ? "#f97316" : s === "none" ? "#94a3b8" : "#e2e8f0";
  const scoreBg = (s: string) =>
    s === "strong" ? "rgba(34,197,94,0.1)" : s === "moderate" ? "rgba(245,158,11,0.1)" : "rgba(148,163,184,0.07)";
  const scoreLabel = (s: string) =>
    s === "strong" ? "S" : s === "moderate" ? "M" : s === "weak" ? "W" : s === "none" ? "—" : "?";
  const tierColor = (t: string) => (t === "HIGH" ? "#22c55e" : t === "MEDIUM" ? "#f59e0b" : "#94a3b8");

  const displayTargets = targetData ? [targetData as unknown as ApiTarget] : [];

  return (
    <div style={{ padding: "32px 40px" }}>
      <div style={{ marginBottom: 28 }}>
        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", color: "var(--text-muted)", marginBottom: 8 }}>
          LAYER 2 — EVIDENCE MATRIX
        </div>
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
          <div>
            <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 5px", letterSpacing: "-0.02em" }}>
              Results Dashboard
            </h1>
            <p style={{ fontSize: 13.5, color: "var(--text-secondary)", margin: 0 }}>
              {displayTargets.length > 0
                ? `${displayTargets.length} targets · 8 evidence dimensions · Click any cell to inspect evidence records`
                : "Loading target data from backend..."}
            </p>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {[
              { color: "#22c55e", label: "Strong" },
              { color: "#f59e0b", label: "Moderate" },
              { color: "#f97316", label: "Weak" },
              { color: "#94a3b8", label: "No Evidence" },
              { color: "#e2e8f0", label: "Unchecked" },
            ].map(({ color, label }) => (
              <div key={label} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "var(--text-muted)" }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, display: "inline-block" }} />
                {label}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 12 }}>
          <thead>
            <tr>
              <th
                style={{
                  padding: "10px 14px",
                  textAlign: "left",
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: "0.1em",
                  color: "var(--text-muted)",
                  borderBottom: "2px solid var(--border)",
                  background: "var(--surface)",
                  position: "sticky",
                  left: 0,
                  zIndex: 2,
                  minWidth: 180,
                }}
              >
                TARGET
              </th>
              <th
                style={{
                  padding: "10px 10px",
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: "0.08em",
                  color: "var(--text-muted)",
                  borderBottom: "2px solid var(--border)",
                  textAlign: "center",
                  whiteSpace: "nowrap",
                  minWidth: 64,
                }}
              >
                SCORE
              </th>
              <th
                style={{
                  padding: "10px 10px",
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: "0.08em",
                  color: "var(--text-muted)",
                  borderBottom: "2px solid var(--border)",
                  textAlign: "center",
                  whiteSpace: "nowrap",
                  minWidth: 56,
                }}
              >
                TIER
              </th>
              {EVIDENCE_DIMENSIONS.map(dim => (
                <th
                  key={dim.id}
                  style={{
                    padding: "10px 6px",
                    fontSize: 9,
                    fontWeight: 700,
                    letterSpacing: "0.06em",
                    color: "var(--text-muted)",
                    borderBottom: "2px solid var(--border)",
                    textAlign: "center",
                    whiteSpace: "nowrap",
                    minWidth: 60,
                    transform: "rotate(-20deg)",
                    transformOrigin: "bottom center",
                  }}
                >
                  {dim.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayTargets.map((target, ri) => (
              <tr key={target.id} style={{ borderBottom: "1px solid var(--border)" }}>
                <td
                  style={{
                    padding: "12px 14px",
                    position: "sticky",
                    left: 0,
                    background: ri % 2 === 0 ? "var(--surface)" : "var(--surface-subtle)",
                    zIndex: 1,
                  }}
                >
                  <button
                    onClick={() => navigate(`/target/${target.id}`)}
                    style={{ background: "none", border: "none", cursor: "pointer", textAlign: "left", padding: 0 }}
                  >
                    <div style={{ fontSize: 13.5, fontWeight: 700, color: "#8b7fd1", fontFamily: "monospace", letterSpacing: "0.02em" }}>
                      {target.symbol}
                    </div>
                    <div style={{ fontSize: 10.5, color: "var(--text-muted)", marginTop: 1 }}>
                      {target.fullName?.substring(0, 28) ?? target.ensembl_id}
                    </div>
                  </button>
                </td>

                <td
                  style={{
                    padding: "12px 10px",
                    textAlign: "center",
                    background: ri % 2 === 0 ? "var(--surface)" : "var(--surface-subtle)",
                  }}
                >
                  <div style={{ fontSize: 17, fontWeight: 700, color: "var(--text-primary)", lineHeight: 1 }}>
                    {target.priorityScore}
                  </div>
                </td>

                <td
                  style={{
                    padding: "12px 10px",
                    textAlign: "center",
                    background: ri % 2 === 0 ? "var(--surface)" : "var(--surface-subtle)",
                  }}
                >
                  <span
                    style={{
                      fontSize: 9.5,
                      fontWeight: 700,
                      letterSpacing: "0.08em",
                      color: tierColor(target.tier),
                      background: `${tierColor(target.tier)}15`,
                      borderRadius: 4,
                      padding: "2px 6px",
                    }}
                  >
                    {target.tier}
                  </span>
                </td>

                {EVIDENCE_DIMENSIONS.map(dim => {
                  const ev = target.evidence?.[dim.id] || { score: "unchecked", value: 0, records: 0, source: "—" };
                  return (
                    <td
                      key={dim.id}
                      onClick={() => setSelected({ targetId: target.id, dimId: dim.id })}
                      style={{
                        padding: "8px 6px",
                        textAlign: "center",
                        cursor: "pointer",
                        background: ri % 2 === 0 ? "var(--surface)" : "var(--surface-subtle)",
                        transition: "background 0.1s",
                      }}
                      onMouseEnter={e => ((e.currentTarget as HTMLElement).style.background = "rgba(139,127,209,0.07)")}
                      onMouseLeave={e => ((e.currentTarget as HTMLElement).style.background = ri % 2 === 0 ? "var(--surface)" : "var(--surface-subtle)")}
                    >
                      <div
                        style={{
                          width: 28,
                          height: 28,
                          borderRadius: 7,
                          background: scoreBg(ev.score),
                          border: `1.5px solid ${scoreColor(ev.score)}40`,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          margin: "0 auto",
                          fontSize: 10,
                          fontWeight: 700,
                          color: scoreColor(ev.score),
                        }}
                      >
                        {scoreLabel(ev.score)}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected && evidenceForAll[selected.targetId] && (
        <EvidenceDrawer
          targetId={selected.targetId}
          dimId={selected.dimId}
          onClose={() => setSelected(null)}
          evidenceList={evidenceForAll[selected.targetId]}
        />
      )}

      {displayTargets.length === 0 && (
        <div style={{ padding: "40px", textAlign: "center", color: "var(--text-muted)" }}>
          Loading target data...
        </div>
      )}
    </div>
  );
}
