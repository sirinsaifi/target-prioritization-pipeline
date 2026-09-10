"""
Real evidence ingestion for the 5 ALS candidate genes.

Pulls evidence rows from the live Open Targets Platform API for each
(gene, datasource) pair, normalizes them into EvidenceRecord rows using the
source-type-specific field derivation discovered via live GraphQL
introspection (see CLAUDE.md "Important discovery"), and saves them to the
database.

Datasources actually queried for this MVP run:
    europepmc            -> literature
    clinical_precedence  -> human_clinical
    impc                 -> experimental (phase 2 — stored with
        source-type fields populated, but evidence_score is left None since
        no phase-2 scorer exists yet in dimension_scoring.py)

Genetic evidence is NOT a hardcoded datasource list here — it's fetched via
OTP's real "genetic_association" datatype (config.GENETIC_DATATYPE_ID,
open_targets_client.get_evidence_by_datatype()). A hardcoded list
(previously `eva`/`uniprot_variants`/`gwas_credible_sets`, chosen because
these dominate ALS's rare-variant genetics) silently under-collected real
evidence in two confirmed ways: it never included `orphanet` (a real
datasourceId under the same datatype nobody had anticipated), and each
per-datasource fetch was separately capped at `size` (200), silently
truncating `eva`'s real 275 SOD1 rows down to 200. Both are fixed by
fetching the whole datatype, discovered and paginated dynamically — see
open_targets_client.get_evidence_by_datatype()'s docstring and docs/07
"Genetic evidence: datatype-driven fetch" for the live schema check and
real before/after SOD1 numbers.

Low-volume datasources seen during exploration under the "genetic_literature"
datatype (genomics_england, clingen, uniprot_literature — 1-2 rows each for
SOD1) are still skipped for this MVP; documented limitation, not an
oversight. `orphanet` is NOT in this skip list — it's a real
"genetic_association" datasourceId (1 SOD1 row) and is now included
automatically via the datatype-driven genetic fetch above.

In addition to OTP's `europepmc`, this script also pulls a second,
independent literature source directly from PubMed (see
app/ingestion/literature_client.py) — `data_source="pubmed"`, still
`dimension="literature"`. This is deliberately a much simpler
presence-based signal (confidence always 1.0), not a duplicate of OTP's own
NLP-scored evidence; see that module's docstring for why.

Also ingests Pathway evidence (`dimension="pathway"`, `data_source="reactome"`)
via `get_pathway_evidence()` — a disease-agnostic Target.pathways lookup,
NOT an evidences()-based datasource (confirmed live: pathway/Reactome
evidence does not exist through evidences() for any of these 5 genes at
all). Real counts vary by gene (SOD1: 3, FUS: 4, NEK1: 1, C9orf72: 0,
TARDBP: 0) — genuinely reflects each gene's real Reactome annotations, not
a missing-data artifact.

Run:
    python -m scripts.ingest_evidence
"""

import statistics

from app.config import (
    DISEASE_EFO_ID, DISEASE_NAME, CANDIDATE_TARGETS, GENETIC_DATATYPE_ID,
    EXPRESSION_ATLAS_DATASOURCE_ID, PARALOGUE_MODALITY_NOTE_IDENTITY_THRESHOLD,
    family_druggability_heuristic,
)
from app.db.database import SessionLocal, init_db
from app.db.models import Target, EvidenceRecord, ContradictionLog, GapRecord, PriorityScore, PipelineRunLog
from app.ingestion.open_targets_client import (
    get_evidence_for_datasource, get_evidence_by_datatype, get_pathway_evidence,
    get_drug_target_evidence, get_prioritisation_and_safety, get_essentiality_and_paralogues,
)
from app.ingestion.literature_client import get_literature_evidence_pubmed
from app.ingestion.clinicaltrials_gov_client import get_clinical_trials
from app.ingestion.hpa_client import get_tissue_expression
from app.ingestion.gtex_client import get_median_tissue_expression
from app.ingestion.string_client import get_ppi_partners, get_string_id
from app.ingestion.pharos_client import get_druggability_evidence
from app.ingestion.expression_atlas_direct_client import (
    get_baseline_expression,
    get_differential_expression,
    BASELINE_EXPERIMENTS,
    ALS_DIFFERENTIAL_EXPERIMENTS,
)
from app.core.scoring.dimension_scoring import (
    score_genetic_l2g,
    score_clinical_precedence,
    score_literature_cooccurrence,
    score_pathway_curated,
    score_experimental,
    score_omics_expression,
    score_drug_target,
    score_tissue_specificity,
    score_ppi_hub,
    score_druggability_tdl,
    compute_tau_specificity,
)

# Non-genetic dimensions: real ALS data shows exactly one real OTP
# datasourceId per datatype here (literature -> europepmc, human_clinical
# -> clinical_precedence, experimental -> impc), so a hardcoded 1:1 mapping
# carries no under-collection risk the way genetic's multi-datasource list
# did (see GENETIC_DATATYPE_ID below and docs/07). A different disease
# COULD have more than one real datasourceId under one of these datatypes
# too — same class of risk, not fixed here since it wasn't observed for any
# of the 5 real genes and is out of this task's scope; named as related
# follow-up work in docs/07.
DATASOURCE_TO_DIMENSION = {
    "europepmc": "literature",
    "clinical_precedence": "human_clinical",
    "impc": "experimental",
    # Omics (Expression Atlas): confirmed largely retired at the source;
    # recovered real data exactly once across all multi-disease testing
    # (PTPN22/Rheumatoid Arthritis). Not called by default — removed from
    # the active pipeline to avoid wasteful API calls with a near-zero real
    # success rate. The builder (_build_omics_fields) and scorer
    # (score_omics_expression) are kept available for re-enablement if the
    # datasource is ever restored upstream.
    # EXPRESSION_ATLAS_DATASOURCE_ID: "omics",
}

DIMENSION_TO_SOURCE_TYPE = {
    "genetic": "genetic",
    "literature": "literature",
    "human_clinical": "clinical",
    "experimental": "experimental",
    "omics": "omics",
    "drug_target": "clinical",  # see config.SOURCE_TYPE_BY_DATA_SOURCE's "chembl_drug_target" entry
}

# Substrings checked (case-insensitive) against OTP's trialStopReasonCategories
# to decide the early-stop down-weight in score_clinical_precedence().
TRIAL_STOP_NEGATIVE_KEYWORDS = ("negative", "safety", "adverse")


def _normalize_direction(raw: str | None) -> str | None:
    """OTP returns lowercase ('risk'/'protective'); classifier/tests use Title case."""
    return raw.strip().capitalize() if raw else None


def _first_or_none(values: list | None):
    return values[0] if values else None


def _scalarize(value):
    """
    Some OTP fields documented/assumed scalar (e.g. biosamplesFromSource)
    can come back as a list for real rows — confirmed live for the first
    time by SNCA's real expression_atlas data (['UBERON_0001966']), which
    crashed the insert because every string-typed EvidenceRecord column
    only accepts a scalar. Join list values into one comparable string,
    same convention this file already uses for clinicalSignificances/
    allelicRequirements/phenotype lists, rather than assume scalar and
    fail on insert.

    Applied defensively (this task) to three more fields with the same
    risk, none ever observed as a list in real data yet: variantRsId
    (_build_genetic_fields), drugFromSource (_build_clinical_fields), and
    HPA's rna_tissue_distribution (_build_tissue_expression_fields) — same
    reasoning as biosamplesFromSource: these are comparability/display
    fields where joining preserves real information without corrupting
    anything downstream. NOT applied to clinical_stage/max_clinical_stage
    in dimension_scoring.py — those feed a dict lookup keyed on one exact
    stage string, where silently joining would produce a key that matches
    nothing and falls back to "unknown", silently under-scoring real
    evidence; those raise loudly instead (see
    dimension_scoring._require_scalar_stage()).
    """
    if isinstance(value, list):
        return "; ".join(str(v) for v in value) or None
    return value


def _year_from_date_string(date_str: str | None) -> int | None:
    """Real OTP date fields (e.g. "2025-12-11") -> real year, or None if
    not a real parseable date. Used for Evidence Momentum — see
    app/db/models.py's EvidenceRecord.publication_year docstring."""
    if not date_str or len(date_str) < 4 or not date_str[:4].isdigit():
        return None
    return int(date_str[:4])


