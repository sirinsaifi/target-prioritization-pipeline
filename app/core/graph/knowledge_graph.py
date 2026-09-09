"""
Real, in-memory knowledge graph for one target, built fresh from
already-persisted data on every call — no new ingestion, no recomputation
of any score/contradiction/gap, and the graph itself is never persisted
(see GET /graph/target/{id}'s docstring for why: this is a cheap read-only
projection over rows the fixed pipeline already computed).

Uses networkx.DiGraph as the actual in-memory graph structure (not just a
plain nested dict) so real graph operations (traversal, connected
components, centrality, etc.) are available on it later if needed — this
task only needs the node/edge listing, built by walking graph.nodes()/
edges() ourselves rather than networkx's own node_link_data() serializer,
to keep exact control over the {"nodes": [...], "edges": [...]} key names
this task specifies (networkx's own serializer's default key names have
changed across versions — see its node_link_data() deprecation notes).

Node types: target, disease, pathway, ppi_partner, gap, evidence_record
(the last only ever appears as an endpoint of a confirmed contradiction
edge — see _add_contradiction_nodes_and_edges()'s docstring for why no
separate "contradiction" node type exists).
Edge types: associated_with_disease, belongs_to_pathway, interacts_with,
has_gap, contradicts.

Pathway/PPI-partner names are not separate structured columns on
EvidenceRecord — they were recorded in `notes` (see
scripts/ingest_evidence.py's _build_pathway_fields()/
_build_ppi_network_fields()) as e.g. "pathway=X; top_level_term=Y" and
"high_confidence_partner_count=N; partners=A, B, C". _parse_note_field()
below reads them back out of that real, already-stored text rather than
re-deriving anything.
"""

import networkx as nx

from app.db.models import Target, EvidenceRecord, GapRecord, ContradictionLog
from app.config import DISEASE_NAME


def _parse_note_field(notes: str | None, key: str) -> str | None:
    if not notes:
        return None
    marker = f"{key}="
    idx = notes.find(marker)
    if idx == -1:
        return None
    start = idx + len(marker)
    end = notes.find(";", start)
    value = (notes[start:end] if end != -1 else notes[start:]).strip()
    return value or None


def _add_pathway_nodes_and_edges(graph: nx.DiGraph, db, target_node_id: str, target_id: int) -> None:
    rows = (
        db.query(EvidenceRecord)
        .filter_by(target_id=target_id, dimension="pathway", data_source="reactome")
        .all()
    )
    for r in rows:
        pathway_name = _parse_note_field(r.notes, "pathway") or r.source_record_id
        node_id = f"pathway:{r.source_record_id}"
        graph.add_node(
            node_id, type="pathway", label=pathway_name,
            data={
                "pathway_id": r.source_record_id,
                "top_level_term": _parse_note_field(r.notes, "top_level_term"),
            },
        )
        graph.add_edge(target_node_id, node_id, type="belongs_to_pathway", label="belongs to pathway")


def _add_ppi_nodes_and_edges(graph: nx.DiGraph, db, target_node_id: str, target_id: int, gene_symbol: str) -> None:
    """
    Real STRING high-confidence partners (see
    scripts/ingest_evidence.py's _build_ppi_network_fields() — one
    aggregate row per gene, partner names comma-joined in `notes`).

    Partners are matched (case-insensitively) against every OTHER real
    Target row currently in this DB — not a hardcoded gene list — to flag
    the cross-target-connection finding from the PPI task: a partner that
    is ALSO one of this pipeline's own candidate targets (e.g. SOD1's real
    STRING partners include FUS and TARDBP, both independently ingested
    as their own targets) gets `is_candidate_target=True` and a real
    `target_id` the frontend can navigate to.
    """
    rows = (
        db.query(EvidenceRecord)
        .filter_by(target_id=target_id, dimension="ppi_network", data_source="string")
        .all()
    )
    if not rows:
        return

    other_targets = {
        t.gene_symbol.upper(): t for t in db.query(Target).all()
        if t.gene_symbol.upper() != gene_symbol.upper()
    }

    seen_partners = set()
    for r in rows:
        partners_str = _parse_note_field(r.notes, "partners")
        if not partners_str or partners_str.lower() == "none":
            continue
        for partner_name in (p.strip() for p in partners_str.split(",")):
            if not partner_name or partner_name in seen_partners:
                continue
            seen_partners.add(partner_name)
            matched_target = other_targets.get(partner_name.upper())
            node_id = f"ppi_partner:{partner_name}"
            graph.add_node(
                node_id, type="ppi_partner", label=partner_name,
                data={
                    "is_candidate_target": matched_target is not None,
                    "target_id": matched_target.id if matched_target else None,
                },
            )
            graph.add_edge(target_node_id, node_id, type="interacts_with", label="high-confidence STRING interaction")


