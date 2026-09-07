# Major Project Pipeline — Scoring Method & Reference at Each Stage

Design rule: every scoring mechanism traces to a specific Open Targets Platform (OTP) documentation page or peer-reviewed paper. Stages with no OTP equivalent are marked explicitly as your own original contribution.

| Pipeline stage | Scoring method used | Reference / link |
|---|---|---|
| **Disease / Research Question** | Normalized to disease ontology ID (EFO) | [OTP Associations docs](https://platform-docs.opentargets.org/associations) |
| **Candidate Targets** | Pulled via Open Targets target-disease associations | [OTP Platform — live site](https://platform.opentargets.org/) |
| **Multi-Source Evidence** | Retrieval per source (genetic, omics, biomarker, pathway, experimental, clinical) | [OTP Evidence docs](https://platform-docs.opentargets.org/evidence) |
| **Evidence Extraction** | NER + entity normalization to Ensembl gene ID / EFO disease ID | [OTP Evidence docs](https://platform-docs.opentargets.org/evidence) |
| **Evidence Normalization** | Structured fields: effect direction, size, population, assay | [OTP Evidence docs](https://platform-docs.opentargets.org/evidence) |
| **→ Genetic dimension** | Locus-to-Gene (L2G) score, evidence included only if L2G > 0.05 | [OTP Evidence docs](https://platform-docs.opentargets.org/evidence) · [Ghoussaini et al. 2021, *Nucleic Acids Research*](https://academic.oup.com/nar/article/49/D1/D1311/5921290) ([free full text, PMC](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7778936/)) |
| **→ Omics dimension** | Score = scaled p-value × (\|log2 fold change\| ÷ 10) × (percentile rank ÷ 100); significance requires \|log2FC\| > 1 and adjusted p ≤ 0.05 | [OTP Evidence docs — Expression Atlas](https://platform-docs.opentargets.org/evidence) |
| **→ Biomarker dimension** | ClinVar 2-step scoring: base score by clinical significance (0–0.9), + modifier by review confidence (+0 to +0.1) | [OTP Evidence docs — ClinVar](https://platform-docs.opentargets.org/evidence) |
| **→ Pathway dimension** | Reactome curated evidence = fixed score of 1.0 | [OTP Evidence docs — Reactome](https://platform-docs.opentargets.org/evidence) |
| **→ Experimental dimension** | IntOGen: scaled combined q-value (0.25 at q=0.1, 1.0 at q<1e-10); or CRISPR screens: linearized significance score | [OTP Evidence docs — IntOGen / CRISPR screens](https://platform-docs.opentargets.org/evidence) |
| **→ Human/Clinical dimension** | Clinical Precedence 2-step: score by trial phase (0.01 preclinical → 1.0 approval), then ×0.5 down-weight if trial stopped early for negative/safety reasons | [OTP Evidence docs — Clinical Precedence](https://platform-docs.opentargets.org/evidence) |
| **Evidence Verification** (LLM proposes → rules confirm) | Direct association (exact target-disease match) vs. indirect association (via EFO ontology descendants) — used to decide what evidence is comparable before confirming a contradiction | [OTP Associations docs — Ontological selection of evidence](https://platform-docs.opentargets.org/associations) |
| **Supporting + Contradictory Findings** | **Your own contribution — finalized below** | Extends OTP's direct/indirect logic and reuses OTP's standardized Direction of Effect field (GoF/LoF, Risk/Protective) as input |
| **Evidence Strength / Consistency / Maturity** | Harmonic sum: sort evidence descending, divide each by position², sum, normalize by ~1.644 (max theoretical harmonic sum) | [OTP Associations docs](https://platform-docs.opentargets.org/associations) |
| **Explainable Prioritization** | Data source weighting before combination (e.g. Europe PMC = 0.2, Expression Atlas = 0.2, IMPC = 0.2, most others = 1.0) + per-dimension score breakdown | [OTP Associations docs — Data source weights](https://platform-docs.opentargets.org/associations) · [Buniello et al. 2025, *Nucleic Acids Research*](https://academic.oup.com/nar/article/53/D1/D1467/7917960) |
| **Research Gap Typing** | Mechanistic / population / modality / validation / evidence-consistency gap taxonomy — Population-heterogeneity findings from the contradiction classifier feed directly into the Population Gap type, and Methodological disagreements feed into the Evidence-Consistency Gap type | **Your own contribution — OTP does not provide this** |
| **Evidence-Gap-Linked Investigation** | Suggestions mechanically tied to the specific gap type identified | **Your own contribution — OTP does not provide this** |
| **Scientist Review** | Final human-in-the-loop check before any decision is acted on | Standard practice, not OTP-specific |

---

## Supporting + Contradictory Findings — finalized specification

**Step 1 — reuse an existing OTP field, don't invent one.** Every piece of evidence already carries a Direction of Effect value (Gain of Function/Loss of Function on the target; Risk/Protective on the trait), standardized by OTP across sources. Use this field as the trigger: if two pieces of evidence for the same target-disease pair report the same direction, there is no contradiction of any kind — stop here.

**Step 2 — if direction differs, classify the type of disagreement using a strict decision tree, checked in this order:**

1. **Direct contradiction** — all 5 comparability fields match (tissue, disease subtype, population/ancestry, assay type, endpoint) and only the effect direction differs. This is the strictest category: a genuine conflict in the underlying science, not a data artifact.
2. **Population-heterogeneity** — tissue, assay, and endpoint match, but population/ancestry does **not** match (e.g. effect seen in a European cohort, absent or reversed in an East Asian cohort). Labeled explicitly as a "population-specific effect," not a contradiction — this is a finding, and it routes into the Population Gap research-gap type rather than penalizing the target's consistency score as heavily as a direct contradiction would.
3. **Methodological disagreement** — tissue, subtype, and population match, but assay type or endpoint definition differs (e.g. RNA-seq vs. qPCR, or different phenotype definitions). Routed into the Evidence-Consistency Gap category, not treated as a true biological conflict.
4. **Not comparable, unclassified** — if multiple fields differ simultaneously, don't force it into one of the three categories above. Flag it honestly as unclassified rather than overclaiming a clean classification.

**Step 3 — log a full traceable record for every classified pair** (this is what fulfills the "source IDs" requirement concretely):
- Source record ID for both pieces of evidence (e.g. PubMed ID, GWAS study accession, ClinVar RCV ID)
- The specific field values compared for both records: tissue, population, assay type, endpoint, disease subtype
- The Direction of Effect value for both records
- The final classification result (direct / population-heterogeneity / methodological / unclassified)

A reviewer should be able to click into any confirmed contradiction in your output and see exactly which two records conflicted, on which fields they matched or diverged, and why the classification landed where it did — not just a flag with no evidence trail.

**Step 4 — validate against known cases.** Before finalizing, run the classifier on 2–3 real, documented examples for your chosen disease: one genuine direct contradiction from the literature, one known population-specific genetic effect (common in GWAS literature — the same variant showing different effect sizes across ancestries), and one known assay-driven discrepancy. Confirm each lands in its expected bucket. This is your evidence the three-way taxonomy actually works on real data, not just that it sounds reasonable on a slide.

---

## Full citations (for your report's reference list)

**Ghoussaini, M. et al. (2021)** "Open Targets Genetics: systematic identification of trait-associated genes using large-scale genetics and functional genomics." *Nucleic Acids Research*, 49(D1), D1311–D1320. DOI: [10.1093/nar/gkaa840](https://academic.oup.com/nar/article/49/D1/D1311/5921290)
Free full text: [PMC7778936](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7778936/)

**Buniello, A. et al. (2025)** "Open Targets Platform: facilitating therapeutic hypotheses building in drug discovery." *Nucleic Acids Research*. [academic.oup.com/nar/article/53/D1/D1467/7917960](https://academic.oup.com/nar/article/53/D1/D1467/7917960)

**Open Targets Platform Documentation — Target–disease associations** (harmonic sum, data source weights, direct/indirect associations): [platform-docs.opentargets.org/associations](https://platform-docs.opentargets.org/associations)

**Open Targets Platform Documentation — Target–disease evidence** (per-source scoring tables: GWAS/L2G, Gene Burden, ClinVar, Clinical Precedence, Expression Atlas, IntOGen, CRISPR, IMPC, etc.): [platform-docs.opentargets.org/evidence](https://platform-docs.opentargets.org/evidence)

**Open Targets Community — scoring FAQ**: [community.opentargets.org/t/how-are-associations-scores-calculated-in-the-open-targets-platform/1113](https://community.opentargets.org/t/how-are-associations-scores-calculated-in-the-open-targets-platform/1113)

**Open Targets Platform — live site** (explore real scored examples): [platform.opentargets.org](https://platform.opentargets.org/)

**Open Targets GraphQL API** (pull scores programmatically): [api.platform.opentargets.org/api/v4/graphql](https://api.platform.opentargets.org/api/v4/graphql)

**Open Targets bulk data downloads**: [platform.opentargets.org/downloads](https://platform.opentargets.org/downloads)

---

## Note on Open Targets Genetics (OTG)

Open Targets Genetics was merged into the unified Open Targets Platform and fully deprecated on 9 July 2025. All genetics functionality (GWAS credible sets, L2G model) now lives inside the single Platform referenced above — you do not need to consult a separate OTG source.