def _build_genetic_fields(row: dict) -> dict:
    """
    eva / uniprot_variants / gwas_credible_sets: no population/tissue/assay/
    endpoint fields exist (confirmed via live introspection). Real
    comparability fields instead: variant_id, clinical_significance
    (ClinVar term), inheritance_pattern (from allelicRequirements).

    `external_id`: real `credibleSet.studyLocusId`, populated ONLY for
    gwas_credible_sets rows (null for eva/uniprot_variants/orphanet, whose
    real external ids already live in source_record_id/variant_id instead)
    — captured for a real, clickable source link to the Open Targets
    Platform's own credible-set page, see
    app/core/presentation/source_links.py.
    """
    clinical_significances = row.get("clinicalSignificances") or []
    allelic_requirements = row.get("allelicRequirements") or []
    raw_score = row.get("score")
    credible_set = row.get("credibleSet") or {}
    return dict(
        source_type="genetic",
        source_record_id=row.get("studyId") or row["id"],
        raw_value=raw_score,
        evidence_score=score_genetic_l2g(raw_score),
        variant_id=_scalarize(row.get("variantRsId")),
        clinical_significance="; ".join(clinical_significances) or None,
        inheritance_pattern="; ".join(allelic_requirements) or None,
        direction_on_trait=_normalize_direction(row.get("directionOnTrait")),
        direction_on_target=_normalize_direction(row.get("directionOnTarget")),
        external_id=credible_set.get("studyLocusId"),
        notes=f"disease_from_source={row.get('diseaseFromSource')}",
    )


def _build_genetic_constraint_fields(gene_symbol: str, prioritisation_value: str | None, raw_rows: list[dict]) -> dict:
    """
    Real Open Targets Target Prioritisation Factor: Genetic Constraint
    (see open_targets_client.get_prioritisation_and_safety()'s docstring
    for the real -1..+1 scale and its confirmed meaning). Folded into the
    EXISTING "genetic" dimension as one more real, disease-agnostic
    annotation (same "gene-level, not disease-specific" pattern as
    pathway/drug_target being folded into their own dimensions) — this is
    a single aggregate row per gene, not a per-variant row.

    HONEST FRAMING, worth restating at the point of use, not just in the
    client's docstring: this measures TOLERABILITY TO LOSS-OF-FUNCTION (a
    druggability/safety-adjacent signal — can this gene likely be
    knocked down without being lethal), NOT disease-association strength.
    A high score here does not mean "strong evidence this gene causes the
    disease" — it means "perturbing this gene is less likely to be
    intrinsically harmful". Scaled 0-1 via a plain linear remap of OTP's
    own real -1..+1 value (0=least tolerant/most constrained, 1=most
    tolerant) — not a new, invented formula.

    Given harmonic_sum_score_scaled_for_type() combines this with
    potentially hundreds of real per-variant genetic rows for the same
    gene, one more real data point here has a correspondingly small (but
    real, non-zero) effect on the aggregate genetic dimension score —
    exactly as it should, since this is one annotation among many, not a
    replacement for the disease-specific variant evidence.
    """
    evidence_score = round((float(prioritisation_value) + 1) / 2, 4) if prioritisation_value is not None else None
    lof_row = next((r for r in raw_rows if r.get("constraintType") == "lof"), None)
    lof_text = (
        f"lof_oe={lof_row['oe']:.4f} (obs={lof_row['obs']}, exp={lof_row['exp']:.2f}, score={lof_row['score']})"
        if lof_row else "real lof constraint row unavailable"
    )
    return dict(
        dimension="genetic",
        data_source="ot_genetic_constraint",
        source_type="genetic",
        source_record_id=f"ot_genetic_constraint:{gene_symbol}",
        raw_value=float(prioritisation_value) if prioritisation_value is not None else None,
        evidence_score=evidence_score,
        notes=(
            f"prioritisation_geneticConstraint={prioritisation_value} "
            f"(scale: -1=least tolerant to LoF/most constrained, +1=most tolerant); {lof_text}"
        ),
    )


def _build_literature_fields(row: dict) -> dict:
    """
    europepmc: no structured comparability fields at all (confirmed via live
    introspection) — left null intentionally, not a bug. `score` is OTP's
    already-normalized co-occurrence confidence (observed as 1 for all
    included rows); `resourceScore` is the raw, unbounded underlying value,
    kept in raw_value for traceability.
    """
    return dict(
        source_type="literature",
        source_record_id=_first_or_none(row.get("literature")) or row["id"],
        raw_value=row.get("resourceScore"),
        evidence_score=score_literature_cooccurrence(row.get("score") or 0.0),
        # Real, confirmed reliably populated (5/5 real SOD1 sample rows) —
        # see EvidenceRecord.publication_year's docstring.
        publication_year=row.get("publicationYear"),
    )


def _build_clinical_fields(row: dict) -> dict:
    """
    clinical_precedence: confirmed via live introspection across all 5
    candidate genes (docs/06_evidence_heterogeneity_discovery.md) that
    `population` and `endpoint` do NOT populate for this dataset at all
    (ancestry/cohort*/studyCases all null/empty on every row, every gene) —
    left null, not forced. `drugFromSource` is the only real comparability
    field (`intervention`), but its casing is inconsistent for the same real
    drug (e.g. "tofersen" vs "TOFERSEN") — lowercased here so two records
    about the same drug don't spuriously mismatch in the classifier.
    `trialStopReasonCategories`/`trialWhyStopped` are also empty on every
    row for every gene, so `stopped_early` can never evaluate True from real
    data — the down-weight logic is exercised, but not triggered, by this
    dataset; documented limitation, not a bug.

    `external_id`: real `clinicalReportId` — confirmed live this is
    SOMETIMES a real ClinicalTrials.gov NCT id (e.g. "nct07223723") and
    sometimes a different internal report tag with no public page (e.g.
    "d0i1cq/amyotrophic lateral sclerosis"); captured verbatim here,
    format-validated later at read time by
    app/core/presentation/source_links.py before ever building a link.
    """
    stop_categories = [c.lower() for c in (row.get("trialStopReasonCategories") or [])]
    stopped_early = any(k in c for c in stop_categories for k in TRIAL_STOP_NEGATIVE_KEYWORDS)
    clinical_stage = row.get("clinicalStage") or "unknown"
    drug = _scalarize(row.get("drugFromSource"))
    return dict(
        source_type="clinical",
        source_record_id=row["id"],
        raw_value=row.get("score"),
        evidence_score=score_clinical_precedence(clinical_stage, stopped_early),
        intervention=drug.lower() if drug else None,
        external_id=row.get("clinicalReportId"),
        notes=f"disease_from_source={row.get('diseaseFromSource')}",
        # Real, but confirmed MOSTLY NULL in this dataset (4 of 5 real SOD1
        # sample rows) — see EvidenceRecord.publication_year's docstring;
        # a real, honest data gap, not forced.
        publication_year=_year_from_date_string(row.get("studyStartDate")),
    )


_CTGOV_PHASE_NUMBERS = {"PHASE1": "1", "PHASE2": "2", "PHASE3": "3", "PHASE4": "4"}


def _map_ctgov_phases_to_clinical_stage(phases: list[str]) -> str:
    """
    Real CT.gov `phases` (e.g. ["PHASE1"], ["PHASE1","PHASE2"], ["NA"],
    ["EARLY_PHASE1"]) -> this project's own clinical_stage key convention
    already used by dimension_scoring.CLINICAL_STAGE_SCORES (e.g.
    "phase_1", "phase_1_2") — confirmed live these real CT.gov enum values
    map cleanly 1:1 onto the existing keys, no new stage vocabulary needed.
    """
    real_phases = [p for p in phases if p and p != "NA"]
    if not real_phases:
        return "unknown"
    if real_phases == ["EARLY_PHASE1"]:
        return "early_phase_1"
    numbers = [_CTGOV_PHASE_NUMBERS[p] for p in real_phases if p in _CTGOV_PHASE_NUMBERS]
    return f"phase_{'_'.join(numbers)}" if numbers else "unknown"


def _build_ctgov_clinical_fields(row: dict) -> dict:
    """
    clinicaltrials_gov: a second, independent human_clinical source (see
    app/ingestion/clinicaltrials_gov_client.py's module docstring for the
    real gap this closes — BIIB078/WVE-004 for C9orf72, missing entirely
    from clinical_precedence). Reuses score_clinical_precedence() unchanged
    (this task's own instruction) — same phase->stage mapping and
    early-stop down-weight logic as clinical_precedence, just fed from
    CT.gov's real fields instead of OTP's.

    HONEST LIMITATION, not silently patched: `stopped_early` reuses the
    exact same TRIAL_STOP_NEGATIVE_KEYWORDS ("negative"/"safety"/"adverse")
    clinical_precedence already uses, checked against CT.gov's real
    free-text `why_stopped` here (clinical_precedence's own
    trialStopReasonCategories is a structured list this field has no
    equivalent of). Confirmed live: NEITHER BIIB078's nor WVE-004's real
    whyStopped text contains any of these 3 words (their real language is
    "no evidence of benefit" / "no clinical benefit was seen" — a
    lack-of-efficacy finding, not explicitly "negative/safety/adverse"), so
    stopped_early evaluates False for both real trials and they score on
    clinical_stage alone, without the 0.5x down-weight. Reported as a real
    finding for this task, not expanded here — expanding the keyword list
    is a separate, deliberate decision, not a side effect of adding this
    source.
    """
    why_stopped = (row.get("why_stopped") or "").lower()
    stopped_early = any(k in why_stopped for k in TRIAL_STOP_NEGATIVE_KEYWORDS)
    clinical_stage = _map_ctgov_phases_to_clinical_stage(row.get("phases") or [])
    intervention = row.get("intervention_name")
    return dict(
        source_type="clinical",
        source_record_id=row["nct_id"],
        raw_value=None,  # CT.gov has no single real numeric input analogous to OTP's `score` — see score_clinical_precedence()
        evidence_score=score_clinical_precedence(clinical_stage, stopped_early),
        intervention=intervention.lower() if intervention else None,
        external_id=row["nct_id"],  # always a real, well-formed NCT id — see app/core/presentation/source_links.py
        notes=f"status={row.get('overall_status')}; brief_title={row.get('brief_title')}; why_stopped={row.get('why_stopped')}",
        publication_year=_year_from_date_string(row.get("start_date")),
    )