def _add_gap_nodes_and_edges(graph: nx.DiGraph, db, target_node_id: str, target_id: int) -> None:
    for g in db.query(GapRecord).filter_by(target_id=target_id).all():
        node_id = f"gap:{g.id}"
        graph.add_node(
            node_id, type="gap", label=g.gap_type,
            data={
                "gap_type": g.gap_type,
                "rationale": g.rationale,
                "investigation_suggestion": g.investigation_suggestion,
            },
        )
        graph.add_edge(target_node_id, node_id, type="has_gap", label="has research gap")


def _add_contradiction_nodes_and_edges(graph: nx.DiGraph, db, target_id: int) -> None:
    """
    A confirmed contradiction (ContradictionLog — structured or
    literature-sourced, see that model's docstring) is a claim about TWO
    PIECES OF EVIDENCE disagreeing, not about the gene itself, so it's
    rendered as an edge directly between the two real EvidenceRecord rows
    involved rather than as a "contradiction" node hanging off the target.

    Real, unexercised by current data: no target in this pipeline (ALS or
    Parkinson's) has ever had a logged contradiction (see CLAUDE.md — real
    ClinVar variant calls are uniformly one-directional for every gene
    tested so far), so this always adds nothing for real targets today.
    Covered by a constructed fixture instead, same pattern already used
    for the contradiction classifier's own null-handling edge case (see
    CLAUDE.md item 8).
    """
    for c in db.query(ContradictionLog).filter_by(target_id=target_id).all():
        rec_a = db.get(EvidenceRecord, c.evidence_record_a_id)
        rec_b = db.get(EvidenceRecord, c.evidence_record_b_id)
        if rec_a is None or rec_b is None:
            continue
        for rec in (rec_a, rec_b):
            node_id = f"evidence_record:{rec.id}"
            if not graph.has_node(node_id):
                graph.add_node(
                    node_id, type="evidence_record", label=f"{rec.dimension}:{rec.data_source}#{rec.id}",
                    data={
                        "dimension": rec.dimension,
                        "data_source": rec.data_source,
                        "source_record_id": rec.source_record_id,
                    },
                )
        graph.add_edge(
            f"evidence_record:{rec_a.id}", f"evidence_record:{rec_b.id}",
            type="contradicts", label=c.classification,
        )


def _graph_to_json(graph: nx.DiGraph) -> dict:
    nodes = [{"id": node_id, **attrs} for node_id, attrs in graph.nodes(data=True)]
    edges = [{"source": u, "target": v, **attrs} for u, v, attrs in graph.edges(data=True)]
    return {"nodes": nodes, "edges": edges}


def build_target_graph(target_id: int, db) -> dict | None:
    """
    Returns {"nodes": [...], "edges": [...]} for one target, or None if the
    target doesn't exist (the route turns that into a 404). Every node has
    {id, type, label, data}; every edge has {source, target, type, label}
    matching node ids — plain dicts, not a Pydantic model, since node
    `data` shapes genuinely differ by type (see module docstring).
    """
    target = db.query(Target).filter_by(id=target_id).first()
    if target is None:
        return None

    graph = nx.DiGraph()

    target_node_id = f"target:{target.id}"
    disease_node_id = f"disease:{target.disease_efo_id}"

    graph.add_node(
        target_node_id, type="target", label=target.gene_symbol,
        data={"gene_symbol": target.gene_symbol, "ensembl_id": target.ensembl_id, "target_id": target.id},
    )
    graph.add_node(
        disease_node_id, type="disease", label=DISEASE_NAME,
        data={"disease_efo_id": target.disease_efo_id},
    )
    graph.add_edge(target_node_id, disease_node_id, type="associated_with_disease", label="associated with")

    _add_pathway_nodes_and_edges(graph, db, target_node_id, target.id)
    _add_ppi_nodes_and_edges(graph, db, target_node_id, target.id, target.gene_symbol)
    _add_gap_nodes_and_edges(graph, db, target_node_id, target.id)
    _add_contradiction_nodes_and_edges(graph, db, target.id)

    return _graph_to_json(graph)
