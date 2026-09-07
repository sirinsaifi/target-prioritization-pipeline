# Discovery: Evidence Source Heterogeneity & Source-Type-Aware Contradiction Classification

## What happened
While preparing to live-test the Open Targets Platform GraphQL API before writing the evidence-ingestion script, live schema introspection revealed that the original contradiction-classifier design assumed a uniform set of comparability fields (`tissue`, `disease_subtype`, `population`, `assay_type`, `endpoint`) existed across all evidence records. This assumption does not hold.

## What the introspection found
- **Genetic evidence** (`eva`, `uniprot_variants`, `gwas_credible_sets`) — dominant source type for SOD1/ALS, since ALS is substantially a rare-variant/Mendelian disease for this gene. None of the five original comparability fields exist. The real, usable fields are: `variant_id`, `clinicalSignificances` (ClinVar terms, e.g. "pathogenic"/"likely pathogenic"), and `allelicRequirements` (e.g. "Autosomal dominant inheritance") as the nearest population/inheritance-pattern proxy.
- **Experimental evidence** (`impc`) — carries a real, rich `phenotype` field, but NOT tissue or assay fields (see confirmed findings below — the original assumption that this source type "carries tissue-like fields" was checked empirically and does not hold for these 5 genes).
- **Clinical evidence** (`clinical_precedence`) — carries a real `intervention` field, but NOT population or endpoint fields (checked empirically across all 5 candidate genes — see below).
- **Literature evidence** (`europe_pmc`) — has no structured comparability fields at all. This is expected and correct, not a gap to fill.

### Confirmed: `impc` and `clinical_precedence` field mapping (previously open item, now resolved)

