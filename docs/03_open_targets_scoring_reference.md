# Open Targets Scoring Reference — For Evidence Scoring Module

**Purpose of this doc:** extract only what you need from Open Targets Platform (OTP) documentation to build your evidence-scoring layer. Use this as your methodological reference, cited explicitly in your report — not reproduced as your own invention.

**Important context:** Open Targets Genetics (OTG) was merged into the Open Targets Platform and fully deprecated on 9 July 2025. You only need to study one system now — the unified Platform — not two.

---

## 1. The three levels of scoring (core concept to borrow)

OTP scores evidence at three levels, each built on top of the previous one:

```
Individual evidence score (per record, per data source)
              ↓
Data source association score (combines all evidence from ONE source, e.g. all GWAS evidence)
              ↓
Data type association score (combines all sources within a category, e.g. all "genetic association" sources)
              ↓
Overall association score (combines everything, across all data types)
```

**Why this matters for your project:** this three-level structure is directly reusable. Instead of your current flat "one evidence score per dimension," adopt this three-level pattern:
- Level 1: score each individual piece of evidence you retrieve (a paper, a GWAS hit, a trial result)
- Level 2: combine same-source evidence into a per-dimension score (your Genetic, Omics, Biomarker, Pathway, Experimental, Human/Clinical dimensions from the prior architecture)
- Level 3: combine dimension scores into an overall picture — but keep dimensions visible/separate as your reviewer's feedback already recommended, rather than forcing one number

## 2. The harmonic sum — the key mechanism to adopt

This is the single most important, reusable piece of OTP's method. Instead of a simple average or weighted sum, OTP combines multiple pieces of evidence using a **harmonic sum**, which rewards having several independent supporting pieces of evidence, but with steeply diminishing returns for each additional one.

**How it works, step by step:**

1. Sort all evidence scores for a given source in descending order. Assign each a position: 1st, 2nd, 3rd, etc.
2. Divide each score by its position squared, and sum the results:
   `harmonic sum = score₁/1² + score₂/2² + score₃/3² + ...`
3. Normalize by dividing by the maximum theoretical harmonic sum (calculated from an infinite vector of 1.0s, which converges to approximately 1.644), so the final score falls between 0 and 1.

**Worked example (from OTP docs) — evidence scores of 1.0, 0.9, 0.8:**
```
Step 1 (sorted):     1.0 → position 1,  0.9 → position 2,  0.8 → position 3
Step 2 (harmonic sum): 1.0/1² + 0.9/2² + 0.8/3² = 1.0 + 0.225 + 0.089 = 1.314
Step 3 (normalize):   1.314 / 1.644 ≈ 0.80
```

**Why adopt this instead of a simple average:** a simple average treats 3 pieces of weak evidence the same as 1 strong piece if the average works out equal. The harmonic sum instead says: your single best piece of evidence matters most, additional corroborating evidence adds confidence but with rapidly shrinking marginal value. This is defensible, published, and exactly the kind of "borrowed methodology" your mentor is asking for — cite it directly rather than re-deriving your own aggregation rule from scratch.

**Implementation note:** when combining scores across data *types* (not data sources), OTP adjusts the normalization constant based on how many sources exist in that type — so a data type with only one source isn't unfairly penalized. Replicate this adjustment if you're combining a variable number of evidence dimensions per target.

## 3. Data source weighting (what to borrow, what to adapt)

OTP applies a weight factor before combining data sources into a data-type or overall score:

| Data source | Weight factor |
|---|---|
| Europe PMC (literature) | 0.2 |
| Expression Atlas | 0.2 |
| IMPC (mouse phenotype) | 0.2 |
| Cancer Biomarkers | 0.5 |
| OTAR Projects | 0.5 |
| All other sources (most genetic/experimental sources) | 1.0 |

**What this tells you methodologically:** OTP deliberately down-weights literature-derived and lower-specificity evidence (0.2) relative to more direct/curated evidence sources (1.0). This is a defensible precedent for your own project: if you're pulling PubMed/literature evidence alongside more direct evidence (FAERS, ClinicalTrials.gov structured records, GWAS), it is methodologically justified to down-weight literature/text-mined evidence relative to structured, curated data.

**What to say in your report (not overclaim):** "We adopt OTP's precedent of down-weighting text-mined/literature evidence relative to structured evidence sources, using their published weight ratios as a starting reference, adjusted for our specific data source mix." Do not claim to replicate their exact weights unless you use their exact sources — your sources are different (FAERS/openFDA, ClinicalTrials.gov, SureChEMBL vs. their much larger source list).

## 4. Per-evidence-type scoring rules (borrow the pattern, adapt the specifics)

Before combination, OTP scores each *individual piece of evidence* using source-specific logic. Examples directly relevant to your project:

- **Clinical trial evidence**: scored first by clinical stage (a Phase 3 trial scores higher than Phase 1). Then, if a trial was stopped early, the score is down-weighted based on *why* it stopped — trials stopped for safety/negative-outcome reasons are down-weighted more than trials stopped for unrelated administrative reasons.
  → **Direct application to your minor project:** you already need to score ClinicalTrials.gov evidence for the Efficacy category. Adopt this exact two-step pattern: (1) base score by trial phase/completion status, (2) down-weight if stopped early, weighted by stop reason.

