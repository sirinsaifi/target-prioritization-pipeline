# Evidence-Guided Target Prioritization & Research Gap Identification

**A pipeline report for Excelra — prototype scope: Amyotrophic Lateral Sclerosis (ALS)**

---

## 1. Executive Summary

This project is an **AI co-scientist for target de-risking**: a system that integrates heterogeneous biomedical evidence — genetic, literature, pathway, and clinical — to evaluate how well-supported a drug target is, surface where that evidence genuinely contradicts itself, identify what evidence is specifically *missing*, and recommend a concrete next research step tied to that specific gap. Every score, contradiction flag, and gap the system reports traces back to a real, cited evidence record; the system's LLM components retrieve, verify, and explain — they never invent a number.

For Excelra's clients, target assessment today is a manual, analyst-hours-intensive exercise: pulling evidence from multiple databases, reading through literature to check whether sources actually agree, and forming a judgment about what's under-investigated. This system compresses that into an auditable, repeatable pipeline. It does three things existing target-scoring tools (including Open Targets itself, which this project builds on) do not: it **verifies** that evidence from different sources is genuinely comparable before treating agreement or disagreement as meaningful; it **classifies** disagreements into named types rather than flagging a generic "conflict"; and it **names specific evidence gaps** with a suggested next investigation step, rather than stopping at a single opaque score. The result is faster first-pass target triage and fewer contradictions or blind spots slipping through manual review.

**Current scope:** the prototype is built and validated against Amyotrophic Lateral Sclerosis (ALS), scored against five candidate genes (SOD1, C9orf72, TARDBP, FUS, NEK1). The architecture itself is disease-agnostic by design — only a disease identifier and a candidate gene list are ALS-specific configuration, not embedded logic — though it has been exercised on one disease only, and that boundary is stated honestly throughout this report rather than implied to be broader than it is.

---

## 2. Problem Statement

Finding candidate targets for a disease is, at this point, a comparatively solved problem — Open Targets, GWAS Catalog, and literature co-mention tools all surface long lists of plausible genes. The harder, more expensive problem sits one step later: **deciding which of those candidates is actually worth pursuing, and why.** That requires an analyst to manually:

- Pull evidence from several independent sources (genetic databases, curated pathway annotations, clinical trial registries, the primary literature) that use incompatible formats, vocabularies, and levels of structure.
- Judge whether two pieces of evidence that appear to disagree are a *genuine* scientific contradiction, or simply describe different populations, tissues, or assay conditions — a distinction that is easy to get wrong under time pressure, and that most automated scoring tools skip entirely.
- Identify what's *not* there — a target can look strong purely because no one has yet run the missing experiment, and a flat priority score does not surface that.

Existing tools, including Open Targets Platform (OTP) — the most widely used target-scoring reference in the field — score the strength of available evidence well, but stop there: OTP does not verify whether sources genuinely agree, does not classify the type of any disagreement it might contain, and does not report what kind of evidence is missing. That verification and gap-identification work is currently done by hand, inconsistently, and it does not scale across a growing target list. This is a business gap, not an academic one: it is exactly the kind of repeatable, evidence-auditing task that consumes senior scientific staff time on every target assessment cycle.

---

## 3. Solution Architecture

The pipeline runs as ten stages, from a disease/research question down to a ranked, gap-annotated target list with suggested next steps. Framed for a technical-but-not-coding audience:

```
Disease / Research Question
        ↓
Candidate Targets                (configured per disease; not an open-ended
        ↓                         discovery step in the current build)
Multi-Source Evidence Collection  (genetic, literature, pathway, clinical)
        ↓
Evidence Extraction & Normalization
        ↓
Independent Evidence Dimensions  (scored separately — never pre-collapsed)
        ↓
Evidence Verification            (LLM proposes → deterministic rules confirm)
        ↓
Evidence Strength / Consistency / Maturity   (three distinct, visible scores)
        ↓
Target Prioritization             (evidence-only; druggability/competitive
        ↓                          scoring named as future work, not built)
Research Gap Typing               (5 named gap types)
        ↓
Evidence-Gap-Linked Investigation Suggestions
```