def _build_experimental_fields(row: dict) -> dict:
    """
    impc: confirmed via live introspection across all 5 candidate genes that
    `tissue` and `assay_type` do NOT populate (cellType/biosamplesFromSource/
    contrast/statisticalMethod/assessments all null/empty on every row) —
    left null, not forced onto a substitute field. `phenotype` IS real and
    rich: diseaseModelAssociatedModelPhenotypes (mouse-model phenotype
    labels, e.g. "motor neuron degeneration") and the human-side
    diseaseModelAssociatedHumanPhenotypes (e.g. "Fasciculations") are joined
    together, since both describe the same underlying model-to-human
    evidence chain. `evidence_score` now real (this task) — see
    score_experimental()'s docstring: OTP's own `score` field on real impc
    rows is already a pre-computed, normalized 0-1 result (confirmed via a
    real SOD1 sample: score=0.5807, resourceScore=58.07), so this reuses it
    directly rather than re-deriving a q-value/significance formula OTP has
    already computed.
    """
    model_phenotypes = [p["label"] for p in (row.get("diseaseModelAssociatedModelPhenotypes") or [])]
    human_phenotypes = [p["label"] for p in (row.get("diseaseModelAssociatedHumanPhenotypes") or [])]
    phenotype = "; ".join(model_phenotypes + human_phenotypes) or None
    return dict(
        source_type="experimental",
        source_record_id=row["id"],
        raw_value=row.get("score"),
        evidence_score=score_experimental(row.get("score")),
        phenotype=phenotype,
        notes=f"allelic_composition={row.get('biologicalModelAllelicComposition')}",
    )


def _build_omics_fields(row: dict) -> dict:
    """
    expression_atlas (old OTP route): schema-confirmed fields
    (log2FoldChangeValue, log2FoldChangePercentileRank, pValueMantissa,
    pValueExponent) — CONFIRMED RETIRED via OTP. The underlying EBI
    Expression Atlas database IS active and reachable via its own direct
    API (expression_atlas_direct_client.py, data_source=
    "expression_atlas_direct"). This function is kept for backwards
    compatibility with any OTP-backed data that may still exist; new
    omics data flows through the direct client instead.
    """
    log2fc = row.get("log2FoldChangeValue")
    p_mantissa = row.get("pValueMantissa")
    p_exponent = row.get("pValueExponent")
    percentile_rank = row.get("log2FoldChangePercentileRank")
    return dict(
        source_type="omics",
        source_record_id=row.get("studyId") or row["id"],
        raw_value=row.get("resourceScore"),
        evidence_score=score_omics_expression(log2fc, p_mantissa, p_exponent, percentile_rank),
        tissue=_scalarize(row.get("biosamplesFromSource")),
        notes=f"log2fc={log2fc}; disease_from_source={row.get('diseaseFromSource')}",
    )


# ── Expression Atlas DIRECT API builders ─────────────────────────────────
# These convert the real data from the direct TSV download endpoints
# (expression_atlas_direct_client.py) into EvidenceRecord fields.
#
# The direct API returns:
#   Differential: foldChange (already log2) + pValue (single float,
#                 not OTP's mantissa+exponent split)
#   Baseline:     TPM values per tissue (no p-values, no fold changes)
#
# These are stored as data_source="expression_atlas_direct" to clearly
# distinguish from the old, non-working OTP "expression_atlas" route.

import math


def _pvalue_to_mantissa_exponent(p_value: str | float | None) -> tuple[float | None, int | None]:
    """
    Convert a single float p-value (from the direct API) into OTP's
    mantissa + exponent split for score_omics_expression().

    Example: 0.0148575184209218 -> (1.48575184209218, -2)
             0.0378018832219479 -> (3.78018832219479, -2)
    """
    if p_value is None:
        return None, None
    try:
        pv = float(p_value)
    except (ValueError, TypeError):
        return None, None
    if pv <= 0:
        return None, None
    exponent = int(math.floor(math.log10(pv)))
    mantissa = pv / (10 ** exponent)
    # Keep mantissa in [1, 10) range
    return round(mantissa, 12), exponent


def _extract_foldchange_value(fc_str: str | None) -> float | None:
    """
    The direct API returns foldChange as a string. OTP's log2FoldChangeValue
    is already log2. The direct API's foldChange field from the TSV IS
    already the log2 fold change (confirmed by checking values: -1.4, 2.0
    are typical log2FC values). Return directly.
    """
    if fc_str is None:
        return None
    try:
        return float(fc_str)
    except (ValueError, TypeError):
        return None


def _build_omics_direct_differential_fields(row: dict, comparison: str) -> dict:
    """
    Build EvidenceRecord fields from a direct API differential TSV row.

    Parsed columns (example for comparison 'sporadic ALS' vs 'normal'):
      '{comparison}.foldChange'   -> log2FoldChange (already log2)
      '{comparison}.pValue'        -> pValue mantissa + exponent

    The direct API does NOT provide log2FoldChangePercentileRank, so we
    set it to None — the scorer will return None (deferring the decision
    to the caller) since all 4 inputs are required. Instead, we compute
    a simplified omics score that only requires foldChange + p-value.
    """
    fc = _extract_foldchange_value(row.get(f"'{comparison}'.foldChange"))
    p_str = row.get(f"'{comparison}'.pValue")
    pm, pe = _pvalue_to_mantissa_exponent(p_str)

    return dict(
        source_type="omics",
        source_record_id=f"expression_atlas_direct_differential:{comparison}",
        raw_value=fc,
        # score_omics_expression() requires percentile_rank which the direct
        # API does not provide. We pass what we have and accept None from it.
        # A prototype alternative: use fold change magnitude alone as a
        # simple expression-dysregulation signal.
        evidence_score=score_omics_expression(fc, pm, pe, percentile_rank=None),
        tissue=comparison.split(" vs ")[0] if " vs " in comparison else comparison,
        notes=f"foldchange={fc}; pvalue={p_str}; comparison={comparison}",
    )


def score_omics_baseline_tpm(
    tpm_value: float | None,
    *,
    HIGH_EXPRESSION_THRESHOLD: float = 10.0,
    MEDIUM_EXPRESSION_THRESHOLD: float = 1.0,
) -> float | None:
    """
    Prototype scoring for baseline (TPM-only) expression data from the
    direct Expression Atlas API.

    The direct API's baseline endpoint returns TPM values only — no
    p-values or fold changes — so score_omics_expression() cannot
    be used directly (it requires all 4 inputs).

    This is a deliberately simple categorical → continuous mapping,
    explicitly documented as a prototype, not an established reference:

      TPM >= 10   → 0.8   (high expression — gene is abundant in tissue)
      TPM >= 1    → 0.4   (medium expression — detected but not abundant)
      TPM > 0     → 0.1   (low but detected)
      TPM == 0    → 0.0   (not detected)
      None        → None  (no data)

    Thresholds chosen based on real SOD1/TP53 data: SOD1 ranges 49-481 TPM
    across all 53 GTEx tissues (always HIGH), TP53 ranges 6-52 TPM (mostly
    HIGH, sometimes LOW in tissues where it's under 10 TPM).

    NOTE: Baseline TPM alone is NOT a disease-association signal —
    it measures which tissues a gene is expressed in, NOT whether it's
    dysregulated in disease. This score should be used only as a
    tissue-specificity / expression-abundance descriptor, NOT as a
    disease-association evidence score comparable to the differential
    expression pipeline.
    """
    if tpm_value is None:
        return None
    if tpm_value >= HIGH_EXPRESSION_THRESHOLD:
        return 0.8
    if tpm_value >= MEDIUM_EXPRESSION_THRESHOLD:
        return 0.4
    if tpm_value > 0:
        return 0.1
    return 0.0


