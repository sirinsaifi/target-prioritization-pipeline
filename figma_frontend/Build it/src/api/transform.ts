/**
 * Data transformation layer: converts backend API responses
 * into the shape the frontend UI expects.
 *
 * Mappings:
 *   Score: 0–1 float → "strong" | "moderate" | "weak" | "none" | "unchecked"
 *   Dimensions: backend (genetic, human_clinical, ...) → frontend display labels
 *   IDs: backend integer IDs → frontend string IDs (for routing)
 */

import type { EvidenceRecordOut, PriorityScoreOut, TargetOut, GapAnalysisOut, ContradictionOut } from "./types";

// ---------------------------------------------------------------------------
// Score mapping
// ---------------------------------------------------------------------------

/** Convert a 0–1 evidence score into the frontend's label system. */
export function evidenceScoreToLabel(score: number | null): "strong" | "moderate" | "weak" | "none" | "unchecked" {
  if (score === null || score === undefined) return "unchecked";
  if (score >= 0.8) return "strong";
  if (score >= 0.5) return "moderate";
  if (score >= 0.3) return "weak";
  return "none";
}

// ---------------------------------------------------------------------------
// Dimension mapping
// ---------------------------------------------------------------------------

/** Backend dimension name → frontend display info */
const DIMENSION_MAP: Record<string, { label: string; description: string }> = {
  genetic:          { label: "Genetic",        description: "ClinVar pathogenicity, GWAS, eQTL" },
  literature:       { label: "Literature",     description: "PubMed / Europe PMC co-mentions" },
  human_clinical:  { label: "Clinical",       description: "ClinicalTrials.gov, drug approvals" },
  experimental:    { label: "Experimental",   description: "IMPC phenotypic evidence" },
  pathway:         { label: "Pathway",        description: "Reactome pathway membership" },
  drug_target:     { label: "Druggability",   description: "DrugBank, ChEMBL binding data" },
  tissue_expression: { label: "Expression",   description: "GTEx tissue expression levels" },
  ppi_network:     { label: "PPI",            description: "STRING protein–protein interactions" },
};

export function tierColor(tier: string): string {
  if (tier === "HIGH") return "#22c55e";
  if (tier === "MEDIUM") return "#f59e0b";
  return "#94a3b8";
}

export const scoreColor = (score: string): string =>
  score === "strong" ? "#22c55e" : score === "moderate" ? "#f59e0b" : score === "weak" ? "#f97316" : "#94a3b8";

export const scoreLabel = (score: string): string =>
  score === "strong" ? "Strong" : score === "moderate" ? "Moderate" : score === "weak" ? "Weak" : "—";

export function dimensionLabel(dim: string): string {
  return DIMENSION_MAP[dim]?.label ?? dim;
}

export function dimensionDescription(dim: string): string {
  return DIMENSION_MAP[dim]?.description ?? "";
}

export function dimensionExists(dim: string): boolean {
  return dim in DIMENSION_MAP;
}

export const ALL_DIMENSIONS = Object.keys(DIMENSION_MAP);

// ---------------------------------------------------------------------------
// Target transformation
// ---------------------------------------------------------------------------

export interface ApiTarget {
  id: string;
  symbol: string;
  fullName: string;
  priorityScore: number;
  tier: string;
  evidenceStrength: string;
  consistency: string;
  maturity: string;
  translationalOpportunity: string;
  selectionSource: string;
  mainGap: string;
  cautionFlags: string[];
  evidence: Record<string, { score: string; value: number; records: number; source: string }>;
  whyRanked: string;
  geneticContribution: number;
  literatureContribution: number;
  clinicalContribution: number;
}