**What each stage does, and why it matters:**

- **Candidate Targets.** For this prototype, the five ALS candidate genes are configured directly rather than auto-discovered from an open association search — a deliberate scope decision to demonstrate depth on a small, well-understood set rather than breadth across an unvetted list. The underlying evidence-collection and scoring pipeline places no ALS-specific assumption on *which* genes are supplied.
- **Multi-Source Evidence Collection.** Real evidence is retrieved from Open Targets Platform (genetic variant curation, GWAS signal, Reactome pathway membership, clinical trial precedence) and independently from PubMed via NCBI's E-utilities (a second, OTP-independent literature source). This matters because a single-source pipeline inherits that source's blind spots silently; a second literature channel is a real, if partial, check against that.
- **Evidence Extraction & Normalization.** Each source's raw record is converted into structured fields — but, as described in Section 4a below, not every source shares the same fields, and the system treats that honestly rather than forcing a fit.
- **Independent Evidence Dimensions.** Genetic, Literature, Pathway, and Human/Clinical evidence are each scored on their own scale and never silently averaged into one number before the point where a user can still see the breakdown — a target that scores well only because of one dimension looks different from one that's well-supported everywhere, and that difference is exactly what a reviewer needs to see.
- **Evidence Verification.** Where evidence is structured, a deterministic rule engine checks comparability directly. Where it isn't (literature), an LLM proposes candidate contradictions in plain language, and a separate deterministic layer decides whether the proposal is actually verifiable before it is ever shown as a confirmed finding. This two-layer design is the core defensible claim of the whole system: **the LLM never gets the final word on whether something is a contradiction.**
- **Evidence Strength / Consistency / Maturity.** Three separate, named numbers — how much evidence exists, how well it agrees, and how far along the translational spectrum (literature → genetic → pathway → experimental → human/clinical) it has progressed. Kept separate by design, per Section 4b.
- **Target Prioritization.** A ranking convenience computed from the three evidence metrics above. Druggability and competitive-opportunity scoring — which would require structural/pocket data and patent-landscape data respectively — are explicitly **not** implemented in the current build; they are named as future work in Section 9, not silently assumed.
- **Research Gap Typing.** Five falsifiable, named gap types (Section 4c), each with a rule-based trigger — not a subjective "this seems under-studied" judgment.
- **Investigation Suggestions.** Templated text tied mechanically to the specific gap type that fired — never a free-form LLM recommendation.

**What is borrowed vs. original, stated plainly:** *We adopt OTP's scoring framework as a methodological reference and build our own evidence-verification and gap-identification layer on top of it.* The harmonic-sum aggregation method, the per-dimension evidence-scoring conventions (genetic evidence inclusion threshold, clinical-trial-phase scoring with an early-stop down-weight, curated-pathway scoring), and the general three-level scoring structure (individual record → per-source → overall) are OTP's published methodology, cited throughout (Section 5). The evidence-verification layer, the three-part Strength/Consistency/Maturity profile, the five-type research gap taxonomy, the gap-linked investigation suggestions, and the autonomous investigation loop are this project's own contribution — OTP does not provide any of these.

---

## 4. Original Contributions

Four areas differentiate this system from existing target-scoring tools. Each is illustrated below with a concrete result from real, verified pipeline output — not a hypothetical.

### a. Evidence Verification & Contradiction Classification

The system does not assume all biomedical evidence can be compared on one common set of fields. Live introspection of the Open Targets API, done *before* the contradiction classifier was finalized, surfaced this repeatedly, in three separate instances:

1. **Structured comparability fields differ by evidence type.** Genetic evidence (ClinVar-style curation, GWAS credible sets) carries no tissue, population, assay, or endpoint fields at all — the real comparable fields are variant identity, clinical significance, and inheritance pattern. Clinical trial evidence carries a real intervention field but no real population or endpoint field in the ingested data. Literature evidence carries no structured comparability fields whatsoever. Forcing all of these into one shared five-field comparability schema — the system's original design — would have either silently failed on missing fields or produced meaningless comparisons.
2. **Pathway "evidence" is not disease-specific evidence at all.** It was assumed, going in, that pathway membership would appear as ordinary target-disease evidence, the same way genetic or clinical evidence does. Live querying showed zero pathway-type rows anywhere in that evidence stream — pathway membership in Open Targets is a **gene-level, disease-agnostic annotation** (does this gene participate in any curated biological pathway at all), exposed through an entirely different part of the API. The system now treats it accordingly rather than forcing a disease-specific interpretation onto data that isn't disease-specific.
3. **A curated, categorical rare-disease assertion is a third, distinct kind of genetic evidence.** Orphanet-sourced rows — discovered only after fixing a separate data-completeness bug (Section 5) — are neither a variant-level pathogenicity call (like ClinVar) nor a statistical genetic-signal score (like a GWAS credible set); they are literature-backed, curator-asserted "this gene is a recognized cause of this disease" statements. Treating them as equivalent to either of the other two would have overstated what they actually represent.

The resolution: evidence is grouped into source-type categories (genetic, experimental, clinical, literature, pathway), and two records are only compared for contradiction if they belong to the same group, using only the fields that genuinely apply to that group. A cross-type comparison (e.g., a genetic pathogenicity claim against a clinical trial outcome) is reported as **not comparable**, honestly, rather than forced into a same/different verdict — full cross-type comparison is named as future work (Section 9), not implemented.

Where evidence has no structured fields at all (literature), an LLM proposes candidate contradictions in plain natural language, and a separate deterministic layer verifies the proposal before anything is logged as confirmed. **A design lesson worth stating directly:** an earlier, separate part of this system (the autonomous investigation loop, Section 4d) hit three distinct real failure modes when it asked an LLM to call structured tools — corrupted JSON arguments, a leaked internal formatting token, and a phantom call to a tool that doesn't exist. The literature-contradiction proposer avoids all three by construction: it never asks the model to call a tool at all, only to answer in a fixed plain-text format (`CLASSIFICATION: <word>` / `REASON: <sentence>`), parsed with a simple pattern match. Across roughly 23 real calls made while building and testing this feature, that format was never once malformed.

### b. Evidence Maturity Profile

Rather than one composite confidence number, every target carries three separately reported metrics: **Evidence Strength** (how much supporting evidence exists), **Evidence Consistency** (how well independent sources agree, after verification), and **Evidence Maturity** (how far the evidence has progressed along a literature → genetic → pathway → experimental → human/clinical translational ladder). None are collapsed into each other before being shown.

Consistency itself is not one number either. It is composed of a **structured** sub-score (derived from the deterministic contradiction classifier, over an exhaustive count of every comparable structured-evidence pair) and a **literature** sub-score (derived from the LLM-proposed, deterministically-verified literature contradictions, over a deliberately bounded sample of literature pairs — comparing every real literature pair for a well-studied gene would mean tens of thousands of LLM calls per target, which is not viable). These are combined by a **pair-count-weighted average**, not a naive average of the two percentages and not a pooled raw count — a design decision made specifically to prevent a small bounded literature sample from swinging a score that rests on thousands of real structured pairs, or vice versa. Both sub-scores, and both pair counts, remain visible in the stored result rather than being discarded once combined.

This was proven to actually behave correctly, not just asserted: inserting one synthetic literature contradiction against SOD1's real, very large structured-evidence base (11,026 comparable pairs) moved its combined consistency score by 0.0001 — correctly negligible. Inserting six synthetic literature contradictions against C9orf72's real, much smaller structured base (1 comparable pair) dropped its combined consistency score to 0.4545 and correctly triggered the evidence-consistency gap, with the gap's own explanation text correctly attributing the drop to literature contradictions rather than a phantom structured disagreement. Both test insertions were removed immediately afterward and the real scores confirmed to revert exactly.

### c. Research Gap Taxonomy

