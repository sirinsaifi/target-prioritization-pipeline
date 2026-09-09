"""
Tests for app/core/presentation/source_links.py — real, clickable external
source links for evidence records. Every URL template here was decided by
live-checking real SOD1/ALS data first (see that module's docstring for
the full per-datasource investigation and the real URLs actually tested).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import Target, EvidenceRecord
from app.core.presentation.source_links import get_source_url


# --- eva: source_record_id IS a real ClinVar RCV accession -----------------

def test_eva_links_to_clinvar_via_source_record_id():
    url = get_source_url("eva", "RCV001095396", None, None, None)
    assert url == "https://www.ncbi.nlm.nih.gov/clinvar/RCV001095396/"


def test_eva_returns_none_without_source_record_id():
    assert get_source_url("eva", None, None, None, None) is None


# --- uniprot_variants: no real UniProt accession available; dbSNP via rsID -

def test_uniprot_variants_links_to_dbsnp_via_variant_id():
    url = get_source_url("uniprot_variants", "some_internal_hash", "rs121912443", None, None)
    assert url == "https://www.ncbi.nlm.nih.gov/snp/rs121912443"


def test_uniprot_variants_returns_none_without_variant_id():
    assert get_source_url("uniprot_variants", "some_internal_hash", None, None, None) is None


# --- europepmc / pubmed: source_record_id is a real PMID for both ----------

def test_europepmc_links_to_pubmed():
    assert get_source_url("europepmc", "27481264", None, None, None) == "https://pubmed.ncbi.nlm.nih.gov/27481264/"


def test_pubmed_links_to_pubmed():
    assert get_source_url("pubmed", "42701881", None, None, None) == "https://pubmed.ncbi.nlm.nih.gov/42701881/"


# --- reactome / chembl_drug_target: source_record_id already real ---------

def test_reactome_links_to_reactome():
    assert get_source_url("reactome", "R-HSA-114608", None, None, None) == "https://reactome.org/content/detail/R-HSA-114608"


def test_chembl_drug_target_links_to_chembl():
    url = get_source_url("chembl_drug_target", "CHEMBL3833346", None, None, None)
    assert url == "https://www.ebi.ac.uk/chembl/compound_report_card/CHEMBL3833346/"


# --- clinical_precedence: external_id (clinicalReportId) sometimes a real
#     NCT id, sometimes not — real, both shapes seen in real SOD1 data -----

def test_clinical_precedence_links_to_clinicaltrials_for_valid_nct():
    url = get_source_url("clinical_precedence", "some_hash", None, "nct07223723", None)
    assert url == "https://clinicaltrials.gov/study/NCT07223723"


def test_clinical_precedence_handles_uppercase_nct():
    url = get_source_url("clinical_precedence", "some_hash", None, "NCT04972487", None)
    assert url == "https://clinicaltrials.gov/study/NCT04972487"


def test_clinical_precedence_returns_none_for_non_nct_report_id():
    # Real value seen for SOD1: not every clinicalReportId is an NCT id.
    url = get_source_url("clinical_precedence", "some_hash", None, "d0i1cq/amyotrophic lateral sclerosis", None)
    assert url is None


def test_clinical_precedence_returns_none_without_external_id():
    assert get_source_url("clinical_precedence", "some_hash", None, None, None) is None


# --- clinicaltrials_gov: external_id is ALWAYS a real, well-formed NCT id -

def test_clinicaltrials_gov_links_to_the_real_biib078_trial():
    url = get_source_url("clinicaltrials_gov", "NCT04288856", None, "NCT04288856", None)
    assert url == "https://clinicaltrials.gov/study/NCT04288856"


def test_clinicaltrials_gov_returns_none_without_external_id():
    assert get_source_url("clinicaltrials_gov", "NCT04288856", None, None, None) is None


# --- gwas_credible_sets: external_id (credibleSet.studyLocusId) -----------

def test_gwas_credible_sets_links_to_platform_credible_set_page():
    url = get_source_url("gwas_credible_sets", "some_hash", None, "7bda1a15194fa9e277e2f76574d6f4b5", None)
    assert url == "https://platform.opentargets.org/credible-set/7bda1a15194fa9e277e2f76574d6f4b5"


def test_gwas_credible_sets_returns_none_without_external_id():
    assert get_source_url("gwas_credible_sets", "some_hash", None, None, None) is None


# --- string: external_id (resolved STRING protein id) ---------------------

def test_string_links_to_string_network_page():
    url = get_source_url("string", "string:SOD1", None, "9606.ENSP00000270142", None)
    assert url == "https://string-db.org/network/9606.ENSP00000270142"


def test_string_returns_none_without_resolved_id():
    assert get_source_url("string", "string:SOD1", None, None, None) is None


# --- hpa: derived purely from the record's own target's ensembl_id --------

def test_hpa_links_to_protein_atlas_via_ensembl_id():
    url = get_source_url("hpa", "hpa:ENSG00000142168", None, None, "ENSG00000142168")
    assert url == "https://www.proteinatlas.org/ENSG00000142168"


def test_hpa_returns_none_without_ensembl_id():
    assert get_source_url("hpa", "hpa:ENSG00000142168", None, None, None) is None


# --- orphanet / impc: no real per-record external id exposed --------------

def test_orphanet_always_returns_none():
    assert get_source_url("orphanet", "some_hash", None, "anything", "ENSG00000142168") is None


def test_impc_always_returns_none():
    assert get_source_url("impc", "some_hash", None, "anything", "ENSG00000142168") is None


def test_unknown_data_source_returns_none():
    assert get_source_url("some_future_datasource", "id123", "rs1", "ext1", "ENSG1") is None


# --- EvidenceRecord.source_url property (real wiring, not just the pure fn) -

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_evidence_record_source_url_property_uses_own_target_ensembl_id(db_session):
    target = Target(gene_symbol="SOD1", ensembl_id="ENSG00000142168", disease_efo_id="MONDO_0004976")
    db_session.add(target)
    db_session.flush()

    hpa_record = EvidenceRecord(
        target_id=target.id, dimension="tissue_expression", data_source="hpa", source_type="tissue_expression",
        source_record_id="hpa:ENSG00000142168",
    )
    eva_record = EvidenceRecord(
        target_id=target.id, dimension="genetic", data_source="eva", source_type="genetic",
        source_record_id="RCV001095396", variant_id="rs199474723",
    )
    db_session.add_all([hpa_record, eva_record])
    db_session.commit()

    assert hpa_record.source_url == "https://www.proteinatlas.org/ENSG00000142168"
    assert eva_record.source_url == "https://www.ncbi.nlm.nih.gov/clinvar/RCV001095396/"


def test_evidence_record_source_url_property_none_for_orphanet(db_session):
    target = Target(gene_symbol="SOD1", ensembl_id="ENSG00000142168", disease_efo_id="MONDO_0004976")
    db_session.add(target)
    db_session.flush()
    record = EvidenceRecord(
        target_id=target.id, dimension="genetic", data_source="orphanet", source_type="genetic",
        source_record_id="some_hash",
    )
    db_session.add(record)
    db_session.commit()
    assert record.source_url is None


# --- GET /evidence/target/{id} includes the real source_url --------------

@pytest.fixture
def client_with_test_db():
    from app.db.database import get_db
    from app.main import app

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app), TestingSessionLocal
    app.dependency_overrides.clear()


def test_get_evidence_response_includes_real_source_url(client_with_test_db):
    client, SessionLocal = client_with_test_db
    db = SessionLocal()
    target = Target(gene_symbol="SOD1", ensembl_id="ENSG00000142168", disease_efo_id="MONDO_0004976")
    db.add(target)
    db.flush()
    db.add(EvidenceRecord(
        target_id=target.id, dimension="genetic", data_source="eva", source_type="genetic",
        source_record_id="RCV001095396", variant_id="rs199474723", evidence_score=0.9,
    ))
    db.add(EvidenceRecord(
        target_id=target.id, dimension="genetic", data_source="orphanet", source_type="genetic",
        source_record_id="some_hash", evidence_score=0.5,
    ))
    db.commit()
    target_id = target.id
    db.close()

    resp = client.get(f"/evidence/target/{target_id}")
    assert resp.status_code == 200
    body = resp.json()
    by_source = {r["data_source"]: r for r in body}
    assert by_source["eva"]["source_url"] == "https://www.ncbi.nlm.nih.gov/clinvar/RCV001095396/"
    assert by_source["orphanet"]["source_url"] is None


def test_get_evidence_response_includes_notes(client_with_test_db):
    # New (safety signal task) — notes wasn't exposed via the API before;
    # needed since the frontend has no other structured field for real
    # safety_signal event names.
    client, SessionLocal = client_with_test_db
    db = SessionLocal()
    target = Target(gene_symbol="SOD1", ensembl_id="ENSG00000142168", disease_efo_id="MONDO_0004976")
    db.add(target)
    db.flush()
    db.add(EvidenceRecord(
        target_id=target.id, dimension="safety_signal", data_source="ot_safety", source_type="safety_signal",
        source_record_id="HP_0001657", notes="event=prolongation of QT interval of ECG; direction=Inhibition; datasource=Bowes et al. (2012)",
    ))
    db.commit()
    target_id = target.id
    db.close()

    resp = client.get(f"/evidence/target/{target_id}")
    assert resp.status_code == 200
    body = resp.json()[0]
    assert "prolongation of QT interval of ECG" in body["notes"]
