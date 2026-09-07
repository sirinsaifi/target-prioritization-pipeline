"""
Research gap taxonomy — your own contribution.

Each gap type is a falsifiable rule evaluated against normalized evidence
data, not an LLM judgment call. Population-heterogeneity and methodological-
disagreement classifications from the contradiction classifier feed directly
into two of these gap types, so the gap analysis is mechanically connected
to the verification stage rather than an arbitrary label.

Investigation suggestions are templated to the gap type, not freely
generated, so every recommendation is auditable back to the rule that
triggered it.
"""

from dataclasses import dataclass, field

from app.config import MVP_DIMENSIONS


@dataclass
class TargetEvidenceSummary:
    """Minimal shape needed to evaluate gap rules for one target."""
    gene_symbol: str
    dimension_scores: dict  # e.g. {"genetic": 0.82, "literature": 0.6, "pathway": 0.9, "human_clinical": 0.1}
    evidence_strength: float
    evidence_consistency: float
    evidence_maturity: float
    has_pathway_evidence: bool
    has_human_clinical_evidence: bool
    has_known_compound: bool  # any ChEMBL/DrugBank entry for this target
    # New (this task) — explicit decision, not an oversight: a real STRING
    # high-confidence interaction partner suppresses the mechanistic gap
    # the same simple way has_pathway_evidence already does (ANY real row
    # present, regardless of hub-score magnitude) — a genuine PPI-network
    # context is itself mechanistic insight, even without curated pathway
    # membership. Deliberately NOT a new 6th gap type: "zero high-confidence
    # partners" is a real, scorable property of a protein's interactome
    # (see score_ppi_hub()'s docstring), not evidence of an unstudied gap
    # the way "no human/clinical evidence" is — decided explicitly here,
    # not left implicit.
    has_ppi_evidence: bool = False
    population_heterogeneity_count: int = 0
    methodological_disagreement_count: int = 0
    # Phase 7 follow-up: a verified literature contradiction
    # (classification="literature_contradiction", see
    # app/core/verification/literature_contradiction_verifier.py) counts
    # toward the SAME evidence_consistency gap as structured contradictions
    # — a target can have zero structured conflicts and still trigger this
    # gap purely from confirmed literature disagreement, since both now
    # feed the same combined evidence_consistency score (see
    # evidence_profile.combine_consistency_scores()). Kept as its own field
    # here (not merged into methodological_disagreement_count) so the
    # rationale/template text below can name which source actually drove
    # the gap, rather than always blaming "methodological disagreement".
    literature_contradiction_count: int = 0


@dataclass
class GapFinding:
    gap_type: str
    rationale: str
    investigation_suggestion: str


