from app.core.scoring.harmonic_sum import harmonic_sum_score
from app.core.scoring.evidence_profile import (
    comparable_pair_count, compute_evidence_consistency, compute_evidence_maturity,
)
from app.core.verification.contradiction_classifier import (
    classify_contradiction, EvidenceForComparison,
)
from app.core.gaps.gap_taxonomy import identify_gaps, TargetEvidenceSummary
from app.agent.orchestrator import _template_narrate
from app.config import SOURCE_TYPE_BY_DATA_SOURCE, COMPARABILITY_FIELDS_BY_SOURCE_TYPE
from scripts.ingest_evidence import _build_pathway_fields


def test_harmonic_sum_matches_otp_worked_example():
    # From platform-docs.opentargets.org/associations
    result = harmonic_sum_score([1.0, 0.9, 0.8])
    assert 0.79 <= result <= 0.81


def test_harmonic_sum_empty_list():
    assert harmonic_sum_score([]) == 0.0


def test_genetic_direct_contradiction():
    a = EvidenceForComparison(1, "EVA:1", "genetic", "Risk",
                               variant_id="rs123", clinical_significance="pathogenic",
                               inheritance_pattern="Autosomal dominant")
    b = EvidenceForComparison(2, "EVA:2", "genetic", "Protective",
                               variant_id="rs123", clinical_significance="pathogenic",
                               inheritance_pattern="Autosomal dominant")
    assert classify_contradiction(a, b).classification == "direct_contradiction"


def test_genetic_methodological_disagreement():
    a = EvidenceForComparison(1, "EVA:1", "genetic", "Risk",
                               variant_id="rs123", clinical_significance="pathogenic",
                               inheritance_pattern="Autosomal dominant")
    b = EvidenceForComparison(2, "EVA:2", "genetic", "Protective",
                               variant_id="rs123", clinical_significance="pathogenic",
                               inheritance_pattern="Autosomal recessive")
    assert classify_contradiction(a, b).classification == "methodological_disagreement"


def test_clinical_population_heterogeneity():
    a = EvidenceForComparison(1, "NCT:1", "clinical", "Risk", population="european", endpoint="survival")
    b = EvidenceForComparison(2, "NCT:2", "clinical", "Protective", population="east_asian", endpoint="survival")
    assert classify_contradiction(a, b).classification == "population_heterogeneity"


def test_cross_source_type_is_refused_not_forced():
    a = EvidenceForComparison(1, "EVA:1", "genetic", "Risk")
    b = EvidenceForComparison(2, "PMID:1", "literature", "Risk")
    assert classify_contradiction(a, b).classification == "not_comparable_cross_type"


def test_literature_has_no_structural_basis_for_classification():
    a = EvidenceForComparison(1, "PMID:1", "literature", "Risk")
    b = EvidenceForComparison(2, "PMID:2", "literature", "Protective")
    assert classify_contradiction(a, b).classification == "unclassified"


def test_no_contradiction_same_direction():
    a = EvidenceForComparison(1, "EVA:1", "genetic", "Risk",
                               variant_id="rs123", clinical_significance="pathogenic")
    b = EvidenceForComparison(2, "EVA:2", "genetic", "Risk",
                               variant_id="rs123", clinical_significance="pathogenic")
    assert classify_contradiction(a, b).classification == "no_contradiction"


def test_all_fields_null_on_one_side_is_unclassified_not_direct_contradiction():
    # Opposite direction, but B has zero comparability data at all — we
    # know NOTHING about whether B's context matches A's. This must NOT be
    # reported as a confirmed direct_contradiction (that claims "same
    # context, opposite direction"); the honest answer is "insufficient
    # information". See contradiction_classifier.py "Null-handling".
    a = EvidenceForComparison(1, "EVA:1", "genetic", "Risk",
                               variant_id="rs123", clinical_significance="pathogenic",
                               inheritance_pattern="Autosomal dominant")
    b = EvidenceForComparison(2, "EVA:2", "genetic", "Protective")  # all fields null
    result = classify_contradiction(a, b)
    assert result.classification == "unclassified"
    assert result.matched_fields == []
    assert result.mismatched_fields == []


