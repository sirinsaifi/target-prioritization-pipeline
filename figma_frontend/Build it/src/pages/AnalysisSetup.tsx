import { useNavigate } from "react-router-dom";
import { useTargets } from "../api/hooks";
import { dimensionLabel } from "../api/transform";

export default function AnalysisSetup() {
  const navigate = useNavigate();
  const { data: targets, loading } = useTargets();

  const disease = "Amyotrophic Lateral Sclerosis";
  const diseaseId = "MONDO_0004976";

  if (loading) {
    return (
      <div style={{ padding: "32px 40px", maxWidth: 900, margin: "0 auto", textAlign: "center", color: "var(--text-muted)", paddingTop: 80 }}>
        Loading targets from backend...
      </div>
    );
  }

  const targetList = targets ?? [];

  return (
    <div style={{ padding: "32px 40px", maxWidth: 900, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", color: "var(--text-muted)", marginBottom: 8 }}>
          LAYER 1 — INPUT
        </div>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>
          Analysis Setup
        </h1>
        <p style={{ fontSize: 13.5, color: "var(--text-secondary)", margin: 0, lineHeight: 1.6 }}>
          Configure the scientific investigation parameters. All evidence sources are pre-integrated.
        </p>
      </div>

      {/* Disease panel */}
      <section style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 10 }}>
          DISEASE
        </div>
        <div
          style={{
            padding: "20px 24px",
            borderRadius: 12,
            border: "1px solid var(--border)",
            background: "var(--surface)",
            display: "flex",
            alignItems: "center",
            gap: 20,
          }}
        >
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: 10,
              background: "var(--brand-gradient-subtle)",
              border: "1px solid #d4cce8",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 20,
              flexShrink: 0,
            }}
          >
            🧬
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 15.5, fontWeight: 700, color: "var(--text-primary)", marginBottom: 3 }}>
              {disease}
            </div>
            <div style={{ fontSize: 11.5, color: "var(--text-muted)", fontFamily: "monospace" }}>
              {diseaseId}
            </div>
          </div>
          <div
            style={{
              fontSize: 10.5,
              fontWeight: 600,
              letterSpacing: "0.08em",
              color: "#22c55e",
              background: "rgba(34,197,94,0.08)",
              border: "1px solid rgba(34,197,94,0.2)",
              borderRadius: 5,
              padding: "3px 9px",
            }}
          >
            CONFIRMED
          </div>
        </div>
      </section>

      {/* Candidate targets */}
      <section style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 10 }}>
          CANDIDATE TARGETS — {targetList.length} configured
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {targetList.map((t) => (
            <div
              key={t.id}
              style={{
                padding: "14px 20px",
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
                  width: 36,
                  height: 36,
                  borderRadius: 8,
                  background: "linear-gradient(135deg, #e8d6ee, #c9b6e4)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 10,
                  fontWeight: 700,
                  color: "#6b5ed4",
                  letterSpacing: "0.02em",
                  flexShrink: 0,
                }}
              >
                {t.gene_symbol.substring(0, 3)}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                  <span style={{ fontSize: 13.5, fontWeight: 700, color: "var(--text-primary)", fontFamily: "monospace" }}>
                    {t.gene_symbol}
                  </span>
                  <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{t.ensembl_id}</span>
                </div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>Open Targets Platform</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Evidence dimensions */}
      <section style={{ marginBottom: 36 }}>
        <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 10 }}>
          EVIDENCE DIMENSIONS — 8 active
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
            gap: 8,
          }}
        >
          {["Genetic", "Literature", "Clinical", "Experimental", "Pathway", "Druggability", "Expression", "PPI"].map((dim) => (
            <div
              key={dim}
              style={{
                padding: "12px 14px",
                borderRadius: 8,
                border: "1px solid var(--border)",
                background: "var(--surface)",
                display: "flex",
                alignItems: "flex-start",
                gap: 10,
              }}
            >
              <div
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: "linear-gradient(135deg, #a596d5, #8b7fd1)",
                  marginTop: 4,
                  flexShrink: 0,
                }}
              />
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)", marginBottom: 2 }}>
                  {dim}
                </div>
                <div style={{ fontSize: 10.5, color: "var(--text-muted)", lineHeight: 1.4 }}>
                  {dim === "Genetic" ? "ClinVar, GWAS, eQTL" :
                   dim === "Literature" ? "PubMed / Europe PMC" :
                   dim === "Clinical" ? "ClinicalTrials.gov" :
                   dim === "Experimental" ? "IMPC phenotypic" :
                   dim === "Pathway" ? "Reactome membership" :
                   dim === "Druggability" ? "DrugBank, ChEMBL" :
                   dim === "Expression" ? "GTEx tissue data" :
                   dim === "PPI" ? "STRING interactions" : ""}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <button
        onClick={() => navigate("/processing")}
        style={{
          padding: "13px 32px",
          borderRadius: 10,
          background: "linear-gradient(135deg, #a596d5, #8b7fd1)",
          border: "none",
          color: "white",
          fontSize: 14,
          fontWeight: 700,
          letterSpacing: "0.04em",
          cursor: "pointer",
        }}
      >
        RUN ANALYSIS
      </button>
    </div>
  );
}
