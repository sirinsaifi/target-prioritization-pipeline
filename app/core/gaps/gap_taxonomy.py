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
    # New (this task) — real Open Targets Known Safety Events
    # (Target.safetyLiabilities). Deliberately a plain has_*/events pair,
    # the same shape as has_pathway_evidence/has_known_compound above, NOT
    # a 0-1 score: a documented safety concern is categorically different
    # from "how much evidence exists" (see
    # scripts/ingest_evidence.py's _build_safety_signal_fields() docstring
    # for the full reasoning on why this dimension is never scored).
    # `safety_signal_events` carries the real event names so the gap
    # rationale below can name them specifically, not just say "yes/no".
    has_safety_signal: bool = False
    safety_signal_events: list = field(default_factory=list)
    # New (this task) — real Open Targets Gene Essentiality (Target.
    # isEssential / DepMap). Kept as its own has_*/note pair, distinct from
    # has_safety_signal above: essentiality is a predictive risk signal
    # from CRISPR knockout screens in cancer cell lines, not an observed
    # clinical safety event — see scripts/ingest_evidence.py's
    # _build_essentiality_fields() docstring for the full reasoning
    # (including why SOD1 being flagged essential does NOT contradict its
    # real, marketed ASO knockdown therapy). `essentiality_risk_note`
    # carries the real DepMap summary text so the gap rationale can be
    # specific, not just yes/no.
    has_essentiality_risk: bool = False
    essentiality_risk_note: str | None = None
    # New (this task) — real Open Targets Paralogues (Target.homologues).
    # Deliberately NOT a has_*/gap-triggering pair like the two above: a
    # paralogue relationship is genuinely two-sided (see
    # scripts/ingest_evidence.py's _build_paralogy_fields() docstring), so
    # it does not get its own gap type. Instead, real paralogues at or
    # above this project's own note-worthiness threshold
    # (config.PARALOGUE_MODALITY_NOTE_IDENTITY_THRESHOLD) are surfaced as
    # an ENRICHMENT to the existing Modality gap's own text when that gap
    # already fires for an unrelated reason (no known compound) — a highly
    # redundant target may be harder to drug effectively, which is exactly
    # what the Modality gap is about. This never changes whether the
    # Modality gap fires, only what it says when it does.
    paralogue_high_identity_matches: list = field(default_factory=list)
    # New (this task — "fully actionable gap" decision-layer feature). Real
    # per-pair field-VALUE detail behind each population_heterogeneity
    # contradiction (e.g. "population: 'european' vs 'east_asian' (eva vs
    # eva)"), built in app/api/routes/gaps.py from the real EvidenceRecord
    # rows a ContradictionLog row references. Distinct from
    # `population_heterogeneity_count` above: the count alone was a
    # generic restatement of the gap type ("N pairs found"), not the
    # SPECIFIC real evidence that led to the gap — this is what lets the
    # gap's "Evidence" text name the actual real cohort/population values
    # found, not a placeholder. Defaults to empty (not every caller
    # supplies it — see identify_gaps()'s own fallback wording when empty).
    population_heterogeneity_details: list = field(default_factory=list)


@dataclass
class GapFinding:
    gap_type: str
    rationale: str
    investigation_suggestion: str
    # New (this task). Two more parts of the "fully actionable gap" format
    # (Gap Type -> Evidence -> Why it matters -> Next investigation ->
    # Decision impact): `rationale` above already served as "Evidence"
    # (the real numbers/values that triggered the rule) and
    # `investigation_suggestion` already served as "Next investigation" —
    # both were audited and found to already exist before this task added
    # anything. These two are genuinely new: TEMPLATED (WHY_IT_MATTERS/
    # DECISION_IMPACT below), one sentence each, never freely generated by
    # an LLM — same deterministic-and-auditable discipline as every other
    # gap field.
    why_it_matters: str
    decision_impact: str


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
    # New (this task). Deliberately does NOT say "avoid this target" — a
    # documented safety liability varies enormously in real severity and
    # target-class relevance (see app/ingestion/open_targets_client.py's
    # get_prioritisation_and_safety() docstring: OTP's own real data spans
    # everything from a specific mechanism-based cardiotoxicity finding to
    # a general drug-toxicity pharmacogenomics note) — this is a prompt to
    # go read the real, specific finding, not an automatic disqualifier.
    "safety_signal": "{gene} shows strong evidence support, but at least one real, documented safety "
                      "concern is on record: {events}. This does not automatically disqualify {gene} as "
                      "a target — safety liabilities vary widely in severity, mechanism, and relevance to "
                      "this specific disease/modality context. Suggest reviewing the specific real "
                      "event(s), their datasource, and any reported tissue/dosing context before treating "
                      "this as prohibitive.",
    # New (this task). Distinct wording from safety_signal above on purpose:
    # essentiality is a PREDICTIVE signal from cancer-cell-line CRISPR
    # knockout screens, not an OBSERVED clinical event — the template says
    # so explicitly, and explicitly names the real SOD1/tofersen
    # counter-example so a reader doesn't over-read a flag here as
    # definitive (see scripts/ingest_evidence.py's
    # _build_essentiality_fields() docstring for the full reasoning).
    "essentiality_risk": "{gene} shows strong evidence support, but is flagged as essential by Open "
                          "Targets/DepMap ({note}). This reflects a COMPLETE CRISPR knockout's effect on "
                          "proliferating cancer cell lines, not necessarily the safety of a specific "
                          "therapeutic modality (e.g. a partial, tissue-targeted knockdown) in a specific "
                          "human tissue — SOD1, an approved ALS drug target via the knockdown therapy "
                          "tofersen, is itself flagged essential by this same real data. This does not "
                          "automatically disqualify {gene}; suggest weighing the real modality actually "
                          "being considered (knockdown vs. full knockout) before treating this as "
                          "prohibitive.",
}


