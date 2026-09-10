import { useState, useEffect } from "react";
import { getTargets, getEvidenceForTarget, getContradictions, getGaps, getPriorityScore, computeScores, runGapAnalysis, runContradictionCheck, getRoot, getMomentum, getTargetGraph } from "./client";
import type { TargetOut, PriorityScoreOut, EvidenceRecordOut, GapAnalysisOut, ContradictionOut, PipelineStatusResponse } from "./types";
import { transformTarget, transformContradictions, ALL_DIMENSIONS, type ApiTarget } from "./transform";

export { computeScores, runContradictionCheck, runGapAnalysis } from "./client";

// ---------------------------------------------------------------------------
// Generic fetch hook
// ---------------------------------------------------------------------------

function useApiData<T>(fetcher: () => Promise<T>, deps: unknown[] = []): { data: T | null; loading: boolean; error: string | null } {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetcher()
      .then(d => { if (!cancelled) { setData(d); setError(null); } })
      .catch(e => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, loading, error };
}

// ---------------------------------------------------------------------------
// Targets
// ---------------------------------------------------------------------------

export function useTargets() {
  return useApiData(() => getTargets());
}

export function useApiTargets() {
  return useApiData(() => getTargets());
}

// ---------------------------------------------------------------------------
// Single target with full data
// ---------------------------------------------------------------------------

export function useTargetData(targetId: number) {
  const [apiTarget, setApiTarget] = useState<ApiTarget | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      getTargets(),
      getPriorityScore(targetId),
      getEvidenceForTarget(targetId),
      getGaps(targetId),
      getContradictions(targetId),
    ])
      .then(([targets, score, evidence, gapAnalysis, contradictions]) => {
        if (cancelled) return;
        const target = targets.find(t => t.id === targetId) ?? targets[0];
        const apiT = transformTarget(target, score, evidence, gapAnalysis as GapAnalysisOut);
        setApiTarget(apiT);
        setError(null);
      })
      .catch(e => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [targetId]);

  return { data: apiTarget, loading, error };
}

// ---------------------------------------------------------------------------
// Priority score
// ---------------------------------------------------------------------------

export function usePriorityScore(targetId: number) {
  const [data, setData] = useState<PriorityScoreOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getPriorityScore(targetId)
      .then(d => { if (!cancelled) setData(d); })
      .catch(e => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [targetId]);

  return { data, loading, error };
}

// ---------------------------------------------------------------------------
// Evidence
// ---------------------------------------------------------------------------

export function useEvidence(targetId: number, dimension?: string) {
  return useApiData(() => getEvidenceForTarget(targetId, dimension), [targetId, dimension]);
}

// ---------------------------------------------------------------------------
// Contradictions
// ---------------------------------------------------------------------------

export function useContradictions(targetId: number) {
  return useApiData(() => getContradictions(targetId), [targetId]);
}

// ---------------------------------------------------------------------------
// Gap analysis
// ---------------------------------------------------------------------------

export function useGapAnalysis(targetId: number) {
  return useApiData(() => getGaps(targetId), [targetId]);
}

// ---------------------------------------------------------------------------
// Pipeline status
// ---------------------------------------------------------------------------

export function usePipelineStatus(targetId: number) {
  const [status, setStatus] = useState<PipelineStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getContradictions(targetId).then(() => true).catch(() => false),
      getPriorityScore(targetId).then(() => true).catch(() => false),
      getGaps(targetId).then(() => true).catch(() => false),
    ])
      .then(([contradictionsDone, scoringDone, gapsDone]) => {
        if (cancelled) return;
        setStatus({
          contradictions_run: contradictionsDone,
          scoring_computed: scoringDone,
          gaps_run: gapsDone,
        });
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [targetId]);

  return { data: status, loading, error };
}

// ---------------------------------------------------------------------------
// Root / context
// ---------------------------------------------------------------------------

export function useRootData() {
  return useApiData(() => getRoot());
}

// ---------------------------------------------------------------------------
// Dimension labels (constant, no API needed)
// ---------------------------------------------------------------------------

export function useEvidenceDimensions() {
  return ALL_DIMENSIONS.map(dim => ({
    id: dim,
    label: dim.charAt(0).toUpperCase() + dim.slice(1).replace("_", " "),
    description: "",
  }));
}
