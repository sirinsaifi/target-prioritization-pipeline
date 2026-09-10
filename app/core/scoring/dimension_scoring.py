"""
Per-evidence-type scoring rules.

Each function implements one of OTP's published scoring tables (see
platform-docs.opentargets.org/evidence), scoped to the sources actually used
in this MVP: Genetic (L2G), Literature (Europe PMC-style), Pathway
(Reactome-style), Human/Clinical (trial phase).

IMPORTANT (per mentor feedback): these are treated as prototype
implementations referencing OTP's published methodology, not a guaranteed
byte-for-byte reproduction of OTP's current production scoring — state this
explicitly in the report.
"""

import math

from app.config import (
    L2G_INCLUSION_THRESHOLD, TRIAL_STOPPED_EARLY_WEIGHT,
    OMICS_LOG2FC_SIGNIFICANCE_THRESHOLD, OMICS_PVALUE_SIGNIFICANCE_THRESHOLD,
    TISSUE_SPECIFICITY_SCORES, PPI_HUB_SCORE_CEILING, TDL_SCORES,
)


def score_genetic_l2g(l2g_score: float) -> float | None:
    """
    Genetic dimension — Locus-to-Gene (L2G) score.
    Reference: platform-docs.opentargets.org/evidence
               Ghoussaini et al. 2021, Nucleic Acids Research

    OTP includes GWAS association evidence only where L2G > 0.05.
    We return the L2G score directly as the evidence score (already 0-1),
    or None if it falls below the inclusion threshold.
    """
    if l2g_score is None or l2g_score <= L2G_INCLUSION_THRESHOLD:
        return None
    return round(l2g_score, 4)


def _require_scalar_stage(value, function_name: str):
    """
    score_clinical_precedence()/score_drug_target() look up ONE exact
    stage string in CLINICAL_STAGE_SCORES. Unlike the field-builder
    comparability fields in scripts/ingest_evidence.py (tissue/variant_id/
    intervention — see that file's _scalarize()), silently joining a
    list-valued stage here would produce a key that matches nothing in
    CLINICAL_STAGE_SCORES, falling back to "unknown" (0.01) and silently
    under-scoring real evidence rather than surfacing a real upstream
    data-shape change. A scoring function receiving a list where a single
    stage is expected is a signal worth surfacing loudly, not flattening
    away — so this raises instead of scalarizing. `None` is a legitimate,
    already-handled value for both callers and passes through unchanged.
    """
    if isinstance(value, list):
        raise TypeError(
            f"{function_name} received a list-valued clinical stage ({value!r}) "
            "where a single scalar stage string was expected."
        )
    return value


CLINICAL_STAGE_SCORES = {
    "unknown": 0.01,
    "preclinical": 0.01,
    "ind": 0.05,
    "early_phase_1": 0.05,
    "phase_1": 0.1,
    "phase_1_2": 0.15,
    "phase_2": 0.2,
    "phase_2_3": 0.5,
    "phase_3": 0.7,
    "preapproval": 0.8,
    "approval": 1.0,
    "phase_4": 1.0,
    "withdrawal": 1.0,
}


def score_clinical_precedence(clinical_stage: str, stopped_early_for_negative_or_safety: bool = False) -> float:
    """
    Human/Clinical dimension — Clinical Precedence, 2-step scoring.
    Reference: platform-docs.opentargets.org/evidence ("Clinical Precedence")

    Step 1: base score by clinical stage.
    Step 2: down-weight by 0.5x if the trial stopped early for a negative
    outcome or safety/side-effect reason.
    """
    clinical_stage = _require_scalar_stage(clinical_stage, "score_clinical_precedence")
    stage_key = clinical_stage.lower().replace(" ", "_").replace("/", "_")
    base_score = CLINICAL_STAGE_SCORES.get(stage_key, 0.01)

    if stopped_early_for_negative_or_safety:
        base_score *= TRIAL_STOPPED_EARLY_WEIGHT

    return round(base_score, 4)


def score_pathway_curated(is_curated: bool = True) -> float:
    """
    Pathway dimension — Reactome-style curated evidence.
    Reference: platform-docs.opentargets.org/evidence ("Reactome")

    All manually curated pathway evidence scores a fixed 1.0 in OTP's scheme.
    """
    return 1.0 if is_curated else 0.0