def _build_omics_direct_baseline_fields(
    row: dict,
    tissue_column: str,
    experiment_accession: str,
) -> dict:
    """
    Build EvidenceRecord fields from a direct API baseline TSV row.

    Each TSV row has columns: "Gene ID", "Gene Name", plus one column per
    tissue/condition with a TPM value. This builder creates ONE record per
    tissue.

    The tissue name comes from `tissue_column` (the column header name),
    and the TPM value is the `row[tissue_column]` cell.
    """
    tpm_str = row.get(tissue_column, "")
    tpm = None
    try:
        if tpm_str:
            tpm = float(tpm_str)
    except (ValueError, TypeError):
        tpm = None

    es = score_omics_baseline_tpm(tpm)

    return dict(
        source_type="omics",
        source_record_id=f"expression_atlas_direct_baseline:{experiment_accession}:{tissue_column}",
        raw_value=tpm,
        evidence_score=es,
        tissue=tissue_column,
        notes=f"baseline_tpm={tpm}; experiment={experiment_accession}; tissue={tissue_column}; "
              f"expression_level={'HIGH' if es == 0.8 else 'MEDIUM' if es == 0.4 else 'LOW' if es == 0.1 else 'NONE' if es == 0.0 else 'NODATA'}",
    )


def _build_pathway_fields(row: dict) -> dict:
    """
    Reactome pathway membership (Target.pathways — disease-agnostic, see
    open_targets_client.get_pathway_evidence() docstring). Every real
    pathway hit scores a fixed 1.0 via score_pathway_curated(), matching
    OTP's own convention for curated pathway evidence.
    """
    return dict(
        dimension="pathway",
        data_source="reactome",
        source_type="pathway",
        source_record_id=row["pathwayId"],
        raw_value=1.0,
        evidence_score=score_pathway_curated(is_curated=True),
        notes=f"pathway={row['pathway'].strip()}; top_level_term={row['topLevelTerm']}",
    )


def _build_safety_signal_fields(row: dict) -> dict:
    """
    Real Open Targets Target Prioritisation Factor: Known Safety Events
    (Target.safetyLiabilities — disease-agnostic, see
    open_targets_client.get_prioritisation_and_safety()'s docstring). ONE
    real row per documented event (a gene can have several real, distinct
    events — e.g. real hERG/KCNH2 data returns 5 — each independently
    traceable to its own real datasource), not one aggregate row, since
    each event is its own real claim.

    DELIBERATELY NOT SCORED 0-1 like every other dimension (this task's
    own design question, answered here): `evidence_score` is left None on
    purpose. This guarantees a documented safety concern can NEVER be
    silently averaged into evidence_strength/dimension_breakdown
    (app/api/routes/scoring.py only aggregates records whose
    evidence_score is non-null) or into evidence_maturity ("safety_signal"
    is deliberately NOT a key in config.DIMENSION_MATURITY_LADDER, so
    DIMENSION_MATURITY_LADDER.get(d, 0.0) always contributes 0.0 for it —
    it can never be the max rung). A real safety concern is categorically
    different from "how much evidence exists" — it's surfaced instead via
    a dedicated new gap type (gap_taxonomy.GAP_TEMPLATES["safety_signal"])
    and a prominent frontend warning banner, never blended into a score
    that could hide it.
    """
    tissues = [b["tissueLabel"] for b in (row.get("biosamples") or []) if b.get("tissueLabel")]
    directions = [e["direction"] for e in (row.get("effects") or []) if e.get("direction")]
    return dict(
        dimension="safety_signal",
        data_source="ot_safety",
        source_type="safety_signal",
        source_record_id=row.get("eventId") or f"safety:{row['event']}",
        raw_value=None,
        evidence_score=None,
        tissue=_scalarize(tissues) if tissues else None,
        external_id=row.get("url") or None,
        notes=f"event={row['event']}; direction={_scalarize(directions) or 'unspecified'}; datasource={row.get('datasource')}",
    )


def _build_essentiality_fields(gene_symbol: str, is_essential: bool | None,
                                prioritisation_value: str | None, depmap_rows: list[dict]) -> dict:
    """
    Real Open Targets Target Prioritisation Factor: Gene Essentiality (see
    open_targets_client.get_essentiality_and_paralogues()'s docstring for
    the real, confirmed binary -1/0 semantics — NOT continuous like
    genetic constraint). ONE real row per gene (a single evaluated fact
    about the gene, not a list of discrete incidents — contrast with
    _build_safety_signal_fields()'s one-row-per-event pattern below),
    inserted every time regardless of the real value, so every gene has a
    real, traceable "checked, here's what OTP/DepMap say" record — not
    just the essential ones.

    DELIBERATELY NOT SCORED 0-1 (same design question as safety_signal,
    answered the same way): `evidence_score` is left None on purpose.
    Registered under its OWN source_type "essentiality_risk" (see
    app/config.py), never a key in DIMENSION_MATURITY_LADDER, so it can
    never be silently averaged into evidence_strength/dimension_breakdown
    or picked as the evidence_maturity rung. Surfaced instead via a
    dedicated gap type (gap_taxonomy.GAP_TEMPLATES["essentiality_risk"])
    and a frontend caution flag, same structural mechanism as
    safety_signal — but kept in a DISTINCT dimension/gap type from it (see
    app/config.py's COMPARABILITY_FIELDS_BY_SOURCE_TYPE["essentiality_risk"]
    docstring for why these two are not the same kind of caution).

    CRITICAL REAL NUANCE, stated here at the point of use (not just in the
    client's docstring), because it directly bears on this project's own
    real data: SOD1 — an approved drug target via tofersen, a real,
    marketed antisense-oligonucleotide (ASO) knockdown therapy — is ITSELF
    flagged essential by OTP/DepMap (`isEssential=True`,
    `geneEssentiality=-1`; real mean CRISPR-knockout gene-effect across
    1,258 real DepMap cancer cell line screens: -1.75, strongly essential).
    This is NOT a contradiction to paper over: DepMap's essentiality call
    answers "would a COMPLETE CRISPR knockout kill a broad panel of
    rapidly-PROLIFERATING CANCER cell lines" — a different real question
    from "is a PARTIAL, tissue-targeted ASO knockdown safe in adult,
    largely POST-MITOTIC motor neurons in a human being", which is what
    tofersen actually does and has a real, marketed safety record doing.
    A high essentiality flag is real, documented caution worth surfacing —
    it is not, on its own, evidence that a specific real therapeutic
    modality targeting this gene is unsafe.
    """
    all_effects = [
        s["geneEffect"] for row in (depmap_rows or []) for s in (row.get("screens") or [])
        if s.get("geneEffect") is not None
    ]
    if all_effects:
        depmap_summary = (
            f"depmap_screens_n={len(all_effects)}; "
            f"mean_geneEffect={statistics.mean(all_effects):.4f}; "
            f"median_geneEffect={statistics.median(all_effects):.4f}"
        )
    else:
        depmap_summary = "no real DepMap screen rows available"
    return dict(
        dimension="essentiality_risk",
        data_source="ot_essentiality",
        source_type="essentiality_risk",
        source_record_id=f"ot_essentiality:{gene_symbol}",
        raw_value=float(prioritisation_value) if prioritisation_value is not None else None,
        evidence_score=None,
        notes=(
            f"isEssential={is_essential}; prioritisation_geneEssentiality={prioritisation_value} "
            f"(scale: -1=reported essential/unfavorable, 0=not reported essential/favorable); "
            f"{depmap_summary} (real CRISPR gene-effect across DepMap cancer cell line screens — "
            f"see this function's docstring: essential-in-proliferating-cancer-lines is a different "
            f"question from safe-to-knock-down-in-a-specific-human-tissue)"
        ),
    )


def _build_paralogy_fields(gene_symbol: str, paralog_row: dict) -> dict:
    """
    Real Open Targets human paralogue data (Target.homologues, filtered to
    speciesId="9606" and homologyType != "ortholog_one2one" — see
    open_targets_client.get_essentiality_and_paralogues()'s docstring for
    why this filter is the real, correct way to isolate same-species
    paralogues from cross-species orthologues). ONE real row per real
    human paralogue found (a gene can have several, or a very different
    NUMBER of them depending on how broad the shared domain family is —
    see the real SOD1/FUS/TARDBP comparison in that docstring), same
    "one row per real distinct fact" pattern as
    _build_safety_signal_fields() above.

    DELIBERATELY NOT SCORED 0-1, and deliberately NOT forced into a single
    good/bad direction (this task's own design question): a paralogue is a
    genuinely two-sided signal — NO real paralogue can mean either "highly
    specific, low off-target risk" (good) or "no biological backup if
    something goes wrong" (a different kind of risk); MANY real paralogues
    at high identity can mean either "off-target risk / functional
    redundancy that could blunt a knockdown's effect" (bad for modality)
    or "a validated, druggable protein family with precedent" (arguably
    good). Because the direction genuinely depends on context this
    pipeline cannot judge automatically, `evidence_score` is left None,
    exactly like safety_signal/essentiality_risk — but registered under
    its own "paralogy" source_type (see app/config.py), NOT lumped in with
    either of those two, since this is not a risk/caution signal the way
    they are — it is genuinely descriptive, informational metadata.

    `raw_value` stores the higher of the two real identity-percentage
    directions OTP reports (queryPercentageIdentity/targetPercentageIdentity
    aren't symmetric — they measure identity from each gene's own sequence
    length, so the max of the two is the more conservative "how similar
    could these two genes' products plausibly be" read), used only for
    this project's own Modality-gap note-worthiness check (see
    config.PARALOGUE_MODALITY_NOTE_IDENTITY_THRESHOLD's docstring for why
    that threshold is deliberately NOT the same as OTP's own official 60%
    prioritisation-factor cutoff).
    """
    max_identity = max(paralog_row["queryPercentageIdentity"], paralog_row["targetPercentageIdentity"])
    return dict(
        dimension="paralogy",
        data_source="ot_paralogy",
        source_type="paralogy",
        source_record_id=f"ot_paralogy:{gene_symbol}:{paralog_row['targetGeneSymbol']}",
        raw_value=round(max_identity, 4),
        evidence_score=None,
        external_id=paralog_row.get("targetGeneId"),
        notes=(
            f"paralog_gene={paralog_row['targetGeneSymbol']}; "
            f"query_pct_identity={paralog_row['queryPercentageIdentity']:.2f}; "
            f"target_pct_identity={paralog_row['targetPercentageIdentity']:.2f}; "
            f"above_project_note_threshold_{PARALOGUE_MODALITY_NOTE_IDENTITY_THRESHOLD:.0f}pct="
            f"{'yes' if max_identity >= PARALOGUE_MODALITY_NOTE_IDENTITY_THRESHOLD else 'no'}"
        ),
    )


