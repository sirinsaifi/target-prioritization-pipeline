"""
Hands agent-gathered evidence (from app/agent/investigation_loop.py) to the
EXISTING, UNMODIFIED deterministic pipeline — harmonic_sum.py,
dimension_scoring.py, contradiction_classifier.py, evidence_profile.py,
gap_taxonomy.py. Not one scoring/classification function is touched or
reimplemented here; this module only (a) converts agent-gathered raw rows
into the same EvidenceRecord shape scripts/ingest_evidence.py already
produces — reusing its exact field-derivation functions, imported directly,
never duplicated — and (b) calls the same deterministic functions every
other path in this codebase calls, in the same order scoring.py/
contradictions.py/gaps.py already do.

Design decision — deliberately kept OUT of the database: this scores
agent-gathered evidence in memory, using transient EvidenceRecord instances
that are never db.add()'d or committed, rather than writing into the
shared evidence_records/priority_scores/contradiction_log/gap_records
tables the fixed pipeline (scripts/ingest_evidence.py) already populated
for the same targets. Two reasons:
  1. This is explicitly a NEW, SEPARATE path "alongside the existing
     fixed-pipeline ingestion, not a replacement" — persisting into the
     same target's rows would silently mix agent-gathered and
     fixed-pipeline evidence together, making it impossible to tell which
     evidence produced which score.
  2. The explicit goal is comparing repeated agent runs against each other
     — writing each run's rows into the same DB rows would accumulate/
     duplicate across runs rather than yielding independently comparable
     profiles.
Promoting this path to a persisted, first-class alternative later is a
deliberate follow-up decision, not implied by this module.
"""

from collections import Counter
from itertools import combinations

from app.db.models import EvidenceRecord
from app.core.scoring.harmonic_sum import harmonic_sum_score_scaled_for_type
from app.core.scoring.dimension_scoring import score_literature_cooccurrence
from app.core.scoring.evidence_profile import (
    comparable_pair_count, compute_evidence_consistency, compute_evidence_maturity,
)
from app.core.verification.contradiction_classifier import classify_contradiction, EvidenceForComparison
from app.core.gaps.gap_taxonomy import identify_gaps, describe_investigation_coverage, TargetEvidenceSummary
from app.config import EVIDENCE_CONSISTENCY_GAP_THRESHOLD, EVIDENCE_STRENGTH_HIGH_THRESHOLD

# Reuse the EXACT same per-row field-derivation logic the fixed pipeline
# uses, rather than duplicating it.
from scripts.ingest_evidence import (
    _build_genetic_fields, _build_clinical_fields, _build_pathway_fields,
    _build_experimental_fields, _build_omics_fields, _build_drug_target_fields,
    _build_tissue_expression_fields, _build_ppi_network_fields,
)


TOOL_TO_DIMENSION = {
    "search_genetic_evidence": "genetic",
    "search_literature_evidence": "literature",
    "search_pathway_evidence": "pathway",
    "search_clinical_evidence": "human_clinical",
    "search_experimental_evidence": "experimental",
    "search_omics_evidence": "omics",
    "search_drug_target_evidence": "drug_target",
    "search_tissue_expression": "tissue_expression",
    "search_ppi_network": "ppi_network",
}


def _literature_row_to_evidence_record(row: dict) -> EvidenceRecord:
    """
    Mirrors scripts/ingest_evidence.py's inline PubMed-row handling — NOT
    _build_literature_fields(), which is for OTP's europepmc row shape.
    Agent-gathered literature evidence always comes from the direct-PubMed
    client (see app/agent/investigation_tools.py's search_literature_evidence).
    """
    return EvidenceRecord(
        dimension="literature",
        data_source="pubmed",
        source_type="literature",
        source_record_id=row["pmid"],
        raw_value=row["confidence"],
        evidence_score=score_literature_cooccurrence(row["confidence"]),
        publication_year=row.get("year"),
    )


