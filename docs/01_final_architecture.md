# Final Architecture v2 — Evidence Intelligence Suite

Design rule throughout: **deterministic modules compute the numbers; the agentic layer retrieves, orchestrates, and explains them.** Where literature is unstructured, the agent may *propose* candidates (e.g. possible contradictions) — but a deterministic rule layer always verifies before anything is presented as a finding.

---

# MAJOR — Evidence-Guided Target Prioritization & Research Gap Identification

**Scope decision:** demo in depth on one disease area. Architecture stays disease-agnostic; correctness is proven on one well-chosen case, not claimed broadly.

## Stage 0 — Input
`Disease / Research Question` → normalized to a disease ontology ID (MONDO/EFO) so every downstream source keys off the same identifier.

## Stage 1 — Candidate Target Generation
Pull candidates from Open Targets / GWAS Catalog / literature co-mention. Output: target list with provenance (which source surfaced each candidate).

## Stage 2 — Multi-Source Evidence Collection (deterministic retrieval)
Parallel pulls per candidate:
- Genetic: GWAS Catalog, ClinVar/OMIM (only where genuinely disease-causing/implicating, not treated as generic evidence), MR databases
- Omics/biomarker: expression, methylation, proteomics datasets
- Pathway/mechanistic: pathway databases
- Experimental: preclinical/public biomedical datasets
- Human/clinical: human validation data where available
- Literature: PubMed/PMC

Every record stored with source ID, field used, retrieval timestamp — the traceability backbone for every later claim.

## Stage 3 — Evidence Extraction & Normalization
NER + normalization converts raw records into structured fields (effect direction, effect size, population, sample size, assay type, tissue, disease subtype, endpoint). Nothing moves downstream unstructured.

## Stage 4 — Independent Evidence Dimensions (corrected structure)

Rather than one composite "evidence score," each dimension is scored **independently** — they are not naturally on the same scale and should not be pre-collapsed:

```
Candidate Target
      ↓
 ┌────┬────┬─────────┬────────┬──────────────┬─────────────────┐
 ↓    ↓    ↓         ↓        ↓              ↓
Genetic Omics Biomarker Pathway Experimental Human/Clinical
      ↓
Each dimension → its own evidence score
```

**Genetic Evidence Strength** (renamed from "tier," reframed as a prototype scale, not established science):
- Prototype weights: Mendelian/rare-variant evidence weighted highest, MR next, GWAS common-variant last — but stated explicitly in the report as: *"Evidence weights are defined for this prototype and would need validation against domain-expert assessment before any real-world use."*
- ClinVar/OMIM only counted where there is genuine disease-causing evidence implicating the specific gene/protein — not treated as generic supporting evidence.

**Omics / Biomarker Evidence** — scored on independent replication and effect consistency across datasets.

**Pathway/Mechanistic Evidence** — scored on pathway centrality and mechanistic plausibility, kept separate from genetic evidence.

**Experimental Evidence** — preclinical/knockout/functional data, scored on its own scale.

**Human/Clinical Evidence** — human validation data (not preclinical), scored separately as it carries different evidentiary weight than animal/cell models.

**Tissue specificity** — computed (GTEx/HPA expression ratio or tau score) but stated explicitly as a *supportive biological-context feature*, **not** a proxy for off-target risk: *"Tissue specificity can inform biological context; it is not treated as a direct measure of off-target risk, which depends on additional factors outside this system's current scope."*

## Stage 5 — Evidence Verification (hybrid contradiction detection — corrected)

```
Literature
   ↓
LLM/NLP proposes candidate conflicting claims
   ↓
Deterministic rule layer checks true comparability:
  same tissue? same disease subtype? same population?
  same assay? same endpoint? same experimental condition?
   ↓
Confirmed contradiction flag (only if truly comparable and conflicting)
```