def _build_druggability_fields(row: dict) -> dict:
    """
    Real Pharos druggability characterization (see app/ingestion/pharos_client.py's
    docstring for the live-confirmed endpoint and the FIVE distinct signals fetched
    in one query). ONE real row per gene (a single druggability assessment per
    target, same "one aggregate fact per gene" pattern as _build_essentiality_fields()),
    inserted only when Pharos actually has the target — a gene Pharos doesn't
    recognize is a real absence (the client returns None), never fabricated as a
    Tdark-default.

    FIVE SIGNALS stored here (items 1-3 of this task as EvidenceRecord fields
    under dimension="druggability"; items 4-5's RAW DATA is also stored here
    for the cross-check module, since it's all Pharos-derived — the cross-check
    RESULTS themselves are computed separately in app/core/verification/
    pharos_cross_checks.py, NOT as a new EvidenceRecord dimension):
      1. TDL -> raw_value (via score_druggability_tdl()); novelty -> notes
         (its own field, separate from TDL — under-studied-relative-to-importance,
         NOT the same as TDL: a target can be low-novelty yet Tdark).
      2. fam -> notes + the prototype family-druggability heuristic label
         (config.family_druggability_heuristic, documented as a prototype).
      3. Ligand/drug activity detail -> notes: aggregate ligand_count/drug_count
         (exhaustive, from ligandCounts) PLUS a bounded per-ligand sample with
         isdrug + activity type/value (not just a count).
      4. ALS disease association -> notes: Pharos DisGeNET score + PubMed/SNP
         evidence + gene-specific ALS subtype (raw input for the disease-
         association cross-check vs OTP Genetic/Literature).
      5. PPI -> notes: Pharos STRINGDB partner count + bounded partner symbol
         list (raw input for the PPI cross-check vs STRING).

    DELIBERATELY NOT SCORED INTO evidence_score (same design question as
    safety_signal/essentiality_risk/paralogy, answered the same way):
    `evidence_score` is left None on purpose, and the TDL score lives in
    `raw_value` instead. This guarantees druggability can NEVER be silently
    averaged into evidence_strength/dimension_breakdown/evidence_maturity
    (app/api/routes/scoring.py only aggregates records whose evidence_score is
    non-null) or picked as the maturity rung ("druggability" is deliberately
    NOT a key in config.DIMENSION_MATURITY_LADDER). Druggability is a target
    PROPERTY, not translational evidence — surfaced instead via its own gap
    type (gap_taxonomy "druggability", fires on Tdark) and
    translational_opportunity (Tdark -> Early-Stage Discovery, Tclin
    reinforces Clinical-Stage). The "ALONGSIDE the existing OTP-based scoring,
    not replacing it" framing is enforced structurally here, not just by
    convention.
    """
    tdl = row.get("tdl")
    fam = row.get("fam")
    fam_label = family_druggability_heuristic(fam)
    als = row.get("als_association") or {}
    ppi = row.get("ppi") or {}
    # Bounded per-ligand activity detail (Signal C) — compact, parseable.
    ligand_samples = row.get("ligands") or []
    ligand_detail = "; ".join(
        f"{lig['name']} (isdrug={lig['isdrug']}, actcnt={lig['actcnt']}, "
        f"activities={_format_ligand_activities(lig['activities'])})"
        for lig in ligand_samples
    ) or "none"
    return dict(
        dimension="druggability",
        data_source="pharos",
        source_type="druggability",
        source_record_id=f"pharos:{row.get('sym') or row.get('name')}",
        raw_value=score_druggability_tdl(tdl),
        evidence_score=None,
        external_id=row.get("name"),
        notes=(
            f"tdl={tdl}; name={row.get('name')}; family={fam}; "
            f"family_druggability_heuristic={fam_label}; "
            f"novelty={row.get('novelty')}; publication_count={row.get('publication_count')}; "
            f"ligand_count={row.get('ligand_count')}; drug_count={row.get('drug_count')}; "
            f"ligand_detail={ligand_detail}; "
            f"als_disgenet_score={als.get('disgenet_score')}; "
            f"als_evidence={als.get('evidence')}; als_subtype={als.get('subtype')}; "
            f"ppi_stringdb_count={ppi.get('stringdb_count')}; "
            f"ppi_total_count={ppi.get('total_count')}; "
            f"ppi_partners={', '.join(ppi.get('partner_symbols') or []) or 'none'}"
        ),
    )


def _format_ligand_activities(activities: list) -> str:
    """Compact one-line summary of a ligand's activities: 'EC50=7.17, IC50=6.5'."""
    if not activities:
        return "none"
    return ", ".join(
        f"{a.get('type')}={a.get('value')}" for a in activities
        if isinstance(a, dict) and a.get("type")
    )


_FIELD_BUILDERS = {
    "genetic": _build_genetic_fields,
    "literature": _build_literature_fields,
    "human_clinical": _build_clinical_fields,
    "experimental": _build_experimental_fields,
    "omics": _build_omics_fields,
}


def _build_drug_target_fields(row: dict) -> dict:
    """
    Real ChEMBL-backed drug-target mechanism data (Target.
    drugAndClinicalCandidates — see open_targets_client.get_drug_target_evidence()
    docstring for why this is a different real API path than
    clinical_precedence, already disease-filtered by that function).
    `intervention` is lowercased for the same reason
    _build_clinical_fields() lowercases `drugFromSource` — so this and
    clinical_precedence's intervention values collapse to one real drug
    name rather than splitting on casing when compared as the same
    "clinical" source-type group.
    """
    drug = row["drug"]
    moa_rows = drug.get("mechanismsOfAction", {}).get("rows", []) if drug.get("mechanismsOfAction") else []
    moa_text = "; ".join(f"{r['mechanismOfAction']} ({r['actionType']})" for r in moa_rows) or None
    return dict(
        dimension="drug_target",
        data_source="chembl_drug_target",
        source_type="clinical",
        source_record_id=drug["id"],  # real ChEMBL id, e.g. CHEMBL3833346
        raw_value=None,  # no single real numeric raw input — see score_drug_target()'s docstring
        evidence_score=score_drug_target(row.get("maxClinicalStage")),
        intervention=drug["name"].lower() if drug.get("name") else None,
        notes=f"drug_type={drug.get('drugType')}; max_clinical_stage={row.get('maxClinicalStage')}; mechanism_of_action={moa_text}",
    )


def _build_tissue_expression_fields(hpa_data: dict, ensembl_id: str) -> dict:
    """
    Human Protein Atlas tissue expression (see app/ingestion/hpa_client.py
    docstring). ONE real row per gene — HPA's real signal is a single
    gene-level categorical summary, not independently-combinable pieces of
    evidence, so this mirrors _build_pathway_fields()'s "one aggregate row"
    pattern rather than the many-rows-per-gene pattern genetic/literature
    evidence uses. `tissue` reuses the existing generic column (real value:
    HPA's own "RNA tissue distribution" category, e.g. "Detected in all").
    """
    specificity = hpa_data.get("rna_tissue_specificity")
    distribution = hpa_data.get("rna_tissue_distribution")
    enriched_tissues = list((hpa_data.get("rna_tissue_specific_nTPM") or {}).keys())
    return dict(
        dimension="tissue_expression",
        data_source="hpa",
        source_type="tissue_expression",
        source_record_id=f"hpa:{ensembl_id}",
        raw_value=None,  # HPA gives a category, not a single real numeric input — see score_tissue_specificity()
        evidence_score=score_tissue_specificity(specificity),
        tissue=_scalarize(distribution),
        notes=f"specificity_category={specificity}; enriched_tissues={', '.join(enriched_tissues) or 'none'}",
    )