**Datasource ID confirmation.** The schema exposes no enum to validate `datasourceIds` against (it's a plain `[String!]`), and the schema's own `associationDatasources` introspection field returns an empty list on the live deployment, so it can't be used either. Confirmed empirically instead: querying all evidence for SOD1 vs. MONDO_0004976 with no datasource filter and grouping by the real `datasourceId`/`datatypeId` returned shows `clinical_precedence` is the only datasource tagged `datatypeId: "clinical"` — it is the correct, real ID, not a guess.

**`impc` (experimental):**
- `phenotype` -> `diseaseModelAssociatedModelPhenotypes { label }` (model-side) and `diseaseModelAssociatedHumanPhenotypes { label }` (human-side). Both are real and rich — e.g. one SOD1 mouse-model row lists 24 model phenotypes ("motor neuron degeneration", "decreased grip strength", "progressive muscle weakness", ...) and 15 human phenotypes ("Spastic paraparesis", "Fasciculations", ...).
- `tissue` -> **left null.** `cellType` and `biosamplesFromSource` are both null/empty on every SOD1 impc row. The closest non-null field, `biologicalModelGeneticBackground` (e.g. `"involves: C3H/HeH * C57BL/6J"`), is genetic background, not tissue — not used as a substitute.
- `assay_type` -> **left null.** `contrast`, `statisticalMethod`, `assessments` are all null/empty for SOD1's impc rows.

**`clinical_precedence` (human/clinical):**
- `intervention` -> `drugFromSource`. Real data, but casing is inconsistent across rows for the same drug (`"tofersen"` vs `"TOFERSEN"`) — needs case-normalization before use as a comparability key.
- `population` -> **left null.** Checked across all 5 candidate genes, not just SOD1: `ancestry`, `ancestryId`, `cohortDescription`, `cohortId`, `cohortPhenotypes`, `cohortShortName`, `studyCases` are null/empty on every single clinical_precedence row for every gene.
- `endpoint` -> **left null.** No field on this datasource carries a trial-endpoint concept with real data.
- The early-stop down-weight in `score_clinical_precedence()` (`stopped_early_for_negative_or_safety`) can never evaluate `True` from this dataset: `trialStopReasonCategories` and `trialWhyStopped` are empty/null on every row for every gene. Document this as a known limitation of the ingested data, not a bug in the down-weighting logic itself.

This is a stronger and more honest finding than "carries tissue/population-like fields" — the fields exist in OTP's schema in general, but are not populated for this specific disease/gene/datasource combination. The ingestion script must derive only `phenotype` (experimental) and `intervention` (clinical) for now; `tissue`, `assay_type`, `population`, `endpoint` stay null for all real ingested records, same as literature's fields do.

## Why this matters (and why it's not a reason to change the disease choice)
It would have been tempting to switch to a common, GWAS-heavy disease where population/tissue-style fields are more readily available. This was explicitly considered and rejected: changing the disease to fit the data model would mean changing the biological problem to avoid a modeling challenge, rather than solving the actual challenge. ALS remains the right choice — its evidence heterogeneity (genetic, functional, clinical, literature, each structured differently) is exactly the kind of real-world messiness the project's evidence-verification layer is meant to handle.

## Resolution: source-type-aware contradiction classification
Rather than forcing every evidence record into one comparability schema, the contradiction classifier (`app/core/verification/contradiction_classifier.py`) now:

1. Groups evidence into source-type categories: `genetic`, `experimental`, `clinical`, `literature` (see `app/config.py`'s `SOURCE_TYPE_BY_DATA_SOURCE` and `COMPARABILITY_FIELDS_BY_SOURCE_TYPE`).
2. Only classifies contradictions **within** the same source-type group — two records are only comparable if they belong to the same group, using the fields that genuinely apply to that group.
3. Returns an explicit `not_comparable_cross_type` result for cross-type pairs (e.g. a genetic pathogenicity claim vs. a clinical trial outcome), rather than forcing a comparison that wouldn't be scientifically meaningful. Cross-type contradiction detection is named as future work, not implemented — comparing a variant classification to a trial outcome isn't a clean field match and deserves its own design pass.
4. Returns `unclassified` for literature-vs-literature comparisons, since there is no structural basis for field-level comparison for that source type (a future direction here would be comparing extracted biological claims directly, rather than structured fields — noted as out of scope for the MVP).

## Why this is a strength, not a limitation
This discovery and its resolution are themselves part of the project's original contribution. The finding — that biological evidence cannot be treated as one uniform table, and that a naive contradiction classifier would either silently fail on missing fields or force meaningless comparisons — is a genuine methodological insight, not an implementation shortcut. State this explicitly in the final report: the evidence-verification layer's value lies precisely in handling this heterogeneity correctly rather than assuming it away.

## Open items
- ~~`impc` and `clinical_precedence` exact field names have not yet been introspected~~ RESOLVED — see confirmed mapping above. All 4 source types now have their real, empirically-checked field mapping documented before the ingestion script is written.
- ~~Null-handling rule for the "single field mismatch" categorization~~ RESOLVED. Real data turned out to be unable to stress-test this at all: checking `direction_on_trait` across all 5 ingested genes shows SOD1/C9orf72/TARDBP/FUS are 100% "Risk" and NEK1 has zero direction-labeled records — ClinVar (the dominant genetic source for these Mendelian ALS genes) only curates pathogenic-risk calls, so no real mixed-direction pair exists to compare, and `classify_contradiction`'s conflict branches (steps 2 onward) are structurally unreachable with this dataset. Had to use constructed test cases instead. Doing so surfaced a real bug: a pair with opposite direction where every applicable field was null on one side fell through to "zero mismatches -> direct_contradiction", which silently claimed "confirmed same context" when the truth was "no information about context at all". Fixed in `app/core/verification/contradiction_classifier.py`: direct_contradiction now requires at least one field CONFIRMED matched (both sides non-null and equal), not merely zero confirmed mismatches; the zero-matched-and-zero-mismatched case now correctly returns `unclassified`. Covered by 2 new regression tests. Re-ran the full pipeline against real data afterward — zero change in output, confirming the fixed branch truly is unreachable with this dataset rather than silently masking something.
- ~~`drugFromSource` casing inconsistency~~ RESOLVED — `scripts/ingest_evidence.py`'s `_build_clinical_fields()` lowercases `drugFromSource` before storing it as `intervention`, from its first version. Verified live: all of SOD1's `intervention` values collapse to the single real drug `"tofersen"` rather than splitting across casing variants.
