"""
Regression tests for two real bugs found during the Parkinson's Disease
smoke test (see CLAUDE.md), both in scripts/ingest_evidence.py:

1. _build_omics_fields() assumed `tissue` (from OTP's
   `biosamplesFromSource`) was always a scalar string. SNCA's real
   expression_atlas data returned it as a list (['UBERON_0001966']) — the
   first time this datasource ever returned real data for any gene tested
   — which raised sqlite3.ProgrammingError on insert (SQLite/SQLAlchemy
   cannot bind a list to a String column).

2. ingest_target() staged an entire gene's evidence in ONE transaction
   with a single commit() at the end. The bug above meant one bad omics
   row rolled back EVERY already-staged record for that gene (genetic,
   literature, clinical, pathway, drug-target — all of it), not just the
   failing row.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import (
    Target, EvidenceRecord, ContradictionLog, GapRecord, PriorityScore, PipelineRunLog,
)
from scripts.ingest_evidence import (
    _build_omics_fields, _build_genetic_fields, _build_clinical_fields,
    _build_tissue_expression_fields, _scalarize, _save_evidence, ingest_target,
    clear_evidence_and_downstream_analysis,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


# --- Bug 1: list-valued tissue field -----------------------------------

def test_scalarize_joins_list_values():
    assert _scalarize(["UBERON_0001966"]) == "UBERON_0001966"
    assert _scalarize(["UBERON_0001966", "UBERON_0000955"]) == "UBERON_0001966; UBERON_0000955"


def test_scalarize_passes_through_non_list_values():
    assert _scalarize("Detected in all") == "Detected in all"
    assert _scalarize(None) is None


def test_build_omics_fields_handles_real_list_valued_tissue():
    """The exact real SNCA row shape that crashed the insert."""
    row = {
        "id": "evidence_id_1",
        "studyId": "study_1",
        "log2FoldChangeValue": 2.5,
        "log2FoldChangePercentileRank": 90,
        "pValueMantissa": 1.0,
        "pValueExponent": -8,
        "resourceScore": 0.9,
        "biosamplesFromSource": ["UBERON_0001966"],
        "diseaseFromSource": "Parkinson's disease",
    }
    fields = _build_omics_fields(row)
    assert fields["tissue"] == "UBERON_0001966"
    assert isinstance(fields["tissue"], str)


def test_build_omics_fields_still_handles_scalar_tissue():
    row = {"id": "evidence_id_2", "biosamplesFromSource": "UBERON_0001966"}
    fields = _build_omics_fields(row)
    assert fields["tissue"] == "UBERON_0001966"


def test_evidence_record_with_list_valued_tissue_actually_saves(db_session):
    """End-to-end: the fixed field would previously fail at db.commit()
    with sqlite3.ProgrammingError; now it must insert cleanly."""
    target = Target(gene_symbol="SNCA", ensembl_id="ENSG00000145335", disease_efo_id="MONDO_0005180")
    db_session.add(target)
    db_session.commit()

    row = {
        "id": "evidence_id_3",
        "log2FoldChangeValue": 2.5,
        "log2FoldChangePercentileRank": 90,
        "pValueMantissa": 1.0,
        "pValueExponent": -8,
        "resourceScore": 0.9,
        "biosamplesFromSource": ["UBERON_0001966"],
    }
    record = EvidenceRecord(target_id=target.id, dimension="omics", data_source="expression_atlas", **_build_omics_fields(row))
    assert _save_evidence(db_session, record, "SNCA", "expression_atlas") is True

    saved = db_session.query(EvidenceRecord).filter_by(target_id=target.id).all()
    assert len(saved) == 1
    assert saved[0].tissue == "UBERON_0001966"


# --- Defensive follow-up: the 3 other list-vs-scalar risks flagged during
# the audit (variantRsId, drugFromSource, HPA's rna_tissue_distribution) ---

def test_build_genetic_fields_handles_list_valued_variant_id():
    row = {
        "id": "g1", "studyId": "s1", "score": 0.9,
        "variantRsId": ["rs1", "rs2"],
        "clinicalSignificances": ["pathogenic"], "allelicRequirements": [],
    }
    fields = _build_genetic_fields(row)
    assert fields["variant_id"] == "rs1; rs2"


def test_build_genetic_fields_still_handles_scalar_variant_id():
    row = {
        "id": "g2", "studyId": "s2", "score": 0.9,
        "variantRsId": "rs123",
        "clinicalSignificances": [], "allelicRequirements": [],
    }
    fields = _build_genetic_fields(row)
    assert fields["variant_id"] == "rs123"


def test_build_clinical_fields_handles_list_valued_drug_from_source():
    row = {"id": "c1", "score": 0.5, "clinicalStage": "phase_2", "drugFromSource": ["Tofersen", "RILUZOLE"]}
    fields = _build_clinical_fields(row)
    assert fields["intervention"] == "tofersen; riluzole"


def test_build_clinical_fields_still_handles_scalar_drug_from_source():
    row = {"id": "c2", "score": 0.5, "clinicalStage": "phase_2", "drugFromSource": "TOFERSEN"}
    fields = _build_clinical_fields(row)
    assert fields["intervention"] == "tofersen"


def test_build_clinical_fields_handles_missing_drug_from_source():
    row = {"id": "c3", "score": 0.5, "clinicalStage": "phase_2"}
    fields = _build_clinical_fields(row)
    assert fields["intervention"] is None


def test_build_tissue_expression_fields_handles_list_valued_distribution():
    hpa_data = {"rna_tissue_specificity": "Tissue enhanced", "rna_tissue_distribution": ["Detected in all", "Detected in many"]}
    fields = _build_tissue_expression_fields(hpa_data, "ENSG00000142168")
    assert fields["tissue"] == "Detected in all; Detected in many"


def test_build_tissue_expression_fields_still_handles_scalar_distribution():
    hpa_data = {"rna_tissue_specificity": "Tissue enhanced", "rna_tissue_distribution": "Detected in all"}
    fields = _build_tissue_expression_fields(hpa_data, "ENSG00000142168")
    assert fields["tissue"] == "Detected in all"


# --- Bug 2: transaction isolation ---------------------------------------

def test_one_bad_record_does_not_roll_back_others_for_the_same_gene(db_session):
    """
    _save_evidence() commits one record at a time, so a failure on one
    record (simulated here with a value SQLite genuinely can't bind) must
    not cost any record saved before it.
    """
    target = Target(gene_symbol="SNCA", ensembl_id="ENSG00000145335", disease_efo_id="MONDO_0005180")
    db_session.add(target)
    db_session.commit()

    good_record_1 = EvidenceRecord(
        target_id=target.id, dimension="genetic", data_source="eva",
        source_type="genetic", source_record_id="rs1", evidence_score=0.9,
    )
    bad_record = EvidenceRecord(
        target_id=target.id, dimension="omics", data_source="expression_atlas",
        source_type="omics", source_record_id="study1", evidence_score=0.5,
        tissue=["this is deliberately a raw unscalarized list to force a real bind failure"],
    )
    good_record_2 = EvidenceRecord(
        target_id=target.id, dimension="literature", data_source="europepmc",
        source_type="literature", source_record_id="pmid1", evidence_score=0.8,
    )

    assert _save_evidence(db_session, good_record_1, "SNCA", "eva") is True
    assert _save_evidence(db_session, bad_record, "SNCA", "expression_atlas") is False
    assert _save_evidence(db_session, good_record_2, "SNCA", "europepmc") is True

    saved = db_session.query(EvidenceRecord).filter_by(target_id=target.id).all()
    saved_sources = {r.data_source for r in saved}
    assert saved_sources == {"eva", "europepmc"}


def test_ingest_target_survives_one_dimension_failing(db_session, monkeypatch):
    """
    Full ingest_target() run: genetic/literature/pathway/drug-target/hpa/
    string all return real-shaped rows successfully; the omics datasource
    deliberately returns a row that fails to save (bad_value re-introduced
    on purpose, matching the real SNCA failure mode, to prove isolation —
    see CLAUDE.md). Every other dimension's data must still be present
    afterward.
    """
    import scripts.ingest_evidence as ie

    monkeypatch.setattr(ie, "get_evidence_by_datatype", lambda *a, **k: [
        {"id": "g1", "studyId": "s1", "datasourceId": "eva", "score": 0.9,
         "clinicalSignificances": ["pathogenic"], "allelicRequirements": ["Autosomal dominant"]},
    ])
    monkeypatch.setattr(ie, "get_evidence_for_datasource", lambda ensembl_id, efo_id, datasource_id: (
        [{"id": "lit1", "literature": ["PMID1"], "score": 1.0, "resourceScore": 1.0, "publicationYear": 2024}]
        if datasource_id == "europepmc" else
        [{"id": "clin1", "score": 0.5, "clinicalStage": "phase_2", "diseaseFromSource": "Parkinson's disease"}]
        if datasource_id == "clinical_precedence" else
        []
        if datasource_id == "impc" else
        # expression_atlas: deliberately malformed (a list-valued `id`,
        # with no studyId, so source_record_id itself becomes a list) to
        # force a real sqlite3-level bind failure independent of the
        # _scalarize() fix — this test proves BUG 2's isolation fix, not
        # a re-test of BUG 1's fix.
        [{"id": ["deliberately", "unscalarizable", "id"]}]
    ))
    monkeypatch.setattr(ie, "get_literature_evidence_pubmed", lambda *a, **k: [])
    monkeypatch.setattr(ie, "get_pathway_evidence", lambda *a, **k: [
        {"pathway": "Some Pathway", "pathwayId": "R-HSA-1", "topLevelTerm": "Metabolism"},
    ])
    monkeypatch.setattr(ie, "get_drug_target_evidence", lambda *a, **k: [
        {"id": "d1", "drug": {"id": "CHEMBL1", "name": "SomeDrug", "drugType": "Small molecule",
                               "mechanismsOfAction": {"rows": []}}, "maxClinicalStage": "phase_3"},
    ])
    monkeypatch.setattr(ie, "get_tissue_expression", lambda *a, **k: None)
    monkeypatch.setattr(ie, "get_ppi_partners", lambda *a, **k: None)

    saved = ingest_target(db_session, "SNCA", "ENSG00000145335")

    records = db_session.query(EvidenceRecord).all()
    dims = sorted({r.dimension for r in records})

    # The omics row's list-valued `source_record_id` is exactly the class of
    # value SQLite/SQLAlchemy cannot bind to a String column (same failure
    # mode as the real, now-fixed tissue bug) — commit() raises, _save_evidence
    # rolls it back and returns False, and the point under test is that this
    # failure is contained to the omics dimension alone.
    assert "omics" not in dims
    assert "genetic" in dims
    assert "literature" in dims
    assert "human_clinical" in dims
    assert "pathway" in dims
    assert "drug_target" in dims
    assert saved == len(records)


# --- Bug 3: stale/mismatched downstream analysis rows surviving a
# re-ingestion, referencing evidence-record ids reused by a DIFFERENT gene
# (real bug found cleaning up an orphaned NEK1 ContradictionLog row) ------

def test_clear_evidence_and_downstream_analysis_removes_everything(db_session):
    """
    Reproduces the real bug end-to-end: ingest evidence for a target, run
    contradictions/gaps/scoring against it (simulated here with direct
    ORM rows rather than the real classifier/scorer, since only the
    clearing behavior is under test), then simulate a re-ingestion refresh
    for the SAME target by calling clear_evidence_and_downstream_analysis().
    Every downstream table must come back empty — not just EvidenceRecord —
    so no stale row can later resolve against a different gene's reused ids.
    """
    target = Target(gene_symbol="SOD1", ensembl_id="ENSG00000142168", disease_efo_id="MONDO_0004976")
    db_session.add(target)
    db_session.commit()

    rec_a = EvidenceRecord(target_id=target.id, dimension="literature", data_source="europepmc", source_record_id="pmid1")
    rec_b = EvidenceRecord(target_id=target.id, dimension="literature", data_source="europepmc", source_record_id="pmid2")
    db_session.add_all([rec_a, rec_b])
    db_session.commit()

    db_session.add(ContradictionLog(
        target_id=target.id, evidence_record_a_id=rec_a.id, evidence_record_b_id=rec_b.id,
        classification="literature_contradiction", status="confirmed", proposed_by="llm_proposer",
    ))
    db_session.add(GapRecord(target_id=target.id, gap_type="mechanistic", rationale="stale rationale"))
    db_session.add(PriorityScore(target_id=target.id, priority_score=0.5, dimension_breakdown="{}"))
    db_session.add(PipelineRunLog(target_id=target.id, stage="contradictions"))
    db_session.add(PipelineRunLog(target_id=target.id, stage="gaps"))
    db_session.commit()

    assert db_session.query(EvidenceRecord).count() == 2
    assert db_session.query(ContradictionLog).count() == 1
    assert db_session.query(GapRecord).count() == 1
    assert db_session.query(PriorityScore).count() == 1
    assert db_session.query(PipelineRunLog).count() == 2

    counts = clear_evidence_and_downstream_analysis(db_session)

    assert counts == {
        "contradiction_log": 1, "gap_records": 1, "priority_scores": 1,
        "pipeline_run_log": 2, "evidence_records": 2,
    }
    assert db_session.query(EvidenceRecord).count() == 0
    assert db_session.query(ContradictionLog).count() == 0
    assert db_session.query(GapRecord).count() == 0
    assert db_session.query(PriorityScore).count() == 0
    assert db_session.query(PipelineRunLog).count() == 0


def test_clear_evidence_and_downstream_analysis_prevents_cross_gene_id_reuse_mismatch(db_session):
    """
    The exact real scenario found in production: target A (NEK1-like) gets
    a ContradictionLog row referencing its own evidence records. A full
    re-ingestion (target A refreshed, or a brand-new target B ingested
    after A) is simulated by clearing, then inserting FRESH evidence rows
    that happen to land on the SAME auto-increment ids (guaranteed here by
    starting from a clean in-memory DB) but for a DIFFERENT target. Without
    clearing ContradictionLog too, the old row would now silently resolve
    to target B's real evidence — a wrong-but-plausible answer. With the
    fix, the old row is gone before the id reuse can even happen.
    """
    target_a = Target(gene_symbol="NEK1", ensembl_id="ENSG00000137601", disease_efo_id="MONDO_0004976")
    db_session.add(target_a)
    db_session.commit()

    rec_a1 = EvidenceRecord(target_id=target_a.id, dimension="literature", data_source="europepmc", source_record_id="pmidA1")
    rec_a2 = EvidenceRecord(target_id=target_a.id, dimension="literature", data_source="europepmc", source_record_id="pmidA2")
    db_session.add_all([rec_a1, rec_a2])
    db_session.commit()
    stale_ids = (rec_a1.id, rec_a2.id)

    db_session.add(ContradictionLog(
        target_id=target_a.id, evidence_record_a_id=rec_a1.id, evidence_record_b_id=rec_a2.id,
        classification="literature_contradiction", status="confirmed", proposed_by="llm_proposer",
    ))
    db_session.commit()

    # Simulate a full re-ingestion: clear everything, then a different
    # gene's evidence happens to be inserted first and lands on the exact
    # same reused primary keys.
    clear_evidence_and_downstream_analysis(db_session)

    target_b = Target(gene_symbol="FUS", ensembl_id="ENSG00000089280", disease_efo_id="MONDO_0004976")
    db_session.add(target_b)
    db_session.commit()
    rec_b1 = EvidenceRecord(target_id=target_b.id, dimension="literature", data_source="europepmc", source_record_id="pmidB1")
    rec_b2 = EvidenceRecord(target_id=target_b.id, dimension="literature", data_source="europepmc", source_record_id="pmidB2")
    db_session.add_all([rec_b1, rec_b2])
    db_session.commit()

    assert (rec_b1.id, rec_b2.id) == stale_ids  # confirms the id-reuse premise actually holds in this test
    # The old ContradictionLog row must be gone — not surviving to silently
    # resolve against target_b's new rows at the same ids.
    assert db_session.query(ContradictionLog).count() == 0