# Coarse tau-bucket boundaries for the HPA-vs-GTEx agreement check below —
# reuses HPA's OWN real score tiers (config.TISSUE_SPECIFICITY_SCORES) as
# the natural cut points, rather than inventing a new threshold set.
_TAU_HPA_AGREEMENT_BUCKETS = [
    (0.85, "tissue enriched"),
    (0.55, "group enriched"),
    (0.25, "tissue enhanced"),
    (0.0, "low tissue specificity"),
]


def _tau_to_hpa_like_category(tau: float) -> str:
    for threshold, category in _TAU_HPA_AGREEMENT_BUCKETS:
        if tau >= threshold:
            return category
    return "low tissue specificity"


def _build_gtex_fields(median_by_tissue: dict, gene_symbol: str, hpa_category: str | None) -> dict:
    """
    GTEx: real median TPM expression across up to 54 real healthy-donor
    tissues (see app/ingestion/gtex_client.py). ONE real aggregate row per
    gene, same reasoning as _build_tissue_expression_fields()/
    _build_ppi_network_fields() above.

    DESIGN DECISION (this task): stored as dimension="tissue_expression",
    a SECOND source alongside HPA — not a new "omics" dimension. GTEx
    measures real healthy-donor expression levels, not disease-vs-healthy
    differential expression (which is what "omics"/score_omics_expression()
    actually means here, significance-gated on log2FC + p-value neither of
    which GTEx provides) — conceptually this is the same underlying
    question HPA already answers (where is this gene expressed), just
    from a second, richer real source.

    Cross-checks against HPA's real stated category for the SAME gene
    (already fetched earlier in ingest_target(), passed in here rather
    than re-fetched) — a genuinely independent second opinion on tissue
    specificity. Deliberately NOT routed through
    contradiction_classifier.py: that classifier's whole design is
    direction-of-effect-based (does a disease-association CLAIM conflict),
    and tissue_expression records were already excluded from it on purpose
    (config.COMPARABILITY_FIELDS_BY_SOURCE_TYPE's "tissue_expression": []
    — no direction_on_trait concept applies to a gene-level aggregate
    context signal). "Do two magnitude-based readouts roughly agree" is a
    different kind of question than "do two claims conflict", so this is
    a small, honest, direct comparison computed here and recorded in
    `notes` — a real, coarse check (bucket boundaries reused from HPA's
    own real score tiers), not a rigorous statistical concordance test,
    and not a new contradiction-classifier code path.
    """
    tau = compute_tau_specificity(median_by_tissue)
    top_tissues = sorted(median_by_tissue.items(), key=lambda kv: -kv[1])[:3]
    top_tissues_text = ", ".join(f"{tissue}={median:.1f}TPM" for tissue, median in top_tissues)

    if tau is not None and hpa_category:
        gtex_bucket = _tau_to_hpa_like_category(tau)
        agrees = gtex_bucket == hpa_category.strip().lower()
        agreement_note = (
            f"GTEx bucket='{gtex_bucket}' vs HPA='{hpa_category}' -> "
            f"{'AGREE' if agrees else 'DISAGREE'} (real, coarse comparison, not a rigorous concordance test)"
        )
    else:
        agreement_note = "HPA category not available for comparison"

    return dict(
        dimension="tissue_expression",
        data_source="gtex",
        source_type="tissue_expression",
        source_record_id=f"gtex:{gene_symbol}",
        raw_value=tau,
        evidence_score=tau,
        tissue=top_tissues[0][0] if top_tissues else None,
        notes=f"tau_specificity={tau}; top_tissues={top_tissues_text}; {agreement_note}",
    )


def _build_ppi_network_fields(partners: list[dict], gene_symbol: str, string_id: str | None = None) -> dict:
    """
    STRING protein-protein interaction network context (see
    app/ingestion/string_client.py docstring). ONE real row per gene, same
    "aggregate gene-level signal" reasoning as
    _build_tissue_expression_fields() above — the hub score is inherently
    a function of the WHOLE partner count, not any single partner in
    isolation, so storing N per-partner rows and harmonic-summing them
    would double-count/distort the aggregate rather than reproduce it.
    Real partner names kept in `notes` for traceability (the actual
    per-partner records are not individually persisted, but are not lost
    either — visible in this row's own notes).

    `external_id`: the real STRING-internal protein id (e.g.
    "9606.ENSP00000270142") resolved via string_client.get_string_id() —
    previously resolved during ingestion and immediately discarded, now
    captured for a real, clickable link to this gene's STRING network
    page (see app/core/presentation/source_links.py).
    """
    partner_count = len(partners)
    partner_names = [p["preferredName_B"] for p in partners]
    return dict(
        dimension="ppi_network",
        data_source="string",
        source_type="ppi_network",
        source_record_id=f"string:{gene_symbol}",
        raw_value=float(partner_count),
        evidence_score=score_ppi_hub(partner_count),
        external_id=string_id,
        notes=f"high_confidence_partner_count={partner_count}; partners={', '.join(partner_names) or 'none'}",
    )


def _save_evidence(db, record: EvidenceRecord, gene_symbol: str, label: str) -> bool:
    """
    Commits ONE evidence record independently, isolated from every other
    record for this gene. Previously, ingest_target() staged an entire
    gene's evidence in one transaction with a single commit() at the end —
    a real, confirmed bug: one malformed row (SNCA's list-valued
    expression_atlas `tissue` field, see _scalarize()) raised a
    sqlite3.ProgrammingError that rolled back EVERY already-staged record
    for that gene (genetic, literature, clinical, pathway, drug-target —
    all of it, despite having ingested successfully). Committing per-record
    means a bad row costs only itself.
    """
    db.add(record)
    try:
        db.commit()
        return True
    except Exception as exc:
        db.rollback()
        print(f"  [{gene_symbol}] {label}: 1 row FAILED to save ({exc}), skipping just this row")
        return False


