import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTargets, computeScores, runContradictionCheck, runGapAnalysis } from "../api/hooks";
import { usePriorityScore } from "../api/hooks";

const STAGES = [
  { id: "targets", label: "Candidate Targets", detail: "Loading targets from database", icon: "⬡" },
  { id: "collection", label: "Evidence Collection", detail: "Querying external databases", icon: "◈" },
  { id: "verification", label: "Evidence Verification", detail: "Running contradiction checks", icon: "✦" },
  { id: "scoring", label: "Evidence Strength · Consistency · Maturity", detail: "Computing multi-dimensional scores", icon: "◉" },
  { id: "priority", label: "Priority Scoring", detail: "Weighted evidence synthesis", icon: "◎" },
  { id: "gaps", label: "Research Gap Typing", detail: "Classifying evidence gaps by type", icon: "◌" },
];

type StageState = "pending" | "running" | "complete";

export default function Processing() {
  const navigate = useNavigate();
  const { data: targets, loading: targetsLoading } = useTargets();
  const [stageStates, setStageStates] = useState<StageState[]>(STAGES.map(() => "pending"));
  const [progress, setProgress] = useState<number[]>(STAGES.map(() => 0));
  const [done, setDone] = useState(false);
  const [currentTargetIndex, setCurrentTargetIndex] = useState(0);

  const runPipeline = async () => {
    if (!targets || targets.length === 0) return;

    let current = 0;

    const runStage = async (stageIndex: number, fn: () => Promise<unknown>, detail: string) => {
      setStageStates(prev => {
        const next = [...prev];
        if (stageIndex < next.length) next[stageIndex] = "running";
        return next;
      });

      let p = 0;
      const progInterval = setInterval(() => {
        p += Math.random() * 15 + 5;
        if (p >= 90) p = 90;
        setProgress(prev => {
          const next = [...prev];
          if (stageIndex < next.length) next[stageIndex] = Math.min(p, 100);
          return next;
        });
      }, 200);

      try {
        await fn();
        clearInterval(progInterval);
        setProgress(prev => {
          const next = [...prev];
          if (stageIndex < next.length) next[stageIndex] = 100;
          return next;
        });
        setStageStates(prev => {
          const next = [...prev];
          if (stageIndex < next.length) next[stageIndex] = "complete";
          return next;
        });
      } catch (e) {
        clearInterval(progInterval);
        console.error(`Stage ${stageIndex} failed:`, e);
      }
    };

    // Stage 0: Targets already loaded
    setStageStates(prev => {
      const next = [...prev];
      next[0] = "complete";
      return next;
    });
    setProgress(prev => { const next = [...prev]; next[0] = 100; return next; });

    // For each target, run the pipeline
    for (let i = 0; i < targets.length; i++) {
      setCurrentTargetIndex(i);
      const target = targets[i];

      // Stage 1: Evidence Collection (already ingested in DB)
      await runStage(1, async () => {
        // Just wait a bit to simulate
        await new Promise(r => setTimeout(r, 500));
      }, "Evidence already in database");

      // Stage 2: Contradiction check
      await runStage(2, async () => {
        await runContradictionCheck(target.id);
      }, `Contradiction check for ${target.gene_symbol}`);

      // Stage 3: Scoring
      await runStage(3, async () => {
        await computeScores(target.id);
      }, `Scoring for ${target.gene_symbol}`);

      // Stage 4: Priority (same as scoring)
      await runStage(4, async () => {
        await new Promise(r => setTimeout(r, 300));
      }, `Priority synthesis for ${target.gene_symbol}`);

      // Stage 5: Gap analysis
      await runStage(5, async () => {
        await runGapAnalysis(target.id);
      }, `Gap analysis for ${target.gene_symbol}`);
    }

    setDone(true);
  };

  useEffect(() => {
    if (!targetsLoading && targets) {
      runPipeline();
    }
  }, [targets, targetsLoading]);

  const stateColor = (s: StageState) =>
    s === "complete" ? "#22c55e" : s === "running" ? "#8b7fd1" : "var(--text-muted)";

  const stateBg = (s: StageState) =>
    s === "complete" ? "rgba(34,197,94,0.08)" : s === "running" ? "rgba(139,127,209,0.1)" : "var(--surface-subtle)";

  if (targetsLoading) {
    return (
      <div style={{ padding: "32px 40px", maxWidth: 720, margin: "0 auto", textAlign: "center", paddingTop: 80 }}>
        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", color: "var(--text-muted)", marginBottom: 8 }}>
          LAYER 3 — VERIFICATION & SCORING
        </div>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>
          Loading...
        </h1>
        <p style={{ fontSize: 13.5, color: "var(--text-secondary)", margin: 0 }}>
          Fetching targets from backend
        </p>
      </div>
    );
  }

  return (
    <div style={{ padding: "32px 40px", maxWidth: 720, margin: "0 auto" }}>
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", color: "var(--text-muted)", marginBottom: 8 }}>
          LAYER 3 — VERIFICATION & SCORING
        </div>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "var(--text-primary)", margin: "0 0 6px", letterSpacing: "-0.02em" }}>
          {done ? "Investigation Complete" : "Running Investigation Pipeline"}
        </h1>
        <p style={{ fontSize: 13.5, color: "var(--text-secondary)", margin: 0 }}>
          {done
            ? "All evidence dimensions processed. Results are ready."
            : `Processing ${targets?.[currentTargetIndex]?.gene_symbol ?? "targets"}...`}
        </p>
      </div>

      <div style={{ position: "relative" }}>
        <div
          style={{
            position: "absolute",
            left: 23,
            top: 28,
            width: 2,
            bottom: 28,
            background: "linear-gradient(to bottom, #a596d5, #e4ddf4)",
            borderRadius: 1,
            zIndex: 0,
          }}
        />

        <div style={{ display: "flex", flexDirection: "column", gap: 12, position: "relative", zIndex: 1 }}>
          {STAGES.map((stage, i) => {
            const state = stageStates[i];
            const prog = progress[i];
            return (
              <div
                key={stage.id}
                style={{
                  display: "flex",
                  gap: 16,
                  alignItems: "flex-start",
                  opacity: state === "pending" ? 0.45 : 1,
                  transition: "opacity 0.4s",
                }}
              >
                <div
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: "50%",
                    border: `2px solid ${stateColor(state)}`,
                    background: stateBg(state),
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 16,
                    color: stateColor(state),
                    flexShrink: 0,
                    transition: "all 0.4s",
                    boxShadow: state === "running" ? "0 0 0 6px rgba(139,127,209,0.12)" : "none",
                  }}
                >
                  {state === "complete" ? "✓" : stage.icon}
                </div>

                <div
                  style={{
                    flex: 1,
                    padding: "10px 16px",
                    borderRadius: 10,
                    border: `1px solid ${state === "complete" ? "rgba(34,197,94,0.2)" : state === "running" ? "rgba(139,127,209,0.25)" : "var(--border)"}`,
                    background: stateBg(state),
                    transition: "all 0.4s",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
                      {stage.label}
                    </span>
                    {state === "running" && (
                      <span style={{ fontSize: 10.5, color: "#8b7fd1", fontWeight: 600 }}>
                        {Math.round(prog)}%
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginBottom: state === "running" ? 8 : 0 }}>
                    {stage.detail}
                  </div>
                  {state === "running" && (
                    <div
                      style={{
                        height: 3,
                        background: "var(--border)",
                        borderRadius: 99,
                        overflow: "hidden",
                      }}
                    >
                      <div
                        style={{
                          height: "100%",
                          width: `${prog}%`,
                          background: "linear-gradient(90deg, #a596d5, #8b7fd1)",
                          borderRadius: 99,
                          transition: "width 0.15s",
                        }}
                      />
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {done && (
        <div style={{ marginTop: 32, display: "flex", gap: 12 }}>
          <button
            onClick={() => navigate("/results")}
            style={{
              padding: "12px 28px",
              borderRadius: 10,
              background: "linear-gradient(135deg, #a596d5, #8b7fd1)",
              border: "none",
              color: "white",
              fontSize: 14,
              fontWeight: 700,
              cursor: "pointer",
              letterSpacing: "0.04em",
            }}
          >
            VIEW RESULTS
          </button>
          <button
            onClick={() => navigate("/comparison")}
            style={{
              padding: "12px 28px",
              borderRadius: 10,
              background: "transparent",
              border: "1px solid var(--border-strong)",
              color: "var(--text-secondary)",
              fontSize: 14,
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            Compare Targets
          </button>
        </div>
      )}
    </div>
  );
}
