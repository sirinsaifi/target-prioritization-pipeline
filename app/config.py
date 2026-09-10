"""
Central configuration: disease scope, candidate targets, and scoring thresholds.
Keep this disease-agnostic in spirit — swapping DISEASE_EFO_ID and CANDIDATE_TARGETS
should be enough to point the pipeline at a different disease later.
"""

# Open Targets disease ID for Amyotrophic Lateral Sclerosis
DISEASE_NAME = "Amyotrophic Lateral Sclerosis"
DISEASE_EFO_ID = "MONDO_0004976"

# Candidate genes, scoped down intentionally (see mentor feedback: narrow the
# demo scope rather than pulling every ALS-associated gene).
# Ensembl gene IDs included so we can query Open Targets directly without an
# extra lookup step.
CANDIDATE_TARGETS = {
    "SOD1": "ENSG00000142168",
    "C9orf72": "ENSG00000147894",
    "TARDBP": "ENSG00000120948",
    "FUS": "ENSG00000089280",
    "NEK1": "ENSG00000137601",
}

# MVP evidence dimensions. Omics/Experimental/Drug-Target promoted from
# Phase 2 here — each has a real ingestion path + scorer wired in
# (see scripts/ingest_evidence.py, app/core/scoring/dimension_scoring.py).
# Biomarker deliberately still deferred: it needs a definitional decision
# (what separates it from genetic evidence) made separately before wiring
# it in — not a build gap, a scoping one.
MVP_DIMENSIONS = [
    "genetic", "literature", "pathway", "human_clinical", "omics", "experimental", "drug_target",
    "tissue_expression", "ppi_network",
]
PHASE_2_DIMENSIONS = ["biomarker"]

# --- Tissue expression (Human Protein Atlas) ---
#
# Added in place of OTP's Expression Atlas (confirmed retired — see
# EXPRESSION_ATLAS_DATASOURCE_ID above) as a genuinely independent external
# source, not a substitute OTP query. Category -> prototype 0-1 specificity
# score, built from HPA's real "RNA tissue specificity" field (confirmed
# live for SOD1/INS/ACTB — see app/ingestion/hpa_client.py's docstring for
# why the more literal-looking "RNA tissue specificity score" field was
# checked and rejected as unreliable/non-comparable). A tau-score-like
# metric, deliberately simple, NOT a reproduction of the published tau
# statistic (which needs a complete per-tissue expression vector HPA's
# JSON API doesn't expose in one field).
#
# FRAMING (per early reviewer feedback, carried over from
# docs/01_final_architecture.md Stage 4): "Tissue specificity can inform
# biological context; it is not treated as a direct measure of off-target
# risk." This dimension is scored and shown like any other — it must
# never be framed as a safety/toxicity predictor in any gap template or
# narration text (see gap_taxonomy.py: this dimension deliberately
# triggers no gap type at all).
TISSUE_SPECIFICITY_SCORES = {
    "tissue enriched": 1.0,
    "group enriched": 0.7,
    "tissue enhanced": 0.4,
    "low tissue specificity": 0.1,
}

# --- Evidence Momentum / Trend Signal ---
#
# Deliberately NOT wired into gap_taxonomy.py or PriorityScore (see
# app/core/scoring/evidence_momentum.py's module docstring) — an
# independent, informational signal. Prototype formula, this project's
# own design, not an external reference: recent-window count vs.
# prior-window count, "last 2 years" vs. "the 2 years before that" (per
# this task's own instruction). "Now" is anchored on the real MAX
# publication_year actually present in a target's own dated evidence, not
# wall-clock date — deliberately, to avoid misreading normal PubMed
# indexing lag (this year's papers not yet indexed) as "interest is
# declining" for every target simultaneously.
MOMENTUM_RECENT_WINDOW_YEARS = 2
MOMENTUM_PRIOR_WINDOW_YEARS = 2
# Bucket boundaries — a complete, non-overlapping partition (this task's
# own examples, ">2.0 accelerating" / "0.8-1.2 stable" / "<0.5 declining",
# left two numeric gaps; resolved here as two hard boundaries so every
# real ratio lands in exactly one bucket, with the stable range kept
# exactly as given): momentum_score > MOMENTUM_ACCELERATING_THRESHOLD ->
# accelerating; between the two thresholds (inclusive) -> stable; below
# MOMENTUM_DECLINING_THRESHOLD -> declining. "emerging" is a separate,
# non-ratio special case (see compute_momentum()'s docstring), not part
# of this numeric partition.
MOMENTUM_ACCELERATING_THRESHOLD = 1.2
MOMENTUM_DECLINING_THRESHOLD = 0.8