GAP_TEMPLATES = {
    "mechanistic": "Genetic/omics evidence is above threshold but no pathway, PPI-network, or "
                   "other mechanistic evidence exists for {gene}. Suggest a pathway/mechanistic "
                   "study (or a STRING interactome/PPI-network check) to clarify mode of action.",
    "population": "Evidence for {gene} shows population-specific effects across "
                  "{count} record pair(s). Suggest a replication study in a complementary, "
                  "currently under-represented population/cohort.",
    # Both modality and validation are read from `clinical_precedence`
    # (drugFromSource / the row's own presence) AND, as of this task, real
    # drug-target mechanism-of-action data (Target.drugAndClinicalCandidates,
    # see open_targets_client.get_drug_target_evidence()) — both are
    # ChEMBL-backed, small-molecule-leaning sources (see docs/06 and docs/07
    # "Data-provenance wording" note). A real C9orf72 case check found
    # BOTH sources have zero rows for that gene despite two real human ASO
    # trials (BIIB078, WVE-004) — plausibly because RNA-targeted therapies
    # aren't the modality either source indexes well, not because no trial
    # exists. Both templates below are worded as "not found in these data
    # sources", never as "does not exist", for exactly that reason.
    "modality": "{gene} has strong evidence support but no known compound was found in the "
                "currently ingested data sources (via ChEMBL-style clinical_precedence records, "
                "nor via real drug-target mechanism-of-action data). "
                "This does not necessarily mean no compound or therapeutic program exists — "
                "coverage gaps in the underlying data sources are possible, particularly for "
                "non-small-molecule modalities such as RNA-targeted therapies or gene therapy "
                "programs that may not be indexed in ChEMBL/DrugBank. Suggest a targeted "
                "literature/ClinicalTrials.gov search to confirm before treating this as a true "
                "druggability/modality gap.",
    "validation": "No human/clinical evidence was found in the currently ingested data sources "
                  "for {gene} (via ChEMBL-style clinical_precedence records, nor via real "
                  "drug-target mechanism-of-action data). This does not necessarily mean no human "
                  "studies exist — coverage gaps in the underlying data sources are possible, "
                  "particularly for non-small-molecule modalities such as RNA-targeted therapies. "
                  "Suggest a targeted literature/ClinicalTrials.gov search to confirm before "
                  "treating this as a true validation gap.",
    # Names whichever real source(s) actually drove the gap — a target can
    # trigger this purely from confirmed literature contradictions with
    # zero structured (methodological/population) conflicts, or purely
    # from structured ones with zero literature conflicts, or both. Never
    # assume it's methodological disagreement by default (that was this
    # template's behavior before literature_contradiction was wired in —
    # see docs/07 Phase 7 follow-up).
    "evidence_consistency": "{gene} shows high evidence strength ({strength:.2f}) but low "
                             "consistency ({consistency:.2f}), driven by {methodological_count} "
                             "methodological disagreement(s) and {literature_count} confirmed "
                             "literature contradiction(s). Suggest a targeted replication study "
                             "using a standardized assay/endpoint (for the structured "
                             "disagreement) and/or a closer read of the conflicting literature "
                             "excerpts (for the literature-sourced contradiction) to resolve it.",
}


def identify_gaps(summary: TargetEvidenceSummary,
                   consistency_gap_threshold: float = 0.5,
                   strength_high_threshold: float = 0.7) -> list[GapFinding]:
    """
    Evaluate all 5 gap rules against a target's evidence summary.
    A target can trigger more than one gap type simultaneously.

    EXPLICIT DECISION (this task): tissue_expression (Human Protein Atlas)
    deliberately triggers and suppresses NO gap type here, and feeds no
    `has_*`/count field on TargetEvidenceSummary at all. Per the project's
    own early reviewer framing (carried into this task's instruction):
    tissue specificity is a supportive biological-context feature, not a
    direct measure of off-target risk, and a target lacking HPA data is a
    data-coverage footnote, not a research gap the way missing genetic/
    clinical/mechanistic evidence is. This is a considered choice, not an
    oversight — contrast with ppi_network below, which WAS wired in.
    """
    findings = []
    g = summary.gene_symbol

    # 1. Mechanistic gap. The `genetic_or_omics_strong` name predates this
    # task but the check itself only ever looked at genetic — a real,
    # pre-existing mismatch between name and behavior, fixed here now that
    # omics is an actual scored dimension rather than silently left as-is.
    genetic_score = summary.dimension_scores.get("genetic", 0)
    omics_score = summary.dimension_scores.get("omics", 0)
    genetic_or_omics_strong = max(genetic_score, omics_score) >= strength_high_threshold
    # Suppressed by EITHER real pathway evidence OR real PPI-network
    # context (this task, explicit decision — see has_ppi_evidence's own
    # docstring on TargetEvidenceSummary): both are real mechanistic
    # context, neither is disease-specific the way genetic/clinical
    # evidence is, and there's no principled reason to require pathway
    # specifically when a genuine high-confidence interactome exists.
    if genetic_or_omics_strong and not summary.has_pathway_evidence and not summary.has_ppi_evidence:
        driver = "Genetic" if genetic_score >= omics_score else "Omics"
        driver_value = genetic_score if genetic_score >= omics_score else omics_score
        findings.append(GapFinding(
            "mechanistic",
            f"{driver} score {driver_value:.2f} >= {strength_high_threshold} "
            f"but no pathway or PPI-network evidence present.",
            GAP_TEMPLATES["mechanistic"].format(gene=g),
        ))

    # 2. Population gap — fed directly by the contradiction classifier's output
    if summary.population_heterogeneity_count > 0:
        findings.append(GapFinding(
            "population",
            f"{summary.population_heterogeneity_count} population-heterogeneity "
            f"pair(s) detected by the contradiction classifier.",
            GAP_TEMPLATES["population"].format(gene=g, count=summary.population_heterogeneity_count),
        ))

    # 3. Modality gap
    if summary.evidence_strength >= strength_high_threshold and not summary.has_known_compound:
        findings.append(GapFinding(
            "modality",
            f"Evidence strength {summary.evidence_strength:.2f} >= {strength_high_threshold} "
            f"but no known compound exists for {g}.",
            GAP_TEMPLATES["modality"].format(gene=g),
        ))

    # 4. Validation gap
    if not summary.has_human_clinical_evidence:
        findings.append(GapFinding(
            "validation",
            f"No human/clinical evidence present for {g}.",
            GAP_TEMPLATES["validation"].format(gene=g),
        ))

    # 5. Evidence-consistency gap — fed by BOTH the structured contradiction
    # classifier's output AND Phase 7's literature contradiction pipeline.
    # evidence_consistency itself is already the combined score (see
    # evidence_profile.combine_consistency_scores()), so this trigger
    # condition is unchanged — a target can fire it from literature
    # contradictions alone, structured ones alone, or both; the rationale/
    # template below names whichever real counts actually apply.
    if (summary.evidence_strength >= strength_high_threshold
            and summary.evidence_consistency < consistency_gap_threshold):
        findings.append(GapFinding(
            "evidence_consistency",
            f"Strength {summary.evidence_strength:.2f} high but consistency "
            f"{summary.evidence_consistency:.2f} below {consistency_gap_threshold}, "
            f"with {summary.methodological_disagreement_count} methodological disagreement(s) "
            f"and {summary.literature_contradiction_count} confirmed literature contradiction(s).",
            GAP_TEMPLATES["evidence_consistency"].format(
                gene=g, strength=summary.evidence_strength,
                consistency=summary.evidence_consistency,
                methodological_count=summary.methodological_disagreement_count,
                literature_count=summary.literature_contradiction_count,
            ),
        ))

    return findings