def score_literature_cooccurrence(normalized_confidence: float) -> float:
    """
    Literature dimension — Europe PMC-style co-occurrence confidence.
    Reference: platform-docs.opentargets.org/evidence ("Europe PMC"),
               citing Kafkas et al., 2017

    OTP computes this via weighted document sections, sentence location, and
    title placement, then normalizes 0-1. For this MVP we accept a
    pre-normalized confidence value (e.g. pulled directly from the OTP API,
    or computed via a simplified NER + section-weighting pipeline) rather
    than reimplementing their full NLP pipeline from scratch.
    """
    return round(max(0.0, min(1.0, normalized_confidence)), 4)


def score_experimental(otp_score: float | None) -> float | None:
    """
    Experimental dimension — IMPC (animal_model) / CRISPR screen evidence.

    Reference: platform-docs.opentargets.org/evidence ("IMPC", "CRISPR
    screens"), which describe IntOGen-style scaled-q-value and CRISPR
    linearized-significance formulas as the underlying methodology.

    ADAPTED, not built from those raw formulas: live introspection (real
    sample rows — SOD1's real impc evidence, ERBB2's one real crispr row)
    confirms both datasources already expose OTP's own final, pre-computed,
    already-normalized 0-1 result via the generic `score` field (e.g. SOD1
    impc: score=0.5807, resourceScore=58.07 — the same score/resourceScore*100
    relationship literature evidence already uses). Recomputing the
    underlying q-value/significance scaling ourselves would just reproduce
    what OTP has already done — same "pull, don't rebuild" precedent as
    score_genetic_l2g() (L2G) and score_pathway_curated() (Reactome
    curation), not a new formula.
    """
    if otp_score is None:
        return None
    return round(max(0.0, min(1.0, otp_score)), 4)


def _scale_pvalue(p_value: float | None) -> float | None:
    """
    Prototype log-scale p-value transform for the omics formula below.

    NOT a reproduction of OTP's own internal scaling (no real omics rows
    exist in this project's data to reverse-engineer it from — see
    config.EXPRESSION_ATLAS_DATASOURCE_ID's docstring). Modeled on the
    same log-scale spirit as OTP's published Gene Burden table (0.25 at
    p=1e-7 ramping to 1.0 at p<1e-17 — +0.075 per order of magnitude past
    1e-7), extended down to p=1.0 -> 0.0 so an unremarkable p-value doesn't
    get a nonzero floor score. Explicitly a prototype approximation,
    stated as such rather than an established reference.
    """
    if p_value is None or p_value <= 0:
        return None
    p_value = min(p_value, 1.0)
    magnitude = -math.log10(p_value)  # 0 at p=1.0, grows as p shrinks
    return round(max(0.0, min(1.0, magnitude / 10)), 4)


def score_omics_expression(log2_fold_change: float | None, p_value_mantissa: float | None,
                            p_value_exponent: int | None, percentile_rank: float | None) -> float | None:
    """
    Omics dimension — Expression Atlas differential expression.
    Reference: platform-docs.opentargets.org/evidence ("Expression Atlas");
               see docs/04_scoring_elements_needed.md item 10.

    score = scaled_p_value * (|log2FC| / 10) * (percentile_rank / 100)

    Significance gate (OTP precedent): |log2FC| > 1 and p <= 0.05, mirroring
    score_genetic_l2g()'s below-threshold-excluded pattern — returns None
    (not a fabricated 0.0) if any required real input is missing, or if the
    real values fall outside the significance thresholds.

    NOTE: The DIRECT Expression Atlas REST API (now queried via
    expression_atlas_direct_client.py, NOT the old OTP route) returns
    foldChange (already log2) + pValue (single float, not mantissa+exponent).
    The direct API does NOT provide log2FoldChangePercentileRank, so
    score_omics_expression() returns None for direct-API rows — they fall
    through to the prototype score_omics_baseline_tpm() (baseline TPM) or
    foldChange-only scoring instead.

    Baseline (TPM-only) data from the direct API is scored via
    score_omics_baseline_tpm() which uses categorical thresholds:
      TPM >= 10  → 0.8 (high expression)
      TPM >= 1   → 0.4 (medium expression)
      TPM > 0    → 0.1 (low but detected)
      TPM == 0   → 0.0 (not detected)

    The old OTP `expression_atlas` datasource (log2FoldChangeValue,
    log2FoldChangePercentileRank, pValueMantissa, pValueExponent) is
    CONFIRMED RETIRED — OTP no longer routes to Expression Atlas correctly.
    The underlying EBI database IS alive and reachable via its own direct
    API at https://www.ebi.ac.uk/gxa (confirmed live Sep 2026 with real
    SOD1, TP53, and all 5 ALS genes returning real baseline data).
    """
    if log2_fold_change is None or p_value_mantissa is None or p_value_exponent is None or percentile_rank is None:
        return None

    if abs(log2_fold_change) <= OMICS_LOG2FC_SIGNIFICANCE_THRESHOLD:
        return None

    p_value = p_value_mantissa * (10 ** p_value_exponent)
    if p_value > OMICS_PVALUE_SIGNIFICANCE_THRESHOLD:
        return None

    scaled_p = _scale_pvalue(p_value)
    if scaled_p is None:
        return None

    score = scaled_p * (abs(log2_fold_change) / 10) * (percentile_rank / 100)
    return round(max(0.0, min(1.0, score)), 4)