# --- PPI network context (STRING) ---
#
# STRING's own documented high-confidence threshold (0-1000 combined_score
# scale — confirmed live this is the scale STRING's `required_score` query
# parameter expects, even though returned `score` values are 0-1 floats;
# see app/ingestion/string_client.py's docstring).
STRING_HIGH_CONFIDENCE_THRESHOLD = 700
# Prototype normalization ceiling for the hub score (this task's own
# instruction): 100 high-confidence partners -> hub score 1.0. Not an
# externally published reference — a documented judgment call.
PPI_HUB_SCORE_CEILING = 100

# --- Druggability (Pharos) ---
#
# New independent signal (this task) — Pharos Target Development Level (TDL),
# from pharos-api.ncats.io (see app/ingestion/pharos_client.py's docstring for
# the live-confirmed endpoint and field semantics). PROTOTYPE 0-1 mapping of
# Pharos's own ordinal tiers, documented the same as every other threshold in
# this file — NOT an externally published scale. Tclin targets have approved
# drugs (Pharos's own top tier); Tdark targets have almost no known
# ligands/drugs (Pharos's own bottom tier). Tchem/Tbio sit between.
#
# REAL, LIVE-CONFIRMED FINDING across the 5 ALS candidates: NONE are Tclin or
# Tdark (SOD1/TARDBP/NEK1 = Tchem, C9orf72/FUS = Tbio) — so the Druggability
# Gap (gap_taxonomy "druggability", fires on Tdark) and the Tdark ->
# Early-Stage Discovery translational rule are real and unit-tested but NOT
# exercised by any of today's real genes, same "real but currently
# unexercised" status as several other features in this project. State this
# honestly in the report rather than implying a Tdark case was found.
TDL_SCORES = {
    "Tclin": 1.0,
    "Tchem": 0.7,
    "Tbio": 0.4,
    "Tdark": 0.1,
}

# --- Protein family druggability heuristic (Signal B) ---
#
# PROTOTYPE HEURISTIC, not established science — documented the same as every
# other threshold in this file. Pharos's `fam` field gives a target's protein
# family (Enzyme, Kinase, GPCR, Ion Channel, Transcription Factor, ...). Some
# families have historically strong small-molecule druggability track records
# (kinases, GPCRs, ion channels, enzymes) vs. traditionally harder ones
# (transcription factors, nuclear receptors are mixed). This is a coarse,
# documented judgment call surfacing family as CONTEXT alongside TDL — it
# NEVER overrides TDL or the priority score, and a family's historical
# tractability is no guarantee a SPECIFIC target in it is druggable.
#
# Values: "favorable" / "challenging" / "neutral" (neutral = not in either
# list, or fam is null — 3 of the 5 real ALS genes return fam=null). Real
# ALS-gene families: SOD1=Enzyme (favorable), NEK1=Kinase (favorable),
# C9orf72/TARDBP/FUS=fam=null (neutral).
DRUGGABLE_FAMILIES_FAVORABLE = {
    "kinase", "gpcr", "g-protein coupled receptor", "ion channel",
    "enzyme", "protease", "phosphatase", "histone deacetylase",
}
DRUGGABLE_FAMILIES_CHALLENGING = {
    "transcription factor", "nuclear receptor",
}


def family_druggability_heuristic(fam: str | None) -> str:
    """
    Prototype family->druggability-favorability label (Signal B). Returns
    'favorable' | 'challenging' | 'neutral'. Coarse heuristic over Pharos's
    real `fam` field, documented as a prototype not established science —
    see DRUGGABLE_FAMILIES_FAVORABLE/CHALLENGING above. None fam -> 'neutral'
    (3 of 5 real ALS genes have fam=null; a real absence, not 'challenging').
    Case-insensitive substring match against the family name.
    """
    if not fam:
        return "neutral"
    fam_lower = fam.lower()
    for f in DRUGGABLE_FAMILIES_CHALLENGING:
        if f in fam_lower:
            return "challenging"
    for f in DRUGGABLE_FAMILIES_FAVORABLE:
        if f in fam_lower:
            return "favorable"
    return "neutral"