def test_direct_contradiction_still_requires_at_least_one_confirmed_matched_field():
    a = EvidenceForComparison(1, "EVA:1", "genetic", "Risk", variant_id="rs123")
    b = EvidenceForComparison(2, "EVA:2", "genetic", "Protective", variant_id="rs123")
    result = classify_contradiction(a, b)
    assert result.classification == "direct_contradiction"
    assert result.matched_fields == ["variant_id"]


def test_missing_direction_is_unclassified_not_guessed():
    a = EvidenceForComparison(1, "EVA:1", "genetic", None)
    b = EvidenceForComparison(2, "EVA:2", "genetic", "Risk")
    assert classify_contradiction(a, b).classification == "unclassified"


def test_validation_gap_triggers_when_no_clinical_evidence():
    summary = TargetEvidenceSummary(
        gene_symbol="TEST1",
        dimension_scores={"genetic": 0.9},
        evidence_strength=0.9,
        evidence_consistency=0.9,
        evidence_maturity=0.9,
        has_pathway_evidence=True,
        has_human_clinical_evidence=False,
        has_known_compound=True,
    )
    gap_types = [g.gap_type for g in identify_gaps(summary)]
    assert "validation" in gap_types
    assert "modality" not in gap_types  # has_known_compound=True should suppress this


def test_validation_and_modality_gap_wording_carries_a_data_provenance_caveat():
    # Real finding (docs/07 Phase 9 case-based validation, C9orf72): a
    # "no human/clinical evidence present" claim, stated as flat fact, is
    # misleading — two real C9orf72 ASO trials (BIIB078, WVE-004) exist but
    # aren't indexed in OTP's ChEMBL-style clinical_precedence datasource.
    # Both templates must therefore read as "not found in our data sources",
    # never as "does not exist" — without changing WHEN either gap fires.
    summary = TargetEvidenceSummary(
        gene_symbol="C9orf72",
        dimension_scores={"genetic": 0.9},
        evidence_strength=0.9,
        evidence_consistency=0.9,
        evidence_maturity=0.9,
        has_pathway_evidence=True,
        has_human_clinical_evidence=False,
        has_known_compound=False,
    )
    findings = {g.gap_type: g for g in identify_gaps(summary)}

    assert "validation" in findings and "modality" in findings  # trigger logic unchanged

    for gap_type in ("validation", "modality"):
        suggestion = findings[gap_type].investigation_suggestion
        assert "clinical_precedence" in suggestion
        assert "does not necessarily mean" in suggestion
        assert "RNA-targeted therapies" in suggestion
        # Must not assert absence as settled fact.
        assert "does not exist" not in suggestion.lower()


def test_validation_and_modality_gap_wording_is_disease_agnostic():
    # This pipeline is meant to generalize beyond ALS (see CLAUDE.md/docs/07
    # disease-agnostic reminder) — DISEASE_EFO_ID and CANDIDATE_TARGETS are
    # the only values allowed to be disease-specific. Prove the templates
    # carry no leaked ALS/C9orf72 text by running them against a made-up
    # gene for a made-up disease and asserting the output only ever
    # mentions the gene we passed in, never anything ALS-specific.
    summary = TargetEvidenceSummary(
        gene_symbol="ZZZFAKE9",
        dimension_scores={"genetic": 0.9},
        evidence_strength=0.9,
        evidence_consistency=0.9,
        evidence_maturity=0.9,
        has_pathway_evidence=True,
        has_human_clinical_evidence=False,
        has_known_compound=False,
    )
    findings = {g.gap_type: g for g in identify_gaps(summary)}

    for gap_type in ("validation", "modality"):
        suggestion = findings[gap_type].investigation_suggestion
        assert "ZZZFAKE9" in suggestion
        assert "clinical_precedence" in suggestion  # the real, generic datasource name — fine to name
        for leaked_term in ("ALS", "Amyotrophic", "C9orf72", "SOD1", "sclerosis", "BIIB078", "WVE-004"):
            assert leaked_term not in suggestion