def score_drug_target(max_clinical_stage: str | None) -> float:
    """
    Drug-Target dimension — real ChEMBL-backed drug-target mechanism data
    from Target.drugAndClinicalCandidates (see
    open_targets_client.get_drug_target_evidence()'s docstring for why this
    is a different real API path than clinical_precedence, not a duplicate
    of it).

    OTP does NOT provide a pre-computed numeric score for this field
    (confirmed via introspection — ClinicalTargetFromTarget's only fields
    are id/maxClinicalStage/drug/clinicalReports/diseases, no `score`) —
    same situation as pathway evidence. PROTOTYPE formula, not an
    established OTP reference (explicitly per this task's instruction):
    reuses the existing CLINICAL_STAGE_SCORES table (the same real,
    OTP-published stage->score table clinical_precedence already uses),
    applied to this row's `maxClinicalStage` — a reasonable, simple,
    documented choice for consistency, not a claim that OTP scores this
    field the same way.
    """
    max_clinical_stage = _require_scalar_stage(max_clinical_stage, "score_drug_target")
    if not max_clinical_stage:
        return CLINICAL_STAGE_SCORES["unknown"]
    stage_key = max_clinical_stage.lower().replace(" ", "_").replace("/", "_")
    return CLINICAL_STAGE_SCORES.get(stage_key, CLINICAL_STAGE_SCORES["unknown"])


def score_tissue_specificity(rna_tissue_specificity: str | None) -> float | None:
    """
    Tissue Expression dimension — Human Protein Atlas (HPA), NOT Open
    Targets (see app/ingestion/hpa_client.py's docstring for why OTP's own
    Expression Atlas datasource is unavailable). PROTOTYPE tau-score-like
    metric, explicitly not a reproduction of the published tau statistic —
    built from HPA's real, reliably-populated "RNA tissue specificity"
    category (confirmed live for 3 real genes spanning the specificity
    spectrum: SOD1="Tissue enhanced", INS="Tissue enriched",
    ACTB="Low tissue specificity" — see TISSUE_SPECIFICITY_SCORES).

    FRAMING (per early reviewer feedback, carried into this task's own
    instruction): this score is a supportive biological-context feature.
    It must never be treated as, or presented as, a measure of
    off-target/safety risk — enforced here by keeping this function pure
    (category -> score, nothing else) and by gap_taxonomy.py deliberately
    wiring this dimension into no gap type at all.

    Returns None for "Not detected" or an unrecognized/missing category —
    a real absence of signal, not a fabricated 0.0.
    """
    if not rna_tissue_specificity:
        return None
    return TISSUE_SPECIFICITY_SCORES.get(rna_tissue_specificity.strip().lower())


def compute_tau_specificity(median_expression_by_tissue: dict) -> float | None:
    """
    Tissue Expression dimension — GTEx, a second independent source
    alongside HPA (see app/ingestion/gtex_client.py's module docstring for
    why this is dimension="tissue_expression", not a new "omics"
    dimension). The REAL, published tau tissue-specificity statistic
    (Yanai et al. 2005, Bioinformatics) — score_tissue_specificity()
    above explicitly could NOT compute this from HPA alone ("HPA's JSON
    API doesn't expose a complete per-tissue expression vector in one
    field"). GTEx's medianGeneExpression endpoint provides exactly that
    real, complete vector (54 real tissues, confirmed live for SOD1/TP53),
    making the actual statistic computable here for the first time in this
    project — not a prototype approximation this time.

    tau = sum(1 - x_i/x_max) / (n - 1) across all real tissues; 0.0 means
    uniformly/ubiquitously expressed, 1.0 means fully tissue-specific.
    Same 0-1 scale and "higher = more tissue-specific" direction as
    score_tissue_specificity()'s TISSUE_SPECIFICITY_SCORES (which tops out
    at 1.0 for "Tissue enriched"), so this can be used as a real,
    continuously-computed evidence_score directly, without bucketing.

    Returns None if fewer than 2 real tissues are available, or the gene
    shows zero real expression everywhere (max <= 0) — genuine "cannot
    compute" cases, not a fabricated 0.0.
    """
    values = list(median_expression_by_tissue.values())
    if len(values) < 2:
        return None
    max_value = max(values)
    if max_value <= 0:
        return None
    tau = sum(1 - (v / max_value) for v in values) / (len(values) - 1)
    return round(tau, 4)