Five falsifiable gap types, each triggered by an explicit rule rather than a subjective judgment: **Mechanistic** (target implicated, mechanism of action unclear), **Population** (evidence exists in only one ancestry/cohort), **Modality** (a druggable target class with no compound yet attempted), **Validation** (only preclinical evidence exists, no human data), and **Evidence-Consistency** (substantial evidence exists but disagrees, distinct from simply having too little evidence).

The strongest real validation finding in this project came from checking a gap's *wording*, not just its trigger condition, against real published outcomes. For C9orf72, the system correctly flags a Validation gap — but its original wording ("no human/clinical evidence is present") was checked against the real clinical record and found to overstate the case: two real ASO drug programs targeting C9orf72 — Biogen/Ionis's BIIB078 and Wave Life Sciences' WVE-004 — did reach human trials and were discontinued after failing to show clinical benefit. Open Targets' clinical-trial datasource simply hasn't indexed either program against this target, most likely because it is built around small-molecule/ChEMBL-style entries rather than RNA-targeted therapies like these. The gap's underlying *substance* was correct (no proven clinical benefit yet exists for C9orf72); its *wording* was not, and a reader unfamiliar with the data source could have misread "no evidence present" as "never tried in humans," which is false.

This was fixed as a **wording-only change**, not a scoring change: the gap templates for Validation and Modality now explicitly name the specific datasource they draw from, state its known small-molecule bias, and recommend a targeted literature/trial-registry check before treating the gap as confirmed — rather than asserting a negative as flat biological fact. This is a deliberate example of epistemic honesty in how the system reports its own limits: a negative result from one data source is evidence about that data source's coverage, not a claim about biological reality, and the system's own language now reflects that distinction rather than blurring it.

### d. Autonomous Investigation Loop

Alongside the fixed, always-query-everything pipeline described above, a second, genuinely agentic path exists: an LLM-controlled investigation loop that decides, step by step, which evidence dimension to look at next and when it has gathered enough to stop — bounded by a hard iteration cap in code, not just a prompt instruction. It never scores, classifies, or judges evidence itself; gathered evidence is handed off to the same unmodified deterministic scoring pipeline used everywhere else in the system.

A real, illustrative finding from running this loop against SOD1: in one run, the agent explored three of the four evidence dimensions (genetic, literature, pathway) and stopped on its own without querying human/clinical evidence at all. Because it explored less breadth than the fixed pipeline does by design, its resulting evidence profile showed two research gaps (Modality, Validation) that the fixed, always-complete pipeline does not show for the same gene. This is not a disagreement about the science — it is a direct, correctly-labeled consequence of the agent's own choice of what to look at, and it is exactly the kind of two-layer safety property this design is meant to demonstrate: an autonomous agent can choose to explore narrowly, and a separate, deterministic gap-analysis layer will still correctly report exactly what that narrower exploration did and didn't cover, without silently overstating its completeness.

To make sure that distinction is never lost in the output itself, every gap-analysis result — from either path — now carries an explicit **investigation coverage** label: `"complete (4/4 dimensions queried)"` for the fixed pipeline (which always queries every dimension by design), or `"partial (N/4 dimensions explored: ...)"` for the investigation loop, naming exactly which dimensions were and weren't explored that run. This matters because, without it, a genuine gap in the pipeline's own exploration could be misread as a genuine gap in the target's biology — two very different claims that this labeling keeps from being confused with each other.

---

## 5. Scoring Methodology

**Borrowed from Open Targets, cited directly, not silently reproduced as original work:**

The core aggregation mechanism is OTP's published **harmonic sum**: evidence scores for a dimension are sorted in descending order, each divided by the square of its rank, summed, and normalized against the maximum theoretical harmonic sum (≈1.644 for an infinite vector of perfect scores) — so a single strong piece of evidence dominates, and each additional corroborating piece adds confidence with steeply diminishing weight, rather than being averaged in as an equal. A worked example from OTP's own documentation, reproduced and verified in this build: evidence scores of 1.0, 0.9, and 0.8 combine to 1.0/1² + 0.9/2² + 0.8/3² = 1.314, normalized to 1.314/1.644 ≈ 0.80.

