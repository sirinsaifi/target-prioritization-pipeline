/**
 * Evidence Network tab — real, in-memory knowledge graph for one target
 * (GET /graph/target/{id}, app/core/graph/knowledge_graph.py), rendered
 * with vis-network (framework-agnostic, no React peer-dependency risk on
 * React 19 — see package.json). The graph itself is already fully
 * computed server-side; this component only renders and styles it.
 *
 * Palette is derived directly from this app's own design tokens
 * (src/index.css) rather than invented: the primary blue (--seq-550/700)
 * used for buttons/active tabs marks the target node itself; the
 * "Categorical (palette.md fixed order)" family (--cat-1..4) — this app's
 * own existing chart-series palette — encodes the other node AND edge
 * types, using the same light-tint-fill + accent-border convention every
 * badge/tag in this app already uses (see TargetDetail.tsx's
 * levelChip()/gapStyle()), rather than flat saturated fills. Edge colors
 * for gap/pathway relationships intentionally reuse the SAME accent as
 * their destination node type (so a gap edge and a gap node read as one
 * family); the PPI edge deliberately uses --cat-1 (blue, otherwise unused
 * by any node in this graph) as a distinct "cool accent" rather than
 * matching the partner node's own warm orange, per this task's own
 * instruction to keep edges and nodes visually separable layers. Gap
 * edges use this app's actual --status-warn token (not --cat-4, which is
 * merely categorical) — gaps are real findings, not routine structure, so
 * they get the app's real "this needs attention" semantic, not just a
 * palette-matching color.
 *
 * Default view is curated, not exhaustive (this task): only the target,
 * disease, gap nodes (real findings, always shown), evidence_record nodes
 * (real confirmed contradictions — same "always show findings" reasoning
 * as gaps, extended here since the task didn't name this case but it's
 * the same principle), and ppi_partner nodes that are ALSO one of this
 * pipeline's own candidate targets are visible by default. Every other
 * pathway/ppi_partner node is hidden until "Show all connections" is
 * clicked — see isHiddenByDefault() and the showAll toggle below.
 *
 * The one interactive feature this task specifically calls for: a
 * ppi_partner node that is ALSO one of this pipeline's own candidate
 * targets (real cross-target STRING connections, e.g. SOD1<->FUS/TARDBP)
 * gets a 3px ring in the target's own accent color (same family, not a
 * separate icon) and is clickable — clicking it navigates to that gene's
 * own detail page via onNavigateToTarget.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Network, DataSet } from 'vis-network/standalone'
import type { TargetGraph, GraphNode, GraphNodeType, GraphEdgeType } from './data'

const FONT_FACE = 'Inter, system-ui, -apple-system, sans-serif'

// One {fill, border} pair per node type, drawn from this app's existing
// tokens (see module docstring) — never a new, unrelated palette.
const NODE_COLORS: Record<GraphNodeType, { fill: string; border: string }> = {
  target: { fill: '#1c5cab', border: '#0d366b' },           // --seq-550 / --seq-700 (this app's primary blue)
  disease: { fill: '#f3f4f6', border: '#6b7280' },          // --status-neutral-bg / --status-neutral
  pathway: { fill: '#e8f9f3', border: '#1baf7a' },          // --cat-3-bg / --cat-3
  ppi_partner: { fill: '#fdf1ec', border: '#eb6834' },      // --cat-2-bg / --cat-2
  gap: { fill: '#fdf3e0', border: '#eda100' },              // --cat-4-bg / --cat-4
  evidence_record: { fill: '#f3f4f6', border: '#6b7280' },  // --status-neutral-bg / --status-neutral
}

// The target node's own accent — reused as the "also a candidate target"
// ring color, so the highlight reads as "part of the target's own family"
// rather than an unrelated icon (see module docstring).
const CANDIDATE_RING_COLOR = NODE_COLORS.target.border

interface EdgeStyle {
  color: string
  opacity: number
  width: number
  dashes: boolean
}

// One style per real edge type (this task) — see module docstring for why
// each color was picked from this app's existing tokens.
const EDGE_STYLES: Record<GraphEdgeType, EdgeStyle> = {
  associated_with_disease: { color: '#c9cfdb', opacity: 0.55, width: 1, dashes: false },   // muted/subtle — context, not a finding
  belongs_to_pathway: { color: '#1baf7a', opacity: 0.85, width: 1.5, dashes: false },       // --cat-3, matches the pathway node
  interacts_with: { color: '#2a78d6', opacity: 0.85, width: 1.5, dashes: false },           // --cat-1, distinct cool accent
  has_gap: { color: '#d97706', opacity: 1, width: 2.5, dashes: false },                     // --status-warn (real "warn" token) — a finding, stands out
  contradicts: { color: '#dc2626', opacity: 1, width: 2.5, dashes: true },                  // unchanged, per instruction
}

const EDGE_DIM_COLOR = '#e2e5ee' // --border, used only for the "not connected to hovered node" state

const BASE_SIZE: Record<GraphNodeType, number> = {
  target: 30,
  ppi_partner: 15,
  pathway: 12,
  disease: 12,
  gap: 11,
  evidence_record: 10,
}

const NODE_LEGEND_ORDER: GraphNodeType[] = ['target', 'disease', 'pathway', 'ppi_partner', 'gap', 'evidence_record']
const EDGE_LEGEND_ORDER: { type: GraphEdgeType; label: string }[] = [
  { type: 'interacts_with', label: 'PPI interaction' },
  { type: 'belongs_to_pathway', label: 'pathway membership' },
  { type: 'has_gap', label: 'research gap' },
  { type: 'associated_with_disease', label: 'disease context' },
  { type: 'contradicts', label: 'contradiction' },
]

function isClickableCandidateTarget(node: GraphNode): boolean {
  return node.type === 'ppi_partner' && node.data.is_candidate_target === true
}

// Curated default view (Priority 2, this task): target/disease/gap/
// evidence_record always visible; a ppi_partner is visible by default
// only if it's ALSO a candidate target; every pathway and every other
// ppi_partner starts hidden.
function isHiddenByDefault(node: GraphNode): boolean {
  if (node.type === 'pathway') return true
  if (node.type === 'ppi_partner') return !isClickableCandidateTarget(node)
  return false
}

interface Props {
  graph: TargetGraph
  onNavigateToTarget: (targetId: number) => void
}

export default function EvidenceNetwork({ graph, onNavigateToTarget }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const networkRef = useRef<Network | null>(null)
  const nodesDataSetRef = useRef<DataSet<Record<string, unknown>> | null>(null)
  const edgesDataSetRef = useRef<DataSet<Record<string, unknown>> | null>(null)
  const hiddenNodeIdsRef = useRef<string[]>([])
  const hiddenEdgeIdsRef = useRef<number[]>([])

  const [showAll, setShowAll] = useState(false)

  const hiddenCount = useMemo(() => graph.nodes.filter(isHiddenByDefault).length, [graph])

  // A fresh graph (different target) always starts curated/collapsed —
  // an expanded view from a previously-viewed gene should not carry over.
  useEffect(() => {
    setShowAll(false)
  }, [graph])

  useEffect(() => {
    if (!containerRef.current) return

    const hiddenNodeIds = new Set(graph.nodes.filter(isHiddenByDefault).map(n => n.id))

    // Size by real degree, layered on top of a per-type base size — the
    // target's real connection count (pathways + partners + gaps) nudges
    // its own size a little further above every other node, on top of the
    // fixed type-based hierarchy (target > ppi_partner > pathway/disease >
    // gap/evidence_record) this task asks for.
    const degreeById = new Map<string, number>()
    for (const e of graph.edges) {
      degreeById.set(e.source, (degreeById.get(e.source) ?? 0) + 1)
      degreeById.set(e.target, (degreeById.get(e.target) ?? 0) + 1)
    }

    const nodeItems = graph.nodes.map(n => {
      const candidate = isClickableCandidateTarget(n)
      const colors = NODE_COLORS[n.type]
      const degree = degreeById.get(n.id) ?? 0
      const size = BASE_SIZE[n.type] + Math.min(degree, 12) * (n.type === 'target' ? 0.6 : 0.15) + (candidate ? 4 : 0)

      return {
        id: n.id,
        label: n.label,
        title: `${n.type.replace(/_/g, ' ')}: ${n.label}` + (candidate ? ' — also a candidate target in this pipeline. Click to open.' : ''),
        shape: 'dot' as const,
        size,
        hidden: hiddenNodeIds.has(n.id),
        widthConstraint: { maximum: n.type === 'target' ? 130 : 100 },
        font: {
          face: FONT_FACE,
          size: n.type === 'target' ? 15 : 11.5,
          color: '#111827', // --ink-1
          bold: n.type === 'target' ? { color: '#111827', face: FONT_FACE, size: 15, mod: '600' } : undefined,
          // A solid pill behind every label — keeps text readable where it
          // crosses an edge (the reported "SOD2 sitting on top of a line"
          // issue) without needing a separate text-shadow hack.
          background: 'rgba(255,255,255,0.88)',
          vadjust: 0,
        },
        color: {
          background: colors.fill,
          border: candidate ? CANDIDATE_RING_COLOR : colors.border,
          highlight: { background: colors.fill, border: candidate ? CANDIDATE_RING_COLOR : colors.border },
          hover: { background: colors.fill, border: candidate ? CANDIDATE_RING_COLOR : colors.border },
        },
        borderWidth: candidate ? 3 : 1.5,
        borderWidthSelected: candidate ? 4 : 2.5,
        chosen: true,
      }
    })

    const originalEdgeStyle = new Map<number, EdgeStyle>()
    const hiddenEdgeIds = new Set<number>()
    const edgeItems = graph.edges.map((e, i) => {
      const style = EDGE_STYLES[e.type]
      originalEdgeStyle.set(i, style)
      const hidden = hiddenNodeIds.has(e.source) || hiddenNodeIds.has(e.target)
      if (hidden) hiddenEdgeIds.add(i)
      return {
        id: i,
        from: e.source,
        to: e.target,
        // vis-network shows `title` as a hover tooltip — matches this
        // task's "edges labeled on hover" requirement without cluttering
        // the graph with always-visible text (e.g. 10 identical
        // "interacts with" labels for a hub gene like SOD1).
        title: e.label,
        hidden,
        color: { color: style.color, opacity: style.opacity, highlight: style.color, hover: style.color },
        width: style.width,
        dashes: style.dashes,
        smooth: { enabled: true, type: 'continuous', roundness: 0.5 },
        arrows: { to: { enabled: false } },
      }
    })

    const nodesDataSet = new DataSet(nodeItems)
    const edgesDataSet = new DataSet(edgeItems)
    nodesDataSetRef.current = nodesDataSet
    edgesDataSetRef.current = edgesDataSet
    hiddenNodeIdsRef.current = [...hiddenNodeIds]
    hiddenEdgeIdsRef.current = [...hiddenEdgeIds]

    const network = new Network(
      containerRef.current,
      { nodes: nodesDataSet, edges: edgesDataSet },
      {
        physics: {
          barnesHut: {
            gravitationalConstant: -12000,
            springLength: 220,
            springConstant: 0.03,
            avoidOverlap: 1, // real vis-network option: factors node/label size into repulsion, so labels don't crash into each other
          },
          stabilization: { iterations: 250 },
        },
        interaction: { hover: true, tooltipDelay: 100, zoomView: true, dragView: true, hoverConnectedEdges: false },
        edges: { smooth: { enabled: true, type: 'continuous', roundness: 0.5 } },
      },
    )
    networkRef.current = network

    // Hover-to-highlight: only the edges touching the hovered node stay at
    // full color/opacity, every other edge dims to a faint neutral gray —
    // makes the specific relationship being explored obvious in a denser
    // graph instead of every line always being equally prominent.
    network.on('hoverNode', params => {
      const connected = new Set(network.getConnectedEdges(params.node as string))
      const updates = graph.edges.map((_, i) => {
        const original = originalEdgeStyle.get(i)!
        return connected.has(i)
          ? { id: i, color: { color: original.color, opacity: 1, highlight: original.color, hover: original.color }, width: original.width + 1 }
          : { id: i, color: { color: EDGE_DIM_COLOR, opacity: 0.18, highlight: EDGE_DIM_COLOR, hover: EDGE_DIM_COLOR }, width: 1 }
      })
      edgesDataSet.update(updates)
    })
    network.on('blurNode', () => {
      const updates = graph.edges.map((_, i) => {
        const original = originalEdgeStyle.get(i)!
        return { id: i, color: { color: original.color, opacity: original.opacity, highlight: original.color, hover: original.color }, width: original.width }
      })
      edgesDataSet.update(updates)
    })

    network.on('click', params => {
      if (params.nodes.length === 0) return
      const nodeId = params.nodes[0] as string
      const node = graph.nodes.find(n => n.id === nodeId)
      if (node && isClickableCandidateTarget(node) && typeof node.data.target_id === 'number') {
        onNavigateToTarget(node.data.target_id)
      }
    })

    return () => {
      network.destroy()
      networkRef.current = null
      nodesDataSetRef.current = null
      edgesDataSetRef.current = null
    }
  }, [graph, onNavigateToTarget])

  // Show all / show fewer toggle — only flips the `hidden` flag on the
  // already-built DataSets (no network rebuild, no lost pan/zoom/physics
  // state), then refits the camera to the newly-visible node set.
  useEffect(() => {
    const nodesDataSet = nodesDataSetRef.current
    const edgesDataSet = edgesDataSetRef.current
    if (!nodesDataSet || !edgesDataSet) return

    nodesDataSet.update(hiddenNodeIdsRef.current.map(id => ({ id, hidden: !showAll })))
    edgesDataSet.update(hiddenEdgeIdsRef.current.map(id => ({ id, hidden: !showAll })))
    networkRef.current?.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } })
  }, [showAll, graph])

  if (graph.nodes.length === 0) {
    return (
      <div style={{ padding: '48px 0', textAlign: 'center', color: 'var(--ink-3)', fontSize: 13 }}>
        No graph data available for this target yet.
      </div>
    )
  }

  return (
    <div>
      <div className="surface-flat" style={{ overflow: 'hidden' }}>
        {/* Header bar: node legend + edge legend (left) + view controls
            (right) — small circular node swatches and short line swatches
            per edge type, matching the graph's own updated styling. */}
        <div
          style={{
            display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10,
            padding: '10px 14px', borderBottom: '1px solid var(--border)', background: 'var(--surface)',
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 11.5, color: 'var(--ink-2)' }}>
              {NODE_LEGEND_ORDER.map(type => (
                <span key={type} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <span
                    style={{
                      width: 10, height: 10, borderRadius: '50%', display: 'inline-block',
                      background: NODE_COLORS[type].fill, border: `1.5px solid ${NODE_COLORS[type].border}`,
                    }}
                  />
                  {type.replace(/_/g, ' ')}
                </span>
              ))}
              <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontWeight: 600 }}>
                <span
                  style={{
                    width: 10, height: 10, borderRadius: '50%', display: 'inline-block',
                    background: NODE_COLORS.ppi_partner.fill, border: `2.5px solid ${CANDIDATE_RING_COLOR}`,
                  }}
                />
                also a candidate target — click to open
              </span>
            </div>
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 11.5, color: 'var(--ink-2)' }}>
              {EDGE_LEGEND_ORDER.map(({ type, label }) => {
                const s = EDGE_STYLES[type]
                return (
                  <span key={type} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                    <svg width="18" height="8" style={{ flexShrink: 0 }}>
                      <line
                        x1="0" y1="4" x2="18" y2="4"
                        stroke={s.color} strokeWidth={s.width} strokeDasharray={s.dashes ? '3,2' : undefined}
                        opacity={Math.max(s.opacity, 0.7)}
                      />
                    </svg>
                    {label}
                  </span>
                )
              })}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
            <button
              onClick={() => setShowAll(v => !v)}
              style={{
                padding: '5px 12px', borderRadius: 6,
                border: `1px solid ${showAll ? 'var(--border)' : '#bcd3ef'}`,
                background: showAll ? 'var(--page-bg)' : '#eaf2fc',
                color: showAll ? 'var(--ink-2)' : 'var(--seq-550)',
                fontSize: 12, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap',
              }}
            >
              {showAll ? 'Show fewer connections' : `Show all connections (${hiddenCount})`}
            </button>
            <button
              onClick={() => networkRef.current?.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } })}
              style={{
                display: 'flex', alignItems: 'center', gap: 6, padding: '5px 12px', borderRadius: 6,
                border: '1px solid var(--border)', background: 'var(--page-bg)', color: 'var(--ink-2)',
                fontSize: 12, fontWeight: 500, cursor: 'pointer', whiteSpace: 'nowrap',
              }}
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4">
                <path d="M2 4V2h2M10 4V2H8M2 8v2h2M10 8v2H8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Reset view
            </button>
          </div>
        </div>

        <div ref={containerRef} style={{ height: 480, background: '#fbfcfe' }} />
      </div>
      <p style={{ margin: '10px 0 0', fontSize: 11.5, color: 'var(--ink-3)' }}>
        Scroll to zoom, drag to pan. Hover a node to highlight its real connections; hover a node or edge to see
        details. Nodes with a bold blue ring are real STRING interaction partners that are ALSO
        independently-ingested candidate targets in this pipeline — click one to open its own detail page. Pathway
        membership and the remaining PPI partners start hidden — findings (gaps, contradictions) and cross-target
        partners are shown first; use "Show all connections" for full detail.
      </p>
    </div>
  )
}