# Dimensions whose real evidence_score has a KNOWN scoring-FORMULA
# limitation that can make a real, meaningful result look artificially
# weak — distinct from a dimension simply having low real evidence. Found
# and documented after a real, live-confirmed case: a gene with 10 real
# high-confidence STRING partners (a genuinely meaningful interactome)
# scores ppi_network=0.10 purely because score_ppi_hub() divides the real
# partner count by PPI_HUB_SCORE_CEILING (100) above — an arbitrary,
# project-chosen denominator, not a reflection of how weak the evidence
# actually is. Consumers that pick "the lowest-scoring dimension" as a
# stand-in for "the weakest real evidence" (see
# app.core.narration.agent_narrator.build_why_this_target_grounding_data())
# must skip dimensions in this set, or they will systematically
# mis-attribute uncertainty to a formula artifact rather than a real gap.
#
# Every other scorer in dimension_scoring.py was checked against this same
# question and deliberately NOT added here:
# - score_genetic_l2g / score_clinical_precedence / score_drug_target: a
#   direct real value (L2G score) or a real, OTP-published stage->score
#   lookup table — a low result there IS the real, intended signal
#   (early-stage/preclinical, or weak L2G), not an arbitrary cap.
# - score_pathway_curated: binary 1.0/0.0, no partial-scoring ceiling to
#   distort.
# - score_literature_cooccurrence / score_experimental: both pass through
#   an already-normalized real 0-1 value (OTP's own confidence/score
#   field) unchanged — no additional denominator introduced by this
#   project at all.
# - score_tissue_specificity (HPA): a real categorical bucket
#   (TISSUE_SPECIFICITY_SCORES) reflecting HPA's own real specificity
#   category — a low score here genuinely means "broadly expressed", not
#   an artifact of an arbitrary count/ceiling division.
# - compute_tau_specificity (GTEx): the real, published Yanai et al. tau
#   statistic — not a prototype approximation at all (see that function's
#   own docstring), so no formula-limitation concern applies.
# - score_omics_expression: never exercised by real data in this project
#   (see EXPRESSION_ATLAS_DATASOURCE_ID), so it can never actually be
#   picked as a real "lowest dimension" today — not added preemptively;
#   revisit if real omics data is ever ingested.
# score_ppi_hub is the ONLY scorer whose low end is a "real count divided
# by an arbitrary, project-chosen ceiling" shape, which is what makes it
# uniquely misleading as a standalone weakness signal.
DIMENSIONS_WITH_SCORING_FORMULA_LIMITATIONS = {"ppi_network"}

# Real OTP schema-level datasourceId for differential-expression evidence
# (Expression Atlas), per platform-docs.opentargets.org/evidence. CONFIRMED
# via live introspection this returns ZERO real rows for all 5 ALS
# candidate genes AND for 2 additional, deliberately unrelated,
# extremely-well-studied cancer gene/disease pairs (TP53 vs lung
# carcinoma, ERBB2 vs breast carcinoma) where such evidence would be
# expected to exist in volume if this datasource were still live — the
# same signature as `ot_genetics_portal`'s earlier-confirmed retirement.
# The Evidence type's own schema DOES still declare the exact fields this
# formula needs (log2FoldChangeValue, log2FoldChangePercentileRank,
# pValueMantissa, pValueExponent — confirmed via introspection), so the
# ingestion/scoring code below is real and correctly wired against real
# field names, not guessed — it is simply never exercised by any evidence
# this pipeline can currently retrieve. Reported as a real finding, not
# silently worked around.
EXPRESSION_ATLAS_DATASOURCE_ID = "expression_atlas"

# UPDATE (Sep 2026): The DIRECT Expression Atlas REST API at
# https://www.ebi.ac.uk/gxa IS actively maintained (4,562 studies)
# and reachable via its own API (expression_atlas_direct_client.py).
# Only OTP's routing to it is broken/retired. The direct API returns
# real baseline TPM data for all 5 ALS genes (confirmed live for
# SOD1, C9orf72, TARDBP, FUS, NEK1) and real differential-expression
# foldChange+pValue data across 5 human ALS experiments.
# New omics data now flows through data_source="expression_atlas_direct",
# not via the old OTP "expression_atlas" route — see
# scripts/ingest_evidence.py's Expression Atlas Direct block.

# Omics/Expression Atlas significance gate (OTP precedent, per
# docs/04_scoring_elements_needed.md item 10): |log2FC| > 1 and adjusted
# p-value <= 0.05 required for inclusion, mirroring L2G_INCLUSION_THRESHOLD's
# below-threshold-is-excluded pattern for genetic evidence.
OMICS_LOG2FC_SIGNIFICANCE_THRESHOLD = 1.0
OMICS_PVALUE_SIGNIFICANCE_THRESHOLD = 0.05