# New (this task) — the "fully actionable gap" decision-layer feature. Two
# more templated (never LLM-generated), one-sentence parts per gap type,
# completing the 5-part format: Gap Type -> Evidence (rationale) -> Why it
# matters -> Next investigation (investigation_suggestion) -> Decision
# impact. Both dicts are keyed by the same gap_type strings as
# GAP_TEMPLATES above and interpolate only {gene} — same disease-agnostic
# discipline as GAP_TEMPLATES (see gap_taxonomy.py's own "Disease-agnostic
# verification" precedent in docs/07).
WHY_IT_MATTERS = {
    "mechanistic": "Without confirmed pathway or interactome context, the biological mechanism "
                   "connecting {gene} to disease remains unclear, raising the risk that an "
                   "intervention would not produce the intended therapeutic effect.",
    "population": "A finding that only replicates in one population/cohort is a real "
                  "generalizability concern — the same effect may not hold in the other patient "
                  "populations a therapeutic program for {gene} would need to serve.",
    "modality": "Without a known compound or clinical program, it is unclear which drug modality "
                "(small molecule, biologic, RNA-targeted, gene therapy) could practically address "
                "{gene}, which affects both technical feasibility and time-to-clinic.",
    "validation": "Without human/clinical data, there is no direct evidence yet that modulating "
                  "{gene} produces a therapeutic benefit or an acceptable safety profile in "
                  "patients.",
    "evidence_consistency": "Disagreeing evidence sources make it harder to trust a single "
                             "interpretation of {gene}'s role in disease, and could indicate a "
                             "real population-, assay-, or context-dependent effect rather than a "
                             "uniform one.",
    "safety_signal": "A documented safety liability could translate into real adverse effects if "
                      "{gene} is modulated therapeutically, independent of how strong the "
                      "disease-association evidence is.",
    "essentiality_risk": "A gene flagged essential in broad CRISPR knockout screens carries a "
                          "real, if not directly transferable, caution about whether strongly "
                          "inhibiting or fully eliminating {gene}'s function could harm healthy "
                          "cells.",
}

DECISION_IMPACT = {
    "mechanistic": "May require additional mechanistic validation before advancing {gene} past "
                   "early discovery, since the pathway a therapy would need to act through is not "
                   "yet confirmed.",
    "population": "Limits confidence in broader patient applicability until addressed with a "
                  "replication study in an independent population.",
    "modality": "May indicate {gene} requires a different drug modality than initially assumed, "
                "or that discovery work on a compound has not yet started.",
    "validation": "{gene}'s translational risk remains largely unproven in humans — treat any "
                  "prioritization decision as preclinical-stage confidence only.",
    "evidence_consistency": "Confidence in {gene}'s priority score should be discounted until the "
                             "source of disagreement is resolved or explained.",
    "safety_signal": "Any advancement decision for {gene} should explicitly weigh this real "
                      "safety liability against the therapeutic benefit sought, not just the "
                      "priority score.",
    "essentiality_risk": "Favor a partial-modulation modality (e.g. knockdown) over full "
                          "knockout/loss-of-function approaches for {gene} until tissue-specific "
                          "safety is better understood.",
}