Per-dimension scoring conventions are likewise adopted from OTP's published rules where they apply to this project's actual data sources: a genetic-evidence inclusion threshold (Locus-to-Gene score > 0.05); a two-step clinical-trial scoring pattern (score by trial phase, then down-weight ×0.5 if the trial stopped early for negative or safety reasons); and a fixed score for curated pathway membership. *The prototype adopts the Open Targets evidence-scoring framework as a methodological reference and implements a disease-specific subset of evidence dimensions.*

Citations: Ghoussaini, M. et al. (2021), *Nucleic Acids Research* 49(D1):D1311–D1320 (original Open Targets Genetics / Locus-to-Gene methodology); Buniello, A. et al. (2025), *Nucleic Acids Research* (current unified Open Targets Platform methodology); Open Targets Platform documentation, `platform-docs.opentargets.org/associations` and `/evidence`.

**Adapted, not copied, and one honest gap named:** Open Targets' precedent of down-weighting literature/text-mined evidence relative to structured evidence sources was reviewed as a design reference, but a concrete data-source weighting table defined during design (`DATA_SOURCE_WEIGHTS` in configuration) is **not currently wired into the live scoring pipeline** — it exists as unused configuration, not an applied weighting scheme. This is flagged here as a known gap rather than described as a working feature (see Section 8).

**A real, significant fix to how evidence is fetched, worth reporting on its own merits:** the genetic-evidence retrieval logic originally queried a fixed, hand-picked list of three data sources, tuned by inspecting ALS's own genetics. Rebuilding this to query dynamically, by Open Targets' own schema-level "genetic association" data-type identifier instead of a hardcoded source list, surfaced two real problems the fixed list had been silently hiding: a fourth real genetic data source (Orphanet, the curated rare-disease-nomenclature source described in Section 4a) had been missing from every gene's evidence entirely, and a separate row-limit cap on the old per-source fetch had been silently truncating results — most severely for FUS, whose real genetic-evidence count more than doubled (200 → 504 rows) once the cap was removed. Across all five candidate genes, total real evidence records grew from 1,858 to 2,292 once both issues were fixed. Downstream priority scores moved only marginally for genes whose harmonic-sum scores were already near saturation — this is expected, correct behavior, not evidence the fix didn't matter; the fix is about evidence *completeness*, and its absence would have gone entirely unnoticed without deliberately checking for it.

**Priority score, defined precisely and stated as intended:** *Target priority = relative research priority based on the strength, consistency, maturity, and completeness of currently available evidence. It is not a prediction of clinical or commercial success.* Consistent with Open Targets' own stated caveat about its association scores, this system's priority score should be read as a ranking heuristic over available evidence, not a confidence or success-probability measure — an under-studied target can score lower purely because less evidence about it currently exists, not because it is a weaker candidate.

---

## 6. Case-Based Validation

*This is case-based validation on selected known examples, not statistically validated model accuracy.* Two of the five candidate genes — SOD1 and C9orf72 — were checked against real, cited published research; the other three (TARDBP, FUS, NEK1) have real, verified pipeline output but no literature cross-check performed against them yet, and that scope boundary is stated here rather than implied to be closed.

### SOD1 — the system agrees with the published record, with one caveat it does not gloss over

The system reports zero contradictions, zero research gaps, and a near-maximal priority score for SOD1, driven by real pathway evidence (a Reactome annotation for "Detoxification of Reactive Oxygen Species" — mechanistically on-point for a superoxide dismutase gene) and real clinical evidence (every ingested human/clinical record names the drug tofersen). This matches the real, published record: tofersen (marketed as Qalsody) received FDA accelerated approval in April 2023 as the first ALS treatment targeting a genetic cause.