# Open Targets' own real schema-level datatype identifier for genetic
# evidence (confirmed via live GraphQL introspection + real data grouping —
# see docs/07 "Genetic evidence: datatype-driven fetch"). NOT a
# disease-specific choice — it's an OTP API constant, the same for every
# disease — used by open_targets_client.get_evidence_by_datatype() to
# discover which specific datasourceIds (eva, uniprot_variants,
# gwas_credible_sets, orphanet, ...) carry genetic evidence for a given
# target-disease pair, rather than hardcoding that list. Replaces the
# previous hardcoded GENETIC_DATASOURCES list, which was tuned for ALS's
# rare-variant genetics and would have silently under-collected evidence
# for a GWAS-driven disease.
GENETIC_DATATYPE_ID = "genetic_association"

# --- Literature contradiction proposer/verifier (Phase 7) ---
#
# Deliberate prototype-scale bound, stated explicitly rather than a silent
# truncation: comparing every pair of a target's literature records would
# mean C(N,2) real LLM calls (SOD1 alone has ~220 real literature rows —
# ~24,000 pairs, wildly impractical for a per-request route). Capped to a
# small, fixed number of records per run instead. LITERATURE_CONTRADICTION_
# MAX_CANDIDATES bounds how many records are even attempted for abstract-text
# backfill (some real PMIDs have no fetchable abstract — see
# literature_text_client.get_abstract_text() — so a slightly larger
# candidate pool is tried to reliably reach MAX_RECORDS real ones).
LITERATURE_CONTRADICTION_MAX_RECORDS = 5
LITERATURE_CONTRADICTION_MAX_CANDIDATES = 15

# --- Literature contradiction proposer: biomedical LLM option (new task) ---
#
# The proposer (app/core/verification/literature_contradiction_proposer.py)
# reads real abstract text and judges CONTRADICT/SUPPORT/UNRELATED — the one
# LLM use in this codebase where domain knowledge genuinely helps (unlike
# narration or the investigation loop, which only need fluent
# instruction-following over already-computed facts). Groq's
# openai/gpt-oss-20b remains the DEFAULT — this is an additional option, not
# a replacement, selected via the LITERATURE_LLM_PROVIDER environment
# variable ("groq" | "biomedical"; unset or unrecognized -> "groq").
#
# REAL, LIVE-CONFIRMED FINDING (checked via HuggingFace's public model API,
# not assumed): neither of the two originally-proposed candidates —
# BioMistral/BioMistral-7B nor aaditya/Llama3-OpenBioLLM-8B — currently has
# ANY active HF Inference Provider (`inferenceProviderMapping` is a literal
# `{}` for both, confirmed against a live control model that DOES show real
# provider entries with status "live"). HuggingFace also fully retired the
# old `api-inference.huggingface.co` serverless domain (DNS no longer
# resolves) in favor of the unified `router.huggingface.co` "Inference
# Providers" API used below. Searching HF's own model hub for other
# biomedical-domain models that ARE currently live turned up
# Intelligent-Internet/II-Medical-8B (Qwen3-8B base, SFT+RL-tuned on medical
# reasoning datasets, scores 40% on OpenAI's HealthBench per its model
# card) — confirmed live today on the `featherless-ai` provider — used here
# instead. Revisit this constant if BioMistral/OpenBioLLM ever become
# provider-hosted again; the calling code
# (app.core.llm_client.call_llm_plain_biomedical()) is generic to any
# HF-hosted chat model and does not need to change.
BIOMEDICAL_LLM_MODEL = "Intelligent-Internet/II-Medical-8B"
BIOMEDICAL_LLM_INFERENCE_PROVIDER = "featherless-ai"

# --- Scoring thresholds (OTP-referenced; treat as prototype defaults) ---

# GWAS/L2G evidence only included above this threshold (OTP default)
L2G_INCLUSION_THRESHOLD = 0.05

# Max theoretical harmonic sum for normalization (OTP uses ~1.644,
# derived from an infinite vector of 1.0s; approximated with N=1000 below)
HARMONIC_SUM_NORMALIZATION_TERMS = 1000

# Clinical trial early-stop down-weight (OTP: negative/safety reasons -> x0.5)
TRIAL_STOPPED_EARLY_WEIGHT = 0.5

# Data source weights before combining into dimension/overall scores
# (OTP precedent: literature/text-mined sources down-weighted relative to
# structured evidence — adapted here to our smaller source set)
DATA_SOURCE_WEIGHTS = {
    "europe_pmc": 0.2,
    "open_targets_genetic": 1.0,
    "reactome_pathway": 1.0,
    "clinical_trials": 1.0,
}

