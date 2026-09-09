"""
Tests for the "fully actionable gap" decision-layer feature (priority #2):
every gap should read as a complete 5-part decision unit — Gap Type ->
Evidence (rationale) -> Why it matters -> Next investigation
(investigation_suggestion) -> Decision impact.

AUDIT FINDING (recorded here, not just in the task's own report): rationale
and investigation_suggestion already existed and already served as
"Evidence" and "Next investigation" respectively — genuinely new work was
(a) `why_it_matters`/`decision_impact`, templated per gap type, and (b)
real population/tissue field-VALUE enrichment for the population gap's
Evidence text (previously just a bare count, a generic restatement of the
gap type rather than the specific real evidence). Real ALS data has never
triggered a population gap (see docs/06/07 — ClinVar direction-of-effect
data is uniformly single-direction for these 5 genes), so the population
tests below use constructed fixtures, same "real mechanism, unexercised by
current data" pattern as several other gap types in this project.
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.db.models import Target, EvidenceRecord, ContradictionLog, PriorityScore
from app.core.gaps.gap_taxonomy import (
    identify_gaps, TargetEvidenceSummary, WHY_IT_MATTERS, DECISION_IMPACT, GAP_TEMPLATES,
)


# --- Every gap type has real why_it_matters/decision_impact templates -----

def test_every_gap_template_has_a_why_it_matters_and_decision_impact_entry():
    for gap_type in GAP_TEMPLATES:
        assert gap_type in WHY_IT_MATTERS, f"{gap_type} missing from WHY_IT_MATTERS"
        assert gap_type in DECISION_IMPACT, f"{gap_type} missing from DECISION_IMPACT"


def test_why_it_matters_and_decision_impact_are_disease_agnostic():
    # Same discipline as test_validation_and_modality_gap_wording_is_disease_agnostic()
    # — interpolate only {gene}, no leaked ALS-specific term.
    for gap_type, template in {**WHY_IT_MATTERS, **DECISION_IMPACT}.items():
        text = template.format(gene="ZZZFAKE9")
        for leaked in ("ALS", "Amyotrophic", "sclerosis", "C9orf72", "SOD1", "tofersen"):
            assert leaked not in text, f"{gap_type} template leaked '{leaked}': {text}"


def test_all_seven_gap_types_populate_why_it_matters_and_decision_impact():
    """Every real gap type identify_gaps() can produce must carry non-empty,
    gene-referencing why_it_matters/decision_impact — constructed to fire
    all 7 simultaneously (an artificial combination, not realistic for one
    real gene, but the cleanest way to exercise every branch at once)."""
    summary = TargetEvidenceSummary(
        gene_symbol="TESTGENE",
        dimension_scores={"genetic": 0.9, "omics": 0.0},
        evidence_strength=0.9,
        evidence_consistency=0.1,
        evidence_maturity=0.3,
        has_pathway_evidence=False,
        has_human_clinical_evidence=False,
        has_known_compound=False,
        has_ppi_evidence=False,
        population_heterogeneity_count=1,
        methodological_disagreement_count=1,
        literature_contradiction_count=1,
        has_safety_signal=True,
        safety_signal_events=["some real event"],
        has_essentiality_risk=True,
        essentiality_risk_note="isEssential=True",
    )
    findings = identify_gaps(summary)
    gap_types_found = {f.gap_type for f in findings}
    assert gap_types_found == {
        "mechanistic", "population", "modality", "validation",
        "evidence_consistency", "safety_signal", "essentiality_risk",
    }
    for f in findings:
        assert f.why_it_matters, f"{f.gap_type} has empty why_it_matters"
        assert f.decision_impact, f"{f.gap_type} has empty decision_impact"
        assert "TESTGENE" in f.why_it_matters or "TESTGENE" in f.decision_impact


# --- Population gap: real field-value enrichment, not a bare count --------

def test_population_gap_evidence_uses_real_field_values_when_provided():
    summary = TargetEvidenceSummary(
        gene_symbol="TESTGENE",
        dimension_scores={"genetic": 0.9},
        evidence_strength=0.9, evidence_consistency=0.9, evidence_maturity=0.9,
        has_pathway_evidence=True, has_human_clinical_evidence=True, has_known_compound=True,
        population_heterogeneity_count=1,
        population_heterogeneity_details=["population: 'european' (eva) vs 'east_asian' (eva)"],
    )
    findings = {f.gap_type: f for f in identify_gaps(summary)}
    assert "population" in findings
    # The real field VALUES must appear — not a generic "1 pair(s) detected"
    # restatement of the gap type.
    assert "european" in findings["population"].rationale
    assert "east_asian" in findings["population"].rationale


def test_population_gap_falls_back_to_count_when_no_details_supplied():
    """Backward compatibility: a caller that doesn't supply the new field
    (e.g. an older evidence profile) still gets a real, honest fallback
    rather than a crash or a fabricated detail."""
    summary = TargetEvidenceSummary(
        gene_symbol="TESTGENE",
        dimension_scores={"genetic": 0.9},
        evidence_strength=0.9, evidence_consistency=0.9, evidence_maturity=0.9,
        has_pathway_evidence=True, has_human_clinical_evidence=True, has_known_compound=True,
        population_heterogeneity_count=2,
    )
    findings = {f.gap_type: f for f in identify_gaps(summary)}
    assert "2 population-heterogeneity pair(s)" in findings["population"].rationale
    assert "specific field values unavailable" in findings["population"].rationale


# --- Route-level: real end-to-end wiring, including population enrichment -

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


def test_get_gaps_run_returns_the_full_5_part_format_for_a_real_gap(client_with_test_db):
    """Real NEK1-shaped case: strong evidence, no known compound, no
    human/clinical evidence -> real, live modality + validation gaps (the
    two gap types actually open for a real ALS gene today — see the
    task's own audit). Confirms every part of the 5-part format is present
    and non-empty via the actual HTTP route, not just the pure function."""
    client, SessionLocal = client_with_test_db
    db = SessionLocal()
    target = Target(gene_symbol="NEK1", ensembl_id="ENSG00000137601", disease_efo_id="MONDO_0004976")
    db.add(target)
    db.flush()
    db.add(EvidenceRecord(
        target_id=target.id, dimension="genetic", data_source="eva", source_type="genetic",
        source_record_id="RCV1", evidence_score=0.99, direction_on_trait="Risk",
    ))
    db.commit()
    target_id = target.id
    db.close()

    client.post(f"/contradictions/target/{target_id}/run")
    client.post(f"/scoring/target/{target_id}/compute")
    result = client.post(f"/gaps/target/{target_id}/run").json()

    gap_types = [g["gap_type"] for g in result["gaps"]]
    assert "modality" in gap_types
    assert "validation" in gap_types
    for g in result["gaps"]:
        assert g["rationale"]
        assert g["investigation_suggestion"]
        assert g["why_it_matters"]
        assert g["decision_impact"]
        assert "NEK1" in g["why_it_matters"] or "NEK1" in g["decision_impact"]


def test_get_gaps_run_enriches_population_gap_with_real_field_values(client_with_test_db):
    """Constructed (no real ALS gene has ever triggered a population gap —
    see module docstring): two real clinical evidence records, opposite
    direction_on_trait, matching on `intervention` but differing ONLY in
    `population` -> a real population_heterogeneity contradiction (per
    contradiction_classifier.py — `population` is only an applicable
    comparability field for the "clinical" source-type group, not
    "genetic"), whose real field values must surface in the gap's Evidence
    text end-to-end through the actual route."""
    client, SessionLocal = client_with_test_db
    db = SessionLocal()
    target = Target(gene_symbol="TESTGENE", ensembl_id="ENSG_TEST", disease_efo_id="MONDO_TEST")
    db.add(target)
    db.flush()
    db.add(EvidenceRecord(
        target_id=target.id, dimension="human_clinical", data_source="clinical_precedence", source_type="clinical",
        source_record_id="NCT1", evidence_score=0.7, direction_on_trait="Risk",
        population="european", intervention="tofersen",
    ))
    db.add(EvidenceRecord(
        target_id=target.id, dimension="human_clinical", data_source="clinical_precedence", source_type="clinical",
        source_record_id="NCT2", evidence_score=0.7, direction_on_trait="Protective",
        population="east_asian", intervention="tofersen",
    ))
    db.commit()
    target_id = target.id
    db.close()

    client.post(f"/contradictions/target/{target_id}/run")
    client.post(f"/scoring/target/{target_id}/compute")
    result = client.post(f"/gaps/target/{target_id}/run").json()

    pop_gap = next((g for g in result["gaps"] if g["gap_type"] == "population"), None)
    assert pop_gap is not None, f"expected a population gap, got {[g['gap_type'] for g in result['gaps']]}"
    assert "european" in pop_gap["rationale"]
    assert "east_asian" in pop_gap["rationale"]
    assert pop_gap["why_it_matters"]
    assert pop_gap["decision_impact"]