def score_ppi_hub(high_confidence_partner_count: int) -> float:
    """
    PPI Network dimension — STRING high-confidence (combined_score > 700)
    interaction partner count.
    Reference: string-db.org (this project's own prototype normalization,
    not a published STRING formula — STRING itself does not define a
    single "hub score"; per this task's own instruction, documented as a
    prototype, not an established reference).

    hub_score = min(partner_count / PPI_HUB_SCORE_CEILING, 1.0)

    A count of 0 real high-confidence partners returns 0.0 (a real,
    meaningful low score — not None): unlike genetic/omics evidence, where
    "below threshold" means "we can't trust this measurement", a gene
    genuinely having no high-confidence STRING partners is itself a real,
    scorable observation about its interactome, not a missing input.
    """
    return round(min(max(high_confidence_partner_count, 0) / PPI_HUB_SCORE_CEILING, 1.0), 4)


def score_druggability_tdl(tdl: str | None) -> float | None:
    """
    Druggability dimension — Pharos Target Development Level (TDL), an
    independent signal from Open Targets (see app/ingestion/pharos_client.py's
    docstring for the live-confirmed field semantics and why this is the
    project's first real druggability source — OTP's own prioritisation
    factors deliberately exclude every structural/druggability factor).

    PROTOTYPE mapping (per this task's own instruction, documented as a
    prototype the same as every other threshold in this project — NOT an
    externally published scale): Tclin=1.0, Tchem=0.7, Tbio=0.4, Tdark=0.1.
    These reflect Pharos's own ordinal druggability tiers (Tclin targets have
    approved drugs; Tdark targets have almost no known ligands/drugs), mapped
    to a 0-1 scale for this project's own ranking convenience.

    IMPORTANT — KEPT OUT OF THE OTP-BASED PRIORITY SCORE: the returned score
    is stored in EvidenceRecord.raw_value, NOT evidence_score (which is left
    None — see scripts/ingest_evidence.py's _build_druggability_fields()
    docstring). This guarantees druggability can NEVER be silently averaged
    into evidence_strength/dimension_breakdown/evidence_maturity (scoring.py
    only aggregates records whose evidence_score is non-null), exactly the
    same structural mechanism safety_signal/essentiality_risk/paralogy already
    use — druggability is a target PROPERTY, not translational evidence, and
    is surfaced instead via its own gap type (gap_taxonomy "druggability") and
    translational_opportunity (Tdark -> Early-Stage Discovery, Tclin
    reinforces Clinical-Stage). This function exists so the mapping is a
    single named, testable, deterministic rule rather than inlined in the
    ingestion builder.

    Returns None for an unrecognized/missing TDL — a real absence of signal,
    not a fabricated 0.0 (Pharos always returns one of the four real tiers
    for a found target, so None here means the target itself wasn't found).
    """
    if not tdl:
        return None
    return TDL_SCORES.get(tdl.strip())


DIMENSION_SCORERS = {
    "genetic": score_genetic_l2g,
    "literature": score_literature_cooccurrence,
    "pathway": score_pathway_curated,
    "human_clinical": score_clinical_precedence,
    "experimental": score_experimental,
    "omics": score_omics_expression,
    "drug_target": score_drug_target,
    "tissue_expression": score_tissue_specificity,
    "ppi_network": score_ppi_hub,
    # NOTE: "druggability" and "competitive_position" are deliberately
    # ABSENT from this dict. Both are independent context signals kept out of
    # the OTP-based priority_score (see score_druggability_tdl()'s docstring
    # and _build_competitive_position_fields()'s) — their scores live in
    # raw_value with evidence_score=None, so scoring.py never aggregates them.
    # Registering them here would imply they flow through the same
    # harmonic-sum strength path as real evidence, which they must not.
}