# Contradiction classification: fields checked for comparability.
#
# DISCOVERY (via live GraphQL introspection against the OTP API): a single
# uniform field set does not work across evidence source types. Genetic
# evidence (eva, uniprot_variants) has no population/tissue/assay/endpoint
# fields — comparability there is variant/pathogenicity-based instead.
# IMPC (experimental/phenotype) evidence does carry tissue-like fields.
# Clinical trial evidence has population/endpoint-like fields but under
# different names. Literature (europepmc) evidence has no structured
# comparability fields at all.
#
# Decision: compare evidence ONLY within the same source-type group for the
# MVP. Cross-type contradiction comparison (e.g. genetic pathogenicity vs.
# clinical trial outcome) is real but structurally harder and is named as
# future work rather than forced into this framework.
COMPARABILITY_FIELDS_BY_SOURCE_TYPE = {
    "genetic": ["variant_id", "clinical_significance", "inheritance_pattern"],
    "experimental": ["tissue", "phenotype", "assay_type"],
    "clinical": ["population", "endpoint", "intervention"],
    "literature": [],  # no structured comparison possible for this source type
    "pathway": [],  # disease-agnostic gene annotation (Target.pathways) — no direction/comparability concept at all
    # New (this task). Real, confirmed-in-schema comparability field for
    # differential expression — tissue is the only one of the 5 original
    # candidate fields that plausibly applies (comparing whether an effect
    # is seen in the same tissue). Never populated with real rows in this
    # project's actual data (see EXPRESSION_ATLAS_DATASOURCE_ID above), so
    # this group is real-but-currently-inert, same status as several
    # already-declared groups above.
    "omics": ["tissue"],
    # New (this task). Both HPA tissue-expression and STRING PPI-network
    # rows are gene-level aggregate summaries (one row per gene, no
    # direction_on_trait ever set — see scripts/ingest_evidence.py's
    # builders) with no disease-association claim to compare across
    # records at all, structurally excluded from contradiction
    # classification the same way pathway already is (empty comparability
    # list + no direction_on_trait), not merely under-populated like omics.
    "tissue_expression": [],
    "ppi_network": [],
    # New (this task). Known Safety Events (Target.safetyLiabilities) is a
    # gene-level, disease-agnostic annotation like pathway/ppi_network
    # above — no direction_on_trait, no disease-association claim to
    # compare across records at all. Structurally excluded from
    # contradiction classification for the same reason; surfaced instead
    # via a dedicated gap type and a UI warning banner (see
    # app/core/gaps/gap_taxonomy.py, deliberately never scored 0-1 — see
    # scripts/ingest_evidence.py's _build_safety_signal_fields() docstring).
    "safety_signal": [],
    # New (this task). Real Open Targets Target Prioritisation Factor: Gene
    # Essentiality (Target.isEssential / Target.depMapEssentiality). Same
    # "gene-level, disease-agnostic, no direction_on_trait" reasoning as
    # safety_signal above — structurally excluded from contradiction
    # classification, surfaced instead via a dedicated gap type + UI
    # caution flag (see scripts/ingest_evidence.py's
    # _build_essentiality_fields() docstring). Deliberately a SEPARATE
    # source_type from "safety_signal", not folded into it: essentiality is
    # a predictive/mechanistic risk signal computed from DepMap CRISPR
    # knockout screens in proliferating cancer cell lines, categorically
    # different from an observed real-world clinical safety liability —
    # conflating the two would misrepresent how much confidence each
    # actually carries.
    "essentiality_risk": [],
    # New (this task). Real Open Targets homologue data (Target.homologues,
    # filtered to real human paralogues) plus OTP's own
    # paralogMaxIdentityPercentage prioritisation factor. Gene-level,
    # disease-agnostic, no direction_on_trait — structurally excluded from
    # contradiction classification for the same reason as pathway/
    # ppi_network/safety_signal/essentiality_risk above. Deliberately its
    # OWN source_type, not folded into "genetic": a paralogue relationship
    # is a two-sided druggability/redundancy signal (see
    # scripts/ingest_evidence.py's _build_paralogy_fields() docstring), not
    # genetic evidence of disease association.
    "paralogy": [],
    # New (this task). Real Pharos Target Development Level (TDL) — an
    # independent druggability signal from pharos-api.ncats.io (NOT Open
    # Targets at all). Confirmed via live introspection that the Pharos
    # Target type carries NO tissue/population/assay_type/direction_on_trait
    # fields — a gene-level target property, not a disease-association claim,
    # so it's structurally excluded from contradiction classification for the
    # same reason as pathway/ppi_network/paralogy above. Deliberately NOT
    # scored into evidence_score (see dimension_scoring.score_druggability_tdl()
    # docstring): druggability is a target PROPERTY, not translational
    # evidence, surfaced instead via its own gap type + translational_opportunity.
    "druggability": [],
    # New (this task). Real Google Patents landscape data (competitive
    # position) — see app/ingestion/patent_client.py. A gene-level aggregate
    # (one row per gene: total patent count, filing-year range, top
    # assignees), not a disease-association claim — structurally excluded
    # from contradiction classification for the same reason as the other
    # context signals above. Deliberately NOT a strength score: high patent
    # activity = HIGH competition (a caution/context signal), never silently
    # merged into priority_score as if more patents = better (same treatment
    # as safety_signal/essentiality_risk).
    "competitive_position": [],
}