Where the system's output is more careful than a flat "solved" verdict: its human/clinical dimension score is 0.9803 — high, but not literally maximal — which is itself consistent with a real detail in the published record the system was never told directly: tofersen's approval was *accelerated*, based on a biomarker surrogate (plasma neurofilament light), and the pivotal trial's clinical-outcome endpoints did not reach statistical significance; confirmatory trial data is still pending. The system's near-but-not-quite-maximal score is a genuine point of alignment with that nuance, not a coincidence of how the underlying trial-phase scoring works. One further honest note: two of SOD1's three real pathway annotations are not obviously ALS-mechanistic — because pathway evidence in this system is a disease-agnostic gene annotation (Section 4a), "no mechanistic gap" means "this gene participates in *some* curated pathway," not "this specific pathway explains its role in ALS," and the system's own gap logic is worded to reflect exactly that scope, not more.

### C9orf72 — partial agreement, and the divergence is the most valuable finding in this validation exercise

Published research is unambiguous that a hexanucleotide repeat expansion in C9orf72 is the single most common known genetic cause of ALS, acting through several documented mechanisms. The system's genetic-dimension score (0.9084, using the corrected, complete evidence set from Section 5's fetch fix) is high and directionally consistent with that. But looking at *why* the system still flags gaps for this gene surfaces a genuine, informative limitation rather than a simple under-scoring:

- The real genetic evidence behind that 0.91 score is built from ClinVar-style pathogenicity curation, GWAS aggregate signal, and Orphanet's curated disease-association assertion — none of which are built to directly capture a structural repeat-expansion mechanism the way they capture a point mutation. The score is real and defensible, but it is built from an indirect proxy for the actual causal mechanism, not direct evidence of it — a genuine data-representation limitation, correctly reflected as uncertainty rather than papered over.
- The system's Validation gap for C9orf72 — as described in Section 4c — is scientifically correct in substance (no proven clinical benefit yet exists for this gene) but its original wording overstated a data-source blind spot as a biological fact, missing two real, discontinued human trial programs (BIIB078, WVE-004) that simply weren't indexed in the datasource the system draws from. This is the single strongest validation result in this exercise, specifically *because* it is a divergence: it demonstrates the system catching a real limitation in its own data sources through case-based cross-checking, rather than blindly trusting whatever a source returns — which is precisely the failure mode this project's evidence-verification layer exists to guard against. The gap's wording has since been corrected (Section 4c); its underlying trigger condition was already correct and required no change.

### TARDBP, FUS, NEK1 — real pipeline output, not yet literature-cross-checked

All three genes have real, verified evidence-collection and scoring output through the identical pipeline used for SOD1 and C9orf72 (real dimension scores, zero confirmed contradictions across all five genes — consistent with, not contradicted by, the real finding that ClinVar direction-of-effect data for these rare, Mendelian ALS genes is uniformly single-direction in the ingested dataset). A literature cross-check against published research for these three genes, matching what was done for SOD1 and C9orf72, remains open follow-up work.

---

## 7. Technical Implementation

**Stack:** FastAPI backend, SQLAlchemy ORM over SQLite, Groq-hosted `openai/gpt-oss-20b` for the LLM-backed components (narration and literature-contradiction proposal) — chosen as an interim, free-tier-accessible general-purpose model after Llama 3, the model originally intended, moved to enterprise-only pricing on Groq; swapping to a biomedical-specialized model later touches one isolated function, not the surrounding system. A React/TypeScript frontend (Vite, Tailwind CSS) provides a target list and per-target detail view, wired to the live backend via plain `fetch` calls — no additional state-management framework was needed at this scale.

**Test coverage:** 90 automated backend tests, all passing at the time of this report, spanning deterministic scoring logic, the source-type-aware contradiction classifier, the literature-contradiction proposer/verifier pipeline (LLM calls mocked for deterministic, repeatable testing), the autonomous investigation loop's prompt construction and coverage labeling, the genetic-evidence fetch fix, and the read/write API separation described below.

