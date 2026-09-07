# Scoring Elements Needed for Your Project — Sourced from Open Targets Documentation

Every item below is taken directly from Open Targets Platform's published documentation, with the source cited. Use these as your methodological reference (cite them), and adapt the specific formulas to your own data sources where OTP's exact source doesn't match yours.

---

## A. Score aggregation logic (MAJOR — core mechanism, adopt as-is)

**1. The Harmonic Sum** — used to combine multiple evidence scores into one.

> "The Platform defines a data source association score by calculating a harmonic sum using the full vector of evidence scores... 1. Evidence sorted descending, assigned positional id. 2. Harmonic sum = sum of (score / position²). 3. Normalized by dividing by max theoretical harmonic sum (~1.644)."
— *Source: platform-docs.opentargets.org/associations*

**Use for:** combining multiple pieces of evidence within one of your dimensions (Genetic, Omics, Biomarker, etc.) into a single dimension score. This replaces a simple average.

**2. Data source weighting before combining into a type/overall score**

| Data source | Weight |
|---|---|
| Europe PMC | 0.2 |
| Expression Atlas | 0.2 |
| IMPC | 0.2 |
| Cancer Biomarkers | 0.5 |
| OTAR Projects | 0.5 |
| All other sources | 1.0 |
— *Source: platform-docs.opentargets.org/associations*

**Use for:** justifying why you down-weight literature-derived/text-mined evidence (your PubMed/PMC source) relative to structured evidence (FAERS, ClinicalTrials.gov, genetic databases) in both your major and minor.

**3. Scaling adjustment when a data type has few sources**

> "So that data types only featuring one data source... are not penalised, the maximum theoretical harmonic sum score is calculated based on a vector of as many ones as data sources are in the respective datatype."
— *Source: platform-docs.opentargets.org/associations*

**Use for:** if one of your evidence dimensions only has 1-2 sources feeding it, don't apply the same normalization constant as a dimension with 5 sources — adjust it per-dimension, exactly as OTP does.

---

## B. Per-evidence-type scoring rules (MAJOR — pick the ones matching your actual data sources)

**4. Genetic association (GWAS) — Locus-to-Gene (L2G) score**

> "GWAS association evidence is defined as any credible set in a GWAS trait associated with a gene with a Locus2Gene (L2G) > 0.05."
— *Source: platform-docs.opentargets.org/evidence*

**Use for:** your genetic evidence dimension. Rather than building your own variant-to-gene mapping, **pull L2G scores directly from the OTP API** for your candidate genes/disease — this is a pre-computed ML score you can use as-is (score > 0.05 threshold for inclusion).

**5. Gene Burden (rare variant) evidence**

> "Evidence scoring: Scaled p-value from 0.25 (p = 1e-7) to 1 (p < 1e-17)."
— *Source: platform-docs.opentargets.org/evidence*

**Use for:** if you incorporate rare-variant/exome data, adopt this exact p-value-to-score scaling logic (a clean, simple, defensible formula you can reimplement).

**6. ClinVar (germline) — 2-step scoring**

Step 1 — score by clinical significance:
| Clinical significance | Score |
|---|---|
| Benign / not provided | 0 |
| Conflicting / uncertain significance | 0.3 |
| Established risk allele / risk factor / affects | 0.5 |
| Likely pathogenic | 0.7 |
| Pathogenic / association / protective | 0.9 |

Step 2 — modifier by review confidence:
| Review status | Modifier |
|---|---|
| No assertion criteria | +0 |
| Criteria, single submitter | +0.02 |
| Multiple submitters, no conflicts | +0.05 |
| Reviewed by expert panel | +0.07 |
| Practice guideline | +0.1 |
— *Source: platform-docs.opentargets.org/evidence*

**Use for:** this is a directly reusable pattern — **base score by evidence strength, then a small additive modifier for how well-reviewed/validated the evidence is.** This exact 2-step structure (base score + confidence modifier) is the one I'd recommend you replicate for your own literature/genetic evidence scoring, since it's simple, published, and defensible.

**7. Clinical Precedence (clinical trial) evidence — 2-step scoring (directly relevant to your MINOR project too)**

Step 1 — score by clinical stage:
| Stage | Score |
|---|---|
| Preclinical | 0.01 |
| Phase I | 0.1 |
| Phase II | 0.2 |
| Phase III | 0.7 |
| Approval | 1.0 |

Step 2 — down-weight if stopped early:
| Reason to stop | Weight |
|---|---|
| Negative outcome | ×0.5 |
| Safety/side effects | ×0.5 |
— *Source: platform-docs.opentargets.org/evidence*