# Real Open Targets Target Prioritisation Factor threshold for Paralogues
# (paralogMaxIdentityPercentage), confirmed via
# platform-docs.opentargets.org/web-interface/target-prioritisation: OTP
# itself only flags a paralogue as "concerning" (its own factor score goes
# negative) at >=60% sequence identity to a real human paralogue. Checked
# live against all 5 real ALS candidates before choosing a project-level
# threshold: NONE of them cross OTP's own 60% cutoff (SOD1's highest real
# hit, CCS, is ~47%; FUS's highest, EWSR1, is ~56% — close, but still under
# 60%). Using OTP's own 60% threshold here would mean this project's
# Modality-gap paralogue note could never fire on any of today's real data,
# even for FUS's well-known, real FET-family relationship (EWSR1/TAF15).
# EXPLICIT, DISCLOSED JUDGMENT CALL (this task): a separate, more inclusive
# project-chosen threshold of 40% is used ONLY for deciding whether to add
# an informational note to the Modality gap's own text (never to change
# whether the gap fires, and never applied to OTP's own prioritisation
# factor, which keeps its real, official 60% cutoff untouched in
# get_essentiality_and_paralogues()'s docstring/data). This is deliberately
# NOT the same number as OTP's own factor threshold — it exists to let a
# real, biologically meaningful relationship like FUS/EWSR1 surface in this
# project's own gap wording, while being explicit that this is our own
# choice, not OTP's.
PARALOGUE_MODALITY_NOTE_IDENTITY_THRESHOLD = 40.0

# Map each concrete data source to its source-type group (extend as new
# sources are added during ingestion)
SOURCE_TYPE_BY_DATA_SOURCE = {
    "eva": "genetic",
    "uniprot_variants": "genetic",
    "gwas_credible_sets": "genetic",
    "orphanet": "genetic",
    "ot_genetics_portal": "genetic",  # retired datasource id; kept for back-compat, returns 0 rows now
    "impc": "experimental",
    "clinical_precedence": "clinical",
    "europepmc": "literature",  # real OTP datasourceId has no underscore
    # Not a real OTP datasourceId (pathway membership comes from
    # Target.pathways, not evidences()) — this is our own internal label
    # for the source, assigned in scripts/ingest_evidence.py.
    "reactome": "pathway",
    "expression_atlas": "omics",
    # New (this task). Real ChEMBL-backed drug-target mechanism-of-action
    # data, but NOT from evidences() — from Target.drugAndClinicalCandidates
    # (gene-level, disease-agnostic at the API level, same shape as
    # pathways; disease-relevance filtered client-side in
    # scripts/ingest_evidence.py before being treated as evidence FOR this
    # disease). Named distinctly from "clinical_precedence" (a different
    # real datasource/API path) even though both land in the "clinical"
    # comparability group — see that group's real fields
    # (population/endpoint/intervention); `intervention` (the drug name)
    # is the one that genuinely applies here too.
    "chembl_drug_target": "clinical",
    # New (this task). Direct ClinicalTrials.gov API v2 pull — a second,
    # independent human_clinical source alongside clinical_precedence (see
    # app/ingestion/clinicaltrials_gov_client.py's module docstring for the
    # real gap this closes: OTP's clinical_precedence returns zero rows for
    # C9orf72 vs ALS, missing 2 real, well-documented discontinued ASO
    # trials — BIIB078 and WVE-004 — that this source recovers). Same
    # "clinical" comparability group as clinical_precedence/
    # chembl_drug_target (same real fields apply: population/endpoint/
    # intervention).
    "clinicaltrials_gov": "clinical",
    "hpa": "tissue_expression",
    # New (this task). Second, independent tissue_expression source
    # alongside HPA — real healthy-donor median expression (GTEx), not a
    # new "omics"/differential-expression dimension (see
    # app/ingestion/gtex_client.py's module docstring for the full
    # reasoning). Same "two sources, one existing dimension" pattern
    # already used for literature (europepmc/pubmed) and human_clinical
    # (clinical_precedence/clinicaltrials_gov).
    "gtex": "tissue_expression",
    "string": "ppi_network",
    # New (this task). Real Open Targets Target Prioritisation Factors —
    # Known Safety Events and Genetic Constraint (see
    # app/ingestion/open_targets_client.py's get_prioritisation_and_safety()
    # docstring for the full field semantics). Genetic constraint is a
    # real, disease-agnostic gene annotation folded into the existing
    # "genetic" comparability group (same pattern as pathway/drug_target
    # being folded into their groups); Known Safety Events gets its own
    # "safety_signal" group (see COMPARABILITY_FIELDS_BY_SOURCE_TYPE above
    # for why it's structurally excluded from contradiction classification,
    # same as pathway/ppi_network).
    "ot_genetic_constraint": "genetic",
    "ot_safety": "safety_signal",
    # New (this task). Real Open Targets Target Prioritisation Factors:
    # Gene Essentiality and Paralogues (see
    # app/ingestion/open_targets_client.py's get_essentiality_and_paralogues()
    # docstring for the full real field semantics, confirmed via
    # platform-docs.opentargets.org). Both deliberately excluded from every
    # structural/druggability prioritisation factor (hasLigand, hasPocket,
    # isInMembrane, etc.) per this task's own scope instruction — only
    # these two simple, non-structural OTP fields are queried.
    "ot_essentiality": "essentiality_risk",
    "ot_paralogy": "paralogy",
    # New (this task). Real Pharos druggability data from
    # pharos-api.ncats.io/graphql (NOT an OTP datasource — see
    # app/ingestion/pharos_client.py). Maps to the "druggability" source-type
    # group above (no comparability fields — a gene-level target property,
    # structurally excluded from contradiction classification).
    "pharos": "druggability",
    # New (this task). Real Google Patents landscape data (competitive
    # position) — see app/ingestion/patent_client.py. Maps to the
    # "competitive_position" source-type group above (no comparability
    # fields — a gene-level aggregate, not a disease-association claim).
    "google_patents": "competitive_position",
}