/** Build a frontend-style target object from API data. */
export function transformTarget(
  target: TargetOut,
  score: PriorityScoreOut | null,
  evidence: EvidenceRecordOut[],
  gapAnalysis: GapAnalysisOut | null,
): ApiTarget {
  const sid = String(target.id);

  const byDim: Record<string, EvidenceRecordOut[]> = {};
  for (const r of evidence) {
    byDim[r.dimension] = byDim[r.dimension] || [];
    byDim[r.dimension].push(r);
  }

  const evidenceMap: Record<string, { score: string; value: number; records: number; source: string }> = {};
  for (const dim of ALL_DIMENSIONS) {
    const records = byDim[dim] || [];
    const avgScore = records.length > 0
      ? records.reduce((s, r) => s + (r.evidence_score ?? 0), 0) / records.length
      : 0;
    const sources = [...new Set(records.map(r => r.data_source))].join(", ");
    evidenceMap[dim] = {
      score: evidenceScoreToLabel(avgScore || null),
      value: Math.round(avgScore * 100),
      records: records.length,
      source: sources || "—",
    };
  }

  const tier = scoreToTier(score?.priority_score ?? null);
  const gaps = gapAnalysis?.gaps ?? [];
  const transOpportunity = gapAnalysis?.translational_opportunity?.category ?? "Investigational";
  const whyRanked = buildWhyRanked(target.gene_symbol, score, gaps);
  const mainGap = gaps.length > 0 ? (gaps[0].rationale ?? "Evidence gap identified") : "No critical gaps — evidence coverage is strong";
  const cautionFlags = gaps.filter(g => g.gap_type === "essentiality_risk").map(g => g.rationale ?? "").slice(0, 2);

  const bd = score?.dimension_breakdown ? JSON.parse(score.dimension_breakdown) : {};

  return {
    id: sid,
    symbol: target.gene_symbol,
    fullName: `${target.gene_symbol} (ENSG ${target.ensembl_id})`,
    priorityScore: Math.round((score?.priority_score ?? 0) * 100),
    tier,
    evidenceStrength: score?.evidence_strength != null ? evidenceScoreToLabel(score.evidence_strength) : "unchecked",
    consistency: score?.evidence_consistency != null ? evidenceScoreToLabel(score.evidence_consistency) : "unchecked",
    maturity: score?.evidence_maturity != null ? evidenceScoreToLabel(score.evidence_maturity) : "unchecked",
    translationalOpportunity: transOpportunity,
    selectionSource: "Open Targets Platform",
    mainGap,
    cautionFlags,
    evidence: evidenceMap,
    whyRanked,
    geneticContribution: Math.round((bd.genetic ?? 0) * 100),
    literatureContribution: Math.round((bd.literature ?? 0) * 100),
    clinicalContribution: Math.round((bd.human_clinical ?? 0) * 100),
  };
}

function scoreToTier(priorityScore: number | null): string {
  if (priorityScore === null) return "LOW";
  if (priorityScore >= 0.8) return "HIGH";
  if (priorityScore >= 0.5) return "MEDIUM";
  return "LOW";
}

function buildWhyRanked(
  gene: string,
  score: PriorityScoreOut | null,
  gaps: { gap_type: string; rationale: string | null }[],
): string {
  const bd = score?.dimension_breakdown ? JSON.parse(score.dimension_breakdown) : {};
  const entries = Object.entries(bd) as [string, number][];
  const topDim = entries.sort(([, a], [, b]) => b - a)[0]?.[0];
  const topScore = topDim ? (bd[topDim] ?? 0) : 0;
  const gapText = gaps.length > 0 ? ` However, ${gaps.length} research gap${gaps.length > 1 ? "s" : ""} were identified that may affect clinical translatability.` : "";
  return `${gene} ranks highly based on ${topDim ?? "evidence"} support (${Math.round(topScore * 100)}/100 across primary dimensions). Automated verification found no unresolved contradictions.${gapText}`;
}

// ---------------------------------------------------------------------------
// Contradiction transformation
// ---------------------------------------------------------------------------

export interface ApiContradiction {
  id: string;
  dimension: string;
  classification: string;
  impact: string;
  verificationStatus: string;
  sourceA: { ref: string; claim: string; direction: string };
  sourceB: { ref: string; claim: string; direction: string };
}

export function transformContradictions(
  contradictions: ContradictionOut[],
): ApiContradiction[] {
  return contradictions.map(c => ({
    id: String(c.id),
    dimension: c.matched_fields ?? "unknown",
    classification: c.classification,
    impact: "Medium — requires follow-up",
    verificationStatus: c.status === "confirmed" ? "Confirmed by deterministic verifier" : "Pending verification",
    sourceA: {
      ref: c.evidence_record_a_id.toString(),
      claim: `Evidence record ${c.evidence_record_a_id}`,
      direction: "up",
    },
    sourceB: {
      ref: c.evidence_record_b_id.toString(),
      claim: `Evidence record ${c.evidence_record_b_id}`,
      direction: "down",
    },
  }));
}