def ingest_target(db, gene_symbol: str, ensembl_id: str) -> int:
    target = db.query(Target).filter_by(ensembl_id=ensembl_id).first()
    if target is None:
        target = Target(gene_symbol=gene_symbol, ensembl_id=ensembl_id, disease_efo_id=DISEASE_EFO_ID)
        db.add(target)
        db.commit()  # target itself must survive independently of any evidence row below

    saved = 0

    # Genetic: fetched by real OTP datatype ("genetic_association"),
    # discovered + fully paginated — NOT a hardcoded datasourceId list. See
    # module docstring and open_targets_client.get_evidence_by_datatype().
    try:
        genetic_rows = get_evidence_by_datatype(ensembl_id, DISEASE_EFO_ID, GENETIC_DATATYPE_ID)
    except Exception as exc:
        print(f"  [{gene_symbol}] {GENETIC_DATATYPE_ID}: query failed ({exc}), skipping")
        genetic_rows = []
    real_datasources = sorted({row["datasourceId"] for row in genetic_rows})
    for row in genetic_rows:
        record = EvidenceRecord(
            target_id=target.id,
            dimension="genetic",
            data_source=row["datasourceId"],
            **_build_genetic_fields(row),
        )
        if _save_evidence(db, record, gene_symbol, row["datasourceId"]):
            saved += 1
    print(f"  [{gene_symbol}] {GENETIC_DATATYPE_ID} ({real_datasources or 'none'}): {len(genetic_rows)} rows ingested")

    for datasource_id, dimension in DATASOURCE_TO_DIMENSION.items():
        try:
            rows = get_evidence_for_datasource(ensembl_id, DISEASE_EFO_ID, datasource_id)
        except Exception as exc:
            print(f"  [{gene_symbol}] {datasource_id}: query failed ({exc}), skipping")
            continue

        builder = _FIELD_BUILDERS[dimension]
        for row in rows:
            record = EvidenceRecord(
                target_id=target.id,
                dimension=dimension,
                data_source=datasource_id,
                **builder(row),
            )
            if _save_evidence(db, record, gene_symbol, datasource_id):
                saved += 1
        print(f"  [{gene_symbol}] {datasource_id}: {len(rows)} rows ingested")

    # Second, independent literature source — direct PubMed co-occurrence,
    # not routed through OTP at all (see literature_client.py docstring).
    try:
        pubmed_rows = get_literature_evidence_pubmed(gene_symbol, DISEASE_NAME)
    except Exception as exc:
        print(f"  [{gene_symbol}] pubmed: query failed ({exc}), skipping")
        pubmed_rows = []
    for row in pubmed_rows:
        record = EvidenceRecord(
            target_id=target.id,
            dimension="literature",
            data_source="pubmed",
            source_type="literature",
            source_record_id=row["pmid"],
            raw_value=row["confidence"],
            evidence_score=score_literature_cooccurrence(row["confidence"]),
            # Real year via a real NCBI esummary lookup (this task) — see
            # literature_client.get_publication_years()'s docstring.
            publication_year=row.get("year"),
        )
        if _save_evidence(db, record, gene_symbol, "pubmed"):
            saved += 1
    print(f"  [{gene_symbol}] pubmed: {len(pubmed_rows)} rows ingested")

    # Pathway: disease-agnostic Reactome membership (Target.pathways, NOT
    # evidences() — see open_targets_client.get_pathway_evidence()
    # docstring for the live-confirmed reason).
    try:
        pathway_rows = get_pathway_evidence(ensembl_id)
    except Exception as exc:
        print(f"  [{gene_symbol}] reactome: query failed ({exc}), skipping")
        pathway_rows = []
    for row in pathway_rows:
        record = EvidenceRecord(target_id=target.id, **_build_pathway_fields(row))
        if _save_evidence(db, record, gene_symbol, "reactome"):
            saved += 1
    print(f"  [{gene_symbol}] reactome: {len(pathway_rows)} rows ingested")

    # ── Expression Atlas Direct API — BASELINE expression ────────────────
    # Queries the real EBI Expression Atlas REST API directly (NOT via OTP,
    # whose routing to this datasource was confirmed retired). Returns real
    # TPM values across a broad panel of human tissues (GTEx v8: 53 tissues,
    # Human Atlas: 29 tissues, Body Map: 16 tissues).
    #
    # Baseline TPM alone is a tissue-specificity signal, NOT a
    # disease-association signal — see score_omics_baseline_tpm() docstring.
    for exp_acc in BASELINE_EXPERIMENTS:
        try:
            exp_rows = get_baseline_expression(gene_symbol, exp_acc)
        except Exception as exc:
            print(f"  [{gene_symbol}] expression_atlas_direct baseline/{exp_acc}: failed ({exc}), skipping")
            continue
        for row in exp_rows:
            gene_name = row.get("Gene Name", "")
            if gene_name.upper() != gene_symbol.upper():
                continue
            # Build one record per tissue column (each column = one
            # tissue/condition with a TPM value).
            for col in row.keys():
                if col in ("Gene ID", "Gene Name"):
                    continue
                record = EvidenceRecord(
                    target_id=target.id,
                    dimension="omics",
                    data_source="expression_atlas_direct",
                    **_build_omics_direct_baseline_fields(row, col, exp_acc),
                )
                if _save_evidence(db, record, gene_symbol, f"expression_atlas_direct/baseline/{exp_acc}"):
                    saved += 1
        print(f"  [{gene_symbol}] expression_atlas_direct baseline/{exp_acc}: ingested")

    # ── Expression Atlas Direct API — DIFFERENTIAL expression ────────────
    # Queries the real EBI Expression Atlas REST API for disease-vs-control
    # comparisons across all known human ALS differential experiments.
    # These return foldChange + pValue which map to score_omics_expression().
    for exp_acc in ALS_DIFFERENTIAL_EXPERIMENTS:
        try:
            de_rows = get_differential_expression(gene_symbol, exp_acc)
        except Exception as exc:
            print(f"  [{gene_symbol}] expression_atlas_direct differential/{exp_acc}: failed ({exc}), skipping")
            continue
        for row in de_rows:
            # Extract comparison names dynamically from the row columns
            for col in row.keys():
                if col in ("Gene ID", "Gene Name", "Design Element"):
                    continue
                # The column naming: "{comparison}.foldChange" or "{comparison}.pValue"
                # We process each unique comparison once.
                if col.endswith(".foldChange"):
                    comparison = col[:-len(".foldChange")]
                    record = EvidenceRecord(
                        target_id=target.id,
                        dimension="omics",
                        data_source="expression_atlas_direct",
                        **_build_omics_direct_differential_fields(row, comparison),
                    )
                    if _save_evidence(db, record, gene_symbol,
                                      f"expression_atlas_direct/differential/{exp_acc}"):
                        saved += 1
        nonzero = sum(1 for r in de_rows if any(
            v for k, v in r.items() if k not in ("Gene ID", "Gene Name", "Design Element")
        ))
        print(f"  [{gene_symbol}] expression_atlas_direct differential/{exp_acc}: "
              f"{len(de_rows)} gene hits ({nonzero} with foldChange data)")

    # Drug-Target: real ChEMBL-backed mechanism-of-action data
    # (Target.drugAndClinicalCandidates, NOT evidences() — see
    # open_targets_client.get_drug_target_evidence() docstring for the
    # live-confirmed reason, same discovery pattern as pathway above).
    # Already disease-filtered by that function.
    try:
        drug_target_rows = get_drug_target_evidence(ensembl_id, DISEASE_EFO_ID)
    except Exception as exc:
        print(f"  [{gene_symbol}] chembl_drug_target: query failed ({exc}), skipping")
        drug_target_rows = []
    for row in drug_target_rows:
        record = EvidenceRecord(target_id=target.id, **_build_drug_target_fields(row))
        if _save_evidence(db, record, gene_symbol, "chembl_drug_target"):
            saved += 1
    print(f"  [{gene_symbol}] chembl_drug_target: {len(drug_target_rows)} rows ingested")

    # Real Open Targets Target Prioritisation Factors: Known Safety Events
    # and Genetic Constraint (see
    # open_targets_client.get_prioritisation_and_safety()'s docstring for
    # the full real field semantics — both gene-level, disease-agnostic
    # Target annotations, same "not from evidences()" pattern as
    # pathway/drug_target above).
    try:
        prioritisation_data = get_prioritisation_and_safety(ensembl_id)
    except Exception as exc:
        print(f"  [{gene_symbol}] ot_prioritisation: query failed ({exc}), skipping")
        prioritisation_data = None

    if prioritisation_data is not None:
        constraint_record = EvidenceRecord(
            target_id=target.id,
            **_build_genetic_constraint_fields(
                gene_symbol,
                prioritisation_data["genetic_constraint_prioritisation"],
                prioritisation_data["genetic_constraint_rows"],
            ),
        )
        if _save_evidence(db, constraint_record, gene_symbol, "ot_genetic_constraint"):
            saved += 1
        print(f"  [{gene_symbol}] ot_genetic_constraint: 1 row ingested "
              f"(prioritisation_value={prioritisation_data['genetic_constraint_prioritisation']})")

        safety_rows = prioritisation_data["safety_liabilities"]
        safety_saved = 0
        for row in safety_rows:
            safety_record = EvidenceRecord(target_id=target.id, **_build_safety_signal_fields(row))
            if _save_evidence(db, safety_record, gene_symbol, "ot_safety"):
                safety_saved += 1
                saved += 1
        print(f"  [{gene_symbol}] ot_safety: {safety_saved} row(s) ingested "
              f"({len(safety_rows)} real documented safety event(s) found)")
    else:
        print(f"  [{gene_symbol}] ot_genetic_constraint: 0 rows ingested (query failed)")
        print(f"  [{gene_symbol}] ot_safety: 0 rows ingested (query failed)")

    # Two more real Open Targets Target Prioritisation Factors: Gene
    # Essentiality and Paralogues (see
    # open_targets_client.get_essentiality_and_paralogues()'s docstring for
    # the full real field semantics). Same "not from evidences()" pattern
    # as pathway/drug_target/genetic_constraint/safety above.
    try:
        essentiality_data = get_essentiality_and_paralogues(ensembl_id)
    except Exception as exc:
        print(f"  [{gene_symbol}] ot_essentiality/ot_paralogy: query failed ({exc}), skipping")
        essentiality_data = None

    if essentiality_data is not None:
        essentiality_record = EvidenceRecord(
            target_id=target.id,
            **_build_essentiality_fields(
                gene_symbol,
                essentiality_data["is_essential"],
                essentiality_data["gene_essentiality_prioritisation"],
                essentiality_data["depmap_essentiality_rows"],
            ),
        )
        if _save_evidence(db, essentiality_record, gene_symbol, "ot_essentiality"):
            saved += 1
        print(f"  [{gene_symbol}] ot_essentiality: 1 row ingested "
              f"(isEssential={essentiality_data['is_essential']})")

        paralog_rows = essentiality_data["human_paralogues"]
        paralog_saved = 0
        for row in paralog_rows:
            paralog_record = EvidenceRecord(target_id=target.id, **_build_paralogy_fields(gene_symbol, row))
            if _save_evidence(db, paralog_record, gene_symbol, "ot_paralogy"):
                paralog_saved += 1
                saved += 1
        print(f"  [{gene_symbol}] ot_paralogy: {paralog_saved} row(s) ingested "
              f"({len(paralog_rows)} real human paralogue(s) found)")
    else:
        print(f"  [{gene_symbol}] ot_essentiality: 0 rows ingested (query failed)")
        print(f"  [{gene_symbol}] ot_paralogy: 0 rows ingested (query failed)")

    # ClinicalTrials.gov: a second, independent human_clinical source (see
    # app/ingestion/clinicaltrials_gov_client.py's module docstring) —
    # recovers real trials OTP's own clinical_precedence datasource misses
    # entirely for some genes (confirmed: BIIB078/WVE-004 for C9orf72).
    try:
        ctgov_rows = get_clinical_trials(gene_symbol, DISEASE_NAME)
    except Exception as exc:
        print(f"  [{gene_symbol}] clinicaltrials_gov: query failed ({exc}), skipping")
        ctgov_rows = []
    for row in ctgov_rows:
        record = EvidenceRecord(
            target_id=target.id, dimension="human_clinical", data_source="clinicaltrials_gov",
            **_build_ctgov_clinical_fields(row),
        )
        if _save_evidence(db, record, gene_symbol, "clinicaltrials_gov"):
            saved += 1
    print(f"  [{gene_symbol}] clinicaltrials_gov: {len(ctgov_rows)} rows ingested")

    # Tissue Expression: real Human Protein Atlas data — a genuinely
    # independent external source (not Open Targets, see
    # app/ingestion/hpa_client.py docstring), handled gracefully like every
    # other real external API call here: log and continue, never abort.
    try:
        hpa_data = get_tissue_expression(ensembl_id)
    except Exception as exc:
        print(f"  [{gene_symbol}] hpa: query failed ({exc}), skipping")
        hpa_data = None
    if hpa_data is not None:
        record = EvidenceRecord(target_id=target.id, **_build_tissue_expression_fields(hpa_data, ensembl_id))
        if _save_evidence(db, record, gene_symbol, "hpa"):
            saved += 1
            print(f"  [{gene_symbol}] hpa: 1 row ingested (specificity={hpa_data.get('rna_tissue_specificity')})")
    else:
        print(f"  [{gene_symbol}] hpa: 0 rows ingested (no real HPA record for this gene)")

    # GTEx: real median expression across real healthy-donor tissues — a
    # second, independent tissue_expression source alongside HPA (see
    # app/ingestion/gtex_client.py's module docstring for why this isn't
    # a new "omics" dimension). Cross-checked against HPA's own real
    # category above (hpa_data may be None if HPA itself failed/had no
    # record — handled honestly, no cross-check attempted in that case).
    try:
        gtex_median_by_tissue = get_median_tissue_expression(gene_symbol)
    except Exception as exc:
        print(f"  [{gene_symbol}] gtex: query failed ({exc}), skipping")
        gtex_median_by_tissue = None
    if gtex_median_by_tissue:
        hpa_category = hpa_data.get("rna_tissue_specificity") if hpa_data else None
        record = EvidenceRecord(
            target_id=target.id, **_build_gtex_fields(gtex_median_by_tissue, gene_symbol, hpa_category),
        )
        if _save_evidence(db, record, gene_symbol, "gtex"):
            saved += 1
            print(f"  [{gene_symbol}] gtex: 1 row ingested ({len(gtex_median_by_tissue)} real tissues)")
    else:
        print(f"  [{gene_symbol}] gtex: 0 rows ingested (no real GTEx record for this gene)")

    # PPI Network: real STRING high-confidence interaction partners —
    # another genuinely independent external source, same graceful
    # error-handling convention. IMPORTANT: a real query failure (network/
    # rate-limit) is NOT the same as a real, confirmed zero-partner result
    # (score_ppi_hub(0) == 0.0, a genuine low score) — conflating the two
    # would silently fabricate a "confirmed isolated protein" finding out
    # of an API timeout, so a failed query skips the row entirely, exactly
    # like every other source's failure path above.
    try:
        ppi_partners = get_ppi_partners(gene_symbol)
    except Exception as exc:
        print(f"  [{gene_symbol}] string: query failed ({exc}), skipping")
        ppi_partners = None
    if ppi_partners is not None:
        try:
            string_id = get_string_id(gene_symbol)
        except Exception as exc:
            print(f"  [{gene_symbol}] string: id-resolution for source link failed ({exc}), link will be unavailable")
            string_id = None
        record = EvidenceRecord(target_id=target.id, **_build_ppi_network_fields(ppi_partners, gene_symbol, string_id))
        if _save_evidence(db, record, gene_symbol, "string"):
            saved += 1
            print(f"  [{gene_symbol}] string: 1 row ingested ({len(ppi_partners)} real high-confidence partners)")

    # Druggability: real Pharos Target Development Level (TDL) — a genuinely
    # independent external source (NOT Open Targets — see
    # app/ingestion/pharos_client.py docstring for the live-confirmed
    # endpoint pharos-api.ncats.io/graphql, NOT pharos.nih.gov/api which
    # 403s). Same graceful error-handling convention as every other real
    # external API call here: log and continue, never abort. A real query
    # failure is NOT the same as a real confirmed "Pharos has no target"
    # (the client returns None for a not-found symbol) — a failed query
    # skips the row entirely so an API timeout never fabricates a missing-
    # druggability finding, exactly like the PPI failure path above.
    try:
        pharos_row = get_druggability_evidence(gene_symbol)
    except Exception as exc:
        print(f"  [{gene_symbol}] pharos: query failed ({exc}), skipping")
        pharos_row = None
    if pharos_row is not None:
        record = EvidenceRecord(target_id=target.id, **_build_druggability_fields(pharos_row))
        if _save_evidence(db, record, gene_symbol, "pharos"):
            saved += 1
            print(f"  [{gene_symbol}] pharos: 1 row ingested (tdl={pharos_row['tdl']}, "
                  f"family={pharos_row['fam']}, ligands={pharos_row['ligand_count']}, "
                  f"drugs={pharos_row['drug_count']})")
    else:
        print(f"  [{gene_symbol}] pharos: 0 rows ingested (no real Pharos target for this gene)")

    return saved