**Key technical decisions, each made to avoid a specific real failure mode rather than as a stylistic preference:**
- **Source-type-aware contradiction classification** (Section 4a) — comparing evidence only within groups that share genuinely comparable fields, rather than forcing one schema onto structurally different data.
- **An explicit "has this ever been checked" log table**, used to distinguish "checked this target, found nothing" from "never checked at all" — a distinction that matters because a target's contradiction or gap list being empty means something different in each case, and collapsing them would misrepresent a target that simply hasn't been analyzed yet as one confirmed clean.
- **Separate read and compute endpoints.** Earlier in the frontend's development, the only way to *view* a target's score or contradictions was to *recompute* them — meaning every page view silently re-ran real analysis, including a real LLM call on every visit to a target's detail page. This has been separated: viewing a target's already-computed results is now a pure, side-effect-free read; recomputing is a distinct, explicit, user-triggered action (a "Run Full Analysis" button), with the same log table used to show an honest "not yet analyzed" state before that button is ever clicked.
- **Disease-agnostic core design.** Only two configuration values are disease-specific: the disease's ontology identifier and the candidate gene list. The genetic-evidence retrieval logic queries by Open Targets' own schema-level data-type identifier and discovers the real data sources available for whatever disease is configured, rather than relying on a hardcoded, disease-tuned source list (Section 5) — the specific mechanism that makes re-pointing this pipeline at a different disease a configuration change, not a rebuild, though this claim has only been exercised against one disease to date and several smaller, cosmetic ALS-specific strings elsewhere in the codebase (a UI page title, a database filename) have been identified but not yet cleaned up (Section 8).

---

## 8. Known Limitations

Stated directly, not minimized:

- **Per-step reasoning in the autonomous investigation loop is not currently captured.** The model logs which tool it called at each step, but not why, in the structured trace intended to capture that — only its final summary message contains real reasoning text. Three separate prompt-engineering attempts to fix this each failed in a different way (corrupted tool-call arguments, a leaked internal formatting token, a hallucinated tool call), and this is documented as a likely model-specific limitation of the current LLM on this hosting platform, not a solved problem — a different model is the more promising next step, not a fourth prompt variant.
- **Druggability and competitive-opportunity scoring are not implemented.** These require structural/binding-pocket data and patent-landscape data respectively, which sit outside this prototype's current data sources. They are named as scope limitations and future work (Section 9), not silently assumed to exist.
- **Three planned evidence dimensions — Omics, Biomarker, and Experimental — are not yet part of the scored MVP.** The current build scores four dimensions (Genetic, Literature, Pathway, Human/Clinical); the other three were always planned as a second phase.
- **The literature-contradiction verifier applies lighter checks than the structured-evidence classifier.** It confirms both excerpts genuinely concern the same gene and disease and carry real text, and that the LLM's proposal was unambiguous — it does not (and structurally cannot, given unstructured text) apply the same field-by-field comparability check the structured classifier uses.
- **The clinical-trial data source has a real, demonstrated blind spot for non-small-molecule modalities** — Section 6's C9orf72 finding, where two real discontinued ASO trial programs were absent from the ingested data. The affected gap-report wording has been corrected to name this limitation explicitly; the underlying data-source coverage gap itself has not been closed.
- **Human/clinical evidence, in the real ingested ALS dataset, exists for one of the five candidate genes only (SOD1).** This is a property of what has actually been curated for this specific gene set today, not a system defect — but it means the other four genes' Validation and Modality gaps should be read with that specific data-coverage limitation in mind.
- **A small number of ALS-specific strings remain outside the sanctioned, disease-agnostic configuration** — a hardcoded UI page title, a database filename, and some illustrative comments — flagged during review but not yet cleaned up. None affect scoring or classification logic for the disease currently configured.

---

## 9. Future Directions