- **GWAS/genetic evidence**: aggregated from significant genome-wide association signals, now resolved through OTP's own Locus-to-Gene (L2G) machine learning model to link a genetic signal to the most likely causal gene.
  → **Application to your major:** you don't need to build your own variant-to-gene mapping — you can pull OTP's already-computed L2G-resolved gene assignments via their API rather than reimplementing this from raw GWAS data. This alone saves significant build time.

- **RNA expression evidence**: explicitly NOT propagated up the disease ontology hierarchy (i.e., not inherited from parent-disease terms to child-disease terms), specifically to avoid diluting scores with weak indirect signals.
  → **Application:** if your evidence dimensions inherit from broader diagnostic categories (e.g. "cancer" → "specific cancer subtype"), apply the same caution for weaker evidence types like raw expression data — don't let it inherit upward and inflate a specific target's score.

## 5. Direct vs. indirect associations (a concept worth adopting)

OTP distinguishes:
- **Direct association**: evidence specifically about your exact target-disease pair
- **Indirect association**: evidence about a related, more general or more specific disease (using disease ontology relationships), which may still be informative

**Application to your major:** if your chosen disease has a specific subtype (e.g. a specific cancer subtype within a broader cancer category), consider explicitly labeling evidence as direct (subtype-specific) vs. indirect (evidence from the broader disease category) rather than treating all evidence as equally direct. This is a "population/subtype gap" consideration that ties directly into your Research Gap Typing (Stage 8 in your finalized architecture).

## 6. Important caveats to state explicitly in your report (borrowed directly from OTP's own guidance)

OTP explicitly warns that its association scores are a ranking heuristic, not a confidence measure — a target scoring low simply because its disease is under-studied could still be the most promising lead. It also cautions that some data sources rely on predictions rather than confirmed relationships, so high scores from those sources should be treated cautiously rather than as certainty.

**Use this almost verbatim in your report** (paraphrased, not copied) as your own scoring caveat — it directly reinforces the "priority score is not a guarantee of success" framing you've already built into your project:

> "Consistent with the precedent set by Open Targets, our prioritization score should be interpreted as a ranking heuristic based on available evidence, not a confidence or success-probability score. Under-studied targets may score lower simply due to limited data availability, not because they are less promising."

## 7. What to actually build vs. what to pull directly from OTP's API

| Component | Build yourself | Pull from OTP API |
|---|---|---|
| Harmonic-sum aggregation logic | ✅ Implement this yourself (it's a simple, documented formula) | — |
| Data-source weighting scheme | ✅ Adapt their pattern to your specific sources | — |
| GWAS → causal gene mapping (L2G) | ❌ Don't rebuild this | ✅ Pull pre-computed L2G results via GraphQL API |
| Baseline overall association score for comparison | ❌ Don't rebuild their full score | ✅ Pull their computed score for your chosen disease/targets as a comparison baseline |
| Contradiction detection / evidence verification | ✅ This is your own contribution — OTP doesn't do this | — |
| Research gap typing | ✅ This is your own contribution — OTP doesn't do this | — |
| Individual evidence score per record (novel evidence you collect yourself, e.g. from your own literature pull) | ✅ Score using OTP's per-type rules as reference | — |

## 8. Where to access everything

- **Scoring methodology docs:** platform-docs.opentargets.org/associations (association scoring) and platform-docs.opentargets.org/evidence (per-source evidence scoring rules)
- **Community FAQ:** community.opentargets.org — search "How are associations scores calculated"
- **Peer-reviewed methods papers (cite these in your report):**
  - Ghoussaini et al. 2021, *Nucleic Acids Research* — original Open Targets Genetics/L2G methodology
  - Buniello et al. 2025, *Nucleic Acids Research*, "Open Targets Platform: facilitating therapeutic hypotheses building in drug discovery" — current unified Platform methodology
- **Live scored examples:** platform.opentargets.org — search any target/disease pair, open its Associations page, inspect the per-source score breakdown
- **Programmatic access:** GraphQL API at api.platform.opentargets.org/api/v4/graphql (browsable GraphiQL interface); bulk downloads at platform.opentargets.org/downloads

## 9. How to phrase this in your report (exact framing to use)

> "Rather than defining evidence weights arbitrarily, this project adopts the Open Targets Platform's published scoring methodology — specifically its harmonic-sum aggregation approach and its precedent for down-weighting literature-derived evidence relative to structured evidence — as a methodological reference. Where computationally feasible, we pull Open Targets' own pre-computed association scores (including Locus-to-Gene results) as a baseline for comparison. Our original contribution builds on top of this foundation: an agentic evidence-verification layer that proposes and confirms genuine contradictions across sources, an evidence-maturity and consistency assessment, and a typed research-gap classification system — none of which the Open Targets Platform itself provides."