def _tool_results_to_evidence_records(tool_name: str, tool_results: list) -> list:
    """`tool_results` is the list of raw return dicts from every call to
    that tool during one loop (usually one call, but the model could call
    the same tool twice) — flatten and convert every real row.

    search_ppi_network is a structural exception (this task): its
    "rows" ARE the raw per-partner dicts, but _build_ppi_network_fields()
    is a gene-level AGGREGATE builder that consumes the whole partner
    list in one call (mirrors ingest_target()'s own real call site) — so
    it is called once per tool_result, not once per row like every other
    branch below."""
    records = []
    for tool_result in tool_results:
        rows = tool_result.get("rows", [])
        if tool_name == "search_ppi_network":
            # A real query failure (tool_result carries "error") must NOT
            # produce an aggregate record at all — unlike the per-row
            # branches below, where an empty `rows` list from a failure
            # naturally adds zero records on its own, this builder always
            # produces exactly one record from whatever `rows` it's given,
            # so a failure's empty list would otherwise be silently
            # confused with a real, confirmed zero-partner result (same
            # distinction ingest_target() already makes).
            if "error" not in tool_result:
                gene = tool_result.get("gene", "unknown")
                records.append(EvidenceRecord(**_build_ppi_network_fields(rows, gene)))
            continue
        if tool_name == "search_genetic_evidence":
            for row in rows:
                fields = _build_genetic_fields(row)
                records.append(EvidenceRecord(
                    # Real field, populated by open_targets_client.get_evidence_by_datatype()
                    # — no longer a synthetic "_datasource_id" injected by the caller.
                    dimension="genetic", data_source=row.get("datasourceId", "unknown"), **fields,
                ))
        elif tool_name == "search_literature_evidence":
            for row in rows:
                records.append(_literature_row_to_evidence_record(row))
        elif tool_name == "search_clinical_evidence":
            for row in rows:
                fields = _build_clinical_fields(row)
                records.append(EvidenceRecord(
                    dimension="human_clinical", data_source="clinical_precedence", **fields,
                ))
        elif tool_name == "search_pathway_evidence":
            for row in rows:
                records.append(EvidenceRecord(**_build_pathway_fields(row)))
        elif tool_name == "search_experimental_evidence":
            for row in rows:
                fields = _build_experimental_fields(row)
                records.append(EvidenceRecord(
                    dimension="experimental", data_source="impc", **fields,
                ))
        elif tool_name == "search_omics_evidence":
            for row in rows:
                fields = _build_omics_fields(row)
                records.append(EvidenceRecord(
                    dimension="omics", data_source="expression_atlas", **fields,
                ))
        elif tool_name == "search_tissue_expression":
            # rows is [hpa_data] (at most one real dict) — see
            # investigation_tools.search_tissue_expression()'s own
            # docstring; ensembl_id comes from the tool_result, not a
            # per-row field.
            ensembl_id = tool_result.get("ensembl_id", "unknown")
            for row in rows:
                records.append(EvidenceRecord(**_build_tissue_expression_fields(row, ensembl_id)))
        elif tool_name == "search_drug_target_evidence":
            # _build_drug_target_fields() already sets dimension/data_source
            # internally (same pattern as _build_pathway_fields() above) —
            # its rows are ClinicalTargetFromTarget-shaped, not generic
            # Evidence rows, and are already disease-filtered by
            # get_drug_target_evidence() before this tool ever returns them.
            for row in rows:
                records.append(EvidenceRecord(**_build_drug_target_fields(row)))
    return records


def _to_comparison(record: EvidenceRecord) -> EvidenceForComparison:
    """Identical shape to app/api/routes/contradictions.py's _to_comparison()."""
    return EvidenceForComparison(
        record_id=id(record),  # transient object, never has a real DB id
        source_record_id=record.source_record_id,
        source_type=record.source_type,
        direction_on_trait=record.direction_on_trait,
        tissue=record.tissue,
        population=record.population,
        assay_type=record.assay_type,
        endpoint=record.endpoint,
        phenotype=record.phenotype,
        intervention=record.intervention,
        variant_id=record.variant_id,
        clinical_significance=record.clinical_significance,
        inheritance_pattern=record.inheritance_pattern,
    )