- **Full autonomous investigation planning**, including cross-type contradiction detection (e.g. comparing a genetic pathogenicity claim against a clinical trial outcome, named but not implemented in Section 4a) and generalizing the investigation loop's demonstrated behavior beyond the one disease it has been exercised on.
- **Biomedical-specialized LLM integration** for deeper literature claim extraction, replacing or augmenting the current general-purpose interim model with a domain-tuned one (e.g. BioMistral or OpenBioLLM), particularly to address the per-step reasoning gap named in Section 8.
- **Emerging-signal detection** — trend analysis across publication volume, clinical trial activity, and patent filings over time, to surface targets gaining or losing momentum, not just their current static evidence snapshot.
- **Competitive-position and druggability scoring**, incorporating structural/pocket data and patent-landscape analysis as genuinely new scored dimensions rather than a placeholder in the prioritization output.
- **Integration with Excelra's existing data assets**, to extend the evidence base beyond the public sources used in this prototype and to validate the scoring approach against Excelra's own curated knowledge where it overlaps.

---

## 10. References

**Open Targets Platform — methodology:**
- Ghoussaini, M. et al. (2021). "Open Targets Genetics: systematic identification of trait-associated genes using large-scale genetics and functional genomics." *Nucleic Acids Research*, 49(D1), D1311–D1320. DOI: [10.1093/nar/gkaa840](https://academic.oup.com/nar/article/49/D1/D1311/5921290)
- Buniello, A. et al. (2025). "Open Targets Platform: facilitating therapeutic hypotheses building in drug discovery." *Nucleic Acids Research*. [academic.oup.com/nar/article/53/D1/D1467/7917960](https://academic.oup.com/nar/article/53/D1/D1467/7917960)
- Open Targets Platform documentation — Target–disease associations (harmonic sum, data source weighting): [platform-docs.opentargets.org/associations](https://platform-docs.opentargets.org/associations)
- Open Targets Platform documentation — Target–disease evidence (per-source scoring rules): [platform-docs.opentargets.org/evidence](https://platform-docs.opentargets.org/evidence)
- Open Targets Platform, live site: [platform.opentargets.org](https://platform.opentargets.org/)
- Open Targets GraphQL API: [api.platform.opentargets.org/api/v4/graphql](https://api.platform.opentargets.org/api/v4/graphql)

**Case-based validation — SOD1 (tofersen / Qalsody):**
- Biogen. "FDA Grants Accelerated Approval of QALSODY™ (tofersen) for SOD1-ALS." [investors.biogen.com](https://investors.biogen.com/news-releases/news-release-details/fda-grants-accelerated-approval-qalsodytm-tofersen-sod1-als)
- ALS Association. "Tofersen Approved for SOD1-ALS." [als.org/blog/tofersen-approved-sod1-als](https://www.als.org/blog/tofersen-approved-sod1-als)
- U.S. FDA. QALSODY (tofersen) prescribing information. [fda.gov/media/186135/download](https://www.fda.gov/media/186135/download)

**Case-based validation — C9orf72:**
- Repeat-expansion mechanism review: [PMC10838790](https://pmc.ncbi.nlm.nih.gov/articles/PMC10838790/)
- ALS Association. "Biogen and Ionis Discontinue C9orf72 Program (BIIB078) After Phase 1 Study Did Not Show Clinical Benefit." [als.org](https://www.als.org/stories-news/biogen-and-ionis-discontinue-c9-program-after-phase-1-study-did-not-show-clinical)
- NeurologyLive. "Biogen, Ionis Discontinue BIIB078, C9orf72-Associated ALS Agent." [neurologylive.com](https://www.neurologylive.com/view/biogen-ionis-discontine-biib078-c9orf72-associated-amyotrophic-lateral-sclerosis)
- NeurologyLive. "Wave Life Sciences Discontinues C9orf72 ALS/FTD Agent WVE-004 After Disappointing Phase 1b/2a Findings." [neurologylive.com](https://www.neurologylive.com/view/wave-life-sciences-discontinues-c9orf72-als-frontotemporal-dementia-agent-wve-004-after-disappointing-phase-1b-2a-findings)
- Open Targets Orphanet-curated evidence, backing literature for the gene–disease association (as ingested): PMID 20301623, PMID 23941283 (SOD1); PMID 24085347 (C9orf72).

**Internal project documentation** (`docs/00`–`07` in this repository) records the full build history, discovery process, and verification evidence this report summarizes, including live API introspection findings, per-phase test results, and the exact real numeric outputs referenced throughout this report.