**Use for:** this is the single most directly transferable item to your **minor project's Efficacy scoring**. Instead of inventing your own trial-quality scoring, use this exact table: score ClinicalTrials.gov evidence by phase, then down-weight (×0.5) if the trial stopped early for negative/safety reasons. Cite this table directly.

**8. Gene2Phenotype / ClinGen — expert-curated confidence tiers**

| Confidence | Score |
|---|---|
| Limited | 0.01 |
| Moderate | 0.5 |
| Strong / Definitive | 1.0 |
— *Source: platform-docs.opentargets.org/evidence*

**Use for:** a simple 3-tier confidence pattern (limited/moderate/strong) you can apply to any curated evidence source you use where you have qualitative confidence labels but want a numeric score.

**9. Europe PMC literature co-occurrence scoring**

> "Score based on weighted document sections, sentence locations, and title for full text articles and abstracts... aggregated scores... normalised between 0 and 1."
— *Source: platform-docs.opentargets.org/evidence, citing Kafkas et al., 2017*

**Use for:** your PubMed/PMC evidence dimension. You don't need to build this from scratch — cite this method (Kafkas et al. 2017 confidence-scoring approach) as your reference for scoring literature co-occurrence strength, and note in your report that you use OTP's Europe PMC scores directly via API rather than reimplementing NER-based confidence scoring yourself (this saves significant build time).

**10. Expression/omics evidence (Expression Atlas)**

> "Scoring is the result of the product of: scaled p-value × absolute log2 fold change / 10 × percentile rank / 100."
Significance thresholds required: absolute log2 fold change > 1, adjusted p-value ≤ 0.05.
— *Source: platform-docs.opentargets.org/evidence*

**Use for:** your Omics/Biomarker dimension if you're working with differential expression data — this is a ready-made, statistically grounded formula (not just "strong/weak") you can adopt directly.

---

## C. Directly relevant to your MINOR project (Drug Displacement)

**11. Clinical Precedence scoring (same table as #7 above)** — use for your **Efficacy** category scoring in the minor project. Trial phase → score, negative/safety-stopped trials → down-weighted 0.5×. This is a ready-made, citable formula for exactly what you need.

**12. Down-weighting rationale for safety-related evidence**

The same "reason to stop" down-weighting logic (#7) is conceptually the inverse of what you need for your **Safety** category — where a safety-related stop is actually the *signal itself* (not something to down-weight). Note this distinction explicitly in your report: OTP down-weights safety-stopped trials for efficacy-evidence purposes, whereas your system should specifically flag/up-weight safety-related stoppage as a Safety-category signal. This shows you understood the source material well enough to adapt it correctly rather than copy it blindly.

---

## D. What to explicitly acknowledge you're NOT copying (cite, don't reproduce)

- Data type categorization scheme (Clinical / Genetic association / Somatic mutations / Affected Pathway / RNA expression / Animal model / Literature) — you can adopt this categorization as an organizing structure for your evidence dimensions, since it's a sensible, published taxonomy, but note it's OTP's structure, adapted for your source set.
- The full weighted formula combining all data types into one "overall association score" — you're deliberately keeping your dimensions separate per your reviewer's earlier feedback, not collapsing to one score like OTP does. State this explicitly as an intentional design difference: *"Unlike OTP's single overall association score, we retain dimension-level transparency by design, to support explainable gap analysis."*

---

## E. Summary table — what to build vs. cite vs. pull via API

| # | Item | Action |
|---|---|---|
| 1 | Harmonic sum aggregation | Build (simple formula, cite source) |
| 2 | Data source weighting | Adapt (your own sources, cite precedent) |
| 3 | Per-type normalization scaling | Build (cite source) |
| 4 | L2G genetic score | Pull via API (don't rebuild) |
| 5 | Gene burden p-value scaling | Build if used (cite table) |
| 6 | ClinVar 2-step scoring | Build as reusable pattern (cite table) |
| 7 | Clinical trial phase scoring | Build for minor project's Efficacy score (cite table) |
| 8 | Confidence-tier scoring | Build as reusable pattern (cite table) |
| 9 | Literature co-occurrence score | Pull via API where possible (cite Kafkas et al. 2017) |
| 10 | Expression/omics formula | Build if used (cite formula) |

**Full citation for your report:**
Buniello, A. et al. (2025) "Open Targets Platform: facilitating therapeutic hypotheses building in drug discovery," *Nucleic Acids Research*. DOI: 10.1093/nar/gkae1076 (check exact issue/DOI on publication page)
Ghoussaini, M. et al. (2021) "Open Targets Genetics: systematic identification of trait-associated genes using large-scale genetics and functional genomics," *Nucleic Acids Research* 49(D1):D1311-D1320. DOI: 10.1093/nar/gkaa840