def score_investigation_result(investigation_result) -> dict:
    """
    Run the UNMODIFIED deterministic pipeline over whatever evidence one
    investigate_target() run gathered. Returns the same kind of output the
    DB-backed pipeline produces (dimension_breakdown, strength, consistency,
    maturity, priority_score, contradiction counts, gaps) but computed
    entirely in memory — see module docstring for why this stays out of
    the database.
    """
    records = []
    for tool_name, tool_results in investigation_result.gathered_evidence.items():
        records.extend(_tool_results_to_evidence_records(tool_name, tool_results))

    # --- Strength: harmonic_sum_score_scaled_for_type(), UNMODIFIED ---
    scores_by_dimension: dict = {}
    for r in records:
        if r.evidence_score is not None:
            scores_by_dimension.setdefault(r.dimension, []).append(r.evidence_score)
    dimension_breakdown = {
        dim: harmonic_sum_score_scaled_for_type(scores) for dim, scores in scores_by_dimension.items()
    }
    all_scores = [s for scores in scores_by_dimension.values() for s in scores]
    evidence_strength = harmonic_sum_score_scaled_for_type(all_scores) if all_scores else 0.0

    # --- Contradictions: classify_contradiction(), UNMODIFIED ---
    direction_labeled = [r for r in records if r.direction_on_trait is not None]
    classifications = []
    for rec_a, rec_b in combinations(direction_labeled, 2):
        outcome = classify_contradiction(_to_comparison(rec_a), _to_comparison(rec_b))
        if outcome.classification != "no_contradiction":
            classifications.append(outcome.classification)
    classification_counts = dict(Counter(classifications))

    # --- Consistency: compute_evidence_consistency(), UNMODIFIED ---
    total_pairs = comparable_pair_count([r.source_type for r in direction_labeled])
    evidence_consistency = compute_evidence_consistency(classification_counts, total_pairs)

    # --- Maturity: compute_evidence_maturity(), UNMODIFIED ---
    dimensions_with_evidence = {r.dimension for r in records}
    evidence_maturity = compute_evidence_maturity(dimensions_with_evidence)

    priority_score = round((evidence_strength + evidence_consistency + evidence_maturity) / 3, 4)

    # --- Gaps: identify_gaps(), UNMODIFIED ---
    summary = TargetEvidenceSummary(
        gene_symbol=investigation_result.gene,
        dimension_scores=dimension_breakdown,
        evidence_strength=evidence_strength,
        evidence_consistency=evidence_consistency,
        evidence_maturity=evidence_maturity,
        has_pathway_evidence=any(r.dimension == "pathway" for r in records),
        # Mirrors app/api/routes/gaps.py's same real extension (this task):
        # drug_target evidence is disease-filtered before ever reaching
        # this function (see get_drug_target_evidence()), so a real row
        # here is real human/clinical evidence for THIS disease in its own
        # right, not just a secondary compound-existence signal.
        has_human_clinical_evidence=any(r.dimension in ("human_clinical", "drug_target") for r in records),
        has_known_compound=any(r.dimension in ("human_clinical", "drug_target") and r.intervention for r in records),
        # Mirrors app/api/routes/gaps.py's same real extension (this task):
        # a ppi_network record always exists after a successful STRING
        # query, even with zero real partners (evidence_score=0.0) — a
        # real, positive score is required, not mere row presence, or a
        # confirmed-isolated protein would wrongly suppress the
        # mechanistic gap the same as genuine interactome evidence would.
        has_ppi_evidence=any(r.dimension == "ppi_network" and (r.evidence_score or 0) > 0 for r in records),
        population_heterogeneity_count=classification_counts.get("population_heterogeneity", 0),
        methodological_disagreement_count=classification_counts.get("methodological_disagreement", 0),
    )
    gaps = identify_gaps(
        summary,
        consistency_gap_threshold=EVIDENCE_CONSISTENCY_GAP_THRESHOLD,
        strength_high_threshold=EVIDENCE_STRENGTH_HIGH_THRESHOLD,
    )

    evidence_record_counts: dict = {}
    for r in records:
        evidence_record_counts[r.dimension] = evidence_record_counts.get(r.dimension, 0) + 1

    # Coverage is derived from which tools the agent actually called this
    # run (gathered_evidence's keys — populated even for a tool call that
    # returned zero rows, since investigation_loop.py records every call
    # unconditionally), NOT from evidence_record_counts — a dimension the
    # agent queried and found nothing in is still "explored", unlike one
    # never checked at all. Contrast with the fixed pipeline's gaps route
    # (app/api/routes/gaps.py), which always passes all 4 MVP dimensions.
    explored_dimensions = {
        TOOL_TO_DIMENSION[tool_name]
        for tool_name in investigation_result.gathered_evidence
        if tool_name in TOOL_TO_DIMENSION
    }
    coverage_label, dimensions_not_explored = describe_investigation_coverage(explored_dimensions, verb="explored")

    return {
        "gene": investigation_result.gene,
        "disease": investigation_result.disease,
        "evidence_record_counts": evidence_record_counts,
        "total_records": len(records),
        "dimension_breakdown": dimension_breakdown,
        "evidence_strength": evidence_strength,
        "evidence_consistency": evidence_consistency,
        "evidence_maturity": evidence_maturity,
        "priority_score": priority_score,
        "contradiction_classification_counts": classification_counts,
        "gaps": [
            {"gap_type": g.gap_type, "rationale": g.rationale, "investigation_suggestion": g.investigation_suggestion}
            for g in gaps
        ],
        "investigation_coverage": coverage_label,
        "dimensions_not_explored": dimensions_not_explored,
    }
