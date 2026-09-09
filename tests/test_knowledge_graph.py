"""
Tests for app/core/graph/knowledge_graph.py — the real, in-memory
knowledge graph built from already-persisted data for one target.

Real data shapes reused here (pathway/PPI notes format) match exactly what
scripts/ingest_evidence.py's _build_pathway_fields()/
_build_ppi_network_fields() actually write — see that module.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import Target, EvidenceRecord, GapRecord, ContradictionLog
from app.core.graph.knowledge_graph import build_target_graph, _parse_note_field


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _node_ids_by_type(graph: dict, node_type: str) -> list[str]:
    return [n["id"] for n in graph["nodes"] if n["type"] == node_type]


def _find_node(graph: dict, node_id: str) -> dict:
    return next(n for n in graph["nodes"] if n["id"] == node_id)


# --- _parse_note_field ----------------------------------------------------

def test_parse_note_field_extracts_middle_value():
    notes = "pathway=Detoxification of Reactive Oxygen Species; top_level_term=Cellular responses to stimuli"
    assert _parse_note_field(notes, "pathway") == "Detoxification of Reactive Oxygen Species"
    assert _parse_note_field(notes, "top_level_term") == "Cellular responses to stimuli"


def test_parse_note_field_extracts_trailing_value_with_no_semicolon():
    assert _parse_note_field("high_confidence_partner_count=2; partners=FUS, TARDBP", "partners") == "FUS, TARDBP"


def test_parse_note_field_missing_key_returns_none():
    assert _parse_note_field("pathway=X; top_level_term=Y", "not_a_real_key") is None


def test_parse_note_field_handles_none_notes():
    assert _parse_note_field(None, "pathway") is None


# --- build_target_graph -----------------------------------------------------

def test_build_target_graph_returns_none_for_missing_target(db_session):
    assert build_target_graph(999, db_session) is None


def _seed_sod1_like_target(db):
    """SOD1-shaped fixture: 1 pathway, 1 PPI row naming FUS/TARDBP (real
    other candidate targets) and UBQLN2 (a real STRING partner that is
    NOT one of this pipeline's candidate targets), 1 gap, no contradictions
    — mirrors the real shapes _build_pathway_fields()/
    _build_ppi_network_fields() actually produce."""
    sod1 = Target(gene_symbol="SOD1", ensembl_id="ENSG00000142168", disease_efo_id="MONDO_0004976")
    fus = Target(gene_symbol="FUS", ensembl_id="ENSG00000089280", disease_efo_id="MONDO_0004976")
    tardbp = Target(gene_symbol="TARDBP", ensembl_id="ENSG00000120948", disease_efo_id="MONDO_0004976")
    db.add_all([sod1, fus, tardbp])
    db.flush()

    db.add(EvidenceRecord(
        target_id=sod1.id, dimension="pathway", data_source="reactome", source_type="pathway",
        source_record_id="R-HSA-3299685", evidence_score=1.0,
        notes="pathway=Detoxification of Reactive Oxygen Species; top_level_term=Cellular responses to stimuli",
    ))
    db.add(EvidenceRecord(
        target_id=sod1.id, dimension="ppi_network", data_source="string", source_type="ppi_network",
        source_record_id="string:SOD1", raw_value=3.0, evidence_score=0.03,
        notes="high_confidence_partner_count=3; partners=FUS, TARDBP, UBQLN2",
    ))
    db.add(GapRecord(
        target_id=sod1.id, gap_type="mechanistic",
        rationale="Genetic score high but no pathway evidence.",
        investigation_suggestion="Run a pathway/mechanistic study.",
    ))
    db.commit()
    return sod1, fus, tardbp


def test_graph_includes_target_and_disease_nodes(db_session):
    sod1, _, _ = _seed_sod1_like_target(db_session)
    graph = build_target_graph(sod1.id, db_session)

    target_node = _find_node(graph, f"target:{sod1.id}")
    assert target_node["label"] == "SOD1"
    assert target_node["data"]["gene_symbol"] == "SOD1"

    disease_nodes = _node_ids_by_type(graph, "disease")
    assert len(disease_nodes) == 1
    edge_types = {e["type"] for e in graph["edges"]}
    assert "associated_with_disease" in edge_types


def test_graph_includes_real_pathway_node(db_session):
    sod1, _, _ = _seed_sod1_like_target(db_session)
    graph = build_target_graph(sod1.id, db_session)

    pathway_node = _find_node(graph, "pathway:R-HSA-3299685")
    assert pathway_node["label"] == "Detoxification of Reactive Oxygen Species"
    assert pathway_node["data"]["top_level_term"] == "Cellular responses to stimuli"

    pathway_edges = [e for e in graph["edges"] if e["type"] == "belongs_to_pathway"]
    assert len(pathway_edges) == 1
    assert pathway_edges[0]["target"] == "pathway:R-HSA-3299685"


def test_graph_flags_ppi_partners_that_are_also_candidate_targets(db_session):
    """The exact real finding this task names: SOD1's graph must show FUS
    and TARDBP as PPI-partner nodes flagged as candidate targets (with a
    real, clickable target_id), while a real STRING partner that is NOT
    one of this pipeline's targets (UBQLN2) is a plain, non-clickable node."""
    sod1, fus, tardbp = _seed_sod1_like_target(db_session)
    graph = build_target_graph(sod1.id, db_session)

    fus_node = _find_node(graph, "ppi_partner:FUS")
    tardbp_node = _find_node(graph, "ppi_partner:TARDBP")
    ubqln2_node = _find_node(graph, "ppi_partner:UBQLN2")

    assert fus_node["data"]["is_candidate_target"] is True
    assert fus_node["data"]["target_id"] == fus.id
    assert tardbp_node["data"]["is_candidate_target"] is True
    assert tardbp_node["data"]["target_id"] == tardbp.id

    assert ubqln2_node["data"]["is_candidate_target"] is False
    assert ubqln2_node["data"]["target_id"] is None

    interacts_edges = [e for e in graph["edges"] if e["type"] == "interacts_with"]
    assert len(interacts_edges) == 3
    assert {e["target"] for e in interacts_edges} == {"ppi_partner:FUS", "ppi_partner:TARDBP", "ppi_partner:UBQLN2"}


def test_graph_includes_gap_node_connected_to_target(db_session):
    sod1, _, _ = _seed_sod1_like_target(db_session)
    graph = build_target_graph(sod1.id, db_session)

    gap_nodes = [n for n in graph["nodes"] if n["type"] == "gap"]
    assert len(gap_nodes) == 1
    assert gap_nodes[0]["data"]["gap_type"] == "mechanistic"

    gap_edges = [e for e in graph["edges"] if e["type"] == "has_gap"]
    assert len(gap_edges) == 1
    assert gap_edges[0]["target"] == gap_nodes[0]["id"]


def test_graph_has_no_ppi_nodes_when_string_reports_zero_partners(db_session):
    target = Target(gene_symbol="NEK1", ensembl_id="ENSG00000137601", disease_efo_id="MONDO_0004976")
    db_session.add(target)
    db_session.flush()
    db_session.add(EvidenceRecord(
        target_id=target.id, dimension="ppi_network", data_source="string", source_type="ppi_network",
        source_record_id="string:NEK1", raw_value=0.0, evidence_score=0.0,
        notes="high_confidence_partner_count=0; partners=none",
    ))
    db_session.commit()

    graph = build_target_graph(target.id, db_session)
    assert _node_ids_by_type(graph, "ppi_partner") == []


def test_graph_represents_a_confirmed_contradiction_as_an_edge_between_evidence_records(db_session):
    """Real data has never triggered this path (see module docstring) —
    constructed directly, same pattern as the classifier's own
    null-handling regression test."""
    target = Target(gene_symbol="TESTGENE", ensembl_id="ENSG_TEST", disease_efo_id="MONDO_TEST")
    db_session.add(target)
    db_session.flush()

    rec_a = EvidenceRecord(
        target_id=target.id, dimension="genetic", data_source="eva", source_type="genetic",
        source_record_id="rsA", evidence_score=0.9, direction_on_trait="Risk",
    )
    rec_b = EvidenceRecord(
        target_id=target.id, dimension="genetic", data_source="eva", source_type="genetic",
        source_record_id="rsB", evidence_score=0.8, direction_on_trait="Protective",
    )
    db_session.add_all([rec_a, rec_b])
    db_session.flush()

    db_session.add(ContradictionLog(
        target_id=target.id, evidence_record_a_id=rec_a.id, evidence_record_b_id=rec_b.id,
        classification="direct_contradiction", status="confirmed", proposed_by="structured_classifier",
    ))
    db_session.commit()

    graph = build_target_graph(target.id, db_session)

    evidence_nodes = _node_ids_by_type(graph, "evidence_record")
    assert set(evidence_nodes) == {f"evidence_record:{rec_a.id}", f"evidence_record:{rec_b.id}"}

    contra_edges = [e for e in graph["edges"] if e["type"] == "contradicts"]
    assert len(contra_edges) == 1
    assert contra_edges[0]["label"] == "direct_contradiction"
    assert contra_edges[0]["source"] == f"evidence_record:{rec_a.id}"
    assert contra_edges[0]["target"] == f"evidence_record:{rec_b.id}"


def test_graph_has_no_contradiction_nodes_when_none_logged(db_session):
    sod1, _, _ = _seed_sod1_like_target(db_session)
    graph = build_target_graph(sod1.id, db_session)
    assert _node_ids_by_type(graph, "evidence_record") == []
    assert [e for e in graph["edges"] if e["type"] == "contradicts"] == []
