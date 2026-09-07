# Architecture Documentation — Index

Read in this order:

1. **01_final_architecture.md** — the authoritative pipeline architecture for both Major (ALS target prioritization) and Minor (drug displacement analysis) projects, incorporating all reviewer/mentor feedback. Start here.

2. **02_pipeline_scoring_with_references.md** — the Major project's pipeline stages mapped side-by-side to the exact scoring method and citation used at each stage, including the finalized contradiction-classification specification (source IDs, decision tree, validation approach).

3. **03_open_targets_scoring_reference.md** — deep-dive reference on Open Targets Platform's actual scoring methodology (harmonic sum, data source weights, per-evidence-type formulas), organized by what to build yourself vs. what to pull directly from their API.

4. **04_scoring_elements_needed.md** — a condensed checklist of exactly which OTP scoring elements apply to this project, each with its source citation and a build/adapt/pull-via-API action.

5. **05_build_blueprint_and_timeline.md** — the original build blueprint and phased plan for narrowing scope, tightening rigor (evidence-maturity rubric, contradiction detection, backtesting), and sequencing work within a limited timeline.

6. **06_evidence_heterogeneity_discovery.md** — a real discovery made during live API introspection: evidence source types (genetic/experimental/clinical/literature) don't share a uniform comparability schema, and the contradiction classifier was redesigned to be source-type-aware as a result. Read this before touching `contradiction_classifier.py` or writing the evidence-ingestion script.

## How this maps to the code
The `als_target_pipeline/` project folder is the implementation of Doc 1 and Doc 2's Major-project architecture, scoped to ALS with the 4 MVP dimensions (Genetic, Literature, Pathway, Human/Clinical). See that project's own `CLAUDE.md` for implementation-specific status and next steps.

The Minor project (drug displacement/confound analysis) architecture is documented in Doc 1 but has no code implementation yet.
