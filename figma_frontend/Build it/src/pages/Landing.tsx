import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useRootData, useTargets } from "../api/hooks";
import { dimensionLabel } from "../api/transform";

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  opacity: number;
  pulse: number;
  pulseSpeed: number;
}

function ParticleCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const particlesRef = useRef<Particle[]>([]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;

    const resize = () => {
      canvas.width = canvas.offsetWidth * window.devicePixelRatio;
      canvas.height = canvas.offsetHeight * window.devicePixelRatio;
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
      initParticles();
    };

    const initParticles = () => {
      const count = Math.floor((canvas.offsetWidth * canvas.offsetHeight) / 10000);
      particlesRef.current = Array.from({ length: Math.min(count, 120) }, () => ({
        x: Math.random() * canvas.offsetWidth,
        y: Math.random() * canvas.offsetHeight,
        vx: (Math.random() - 0.5) * 0.25,
        vy: (Math.random() - 0.5) * 0.25,
        radius: Math.random() * 2 + 0.5,
        opacity: Math.random() * 0.5 + 0.15,
        pulse: Math.random() * Math.PI * 2,
        pulseSpeed: Math.random() * 0.02 + 0.005,
      }));
    };

    resize();
    window.addEventListener("resize", resize);

    let t = 0;
    const draw = () => {
      ctx.clearRect(0, 0, canvas.offsetWidth, canvas.offsetHeight);
      t += 0.005;

      const ps = particlesRef.current;
      const w = canvas.offsetWidth;
      const h = canvas.offsetHeight;

      for (let i = 0; i < ps.length; i++) {
        for (let j = i + 1; j < ps.length; j++) {
          const dx = ps[i].x - ps[j].x;
          const dy = ps[i].y - ps[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 120) {
            const alpha = (1 - dist / 120) * 0.12;
            ctx.beginPath();
            ctx.strokeStyle = `rgba(165, 150, 213, ${alpha})`;
            ctx.lineWidth = 0.7;
            ctx.moveTo(ps[i].x, ps[i].y);
            ctx.lineTo(ps[j].x, ps[j].y);
            ctx.stroke();
          }
        }
      }

      ps.forEach((p) => {
        p.pulse += p.pulseSpeed;
        const pulsedOpacity = p.opacity + Math.sin(p.pulse) * 0.08;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(139, 127, 209, ${pulsedOpacity})`;
        ctx.fill();

        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0) p.x = w;
        if (p.x > w) p.x = 0;
        if (p.y < 0) p.y = h;
        if (p.y > h) p.y = 0;
      });

      if (Math.sin(t * 3) > 0.97 && ps.length > 0) {
        const anchor = ps[Math.floor(Math.random() * ps.length)];
        const radius = (Math.sin(t * 3) - 0.97) * 300;
        ctx.beginPath();
        ctx.arc(anchor.x, anchor.y, radius, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(139,127,209, ${(0.03 * (1 - radius / 300)).toFixed(3)})`;
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      animRef.current = requestAnimationFrame(draw);
    };

    draw();
    return () => {
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(animRef.current);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
    />
  );
}

const PILLS = ["Genetic", "Clinical", "Functional", "Literature", "Druggability", "Safety", "Expression", "Animal Model", "Pathway", "PPI", "Biomarker"];

export default function Landing() {
  const navigate = useNavigate();
  const rootData = useRootData();
  const targets = useTargets();
  const [disease, setDisease] = useState("Amyotrophic Lateral Sclerosis");
  const [diseaseId, setDiseaseId] = useState("MONDO_0004976");

  useEffect(() => {
    if (rootData.data) {
      setDisease(rootData.data.disease);
      setDiseaseId(rootData.data.disease_efo_id);
    }
  }, [rootData.data]);

  const targetSymbols = targets.data?.map(t => t.gene_symbol) ?? [];
  const evidenceCount = targets.data?.length ? "1,850+" : "0";

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "linear-gradient(160deg, #fde2e7 0%, #e8d6ee 30%, #c9b6e4 60%, #8b7fd1 100%)",
        position: "relative",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <ParticleCanvas />

      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "radial-gradient(ellipse 70% 60% at 50% 40%, rgba(255,255,255,0.18) 0%, transparent 70%)",
          pointerEvents: "none",
        }}
      />

      <nav
        style={{
          position: "relative",
          zIndex: 10,
          display: "flex",
          alignItems: "center",
          padding: "20px 40px",
          gap: 16,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              background: "rgba(255,255,255,0.25)",
              backdropFilter: "blur(8px)",
              border: "1px solid rgba(255,255,255,0.4)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 16,
              color: "white",
            }}
          >
            ◈
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: "white", letterSpacing: "0.1em" }}>
              EVIDENS
            </div>
            <div style={{ fontSize: 9.5, color: "rgba(255,255,255,0.65)", letterSpacing: "0.06em" }}>
              Scientific Intelligence Platform
            </div>
          </div>
        </div>

        <div style={{ flex: 1 }} />

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {["Documentation", "About"].map((l) => (
            <button
              key={l}
              style={{
                background: "transparent",
                border: "none",
                color: "rgba(255,255,255,0.75)",
                fontSize: 13,
                cursor: "pointer",
                padding: "6px 12px",
                borderRadius: 6,
              }}
            >
              {l}
            </button>
          ))}
          <button
            onClick={() => navigate("/setup")}
            style={{
              background: "rgba(255,255,255,0.18)",
              backdropFilter: "blur(8px)",
              border: "1px solid rgba(255,255,255,0.35)",
              color: "white",
              fontSize: 13,
              fontWeight: 600,
              cursor: "pointer",
              padding: "7px 18px",
              borderRadius: 8,
              letterSpacing: "0.02em",
            }}
          >
            Start Analysis
          </button>
        </div>
      </nav>

      <div
        style={{
          position: "relative",
          zIndex: 10,
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "40px 24px 60px",
          textAlign: "center",
        }}
      >
        <div
          style={{
            fontSize: 10.5,
            fontWeight: 700,
            letterSpacing: "0.18em",
            color: "rgba(255,255,255,0.65)",
            marginBottom: 20,
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <span style={{ width: 28, height: 1, background: "rgba(255,255,255,0.4)", display: "inline-block" }} />
          EVIDENCE-GUIDED TARGET PRIORITIZATION
          <span style={{ width: 28, height: 1, background: "rgba(255,255,255,0.4)", display: "inline-block" }} />
        </div>

        <h1
          style={{
            fontFamily: "'DM Serif Display', serif",
            fontSize: "clamp(42px, 7vw, 80px)",
            fontWeight: 400,
            color: "white",
            lineHeight: 1.08,
            margin: "0 0 22px",
            maxWidth: 800,
            letterSpacing: "-0.01em",
          }}
        >
          Navigate the Evidence.<br />
          <span style={{ fontStyle: "italic", opacity: 0.85 }}>Find the Signal.</span>
        </h1>

        <p
          style={{
            fontSize: 16,
            color: "rgba(255,255,255,0.78)",
            maxWidth: 560,
            lineHeight: 1.65,
            margin: "0 0 40px",
            fontWeight: 300,
          }}
        >
          Evidens evaluates the multi-dimensional evidence supporting each therapeutic target,
          identifies contradictions and missing evidence, and surfaces the most critical
          research gaps — so your team decides with clarity.
        </p>

        <div
          style={{
            background: "rgba(255,255,255,0.14)",
            backdropFilter: "blur(16px)",
            border: "1px solid rgba(255,255,255,0.28)",
            borderRadius: 16,
            padding: "24px 28px",
            width: "100%",
            maxWidth: 640,
            marginBottom: 28,
          }}
        >
          <div style={{ display: "flex", gap: 16, marginBottom: 20 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: "rgba(255,255,255,0.55)", marginBottom: 6 }}>
                DISEASE
              </div>
              <div
                style={{
                  background: "rgba(255,255,255,0.2)",
                  border: "1px solid rgba(255,255,255,0.3)",
                  borderRadius: 8,
                  padding: "9px 14px",
                  color: "white",
                  fontSize: 13.5,
                  fontWeight: 500,
                }}
              >
                {disease}
                <span style={{ marginLeft: 8, fontSize: 10.5, opacity: 0.6, fontWeight: 400 }}>{diseaseId}</span>
              </div>
            </div>
          </div>

          <div style={{ marginBottom: 18 }}>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: "rgba(255,255,255,0.55)", marginBottom: 8 }}>
              CANDIDATE TARGETS
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {targetSymbols.map((t) => (
                <span
                  key={t}
                  style={{
                    background: "rgba(255,255,255,0.18)",
                    border: "1px solid rgba(255,255,255,0.28)",
                    borderRadius: 6,
                    padding: "4px 10px",
                    fontSize: 12,
                    fontWeight: 600,
                    color: "white",
                    letterSpacing: "0.03em",
                  }}
                >
                  {t}
                </span>
              ))}
            </div>
          </div>

          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: "rgba(255,255,255,0.55)", marginBottom: 8 }}>
              EVIDENCE DIMENSIONS
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
              {PILLS.map((p) => (
                <span
                  key={p}
                  style={{
                    background: "rgba(255,255,255,0.1)",
                    border: "1px solid rgba(255,255,255,0.2)",
                    borderRadius: 99,
                    padding: "3px 10px",
                    fontSize: 10.5,
                    color: "rgba(255,255,255,0.8)",
                    letterSpacing: "0.02em",
                  }}
                >
                  {p}
                </span>
              ))}
            </div>
          </div>

          <button
            onClick={() => navigate("/setup")}
            style={{
              width: "100%",
              padding: "12px 0",
              borderRadius: 10,
              background: "white",
              border: "none",
              color: "#6b5ed4",
              fontSize: 14,
              fontWeight: 700,
              letterSpacing: "0.04em",
              cursor: "pointer",
              transition: "opacity 0.15s",
            }}
            onMouseEnter={(e) => ((e.target as HTMLElement).style.opacity = "0.9")}
            onMouseLeave={(e) => ((e.target as HTMLElement).style.opacity = "1")}
          >
            START ANALYSIS
          </button>
        </div>

        <div style={{ display: "flex", gap: 40, color: "rgba(255,255,255,0.65)", fontSize: 12, flexWrap: "wrap", justifyContent: "center" }}>
          {[
            { n: "8", label: "Evidence Dimensions" },
            { n: "6", label: "Scientific Source Tiers" },
            { n: evidenceCount, label: "Evidence Records Evaluated" },
          ].map(({ n, label }) => (
            <div key={label} style={{ textAlign: "center" }}>
              <div style={{ fontSize: 22, fontWeight: 700, color: "white", lineHeight: 1.1 }}>{n}</div>
              <div style={{ marginTop: 3 }}>{label}</div>
            </div>
          ))}
        </div>
      </div>

      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: 100,
          background: "linear-gradient(to bottom, transparent, rgba(139,127,209,0.3))",
          pointerEvents: "none",
        }}
      />
    </div>
  );
}