# Deprecated: kept only for backward compatibility with earlier prototype
# code. Do not use for new contradiction-classification logic — see
# COMPARABILITY_FIELDS_BY_SOURCE_TYPE above.
COMPARABILITY_FIELDS = ["tissue", "disease_subtype", "population", "assay_type", "endpoint"]

# Evidence-consistency gap threshold: below this consistency score despite
# high strength -> flagged as an evidence-consistency gap (prototype default,
# to be validated against domain-expert assessment per mentor feedback)
EVIDENCE_CONSISTENCY_GAP_THRESHOLD = 0.5
EVIDENCE_STRENGTH_HIGH_THRESHOLD = 0.7

# --- "Why This Target?" structured narrative (decision-layer strategy) ---
#
# Confidence label (High/Medium/Low), derived from real evidence_consistency.
# Prototype cutoffs, same status as every other threshold in this file —
# NOT an externally published reference. The Low/Medium boundary
# deliberately REUSES EVIDENCE_CONSISTENCY_GAP_THRESHOLD (0.5) rather than
# introducing a second, slightly-different number for what is conceptually
# the same "this is where consistency starts being a real concern" line the
# evidence_consistency gap already uses.
CONFIDENCE_HIGH_THRESHOLD = 0.8  # >= this -> "High"
CONFIDENCE_LOW_THRESHOLD = EVIDENCE_CONSISTENCY_GAP_THRESHOLD  # < this -> "Low"; between the two -> "Medium"

# Evidence maturity label (High/Medium/Low), derived from real
# evidence_maturity (the DIMENSION_MATURITY_LADDER rung reached — see
# evidence_profile.py). Thresholds chosen against that ladder's own real
# values: >=0.9 means the human_clinical (1.0) or drug_target (0.9) rung
# was reached (translationally the most advanced evidence this project
# scores); <0.4 means only literature (0.2), omics (0.3), or
# tissue_expression (0.25) was reached (the least advanced); everything
# else (genetic 0.4 through ppi_network 0.45 / pathway 0.5 / experimental
# 0.7) is "Medium". Prototype cutoffs, not an externally published scale.
MATURITY_HIGH_THRESHOLD = 0.9
MATURITY_LOW_THRESHOLD = 0.4