def describe_investigation_coverage(explored_dimensions, verb: str = "explored") -> tuple[str, list[str]]:
    """
    Label how completely the 4 MVP dimensions (app.config.MVP_DIMENSIONS)
    were covered before gap findings were computed, so a gap from the
    exhaustive fixed pipeline and a gap from the (possibly incomplete)
    autonomous investigation loop can never be presented as equally
    authoritative — a "no human/clinical evidence" gap means something
    different depending on whether human_clinical was actually checked.

    `verb` is the deliberate wording difference between the two callers:
    the fixed pipeline always passes "queried" (it queries every dimension
    by design), the investigation loop always passes "explored" (an agent
    decision, not a guarantee). Returns (coverage_label, dimensions_not_explored).
    """
    explored = [d for d in MVP_DIMENSIONS if d in explored_dimensions]
    not_explored = [d for d in MVP_DIMENSIONS if d not in explored_dimensions]
    n, total = len(explored), len(MVP_DIMENSIONS)
    if not not_explored:
        return f"complete ({n}/{total} dimensions {verb})", not_explored
    return f"partial ({n}/{total} dimensions {verb}: {', '.join(explored)})", not_explored


if __name__ == "__main__":
    example = TargetEvidenceSummary(
        gene_symbol="FUS",
        dimension_scores={"genetic": 0.85, "literature": 0.6, "pathway": 0.0, "human_clinical": 0.0},
        evidence_strength=0.8,
        evidence_consistency=0.4,
        evidence_maturity=0.3,
        has_pathway_evidence=False,
        has_human_clinical_evidence=False,
        has_known_compound=False,
        population_heterogeneity_count=1,
        methodological_disagreement_count=2,
    )
    for finding in identify_gaps(example):
        print(f"[{finding.gap_type}] {finding.investigation_suggestion}")