This is a correction from a purely rule-only approach: unstructured literature needs the LLM to *surface* candidates, but only the deterministic comparability check can confirm a genuine contradiction versus an apparent one (e.g. opposite expression direction in different tissues is not a contradiction).

Each confirmed contradiction is logged with both source IDs and the specific conflicting claim.

## Stage 6 — Evidence Strength / Consistency / Maturity Assessment
Three distinct, separately reported metrics per target (not collapsed into one number):
- **Evidence Strength** — magnitude/quality of supporting evidence across dimensions
- **Evidence Consistency** — degree of agreement across independent sources (post-verification)
- **Evidence Maturity** — how far the evidence has progressed (preclinical-only vs. human-validated)

## Stage 7 — Target Prioritization (separated from evidence scoring — corrected)

Evidence scoring answers *"how strong is the evidence?"* Prioritization answers *"how attractive is this target given that evidence plus other criteria?"* These are kept explicitly separate:

```
Target X
Evidence Strength        86
Evidence Consistency     74
Evidence Maturity        61
Druggability              —   (future work; not scored in current build — see note below)
Competitive Opportunity   —   (future work; not scored in current build — see note below)
------------------------------
Priority Score            (computed from currently available dimensions, documented as partial)
```

**Scope note:** Druggability and competitive-opportunity scoring require structural/pocket data and patent-landscape data respectively, which sit outside this project's current data sources and timeline. They are named and defined in the report as planned future dimensions rather than implemented — this is stated explicitly to avoid overclaiming what the prototype currently does.

**Per-dimension score breakdown** (required, agent-generated from real sub-scores): e.g. "62% of this score's evidence weight came from genetic evidence, 20% from omics, 18% from pathway support."

**Formal definition of "priority" (required — put this in the report verbatim):**
> *Target priority = relative research priority based on the strength, consistency, maturity, and completeness of currently available evidence. It is not a prediction of clinical or commercial success.*

## Stage 8 — Research Gap Typing (extended taxonomy)
1. **Mechanistic gap** — target implicated, MOA unclear
2. **Population gap** — evidence exists in one ancestry/cohort only
3. **Modality gap** — druggable class, no compound attempted
4. **Validation gap** — only preclinical/animal evidence exists
5. **Evidence consistency gap** *(added)* — substantial evidence exists but is inconsistent across studies; distinct from simply having too little evidence

## Stage 9 — Investigation Suggestions (reframed — corrected)
Renamed from "agent-generated recommendations" to **evidence-gap-linked investigation suggestions** — tied mechanically to the specific gap type from Stage 8, not framed as the agent prescribing a research program:
- Population gap → suggests validation in an additional population/cohort
- Validation gap → suggests additional experimental/human validation
- Evidence consistency gap → suggests targeted replication study to resolve disagreement

## Agentic layer role (across all stages)
Understands the question → selects sources/tools → triggers retrieval → invokes deterministic scoring modules as tools → proposes candidate contradictions for the rule layer to verify → assembles the evidence profile → generates the explainable narrative and per-dimension breakdown, citing record IDs throughout.

## Validation (corrected terminology and scope)
**Case-based validation**, not "model validation": evaluate whether the framework reproduces the expected evidence profile and prioritization rationale for 3–5 deeply-documented known cases (one clinical success, one documented failure). Explicitly stated in the report: *this demonstrates plausibility on selected cases, not statistically validated accuracy.*

## Failure-mode documentation (in final report)
Sparse-evidence targets; population heterogeneity misclassified as contradiction before comparability checks; LLM narrative drift from underlying computed scores; unscored dimensions (druggability, competitive opportunity) limiting the completeness of the priority score.