def test_comparable_pair_count_groups_by_source_type():
    # 3 genetic + 2 clinical -> C(3,2) + C(2,2) = 3 + 1 = 4; None entries ignored
    assert comparable_pair_count(["genetic", "genetic", "genetic", "clinical", "clinical", None]) == 4


def test_consistency_is_1_when_no_comparable_pairs():
    assert compute_evidence_consistency({"direct_contradiction": 5}, total_within_type_pairs=0) == 1.0


def test_consistency_penalizes_direct_contradiction_more_than_population_heterogeneity():
    direct = compute_evidence_consistency({"direct_contradiction": 1}, total_within_type_pairs=4)
    population = compute_evidence_consistency({"population_heterogeneity": 1}, total_within_type_pairs=4)
    assert direct < population


def test_maturity_takes_the_most_advanced_dimension_reached():
    # human_clinical (1.0) should dominate even though literature/genetic are also present
    assert compute_evidence_maturity({"literature", "genetic", "human_clinical"}) == 1.0
    assert compute_evidence_maturity({"literature"}) < compute_evidence_maturity({"genetic"})


def test_maturity_is_0_with_no_evidence():
    assert compute_evidence_maturity(set()) == 0.0


def test_template_narrate_reports_missing_target():
    assert _template_narrate(None) == "Target not found."


def test_template_narrate_reports_missing_scores_without_inventing_them():
    context = {"gene_symbol": "TEST1", "has_scores": False}
    narrative = _template_narrate(context)
    assert "TEST1" in narrative
    assert "no scores computed" in narrative


def test_template_narrate_only_prints_values_present_in_context():
    # Every number in the narrative must trace back to `context` — this
    # test locks that down by checking the exact values appear verbatim.
    context = {
        "gene_symbol": "SOD1",
        "ensembl_id": "ENSG00000142168",
        "disease_efo_id": "MONDO_0004976",
        "has_scores": True,
        "evidence_strength": 0.9996,
        "evidence_consistency": 1.0,
        "evidence_maturity": 1.0,
        "priority_score": 0.9999,
        "dimension_breakdown": {"genetic": 0.9992},
        "evidence_record_counts": {"genetic": 285},
        "contradictions": {"counts": {}, "total_logged": 0, "examples": []},
        "gaps": [],
    }
    narrative = _template_narrate(context)
    assert "SOD1" in narrative
    assert "1.00" in narrative  # consistency/maturity
    assert "genetic=1.00" in narrative
    assert "285 genetic" in narrative
    assert "No contradictions logged" in narrative
    assert "No research gaps identified" in narrative


def test_no_gaps_when_everything_is_covered():
    summary = TargetEvidenceSummary(
        gene_symbol="TEST2",
        dimension_scores={"genetic": 0.9},
        evidence_strength=0.9,
        evidence_consistency=0.9,
        evidence_maturity=0.9,
        has_pathway_evidence=True,
        has_human_clinical_evidence=True,
        has_known_compound=True,
    )
    assert identify_gaps(summary) == []


def test_pathway_registered_as_its_own_source_type():
    # Reactome membership (see open_targets_client.get_pathway_evidence)
    # has no direction/comparability concept at all — must map to an empty
    # comparability list, same reasoning as literature.
    assert SOURCE_TYPE_BY_DATA_SOURCE["reactome"] == "pathway"
    assert COMPARABILITY_FIELDS_BY_SOURCE_TYPE["pathway"] == []


def test_build_pathway_fields_scores_every_real_hit_as_curated():
    row = {"pathway": "Detoxification of Reactive Oxygen Species ", "pathwayId": "R-HSA-3299685", "topLevelTerm": "Cellular responses to stimuli"}
    fields = _build_pathway_fields(row)

    assert fields["dimension"] == "pathway"
    assert fields["data_source"] == "reactome"
    assert fields["source_type"] == "pathway"
    assert fields["source_record_id"] == "R-HSA-3299685"
    assert fields["evidence_score"] == 1.0
    assert "Detoxification of Reactive Oxygen Species" in fields["notes"]
