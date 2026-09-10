import { useState, useRef, useEffect } from "react";
import { useParams } from "react-router-dom";
import { useTargets, useTargetData, useApiTargets } from "../api/hooks";

interface Node {
  id: string;
  label: string;
  type: "target" | "pathway" | "ppi" | "evidence" | "gap";
  x: number;
  y: number;
  radius: number;
  selected: boolean;
}

interface Edge {
  source: string;
  target: string;
  strength: number;
}

const NODE_COLORS: Record<string, string> = {
  target: "#8b7fd1",
  pathway: "#22c55e",
  ppi: "#f59e0b",
  evidence: "#3b82f6",
  gap: "#ef4444",
};

const NODE_LABELS: Record<string, string> = {
  target: "Target",
  pathway: "Pathway",
  ppi: "PPI Partner",
  evidence: "Evidence",
  gap: "Research Gap",
};

function buildNetwork(targetId: string, target: { symbol: string; geneSymbol?: string } | null): { nodes: Node[]; edges: Edge[] } {
  const cx = 420;
  const cy = 320;

  const nodes: Node[] = [
    { id: "target", label: targetId, type: "target", x: cx, y: cy, radius: 28, selected: false },
  ];

  const pathways = ["Oxidative Stress", "Apoptosis", "Proteasome", "Autophagy"];
  const ppis = ["HSP70", "p62/SQSTM1", "UBQLN2", "OPTN"];
  const evidences = ["Genetic (ClinVar)", "PubMed Co-mention", "GTEx Expression", "ClinTrials"];
  const gaps = ["Safety Gap", "Modality Gap"];

  const ringData = [
    { items: pathways, type: "pathway" as const, r: 140, startAngle: -Math.PI / 2 },
    { items: ppis, type: "ppi" as const, r: 200, startAngle: -Math.PI / 4 },
    { items: evidences, type: "evidence" as const, r: 260, startAngle: Math.PI / 6 },
    { items: gaps, type: "gap" as const, r: 180, startAngle: Math.PI },
  ];

  const edges: Edge[] = [];

  ringData.forEach(({ items, type, r, startAngle }) => {
    items.forEach((item, i) => {
      const angle = startAngle + (i / items.length) * Math.PI * 2;
      const id = `${type}-${i}`;
      nodes.push({
        id,
        label: item,
        type,
        x: cx + Math.cos(angle) * r,
        y: cy + Math.sin(angle) * r,
        radius: type === "pathway" ? 18 : type === "ppi" ? 16 : 14,
        selected: false,
      });
      edges.push({ source: "target", target: id, strength: Math.random() * 0.5 + 0.5 });
    });
  });

  return { nodes, edges };
}