## Final architecture diagram
```
Disease / Research Question
              ↓
       Candidate Targets
              ↓
    Multi-Source Evidence
              ↓
       Evidence Extraction
              ↓
    Evidence Normalization
              ↓
 ┌──────┬──────┬─────────┬────────┬──────────────┬──────────────┐
 ↓      ↓      ↓         ↓        ↓              ↓
Genetic Omics Biomarker Pathway Experimental  Human/Clinical
 └──────┴──────┴─────────┴────────┴──────────────┴──────────────┘
              ↓
   Evidence Verification (LLM proposes → rules confirm)
              ↓
  Supporting + Contradictory Findings
              ↓
 Evidence Strength / Consistency / Maturity
              ↓
      Target Prioritization
   (Evidence dims + placeholder Druggability/Competitive)
              ↓
      Research Gap Typing (5 types)
              ↓
   Evidence-Gap-Linked Investigation Suggestions
```

---

# MINOR — AI-Assisted Drug Displacement & Confound Analysis
*(unchanged from prior version — no reviewer corrections applied here)*

## Stage 0 — Input & Displacement Anchor
`Drug A → Drug B`, anchored to a hard displacement date: Drug A's usage-signal proxy drops within N months of Drug B's FDA approval/launch date.

## Stage 1 — Multi-Source Evidence Pull
FAERS/openFDA → Safety · ClinicalTrials.gov → Efficacy · Patents/SureChEMBL → Patent signal · PubMed/PMC → supporting context.

## Stage 2 — Category Scoring (deterministic decision tree)
- **Efficacy:** ≥N head-to-head trials showing statistically significant superiority (trial ID + endpoint cited)
- **Safety:** PRR/ROR for Drug A's adverse events before vs. after Drug B's rise, with chi-square/Fisher's exact significance test
- **Patent:** Drug A's patent expiry within a defined window of displacement date
- **Pragmatic:** default only if none of the above clear threshold

## Stage 3 — Evidence Fusion + Agentic Analysis
Agent aggregates the three deterministic scores, applies decision-tree logic, drafts explanation grounded to actual computed values.

## Stage 4 — Confound Checklist (explicit, all four tested and reported)
1. Both drugs got expanding indications simultaneously
2. A third drug entered the market at the same time
3. Black-box warning/recall on Drug A unrelated to Drug B
4. Formulary/pricing shift unrelated to clinical evidence

## Stage 5 — Confidence Scoring (published formula)
`confidence = (qualifying_trials × w1) + (PRR_magnitude × w2) + (patent_timing_match × w3)`, normalized to 100, weights documented.

## Stage 6 — Output
`Most Likely Reason` → `Confidence + Evidence` (source-linked) → `Confound Flag` (checklist results). Stretch goal: multi-reason output (e.g. "Primary: efficacy 62%, Secondary: safety 31%").

## Validation
Case-based backtest on 3–5 well-documented displacement cases (one efficacy-driven, one patent-driven, one safety-recall-driven).

## Non-goals (protect the timeline)
No proprietary prescription/sales data — public approval/trial dates as proxy. Cap backtest at 4–5 cases.

---

# Shared Engineering Notes

- **Backend:** FastAPI, one endpoint per deterministic module (per evidence dimension, decision rules, confound checks) — unit-tested independently before agent integration.
- **Storage:** SQL store, every evidence row carries source ID + retrieval timestamp.
- **Agent layer:** function-calling architecture — deterministic modules exposed as callable tools, never reimplemented as prompt logic.
- **Reporting/UI:** Streamlit, built last.
- **Docker:** containerize once pipeline is functionally stable.

# Report-writing checklist (say these explicitly, in these words)
- [ ] "Target priority = relative research priority based on strength, consistency, maturity, and completeness of currently available evidence — not a prediction of clinical success."
- [ ] "Genetic evidence weights are prototype values, to be validated against domain-expert assessment."
- [ ] "Tissue specificity is a supportive biological-context feature, not a direct measure of off-target risk."
- [ ] "This is case-based validation on selected known examples, not statistically validated model accuracy."
- [ ] "Druggability and competitive-opportunity scoring are defined as future work, not implemented in the current prototype."
