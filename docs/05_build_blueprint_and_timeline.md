# Build Blueprint: Evidence Intelligence Suite

**Major:** Evidence-Guided Target Prioritization & Research Gap Identification
**Minor:** AI-Assisted Drug Displacement & Confound Analysis

**Design philosophy:** Every score, flag, or "confidence" number in both systems must trace back to a computed value or an explicit rule — never an LLM's unsupported judgment call. The LLM's job is to *orchestrate, retrieve, and explain* — not to *invent numbers*. This is the single thing that will make your projects stand out from typical "LLM summarizes some papers" student work.

---

## PART 1 — MAJOR: Target Prioritization & Research Gap Identification

### 1.1 Core architecture (keep as designed)
Disease/Question → Candidate Targets → Multi-Source Evidence Collection → Evidence Extraction & Normalization → Supporting/Contradictory Analysis → Evidence Strength & Maturity → Explainable Prioritization → Research Gap Identification → Further Investigation Areas

### 1.2 What needs a real formula (not an LLM guess)

**Evidence Maturity Score** — build a weighted rubric, e.g.:
| Evidence type | Points |
|---|---|
| Genetic association (GWAS, strong effect size / low p-value tier) | 30 |
| Independent replication (2+ sources agree) | 20 |
| Human validation data (clinical/tissue-level, not just cell line) | 25 |
| Pathway/mechanistic support | 15 |
| Preclinical-only support | 10 |

Normalize to 0–100. Publish this table in your report — it's the difference between "explainable" and "an LLM said so."

**Contradiction Detection** — define programmatically before the LLM touches it:
- Two sources reporting opposite direction-of-effect for the same target-disease pair
- A biomarker validated in one study, refuted in another
- Log which two records conflicted and on what specific claim — don't let the LLM summarize this away

**Source-to-claim traceability** — every claim in the final report must carry a record ID (PubMed ID, dataset accession, etc.) it was pulled from. If you can't point to the exact source behind a sentence in your output, that sentence shouldn't exist.

### 1.3 Validation (this is what will make graders believe you)
Pick 3–5 targets with **known real-world outcomes** (one that succeeded in clinical development, one that failed for documented reasons). Run your pipeline retrospectively. If it correctly flags the failure as "low evidence maturity" and the success as "high priority," that's concrete, falsifiable proof your scoring works — put this front and center in your defense, not buried in an appendix.

### 1.4 Failure-mode section (add to report)
Explicitly name where the system can be wrong: sparse-evidence targets, sources disagreeing due to different disease subtypes (not a true contradiction), LLM misclassification risk. This is what separates a mature project from an overconfident demo.

### 1.5 What to say out loud in your defense
"The LLM never invents an evidence-maturity score — it applies a documented weighted rubric. The LLM never decides something is contradictory — it applies explicit contradiction rules and reports the specific conflicting records. The LLM's job is retrieval orchestration and narrative synthesis, grounded to source IDs at every step."

---

## PART 2 — MINOR: Drug Displacement & Confound Analysis

### 2.1 Core architecture (keep as designed)
Drug A → Drug B → FAERS/Clinical Trials/Patents (parallel evidence pull) → Evidence Fusion + Agentic Analysis → Category Classification (Safety/Efficacy/Patent/Pragmatic) → Most Likely Reason → Confidence + Evidence → Confound Flag

### 2.2 What needs a real formula (not an LLM guess)

**Anchor "displacement" to a hard date** — e.g., Drug A's usage signal drops within N months of Drug B's approval/launch date (FDA approval date as the trigger).

**Turn the 4 categories into a decision tree:**
- Efficacy → ≥N head-to-head trials showing statistically significant superiority (cite trial ID + endpoint)
- Safety → PRR or ROR (Proportional/Reporting Odds Ratio) for Drug A's adverse events, before vs. after Drug B's rise, above a defined threshold — run a chi-square or Fisher's exact test for significance, not just the raw ratio
- Patent → Drug A's patent expiry falls within a defined window of the displacement date
- Pragmatic → default only when none of the above three clear their bar

**Confound checklist** (test each explicitly, report which were ruled out):
1. Both drugs got expanded indications around the same time
2. A third drug entered the market simultaneously
3. Black-box warning/recall on Drug A unrelated to Drug B
4. Formulary/pricing shift unrelated to clinical evidence

**Confidence formula** — weighted sum, e.g.:
`confidence = (qualifying_trials × w1) + (PRR_magnitude × w2) + (patent_timing_match × w3)`, normalized to 100. Publish the formula and weights.

### 2.3 Stretch goal (only if time allows)
Allow multi-reason output: "Primary: efficacy (62%), Secondary: safety (31%)" instead of forcing one label — real-world displacement is often multi-causal, and this is more honest and more sophisticated than a single bucket.

### 2.4 Validation
Backtest on 3–5 well-documented real displacement cases (a clear efficacy-driven case, a clear patent-expiry case, a clear safety-recall case). Show the pipeline recovers the known, publicly documented reason.

### 2.5 What NOT to do (diminishing returns)
- Don't chase proprietary prescription/market-share data — FDA approval date + trial publication date as a displacement proxy is fine
- Don't add more than 4–5 backtest cases
- Don't over-invest here relative to the major — this project carries less grading weight

---

## PART 3 — What "standing out" actually means here

The differentiator between your project and a typical "LLM reads some PubMed abstracts and writes a summary" project is this exact pattern, repeated everywhere:

> **Computed/rule-based number** (evidence maturity score, PRR, contradiction flag) **→ LLM explains it in plain English, grounded to the source record.**

Never the reverse (LLM invents the number, then explains its own invention). This is also precisely what makes Sanjana's structural-biology project feel rigorous — her pocket volumes and TM-align scores exist independent of any LLM. Give your evidence-scoring system the same backbone, and your pipeline is arguably *more* impressive because it demonstrates you can build a trustworthy agentic reasoning system, which is a harder and more current skill than a fixed structural-biology pipeline.

## PART 4 — Build order (suggested)

1. Data ingestion + normalization layer for all sources (PubMed, FAERS/openFDA, ClinicalTrials.gov, patents/SureChEMBL)
2. Deterministic scoring modules first (evidence maturity rubric, PRR/ROR calculator, contradiction rules) — get these working and tested on real data *before* touching the LLM
3. Agent orchestration layer that calls the deterministic modules as tools and explains their outputs
4. Source-traceability layer (record ID → claim mapping)
5. Backtest suite against known cases
6. Failure-mode documentation
7. UI/report generation (Streamlit) last — it's the least risky part