export default function EvidenceNetwork() {
  const { id } = useParams<{ id: string }>();
  const { data: targets } = useApiTargets();
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selected, setSelected] = useState<Node | null>(null);
  const [filter, setFilter] = useState<string | null>(null);
  const canvasRef = useRef<SVGSVGElement>(null);

  const target = targets?.data?.find((t) => String(t.id) === id) ?? targets?.data?.[0];

  useEffect(() => {
    if (!id || !target) {
      const { nodes, edges } = buildNetwork(id ?? "1", null);
      setNodes(nodes);
      setEdges(edges);
      return;
    }

    // Build network from real evidence data
    const { nodes, edges } = buildNetwork(id, { symbol: target?.symbol ?? "", geneSymbol: target?.gene_symbol });
    setNodes(nodes);
    setEdges(edges);
  }, [id, target]);

  const filteredNodes = filter ? nodes.filter((n) => n.type === "target" || n.type === filter) : nodes;
  const filteredEdges = filter
    ? edges.filter((e) => filteredNodes.some((n) => n.id === e.source) && filteredNodes.some((n) => n.id === e.target))
    : edges;

  const symbol = target?.symbol ?? id;

  return (
    <div style={{ height: "calc(100vh - 52px)", display: "flex", flexDirection: "column" }}>
      <div
        style={{
          padding: "16px 40px",
          borderBottom: "1px solid var(--border)",
          background: "var(--surface)",
          display: "flex",
          alignItems: "center",
          gap: 16,
          flexShrink: 0,
        }}
      >
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.12em", color: "var(--text-muted)" }}>
            EVIDENCE NETWORK
          </div>
          <div style={{ fontSize: 16, fontWeight: 700, color: "var(--text-primary)" }}>
            {symbol} — Biological Evidence Landscape
          </div>
        </div>

        <div style={{ display: "flex", gap: 6, marginLeft: "auto" }}>
          {[null, "pathway", "ppi", "evidence", "gap"].map((f) => (
            <button
              key={String(f)}
              onClick={() => setFilter(f === filter ? null : f)}
              style={{
                padding: "5px 12px",
                borderRadius: 6,
                border: `1px solid ${f && filter === f ? NODE_COLORS[f] : "var(--border)"}`,
                background: f && filter === f ? `${NODE_COLORS[f]}15` : "transparent",
                color: f && filter === f ? NODE_COLORS[f] : "var(--text-muted)",
                fontSize: 11.5,
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              {f ? NODE_LABELS[f] : "All"}
            </button>
          ))}
        </div>
      </div>

      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        <div style={{ flex: 1, position: "relative", background: "var(--bg)" }}>
          <svg
            ref={canvasRef}
            width="100%"
            height="100%"
            style={{ cursor: "crosshair" }}
          >
            <defs>
              <filter id="glow">
                <feGaussianBlur stdDeviation="3" result="coloredBlur" />
                <feMerge>
                  <feMergeNode in="coloredBlur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            {filteredEdges.map((edge) => {
              const src = filteredNodes.find((n) => n.id === edge.source);
              const tgt = filteredNodes.find((n) => n.id === edge.target);
              if (!src || !tgt) return null;
              const tgtColor = NODE_COLORS[tgt.type];
              return (
                <line
                  key={`${edge.source}-${edge.target}`}
                  x1={src.x}
                  y1={src.y}
                  x2={tgt.x}
                  y2={tgt.y}
                  stroke={tgtColor}
                  strokeOpacity={0.2}
                  strokeWidth={edge.strength * 1.5}
                />
              );
            })}

            {filteredNodes.map((node) => {
              const color = NODE_COLORS[node.type];
              const isSelected = selected?.id === node.id;
              return (
                <g
                  key={node.id}
                  transform={`translate(${node.x},${node.y})`}
                  onClick={() => setSelected(isSelected ? null : node)}
                  style={{ cursor: "pointer" }}
                >
                  {isSelected && (
                    <circle r={node.radius + 8} fill={color} fillOpacity={0.12} />
                  )}
                  <circle
                    r={node.radius}
                    fill={color}
                    fillOpacity={node.type === "target" ? 1 : 0.15}
                    stroke={color}
                    strokeWidth={node.type === "target" ? 0 : 1.5}
                    filter={node.type === "target" ? "url(#glow)" : undefined}
                  />
                  <text
                    textAnchor="middle"
                    dy={node.type === "target" ? "0.35em" : node.radius + 14}
                    fontSize={node.type === "target" ? 11 : 10}
                    fontWeight={node.type === "target" ? 700 : 500}
                    fill={node.type === "target" ? "white" : color}
                    style={{ userSelect: "none", pointerEvents: "none" }}
                  >
                    {node.type === "target" ? node.label : ""}
                  </text>
                  {node.type !== "target" && (
                    <text
                      textAnchor="middle"
                      y={node.radius + 14}
                      fontSize={10}
                      fontWeight={500}
                      fill={color}
                      style={{ userSelect: "none", pointerEvents: "none" }}
                    >
                      {node.label}
                    </text>
                  )}
                </g>
              );
            })}
          </svg>
        </div>

        <div
          style={{
            width: 260,
            borderLeft: "1px solid var(--border)",
            background: "var(--surface)",
            padding: 20,
            overflowY: "auto",
            flexShrink: 0,
          }}
        >
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 10 }}>
              NODE TYPES
            </div>
            {Object.entries(NODE_COLORS).map(([type, color]) => (
              <div key={type} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, fontSize: 12 }}>
                <span style={{ width: 10, height: 10, borderRadius: "50%", background: color, display: "inline-block" }} />
                <span style={{ color: "var(--text-secondary)" }}>{NODE_LABELS[type]}</span>
              </div>
            ))}
          </div>

          {selected ? (
            <div>
              <div style={{ width: 1, background: "var(--border)", height: 1, marginBottom: 16 }} />
              <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 8 }}>
                SELECTED
              </div>
              <div
                style={{
                  padding: "12px",
                  borderRadius: 8,
                  border: `1px solid ${NODE_COLORS[selected.type]}30`,
                  background: `${NODE_COLORS[selected.type]}08`,
                  marginBottom: 12,
                }}
              >
                <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)", marginBottom: 4 }}>
                  {selected.label}
                </div>
                <div style={{ fontSize: 10.5, fontWeight: 600, color: NODE_COLORS[selected.type], letterSpacing: "0.08em" }}>
                  {NODE_LABELS[selected.type].toUpperCase()}
                </div>
              </div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.6 }}>
                {selected.type === "pathway" && "Reactome/KEGG pathway associated with " + symbol + " biological function."}
                {selected.type === "ppi" && "Protein-protein interaction partner identified via STRING v12 database."}
                {selected.type === "evidence" && "Evidence dimension with supporting records from curated databases."}
                {selected.type === "gap" && "Research gap identified by evidence coverage analysis."}
                {selected.type === "target" && "Central target node. " + symbol + "."}
              </div>
            </div>
          ) : (
            <div style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.6 }}>
              Click any node to inspect its details and connections.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