# "Main remaining uncertainty" gap-type priority order (this task's own
# judgment call, documented rather than left arbitrary): when a target has
# more than one open EVIDENCE-COMPLETENESS gap (excludes the two risk-flag
# gap types below, which are already surfaced via their own caution-flag
# bullet, not as an "uncertainty"), the first type in this list that's
# actually present is picked as the single most relevant one to name.
# Reasoning: a confirmed disagreement in the evidence itself
# (evidence_consistency) is treated as more fundamental than simply having
# no human data yet (validation), which in turn is treated as more
# fundamental than an unclear mechanism (mechanistic) or a missing compound
# (modality) or a narrow population sample (population) — each of the
# latter three is a real but comparatively more "expected, next-step"
# limitation for an early-stage target than the first two.
WHY_THIS_TARGET_UNCERTAINTY_GAP_PRIORITY = [
    "evidence_consistency", "validation", "mechanistic", "modality", "population",
]
# These two gap types are deliberately EXCLUDED from the priority list
# above — they fire because a real fact EXISTS (a safety event or an
# essentiality flag), not because evidence is missing, and are already
# reported via the "why this target" caution-flags bullet, so naming one
# again as the "main remaining uncertainty" would double-count it under a
# misleading label (a documented risk is not the same kind of "gap" as
# missing evidence).
WHY_THIS_TARGET_UNCERTAINTY_EXCLUDED_GAP_TYPES = {"safety_signal", "essentiality_risk"}

# --- Evidence Profile: Consistency & Maturity (original contribution, not
# from OTP — OTP does not publish per-target consistency/maturity scores) ---

# Per-pair penalty applied when computing Evidence Consistency, by
# contradiction classification severity. "not_comparable_cross_type" is
# deliberately absent (weight 0, and excluded from the pair denominator
# entirely in evidence_profile.py) — it was never a real comparability
# attempt, so it shouldn't dilute the score either way. "unclassified" sits
# between a confirmed conflict and a confirmed non-conflict: it's an honest
# "can't confirm," not evidence of agreement.
CONTRADICTION_SEVERITY_WEIGHTS = {
    "direct_contradiction": 1.0,
    "unclassified": 0.5,
    "population_heterogeneity": 0.25,
    "methodological_disagreement": 0.25,
    # Weighted the same as direct_contradiction (not a softer tier like
    # population/methodological): a "literature_contradiction" row only
    # exists after BOTH the LLM proposer said CONTRADICT AND the
    # deterministic verifier confirmed both excerpts are genuinely about
    # the same gene+disease with real text (see
    # app/core/verification/literature_contradiction_verifier.py) — there's
    # no softer "different population/methodology" sub-classification for
    # literature the way structured evidence has, so a confirmed one is
    # a full-severity real conflict, not a partial one. Used only by
    # compute_literature_consistency() (evidence_profile.py) — NEVER by
    # compute_evidence_consistency(), which explicitly excludes this
    # classification from its own (structured-only) denominator.
    "literature_contradiction": 1.0,
}

# Evidence Maturity ladder: how far along the translational-evidence
# spectrum a dimension sits, from text-mined literature (least mature)
# through human/clinical evidence (most mature). A target's maturity score
# is the single most advanced rung reached — this measures how far the
# evidence has progressed, not how many dimensions happen to have data
# (that's closer to Strength/breadth, kept separate per design principle).
DIMENSION_MATURITY_LADDER = {
    "literature": 0.2,
    # New (this task) — prototype placement, not an OTP reference:
    # differential-expression/omics evidence is molecular, same general
    # tier as genetic evidence, placed just below it since it's typically
    # one step further from direct causal variant evidence. Never
    # exercised by real data in this project (see
    # config.EXPRESSION_ATLAS_DATASOURCE_ID) — placement is a documented
    # judgment call, open to revision once real omics evidence exists.
    "omics": 0.3,
    "genetic": 0.4,
    "pathway": 0.5,
    "experimental": 0.7,
    # New (this task) — prototype placement: real drug/clinical-stage
    # evidence (Target.drugAndClinicalCandidates), same general concept as
    # human_clinical's clinical-trial-phase evidence, placed just below it
    # since clinical_precedence remains this project's primary clinical
    # evidence source and drug_target a supplementary one.
    "drug_target": 0.9,
    "human_clinical": 1.0,
    # New (this task) — prototype placements, not OTP references (neither
    # source is OTP data at all). Both are supportive/contextual evidence
    # rather than direct causal-disease evidence, so both sit low —
    # explicitly reinforcing tissue_expression's "supportive context, not
    # a risk predictor" framing (see TISSUE_SPECIFICITY_SCORES above) by
    # NOT placing it anywhere near the translationally-advanced end of the
    # ladder. ppi_network sits just below pathway (0.5): conceptually
    # similar (mechanistic/functional context, not disease-causal
    # evidence) but STRING's confidence is probabilistic/computed rather
    # than Reactome's curated membership.
    "tissue_expression": 0.25,
    "ppi_network": 0.45,
}
