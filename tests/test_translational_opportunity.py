"""
Tests for the Translational Opportunity classifier (decision-layer
strategy) — app/core/classification/translational_opportunity.py.

Real, live-verified result across the 5 ALS candidates (see CLAUDE.md):
SOD1 and TARDBP -> "De-risking Needed" (real essentiality_risk flag);
C9orf72 and FUS -> "Clinical-Stage" (real known compound + real human/
clinical evidence via clinicaltrials_gov); NEK1 -> "Early-Stage Discovery"
(real open modality + validation gaps). "Preclinical High-Confidence" is
real and tested here but not hit by any of the 5 real genes today — same
"real but currently unexercised" status as several other features in
this project.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.db.models import Target, EvidenceRecord, PriorityScore
from app.core.classification.translational_opportunity import (
    TranslationalOpportunityInput, classify_translational_opportunity, CATEGORIES,
)


def _base_input(**overrides) -> TranslationalOpportunityInput:
    defaults = dict(
        gene_symbol="TESTGENE", priority_score=0.9, evidence_maturity=0.9,
        has_known_compound=False, has_human_clinical_evidence=False,
        has_safety_signal=False, has_essentiality_risk=False,
    )
    defaults.update(overrides)
    return TranslationalOpportunityInput(**defaults)


# --- Rule 1: caution flags ALWAYS win (the core safety requirement) --------

def test_essentiality_risk_flag_forces_de_risking_needed_even_with_strong_evidence():
    """Real SOD1-shaped case: high priority, high maturity, a real known
    compound AND real clinical evidence (i.e. everything that would
    otherwise qualify for Clinical-Stage) — but a real essentiality flag
    must still force De-risking Needed. This is the literal requirement:
    a caution-flagged target must NEVER land in a purely positive category."""
    inp = _base_input(
        gene_symbol="SOD1", priority_score=0.9999, evidence_maturity=1.0,
        has_known_compound=True, has_human_clinical_evidence=True,
        has_essentiality_risk=True, essentiality_risk_note="isEssential=True",
    )
    result = classify_translational_opportunity(inp)
    assert result.category == "De-risking Needed"
    assert result.is_prototype is True
    # The rationale must state BOTH facts — real strength AND the real
    # flag — never implying the underlying evidence itself is weak.
    assert "high priority" in result.rationale.lower()
    assert "high evidence maturity" in result.rationale.lower()
    assert "essential" in result.rationale.lower()


def test_safety_signal_flag_forces_de_risking_needed_and_names_the_real_event():
    inp = _base_input(
        has_safety_signal=True, safety_signal_events=["prolongation of QT interval of ECG"],
    )
    result = classify_translational_opportunity(inp)
    assert result.category == "De-risking Needed"
    assert "prolongation of QT interval of ECG" in result.rationale


def test_both_caution_flags_present_names_both():
    inp = _base_input(
        has_safety_signal=True, safety_signal_events=["Torsades de Pointes"],
        has_essentiality_risk=True,
    )
    result = classify_translational_opportunity(inp)
    assert result.category == "De-risking Needed"
    assert "Torsades de Pointes" in result.rationale
    assert "essential" in result.rationale.lower()


# --- Rule 2: Clinical-Stage --------------------------------------------------

def test_known_compound_and_clinical_evidence_is_clinical_stage():
    """Real C9orf72/FUS-shaped case: no caution flags, real known compound
    + real human/clinical evidence (via clinicaltrials_gov)."""
    inp = _base_input(has_known_compound=True, has_human_clinical_evidence=True)
    result = classify_translational_opportunity(inp)
    assert result.category == "Clinical-Stage"


def test_known_compound_alone_without_clinical_evidence_is_not_clinical_stage():
    inp = _base_input(has_known_compound=True, has_human_clinical_evidence=False)
    result = classify_translational_opportunity(inp)
    assert result.category != "Clinical-Stage"


# --- Rule 3: Preclinical High-Confidence -------------------------------------

def test_high_priority_high_maturity_no_gaps_no_compound_is_preclinical_high_confidence():
    inp = _base_input(
        priority_score=0.9, evidence_maturity=0.9,
        has_known_compound=False, has_human_clinical_evidence=False,
        open_evidence_gap_types=[],
    )
    result = classify_translational_opportunity(inp)
    assert result.category == "Preclinical High-Confidence"


def test_preclinical_high_confidence_requires_no_open_gaps():
    inp = _base_input(
        priority_score=0.9, evidence_maturity=0.9,
        open_evidence_gap_types=["mechanistic"],
    )
    result = classify_translational_opportunity(inp)
    assert result.category != "Preclinical High-Confidence"


# --- Rule 4: Early-Stage Discovery (fallback) --------------------------------

def test_open_gaps_and_lower_priority_is_early_stage_discovery():
    """Real NEK1-shaped case: priority just above the High cutoff isn't
    enough on its own — real open modality/validation gaps and no known
    compound push this to Early-Stage Discovery, not Preclinical
    High-Confidence (which requires zero open gaps)."""
    inp = _base_input(
        gene_symbol="NEK1", priority_score=0.8291, evidence_maturity=0.5,
        has_known_compound=False, has_human_clinical_evidence=False,
        open_evidence_gap_types=["modality", "validation"],
    )
    result = classify_translational_opportunity(inp)
    assert result.category == "Early-Stage Discovery"
    assert "modality" in result.rationale
    assert "validation" in result.rationale


def test_low_priority_with_no_gaps_still_falls_to_early_stage_discovery():
    inp = _base_input(priority_score=0.2, evidence_maturity=0.2, open_evidence_gap_types=[])
    result = classify_translational_opportunity(inp)
    assert result.category == "Early-Stage Discovery"


# --- Every real category is a documented, real string ----------------------

def test_all_returned_categories_are_in_the_documented_list():
    scenarios = [
        _base_input(has_essentiality_risk=True),
        _base_input(has_known_compound=True, has_human_clinical_evidence=True),
        _base_input(priority_score=0.9, evidence_maturity=0.9, open_evidence_gap_types=[]),
        _base_input(priority_score=0.2, evidence_maturity=0.2, open_evidence_gap_types=["mechanistic"]),
    ]
    for inp in scenarios:
        result = classify_translational_opportunity(inp)
        assert result.category in CATEGORIES
        assert result.is_prototype is True


def test_rationale_never_empty_and_names_the_gene():
    inp = _base_input(gene_symbol="ZZZFAKE9")
    result = classify_translational_opportunity(inp)
    assert result.rationale
    # Rule 4 (Early-Stage Discovery, this input's real outcome) names the
    # gene directly in its own template.
    assert "ZZZFAKE9" in result.rationale


# --- Route-level: real end-to-end wiring, both POST and GET -----------------

@pytest.fixture
def client_with_test_db():
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

    from app.main import app
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app), TestingSessionLocal
    app.dependency_overrides.clear()


def test_post_gaps_run_includes_translational_opportunity_with_caution_flag(client_with_test_db):
    """Real SOD1-shaped scenario through the actual route: strong evidence
    + a real essentiality flag -> De-risking Needed, never a purely
    positive category, confirmed via the real HTTP response."""
    client, SessionLocal = client_with_test_db
    db = SessionLocal()
    target = Target(gene_symbol="SOD1", ensembl_id="ENSG00000142168", disease_efo_id="MONDO_0004976")
    db.add(target)
    db.flush()
    db.add(EvidenceRecord(
        target_id=target.id, dimension="genetic", data_source="eva", source_type="genetic",
        source_record_id="RCV1", evidence_score=0.99, direction_on_trait="Risk",
    ))
    db.add(EvidenceRecord(
        target_id=target.id, dimension="human_clinical", data_source="clinical_precedence", source_type="clinical",
        source_record_id="NCT1", evidence_score=0.9, intervention="tofersen",
    ))
    db.add(EvidenceRecord(
        target_id=target.id, dimension="essentiality_risk", data_source="ot_essentiality",
        source_type="essentiality_risk", source_record_id="ot_essentiality:SOD1",
        raw_value=-1.0, evidence_score=None, notes="isEssential=True; prioritisation_geneEssentiality=-1",
    ))
    db.commit()
    target_id = target.id
    db.close()

    client.post(f"/contradictions/target/{target_id}/run")
    client.post(f"/scoring/target/{target_id}/compute")
    result = client.post(f"/gaps/target/{target_id}/run").json()

    opp = result["translational_opportunity"]
    assert opp["category"] == "De-risking Needed"
    assert opp["is_prototype"] is True
    assert "essential" in opp["rationale"].lower()


def test_get_gaps_returns_the_same_translational_opportunity_without_recomputing_gaps(client_with_test_db):
    client, SessionLocal = client_with_test_db
    db = SessionLocal()
    target = Target(gene_symbol="C9orf72", ensembl_id="ENSG00000147894", disease_efo_id="MONDO_0004976")
    db.add(target)
    db.flush()
    db.add(EvidenceRecord(
        target_id=target.id, dimension="genetic", data_source="eva", source_type="genetic",
        source_record_id="RCV1", evidence_score=0.9, direction_on_trait="Risk",
    ))
    db.add(EvidenceRecord(
        target_id=target.id, dimension="human_clinical", data_source="clinicaltrials_gov", source_type="clinical",
        source_record_id="NCT03626012", evidence_score=0.7, intervention="biib078",
    ))
    db.commit()
    target_id = target.id
    db.close()

    client.post(f"/contradictions/target/{target_id}/run")
    client.post(f"/scoring/target/{target_id}/compute")
    post_result = client.post(f"/gaps/target/{target_id}/run").json()
    get_result = client.get(f"/gaps/target/{target_id}").json()

    assert post_result["translational_opportunity"]["category"] == "Clinical-Stage"
    assert get_result["translational_opportunity"]["category"] == "Clinical-Stage"


def test_translational_opportunity_never_omitted_from_gap_analysis_response(client_with_test_db):
    """Requirement: translational_opportunity is a SEPARATE, always-present
    field — never merged into gaps, never absent from the response shape."""
    client, SessionLocal = client_with_test_db
    db = SessionLocal()
    target = Target(gene_symbol="NEK1", ensembl_id="ENSG00000137601", disease_efo_id="MONDO_0004976")
    db.add(target)
    db.flush()
    db.add(EvidenceRecord(
        target_id=target.id, dimension="genetic", data_source="eva", source_type="genetic",
        source_record_id="RCV1", evidence_score=0.5, direction_on_trait="Risk",
    ))
    db.commit()
    target_id = target.id
    db.close()

    client.post(f"/contradictions/target/{target_id}/run")
    client.post(f"/scoring/target/{target_id}/compute")
    result = client.post(f"/gaps/target/{target_id}/run").json()

    assert "translational_opportunity" in result
    assert "category" in result["translational_opportunity"]
    assert "rationale" in result["translational_opportunity"]
    # Structurally separate from the gaps list itself.
    assert "translational_opportunity" not in result["gaps"]