def identify_gaps(summary: TargetEvidenceSummary,
                   consistency_gap_threshold: float = 0.5,
                   strength_high_threshold: float = 0.7) -> list[GapFinding]:
    """
    Evaluate all 7 gap rules against a target's evidence summary.
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
            WHY_IT_MATTERS["mechanistic"].format(gene=g),
            DECISION_IMPACT["mechanistic"].format(gene=g),
        ))

    # 2. Population gap — fed directly by the contradiction classifier's
    # output. Evidence text enriched (this task) with the real
    # population/tissue field VALUES behind each contradiction pair when
    # available (population_heterogeneity_details, built in
    # app/api/routes/gaps.py from the real EvidenceRecord rows) — a
    # generic count alone was a restatement of the gap type, not the
    # specific real evidence that triggered it. Falls back to the count
    # alone if a caller doesn't supply the real details (e.g. an older or
    # simplified evidence profile), so this stays backward compatible.
    if summary.population_heterogeneity_count > 0:
        if summary.population_heterogeneity_details:
            evidence_text = "; ".join(summary.population_heterogeneity_details)
        else:
            evidence_text = (
                f"{summary.population_heterogeneity_count} population-heterogeneity "
                f"pair(s) detected by the contradiction classifier (specific field values unavailable)."
            )
        findings.append(GapFinding(
            "population",
            evidence_text,
            GAP_TEMPLATES["population"].format(gene=g, count=summary.population_heterogeneity_count),
            WHY_IT_MATTERS["population"].format(gene=g),
            DECISION_IMPACT["population"].format(gene=g),
        ))

    # 3. Modality gap. Enriched (this task) with a real paralogue note when
    # one applies — see PARALOGUE_MODALITY_NOTE_IDENTITY_THRESHOLD's own
    # docstring for why this is a separate, more inclusive project-chosen
    # threshold than OTP's own official paralogue-redundancy factor cutoff.
    # This NEVER changes whether the gap fires (still purely
    # has_known_compound-driven) — it only adds real, specific text when it
    # already would have fired anyway.
    if summary.evidence_strength >= strength_high_threshold and not summary.has_known_compound:
        modality_text = GAP_TEMPLATES["modality"].format(gene=g)
        if summary.paralogue_high_identity_matches:
            matches_text = ", ".join(summary.paralogue_high_identity_matches)
            modality_text += (
                f" Note: {g} has real human paralogue(s) with notable sequence identity ({matches_text}) — "
                f"functional redundancy from a close paralogue could reduce a knockdown/knockout approach's "
                f"efficacy as a therapeutic modality, independent of the compound-availability gap above."
            )
        findings.append(GapFinding(
            "modality",
            f"Evidence strength {summary.evidence_strength:.2f} >= {strength_high_threshold} "
            f"but no known compound exists for {g}.",
            modality_text,
            WHY_IT_MATTERS["modality"].format(gene=g),
            DECISION_IMPACT["modality"].format(gene=g),
        ))

    # 4. Validation gap
    if not summary.has_human_clinical_evidence:
        findings.append(GapFinding(
            "validation",
            f"No human/clinical evidence present for {g}.",
            GAP_TEMPLATES["validation"].format(gene=g),
            WHY_IT_MATTERS["validation"].format(gene=g),
            DECISION_IMPACT["validation"].format(gene=g),
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
            WHY_IT_MATTERS["evidence_consistency"].format(gene=g),
            DECISION_IMPACT["evidence_consistency"].format(gene=g),
        ))

    # 6. Safety Signal gap (this task). Deliberately gated on high evidence
    # strength, same pattern as modality/evidence_consistency above —
    # this is specifically the "don't get too excited" finding: a target
    # that otherwise looks like a strong candidate but carries at least
    # one real, documented safety concern. A target with weak evidence
    # already isn't being prioritized on its merits, so a safety flag
    # there is lower-stakes information, not the finding this gap type
    # exists to surface. NOTE, unlike every gap type above: this is the
    # one gap that fires because evidence EXISTS (a real safety event was
    # found), not because it's missing — see GAP_TEMPLATES["safety_signal"].
    if summary.evidence_strength >= strength_high_threshold and summary.has_safety_signal:
        events_text = ", ".join(summary.safety_signal_events) or "documented event(s)"
        findings.append(GapFinding(
            "safety_signal",
            f"Evidence strength {summary.evidence_strength:.2f} >= {strength_high_threshold} "
            f"but {g} has {len(summary.safety_signal_events)} documented safety event(s): {events_text}.",
            GAP_TEMPLATES["safety_signal"].format(gene=g, events=events_text),
            WHY_IT_MATTERS["safety_signal"].format(gene=g),
            DECISION_IMPACT["safety_signal"].format(gene=g),
        ))

    # 7. Essentiality Risk gap (this task). Same gate pattern as
    # safety_signal above (evidence_strength >= threshold) and the same
    # "fires because a real fact EXISTS, not because evidence is missing"
    # character — but a DISTINCT gap type from safety_signal, not merged
    # into it (see TargetEvidenceSummary.has_essentiality_risk's own
    # docstring for why).
    if summary.evidence_strength >= strength_high_threshold and summary.has_essentiality_risk:
        note = summary.essentiality_risk_note or "flagged essential"
        findings.append(GapFinding(
            "essentiality_risk",
            f"Evidence strength {summary.evidence_strength:.2f} >= {strength_high_threshold} "
            f"but {g} is flagged essential by Open Targets/DepMap: {note}.",
            GAP_TEMPLATES["essentiality_risk"].format(gene=g, note=note),
            WHY_IT_MATTERS["essentiality_risk"].format(gene=g),
            DECISION_IMPACT["essentiality_risk"].format(gene=g),
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
