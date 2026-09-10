/**
 * API Client for the ALS Target Prioritization Backend.
 *
 * Base URL: configured via API_BASE_URL env var, defaults to http://localhost:8000
 * All functions are typed to return properly shaped data matching the backend schemas.
 */

import type {
  RootResponse,
  ContextResponse,
  TargetOut,
  PriorityScoreOut,
  EvidenceRecordOut,
  GapRecordOut,
  GapAnalysisOut,
  ContradictionOut,
  ContradictionRunResponse,
  LiteratureContradictionRunOut,
  GraphResponse,
  MomentumOut,
  PharosCrossChecksOut,
  NarrativeResponse,
  KeyFreeNarrativeResponse,
} from "./types";

// API base URL - can be overridden via environment variable
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Helper: typed fetch wrapper
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `API Error: ${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Root / Context
// ---------------------------------------------------------------------------

export const getRoot = (): Promise<RootResponse> =>
  apiFetch<RootResponse>("/");

export const getContext = (): Promise<ContextResponse> =>
  apiFetch<ContextResponse>("/context");

export const getTargets = (): Promise<TargetOut[]> =>
  apiFetch<TargetOut[]>("/targets/");

// ---------------------------------------------------------------------------
// Targets (Seeding)
// ---------------------------------------------------------------------------

export const seedTargets = (): Promise<TargetOut[]> =>
  apiFetch<TargetOut[]>("/targets/seed", { method: "POST" });

// ---------------------------------------------------------------------------
// PriorityScore
// ---------------------------------------------------------------------------

export const getPriorityScore = (targetId: number): Promise<PriorityScoreOut> =>
  apiFetch<PriorityScoreOut>(`/scoring/target/${targetId}`);

export const computeScores = (targetId: number): Promise<PriorityScoreOut> =>
  apiFetch<PriorityScoreOut>(`/scoring/target/${targetId}/compute`, { method: "POST" });

// ---------------------------------------------------------------------------
// EvidenceRecord
// ---------------------------------------------------------------------------

export const getEvidenceForTarget = (
  targetId: number,
  dimension?: string,
): Promise<EvidenceRecordOut[]> => {
  const dimParam = dimension ? `?dimension=${dimension}` : "";
  return apiFetch<EvidenceRecordOut[]>(`/evidence/target/${targetId}${dimParam}`);
};

// ---------------------------------------------------------------------------
// GapRecord
// ---------------------------------------------------------------------------

export const getGaps = (targetId: number): Promise<GapAnalysisOut> =>
  apiFetch<GapAnalysisOut>(`/gaps/target/${targetId}`);

export const runGapAnalysis = (targetId: number): Promise<GapAnalysisOut> =>
  apiFetch<GapAnalysisOut>(`/gaps/target/${targetId}/run`, { method: "POST" });

// ---------------------------------------------------------------------------
// ContradictionLog
// ---------------------------------------------------------------------------

export const getContradictions = (targetId: number): Promise<ContradictionOut[]> =>
  apiFetch<ContradictionOut[]>(`/contradictions/target/${targetId}`);

export const runContradictionCheck = (targetId: number): Promise<ContradictionRunResponse> =>
  apiFetch<ContradictionRunResponse>(`/contradictions/target/${targetId}/run`, { method: "POST" });

export const runLiteratureContradictionCheck = (targetId: number): Promise<LiteratureContradictionRunOut> =>
  apiFetch<LiteratureContradictionRunOut>(`/contradictions/target/${targetId}/run-literature`, { method: "POST" });

// ---------------------------------------------------------------------------
// Knowledge Graph
// ---------------------------------------------------------------------------

export const getTargetGraph = (targetId: number): Promise<GraphResponse> =>
  apiFetch<GraphResponse>(`/graph/target/${targetId}`);

// ---------------------------------------------------------------------------
// MomentumScore
// ---------------------------------------------------------------------------

export const getMomentum = (targetId: number): Promise<MomentumOut> =>
  apiFetch<MomentumOut>(`/momentum/target/${targetId}`);

// ---------------------------------------------------------------------------
// Pharos Cross-Checks
// ---------------------------------------------------------------------------

export const getPharosCrossChecks = (targetId: number): Promise<PharosCrossChecksOut> =>
  apiFetch<PharosCrossChecksOut>(`/cross-checks/pharos/target/${targetId}`);

// ---------------------------------------------------------------------------
// Narratives
// ---------------------------------------------------------------------------

export const getNarrative = (targetId: number): Promise<KeyFreeNarrativeResponse> =>
  apiFetch<KeyFreeNarrativeResponse>(`/narrative/target/${targetId}`);

export const getLLMNarration = (targetId: number): Promise<NarrativeResponse> =>
  apiFetch<NarrativeResponse>(`/narration/target/${targetId}`);

// ---------------------------------------------------------------------------
// Utility: Get combined target data with scores
// ---------------------------------------------------------------------------

export interface TargetWithData extends TargetOut {
  priorityScore: number;
  evidenceStrength: string;
  consistency: string;
  maturity: string;
  tier: "HIGH" | "MEDIUM" | "LOW";
  dimensionBreakdown: Record<string, number>;
  dimensionRecords: Record<string, { score: string; value: number; records: number; source: string }>;
}

// Helper to convert score to label
export function scoreToLabel(score: number | null): string {
  if (score === null) return "LOW";
  if (score >= 0.8) return "HIGH";
  if (score >= 0.5) return "MEDIUM";
  return "LOW";
}

export function evidenceScoreToLabel(score: number | null): string {
  if (score === null) return "HIGH";
  if (score >= 0.8) return "HIGH";
  if (score >= 0.5) return "MEDIUM";
  if (score >= 0.3) return "WEAK";
  return "NONE";
}

export function tierToLabel(tier: number | null): string {
  if (tier === null) return "LOW";
  if (tier >= 0.8) return "HIGH";
  if (tier >= 0.5) return "MEDIUM";
  return "LOW";
}