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
}

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
    "hpa": "tissue_expression",
    "string": "ppi_network",
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