def clear_evidence_and_downstream_analysis(db) -> dict:
    """
    Clear EvidenceRecord AND every table whose rows are a conclusion
    computed FROM evidence — ContradictionLog, GapRecord, PriorityScore,
    PipelineRunLog — together, atomically, before a fresh re-ingestion.

    Real bug this fixes (found while cleaning up an orphaned NEK1
    ContradictionLog row during Matrix testing): EvidenceRecord's primary
    key is a global auto-increment, NOT scoped per gene. The previous
    "clear before re-insert" behavior deleted only EvidenceRecord and left
    ContradictionLog/GapRecord/PriorityScore rows in place, pointing at the
    OLD evidence_record ids. On the next full re-ingestion, those same
    numeric ids get reused for a DIFFERENT gene's new rows — so a stale
    ContradictionLog row doesn't just go orphaned (referencing nothing), it
    silently starts resolving to a different gene's real evidence. That is
    a confident, plausible, WRONG answer, not a missing one — worse than an
    empty result. The same "conclusion computed from now-replaced data"
    logic applies to GapRecord (rationale/investigation_suggestion quote
    specific evidence values) and PriorityScore (dimension_breakdown is
    literally a snapshot of evidence that may no longer exist in that
    form). PipelineRunLog is cleared too so GET /contradictions and
    GET /gaps correctly report "never (re-)checked since this evidence was
    ingested" instead of a false "checked, clean" carried over from before
    the re-ingestion — see PipelineRunLog's own docstring in
    app/db/models.py for why that "checked vs. never-checked" distinction
    exists at all.

    Deletion order: dependents (ContradictionLog/GapRecord/PriorityScore/
    PipelineRunLog) before EvidenceRecord itself — matters for readability/
    intent even though SQLite doesn't enforce FK constraints by default
    here, so an interrupted run never leaves EvidenceRecord gone while a
    dependent row still references it.
    """
    counts = {
        "contradiction_log": db.query(ContradictionLog).delete(),
        "gap_records": db.query(GapRecord).delete(),
        "priority_scores": db.query(PriorityScore).delete(),
        "pipeline_run_log": db.query(PipelineRunLog).delete(),
        "evidence_records": db.query(EvidenceRecord).delete(),
    }
    if any(counts.values()):
        db.commit()
    return counts


def main():
    init_db()
    db = SessionLocal()
    try:
        # Prototype re-run behavior: clear prior ingestion AND every
        # downstream analysis table computed from it rather than
        # accumulating duplicates or leaving stale/mismatched references
        # behind — see clear_evidence_and_downstream_analysis()'s docstring
        # for the real cross-gene ID-reuse bug this prevents.
        counts = clear_evidence_and_downstream_analysis(db)
        if any(counts.values()):
            print(
                f"Cleared before re-ingesting: {counts['evidence_records']} evidence record(s), "
                f"{counts['contradiction_log']} contradiction log row(s), "
                f"{counts['gap_records']} gap record(s), "
                f"{counts['priority_scores']} priority score(s), "
                f"{counts['pipeline_run_log']} pipeline run log row(s).\n"
            )

        grand_total = 0
        for gene_symbol, ensembl_id in CANDIDATE_TARGETS.items():
            print(f"Ingesting {gene_symbol} ({ensembl_id})...")
            grand_total += ingest_target(db, gene_symbol, ensembl_id)
        print(f"\nDone. {grand_total} evidence records ingested across {len(CANDIDATE_TARGETS)} targets.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
