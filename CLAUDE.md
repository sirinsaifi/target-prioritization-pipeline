# Project Brief for Claude Code

## What this project is
Prototype: **Evidence-Guided Target Prioritization & Research Gap Identification**, scoped to Amyotrophic Lateral Sclerosis (ALS). Given a disease, it collects multi-source biomedical evidence for candidate genes, scores it using a methodology referenced from the Open Targets Platform (OTP), verifies whether evidence sources genuinely agree or conflict, assesses evidence maturity, and identifies specific research gaps with linked investigation suggestions.

This is a student major project. A companion minor project (drug displacement/confound analysis) exists as a separate scope — not in this codebase yet.

## Core design principle (do not violate)
**Deterministic modules compute every number. The agentic/LLM layer only retrieves, orchestrates, and explains.** The LLM must never originate a score, weight, or threshold. Where an LLM is used (e.g. proposing candidate contradictions from free-text literature), a deterministic rule layer always verifies before anything is presented as a confirmed finding.

## Current status
A working skeleton exists (see file tree below). It has been tested and confirmed working:
- FastAPI app boots successfully
- Database initializes and seeds 5 candidate targets
- Harmonic sum scoring tested against OTP's own worked example (matches ~0.80)
- Contradiction classifier tested against all categories, **now source-type-aware** (see discovery below) — 11/11 pytest unit tests pass
- Gap taxonomy tested — all 5 gap types trigger/suppress correctly
- Real evidence ingested from the live OTP API for all 5 candidate genes — 1,750 `EvidenceRecord` rows (`scripts/ingest_evidence.py`)
- Contradiction classifier, scoring (Strength/Consistency/Maturity), and gap analysis all run end-to-end against real evidence for all 5 targets
- Agent orchestration layer (template-narrator version) live at `GET /narrative/target/{id}` — 19/19 pytest unit tests pass
- Streamlit UI live (`streamlit run streamlit_app.py`), verified end-to-end against real data in a browser
- Second, independent literature source live (PubMed via NCBI E-utilities, `app/ingestion/literature_client.py`) — 1,850 total evidence records, 21/21 pytest unit tests pass
- Docker Compose added for both services (`api` + `ui`) — written and YAML-validated, but NOT run end-to-end (Docker isn't installed in this dev environment; see item 7 caveat below)
- `python-dotenv` wired into `app/main.py` (loads `.env` for `GROQ_API_KEY`) — **a real Groq key now works in this environment.** Real (non-mocked) LLM calls verified live: narration (`GET /narration/target/1`) and the new autonomous investigation loop (3 real runs for SOD1) both produced grounded, real output — see full write-ups below.
- Autonomous investigation loop built and run live 3x for SOD1 — the one genuinely agentic component in this codebase (LLM controls sequencing, not just narration). See "Autonomous investigation loop" section below for the full comparison and two honest findings.
- Real LLM-backed narration layer built: `app/core/narration/agent_narrator.py` + `GET /narration/target/{id}`. Makes an actual LLM API call (not a template), grounded strictly in `PriorityScore`/`ContradictionLog`/`GapRecord` — see full writeup below. **Provider: Groq (`openai/gpt-oss-20b`), an interim, deliberately-not-final choice — see "LLM provider choice" note below.** **No `GROQ_API_KEY` exists anywhere in this environment** (confirmed by search), so the real LLM call has NOT been exercised live — verified instead via: 6 mocked unit tests (27/27 total pass) proving the grounding-data assembly and prompt construction are correct, plus a live, unmocked run against real SOD1 data confirming the function (a) fetches the actual stored values correctly, (b) builds the exact real prompt correctly, and (c) fails loudly with a clear, actionable RuntimeError instead of fabricating output when no key is present. **A real generated narrative still needs to be shown and sanity-checked once a key is available — that verification step is not done.**

### LLM provider choice for narration — interim, not final
The narration layer (`app/core/narration/agent_narrator.py`) currently calls **Groq's `openai/gpt-oss-20b`**, not Llama 3 as first requested. Reason, confirmed live against `console.groq.com/docs` at the time of this change: Groq deprecated `llama-3.1-8b-instant` and `llama-3.3-70b-versatile` to Enterprise-only pricing in June 2026 — both model IDs still resolve but require a committed-spend contract, so neither is usable on this project's free/developer-tier key. `openai/gpt-oss-20b` is the closest available free-tier general-purpose substitute (confirmed free-tier accessible, 30 RPM / 1K RPD / 8K TPM — generous enough for this project's per-target, on-demand usage). This is explicitly a **general-purpose interim choice** — swapping in (or adding alongside) a biomedical-specialized model, e.g. **BioMistral or OpenBioLLM via HuggingFace**, is a planned next step, not urgent right now. `_call_llm()` is the single isolated function that would need to change again for that swap — same pattern used to go from Anthropic to Groq, `fetch_grounding_data()`/`build_prompt()`/the no-invention system prompt all stay untouched regardless of provider.
- **Bug caught live while verifying the above:** the route wrapped `generate_target_narrative()` with no exception handling, so the expected-and-correct RuntimeError (no API key) surfaced through the actual HTTP server as a bare 500 with a stack trace, not the clean error the function was designed to produce. Fixed in `app/api/routes/narration.py`: catches `RuntimeError` and re-raises as `HTTPException(503, ...)` with the same message. (A red herring along the way: the first `--reload` cycle appeared not to pick up the fix — confirmed via FastAPI's `TestClient` that the code itself was already correct, then a hard server restart resolved it. Stale reload process, not a code bug — worth remembering if this happens again.)
- **All originally-scoped build items are now done except Docker verification and getting a real (non-mocked) LLM narrative output** — see above.

### How an LLM touches this system — three components, only one genuinely agentic
As of this update there are three places an LLM is involved, deliberately kept distinct (see "Core design principle" above):

1. **Narration** (`app/agent/orchestrator.py` key-free template, `app/core/narration/agent_narrator.py` real-LLM) — the LLM only rephrases already-computed `PriorityScore`/`ContradictionLog`/`GapRecord` values into prose. It never chooses what to look at and never makes a judgment call. Verified live: `GET /narration/target/1` (SOD1) produced a real narrative where every number (0.9999, 0.9997, 1.0, 1.0, 0.9992, 0.9995, 0.9803, the 0.7 threshold) traces exactly to the stored `PriorityScore`/`GapRecord`.
2. **Literature contradiction proposer** — planned in the architecture (`docs/01_final_architecture.md` Stage 5: "LLM/NLP proposes candidate conflicting claims -> deterministic rule layer checks true comparability") but **NOT YET BUILT**. A prior request to build this was paused mid-clarification and never resumed — correcting the record here since a later message incorrectly assumed it existed. `abstract_text` on `EvidenceRecord`, `literature_text_client.py`, `literature_contradiction_proposer.py`/`_verifier.py`, and the `ContradictionLog.status`/`proposed_by`/`verification_reason` columns described in that request do not exist in the codebase.
3. **Autonomous investigation loop** (`app/agent/investigation_loop.py`, NEW) — **this is the one place "the agent controls the investigation" is literally true**, not just a narration framing. The LLM decides, step by step, which evidence tool to call next and when it has gathered enough to stop; a hard `max_iterations` cap in code (not just the prompt) bounds it regardless of what the model requests. It never scores, classifies, or judges evidence — see "Autonomous investigation loop" write-up below for what it does and doesn't control, and the real 3-run comparison.

### Environment setup: python-dotenv + .env
`app/main.py` now calls `load_dotenv()` as its very first statement (before any other import), loading a `.env` file in the project root into the process environment — this is how `GROQ_API_KEY` reaches the app without being hardcoded or exported manually every session. `.env` is gitignored (new `.gitignore` added, also covering `venv/`, `__pycache__/`, `als_pipeline.db`). Anything that imports `app.main` (the live server, `TestClient`) gets this automatically; a standalone script that never imports `app.main` must call `load_dotenv()` itself first.

**Two real bugs caught getting this working, worth remembering:**
- `groq==0.11.0` (the version originally pinned) is incompatible with the currently-installed `httpx==0.28.1` — its old client code passes a `proxies` kwarg httpx 0.28 removed, causing `TypeError: Client.__init__() got an unexpected keyword argument 'proxies'` on every call. Fixed by upgrading to `groq==1.7.0`. If this recurs, check `pip show httpx groq` for a similar mismatch before assuming the API key is the problem.
- The investigation loop's tool results are FAR too large for the free tier's context limit: `search_genetic_evidence('SOD1')` alone returns 285 real rows, which serialized whole blew a single call from ~1K to ~55K tokens against Groq's 8K TPM cap (`413 Request too large`). Fixed in `investigation_loop.py`: the model only ever sees a 5-row sample per tool call (`_summarize_for_model()`); `InvestigationResult.gathered_evidence` still keeps the full, real, untruncated data for the scoring handoff. Any future tool that can return more than a handful of rows needs this same treatment — an LLM deciding what to investigate next does not need every raw record, only enough to judge coverage.

### Autonomous investigation loop
New, separate path alongside the existing fixed pipeline (`scripts/ingest_evidence.py`, which always queries every configured datasource for every gene in a fixed order) — not a replacement. Both remain available.

- **`app/agent/investigation_tools.py`** — 4 tools (`search_genetic_evidence`, `search_literature_evidence`, `search_pathway_evidence`, `search_clinical_evidence`), each a thin wrapper around the already-built `open_targets_client.py`/`literature_client.py`, no new data-fetching logic. Named `investigation_tools.py`, NOT `tools.py` as originally requested — `app/agent/tools.py` already existed (the narration layer's DB-wrapper module, live at `/narrative/`) and would have been overwritten. `search_pathway_evidence` is honest about a real, pre-existing gap: no pathway/Reactome ingestion client has ever been built in this codebase, so it always returns zero rows with an explicit "not implemented" note rather than fabricating data.
- **`app/agent/investigation_loop.py`** — `investigate_target(gene, disease, max_iterations=6)`. Uses Groq's native (OpenAI-compatible) tool-calling API via a new `app/core/llm_client.py::call_llm_with_tools()` (the existing `agent_narrator._call_llm()` only does plain text, not tools).
- **`InvestigationTrace` table** (`app/db/models.py`) — every tool call logged in order: `target_id`, `run_id` (added beyond the original spec — without it, repeated runs for the same target collide on `step_number` and can't be told apart), `step_number`, `tool_called`, `tool_input`, `tool_result_summary`, `agent_reasoning`, `timestamp`.
- **`app/agent/pipeline_handoff.py`** — hands gathered evidence to the deterministic pipeline (`harmonic_sum.py`, `dimension_scoring.py`, `contradiction_classifier.py`, `evidence_profile.py`, `gap_taxonomy.py`) completely unmodified, reusing `scripts/ingest_evidence.py`'s exact field-derivation functions rather than duplicating them. **Deliberately scores in memory and does NOT write into the shared `EvidenceRecord`/`PriorityScore`/`ContradictionLog`/`GapRecord` tables** — writing agent-gathered rows into the same target's rows as the fixed pipeline already populated would silently mix the two, and would make repeated runs accumulate/duplicate rather than stay independently comparable. Promoting this to a persisted path is a deliberate future decision, not implied by this build.
- **`POST /agent/investigate/{target_id}`** — runs the loop, persists the trace, returns both the trace and the in-memory evidence profile.

**Real 3-run comparison for SOD1 (target_id=1), via the actual route, with `GROQ_API_KEY` working:**

| | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| Tool sequence | genetic → literature → clinical | genetic → literature → clinical | genetic → literature → clinical |
| Stopped reason | model_stopped | model_stopped | model_stopped |
| evidence_strength | 0.9993 | 0.9993 | 0.9993 |
| evidence_consistency | 1.0 | 1.0 | 1.0 |
| evidence_maturity | 1.0 | 1.0 | 1.0 |
| priority_score | 0.9998 | 0.9998 | 0.9998 |
| gaps | [mechanistic] | [mechanistic] | [mechanistic] |

Persisted correctly: 9 `InvestigationTrace` rows (3 steps × 3 runs), grouped into 3 distinct `run_id`s.

**Honest findings, not smoothed over:**
- **`agent_reasoning` was empty (`""`) on every single step across all 3 runs.** The system prompt explicitly asks the model to "state your reasoning for what to do next" after each tool result — `openai/gpt-oss-20b` doesn't do this; it calls tools silently and only produces reasoning text in its final, no-more-tool-calls message (which IS well-grounded — run 3's final message cites the real drug name "tofersen" and real trial stages, not fabricated). The per-step audit trail this column was designed to capture isn't materializing as designed for this model; this is a real gap between intended and actual behavior, not a wiring bug.
- **Pathway was never called, in any run** — and this looks like genuine judgment, not list-order coincidence: pathway sits third in the tool schema (before clinical), yet the model skipped straight to clinical every time, apparently reading `search_pathway_evidence`'s schema description ("NOTE: not yet implemented ... always returns zero rows") and rationally avoiding a tool documented as useless.
- **The 3 evidence profiles are IDENTICAL, not just "roughly consistent"** — but this only demonstrates reproducibility of the *scoring*, not order-invariance of the *investigation*: all 3 runs happened to pick the exact same tool sequence, so this run has not yet actually tested "does the profile stay consistent even when tool-call order differs" — that would require observing a run that explores tools in a different order (e.g. literature before genetic, or with a pathway detour), which didn't happen in these 3 samples. Worth re-running more times, or across other genes, before treating order-invariance as demonstrated rather than merely not-yet-falsified.
- **Temperature was never set anywhere** (confirmed by grep) — Groq's documented default is **1**, not 0. The identical 3 profiles above are therefore NOT a determinism artifact; they reflect genuine model consistency at default (non-zero) temperature, which is a stronger signal than if it had been forced to 0.

**Three separate attempts to fix `agent_reasoning`'s empty-per-step problem, all failed differently — do not try a fourth prompt variant without changing the underlying strategy:**
1. Reasoning + tool call in one turn, "MANDATORY FORMAT" wording → model merged the reasoning sentence into the tool-call arguments JSON, corrupting it (`400 Failed to parse tool call arguments as JSON`).
2. Same combined-turn approach, explicit "reasoning goes ONLY in content, never arguments" → model instead leaked an internal `<|channel|>commentary` formatting token (its own internal Harmony response-format artifact) into the function name, rejected by Groq (`Tool call validation failed`).
3. A fully separate, tools-disabled call before the tool-calling turn (`call_llm_plain()`, no `tools` param at all — the architecturally "correct" fix for failures 1-2) → the model attempted a tool call anyway, hallucinating a tool name that doesn't exist in this codebase (`ncbi_gene`), rejected by Groq (`Tool choice is none, but model called a tool`). Once the conversation history contains real prior tool calls, this model appears to keep trying to continue that pattern even on a call where no tools are registered.

All three attempts were reverted cleanly back to the original prompt (confirmed working again each time). `call_llm_plain()` remains in `app/core/llm_client.py` as a working, reusable utility (the function itself works correctly — attempt 3's failure was model behavior, not a bug in the call). **This looks like a genuine limitation of `openai/gpt-oss-20b`'s tool-calling behavior on Groq, not a solvable prompt-wording problem** — worth trying a different model before another prompt attempt, or accepting empty per-step reasoning as a stated limitation (the final stop message's reasoning remains real and well-grounded throughout).

### Real Pathway (Reactome) ingestion
Built after confirming, live, that the original assumption ("pathway evidence might exist via evidences(), just never queried") was wrong in an interesting way: grouping **every** real evidence row for all 5 genes (9,564 for SOD1 alone) by datasourceId/datatypeId shows **zero** pathway-like entries anywhere via `evidences()`. Pathway data in OTP is not per-disease evidence at all — it's a disease-agnostic **target annotation**, exposed via `Target.pathways` (type `ReactomePathway`: `pathway`, `pathwayId`, `topLevelTerm`), confirmed by introspecting the `Target` type's own fields.

- **`open_targets_client.get_pathway_evidence(ensembl_id)`** — new function, queries `Target.pathways` directly (not `get_evidence_for_datasource`, since this isn't an evidences()-based datasource at all).
- **`scripts/ingest_evidence.py`** — new `_build_pathway_fields()` builder (mirrors the existing `_build_genetic_fields`/`_build_clinical_fields` pattern), wired into `ingest_target()`. Every real pathway hit scores a fixed 1.0 via the already-existing `score_pathway_curated()`.
- **`app/config.py`** — added `"reactome": "pathway"` to `SOURCE_TYPE_BY_DATA_SOURCE` and `"pathway": []` to `COMPARABILITY_FIELDS_BY_SOURCE_TYPE` (no direction/comparability concept applies, same reasoning as literature).

**Real counts after re-ingestion (1,858 total evidence records):** SOD1: 3 pathways ("Detoxification of Reactive Oxygen Species" among them — biologically on-point for a superoxide dismutase gene), FUS: 4, NEK1: 1, C9orf72: 0, TARDBP: 0 — genuinely reflects each gene's real Reactome annotations, not a missing-data artifact.

**Confirmed real effect on the mechanistic gap, exactly as predicted:** re-ran scoring + gaps for all 5 targets — SOD1's mechanistic gap is now **gone** (zero gaps at all for SOD1: pathway=1.0 present, clinical present too), FUS and NEK1 also correctly lost the mechanistic gap, while C9orf72 and TARDBP (genuinely 0 real pathway rows) correctly still have it. Two new tests added (29/29 pass): `SOURCE_TYPE_BY_DATA_SOURCE`/`COMPARABILITY_FIELDS_BY_SOURCE_TYPE` registration, and `_build_pathway_fields()`'s field derivation.

**Asymmetry resolved:** `search_pathway_evidence()` in `app/agent/investigation_tools.py` now wraps the same real `open_targets_client.get_pathway_evidence()` the fixed pipeline uses (no reimplementation), and `app/agent/pipeline_handoff.py` converts real pathway rows via the same `_build_pathway_fields()` used by `scripts/ingest_evidence.py`, imported directly. Both the fixed pipeline and the investigation loop now see real pathway data.

**Real re-run for SOD1 through the actual `/agent/investigate/{id}` route, with real pathway data now available:** tool sequence was `search_genetic_evidence` → `search_literature_evidence` → `search_pathway_evidence`, `stopped_reason: model_stopped`. This is a genuine change from the earlier 3-run comparison above, where the model always chose `clinical` third and never called `pathway` (reasoning at the time: the tool schema described pathway as "not yet implemented ... always returns zero rows", so skipping it was rational). With that description now honestly describing a real capability, the model chose pathway over clinical this run — real evidence that the agent's tool selection is sensitive to the schema description, not just a fixed habit. (Still only one run; not yet re-tested for run-to-run stability now that pathway is a live option — see Phase 8 follow-ups.)

Resulting evidence profile: genetic=0.9992, literature=1.0, pathway=1.0, evidence_strength=0.9993, evidence_consistency=1.0, evidence_maturity=0.5 (pathway is a lower rung than human_clinical on `DIMENSION_MATURITY_LADDER` — this run never reached the top rung because it didn't call clinical), priority_score=0.8331. No mechanistic gap (pathway evidence present, exactly as the fixed pipeline found in Task 2) — but **modality** and **validation** gaps are present, because this run has no human_clinical evidence at all (the agent didn't call `search_clinical_evidence` this time). This is a real, worth-flagging disagreement with the fixed pipeline's result for SOD1 (zero gaps, since the fixed pipeline always queries every dimension including clinical) — not a bug in either system, but a direct consequence of the investigation loop's autonomy: an agent that chooses breadth over completeness will surface gaps a fixed, always-query-everything pipeline won't. Do not silently reconcile the two numbers in the report; state both and explain why they differ.

### Important discovery — evidence is not a uniform table (resolved)
Live GraphQL introspection against the real OTP API found that `population`, `tissue`, `assay_type`, `endpoint` do **not** exist as uniform fields across evidence source types:
- **Genetic evidence** (`eva`, `uniprot_variants`, `gwas_credible_sets` — dominant for SOD1/ALS, a rare-variant/Mendelian disease) has no population/tissue/assay/endpoint fields. Real comparable fields: `variant_id`, `clinical_significance` (ClinVar term, e.g. "pathogenic"), `inheritance_pattern` (derived from `allelicRequirements`, e.g. "Autosomal dominant").
- **Experimental evidence** (`impc`) carries tissue/phenotype-like fields.
- **Clinical evidence** (`clinical_precedence`) has population/endpoint-like fields under different names.
- **Literature evidence** (`europe_pmc`) has no structured comparability fields at all.

**Resolution implemented:** the contradiction classifier is now **source-type-aware**. Two evidence records are only classified against each other if they belong to the same source-type group (genetic / experimental / clinical / literature), using the fields that actually apply to that group (see `app/config.py`'s `COMPARABILITY_FIELDS_BY_SOURCE_TYPE`). Cross-type comparison (e.g. a genetic pathogenicity claim vs. a clinical trial outcome) returns `not_comparable_cross_type` rather than being forced — this is named as future work, not implemented.

This discovery is itself part of the project's original contribution: it demonstrates that biological evidence cannot be treated as one uniform table, and that a naive contradiction classifier would either silently fail or produce meaningless comparisons. State this explicitly in the report.

**Bug found and fixed while verifying the Docker/UI work:** `POST /gaps/target/{id}/run` accumulated duplicate `GapRecord` rows on every re-run instead of replacing them (surfaced visibly in the Streamlit UI — a target showed each gap type twice after two runs). Fixed in `app/api/routes/gaps.py`: now deletes the target's prior `GapRecord` rows before inserting new ones, matching `scripts/ingest_evidence.py`'s existing "clear before re-insert" prototype convention. Verified by re-running gap analysis for all 5 targets and confirming counts dropped back to the expected 1-3 per target, and by re-checking the live UI.

**What is NOT built yet — this is the next work:**
1. ~~Real evidence ingestion~~ DONE — `scripts/ingest_evidence.py` runs against the live OTP API for all 5 genes across `eva`/`uniprot_variants`/`gwas_credible_sets` (genetic), `europepmc` (literature), `clinical_precedence` (clinical), `impc` (experimental): 1,750 real `EvidenceRecord` rows ingested. Source-type-specific fields populated per the confirmed derivations in `docs/06_evidence_heterogeneity_discovery.md` — `tissue`/`assay_type`/`population`/`endpoint` correctly left null (confirmed empirically absent from this dataset, not an oversight); `phenotype` (experimental) and `intervention` (clinical, case-normalized) are real and populated. Re-run with `python -m scripts.ingest_evidence` — it clears and re-ingests on every run (prototype behavior, not additive).
2. ~~No `literature_client.py` yet~~ DONE — `app/ingestion/literature_client.py` queries NCBI's public E-utilities API directly (no API key required), independent of OTP's `europepmc`. Confidence is always 1.0 (presence-based: a paper either co-mentions the gene and disease in title/abstract, or it wasn't returned) — deliberately not a weighted NLP score, mirroring what OTP's own `europepmc` rows actually do in this dataset (score=1 for every included row). Wired into `scripts/ingest_evidence.py` as `data_source="pubmed"` alongside the OTP sources; 20 PMIDs ingested per gene (100 new records, 1,850 total). Comparability fields correctly left null, same as `europepmc`.
3. ~~`app/api/routes/gaps.py` placeholder~~ DONE — now reads real dimension scores/strength/consistency/maturity from the latest `PriorityScore` row (requires `/scoring/.../compute` to have run first — raises 400 otherwise) and real `has_pathway_evidence`/`has_human_clinical_evidence`/`has_known_compound` flags from `EvidenceRecord`.
4. ~~Evidence Consistency and Evidence Maturity~~ DONE — new module `app/core/scoring/evidence_profile.py`. Consistency: severity-weighted contradiction count (`CONTRADICTION_SEVERITY_WEIGHTS` in config.py) normalized against `comparable_pair_count()` (same-source-type pairs only, matching the classifier's own step-0 rule); returns 1.0 with zero comparable pairs. Maturity: max rung reached on `DIMENSION_MATURITY_LADDER` (literature 0.2 -> genetic 0.4 -> pathway 0.5 -> experimental 0.7 -> human_clinical 1.0), not an average — measures how far evidence has progressed, not breadth. `priority_score` is now a simple unweighted average of the three, for ranking convenience only — Strength/Consistency/Maturity are still reported separately (non-collapsed, per the design principle). Ran end-to-end for all 5 real targets: SOD1 (has clinical + drug evidence) scores maturity=1.0 with no modality/validation gaps; NEK1 (weakest genetic signal) correctly skips the mechanistic gap. Consistency reads 1.0 for all 5 genes in the current real dataset — SOD1's ClinVar variants are uniformly "risk"-direction, so no direct contradictions exist to detect; this is a property of the real data (rare pathogenic variants trend one direction), not evidence the classifier isn't exercised — worth stating this honestly in the report rather than implying conflicts were found where none exist.
5. ~~Agent orchestration layer~~ DONE — two narration paths now exist, deliberately kept separate rather than merged into one:
   - **Key-free, deterministic**: `app/agent/tools.py` + `app/agent/orchestrator.py` (`build_context()` assembles one auditable fact dict; `_template_narrate()` formats it with pure string interpolation, zero LLM involvement at all). Exposed at `GET /narrative/target/{id}`. Fully verified live for SOD1/C9orf72 — every value traces 1:1 back to the stored PriorityScore.
   - **Real LLM-backed**: `app/core/narration/agent_narrator.py` (`fetch_grounding_data()` pulls PriorityScore/ContradictionLog/GapRecord; `build_prompt()` embeds that data verbatim as JSON plus an explicit no-invention instruction; `_call_llm()` makes an actual Groq API call, model `openai/gpt-oss-20b` — isolated into its own function specifically so tests can mock it, and so swapping providers again only touches this one function). Exposed at `GET /narration/target/{id}` (note: `/narration/`, not `/narrative/` — both routes are intentionally live simultaneously). Requires `GROQ_API_KEY`, which does NOT exist anywhere in this environment (confirmed by search) — so this path is verified via 6 mocked unit tests (grounding-data assembly + prompt construction, no real network call) plus one live unmocked run against real SOD1 data confirming it fetches real values, builds the real prompt correctly, and fails with a clear RuntimeError rather than fabricating output when no key is present. **Getting one real (non-mocked) generated narrative and sanity-checking it against the source data is still an open task** — do this as soon as a key is available, per the user's own explicit request to see it before considering this piece done. See "LLM provider choice for narration" above for why Groq/gpt-oss-20b rather than Anthropic (first version) or Llama 3 (as later requested, but no longer free-tier viable on Groq).
   Both paths share the same design constraint from CLAUDE.md's core principle (never invent a score) and the same underlying tables — they differ only in whether an LLM is actually called or the text is templated.
6. ~~Streamlit UI~~ DONE — `streamlit_app.py` at the repo root, deliberately a thin client: calls the FastAPI backend via `requests` only, never touches the DB or deterministic modules directly (single source of truth stays the API). Gene selector, sidebar buttons for the 3 pipeline steps (contradictions -> scoring -> gaps, in the documented dependency order), Evidence Profile metrics, per-dimension bar chart, evidence record counts, contradictions table, gap explanations, and the full narrative text. Verified live in a browser against real data for SOD1 and C9orf72, including clicking "Run contradiction check" and seeing the real API response update the page. Run with `streamlit run streamlit_app.py` alongside the FastAPI backend. Added `streamlit==1.38.0` to requirements.txt.
7. Docker — `docker-compose.yml` added, running both services from the same image: `api` (FastAPI, port 8000, unchanged `CMD`) and `ui` (Streamlit, port 8501, overrides `command` to run `streamlit_app.py` instead). `streamlit_app.py` now reads its default API base URL from `API_BASE_URL` (env var) instead of hardcoding `127.0.0.1` — needed because the `ui` container reaches `api` by service name (`http://api:8000`), not localhost. **Caveat, stated honestly:** Docker itself is not installed in this development environment, so `docker compose up --build` has NOT been run end-to-end — only the Dockerfile logic, `docker-compose.yml` YAML syntax (parsed with PyYAML to confirm it's well-formed), and the underlying `requirements.txt` install (already verified working in this venv) were checked. This is a step down in confidence from every other item on this list, which were all verified live — test an actual `docker compose up --build` before relying on this for a demo. The SQLite DB is also not persisted across `docker compose down` (documented in the compose file) — matches the existing prototype design, not a new limitation.
8. ~~The "single mismatch" null-handling question~~ RESOLVED via constructed test cases (real data structurally can't exercise this — confirmed by checking direction_on_trait diversity across all 5 genes: SOD1/C9orf72/TARDBP/FUS are 100% "Risk", NEK1 has zero direction-labeled records; ClinVar only curates pathogenic-risk calls for these Mendelian ALS genes, so mixed-direction pairs never occur in this real dataset). Found and fixed a real bug while stress-testing: a pair with opposite direction where EVERY applicable field was null on one side previously fell through to "zero mismatches -> direct_contradiction", silently claiming "confirmed same context" when the honest answer is "we know nothing about context". Fixed in `contradiction_classifier.py`: direct_contradiction now requires at least one CONFIRMED matched field, not just zero mismatches; zero-matched-and-zero-mismatched now correctly returns unclassified. 2 new regression tests added (21/21 pytest pass). Re-ran the full real-data pipeline after the fix — no change in real output (confirms the branch really is unreachable with this dataset, exactly as expected).

## Disease & target scope (edit in `app/config.py` if changing)
- Disease: Amyotrophic Lateral Sclerosis, Open Targets EFO/MONDO ID: `MONDO_0004976`
- Candidate genes (Ensembl IDs already resolved in config): SOD1, C9orf72, TARDBP, FUS, NEK1
- MVP evidence dimensions (build these first): **Genetic, Literature, Pathway, Human/Clinical**
- Phase 2 dimensions (add later): Omics, Biomarker, Experimental

## Methodological reference — Open Targets Platform (OTP)
This project explicitly does NOT invent its own evidence-scoring weights. It adopts OTP's published methodology as a reference. Cite these in report/docstrings, don't silently reproduce without attribution:
- Ghoussaini, M. et al. (2021) "Open Targets Genetics..." *Nucleic Acids Research*, 49(D1), D1311–D1320. DOI: 10.1093/nar/gkaa840
- Buniello, A. et al. (2025) "Open Targets Platform..." *Nucleic Acids Research*.
- Scoring docs: https://platform-docs.opentargets.org/associations and https://platform-docs.opentargets.org/evidence
- API: https://api.platform.opentargets.org/api/v4/graphql

Note: Open Targets Genetics (OTG) was merged into the unified Open Targets Platform and deprecated 9 July 2025 — only the unified Platform API needs to be used.

Report language to preserve wherever this is described: *"The prototype adopts the Open Targets evidence-scoring framework as a methodological reference and implements a disease-specific subset of evidence dimensions."* Do not claim exact reproduction of OTP's current production scoring — their formulas may change between releases.

## Key formulas already implemented (see docstrings for citations)
- **Harmonic sum** (`app/core/scoring/harmonic_sum.py`): combines multiple evidence scores with diminishing returns per additional piece of evidence. `harmonic_sum_score_scaled_for_type()` is the variant used for per-dimension aggregation (adjusts normalization for small evidence counts).
- **Per-dimension scoring** (`app/core/scoring/dimension_scoring.py`): L2G threshold (0.05) for genetic evidence, clinical trial phase scoring with early-stop down-weighting (×0.5) for human/clinical evidence, fixed 1.0 for curated pathway evidence, normalized confidence for literature.
- **Contradiction classification** (`app/core/verification/contradiction_classifier.py`): source-type-aware strict decision tree. Only compares evidence within the same source-type group (genetic / experimental / clinical / literature), using the comparability fields that actually apply to that group (see `app/config.py`'s `COMPARABILITY_FIELDS_BY_SOURCE_TYPE`), plus Direction of Effect (reused from OTP's standard field, present across all source types). See module docstring for the exact decision order, including the cross-type refusal case. This is an original contribution, not from OTP — and the source-type-awareness itself was a discovery made through live API introspection, worth highlighting in the report.
- **Gap taxonomy** (`app/core/gaps/gap_taxonomy.py`): 5 gap types (mechanistic, population, modality, validation, evidence_consistency), each a falsifiable rule against normalized evidence data. Population and evidence_consistency gaps are fed directly by the contradiction classifier's output counts. This is an original contribution, not from OTP.

## Original contributions (the "own work" to emphasize, per mentor/reviewer feedback)
These four areas are what differentiate this project from simply re-implementing Open Targets — emphasize them in code comments, commit messages, and any generated documentation:
1. Evidence Verification & Contradiction Classification
2. Evidence Maturity / Evidence Profile (Strength/Consistency/Maturity kept as separate, non-collapsed outputs)
3. Research Gap Taxonomy (5 types)
4. Evidence-Gap-Linked Investigation Suggestions (templated to gap type, never freely generated by an LLM)

Target Prioritization itself should be framed as "OTP-informed evidence assessment + our own explainable research-prioritization layer" — not a new target score, and kept explicitly separate from OTP's own association score in all outputs and documentation.

## File tree
```
app/
  main.py                          FastAPI entrypoint, wires all routers (incl. narrative), calls init_db() on startup
  config.py                        Disease ID, target list, ALL scoring/consistency/maturity constants — single source of truth
  db/
    database.py                    SQLAlchemy engine/session (SQLite: als_pipeline.db)
    models.py                      Target, EvidenceRecord, ContradictionLog, GapRecord, PriorityScore, InvestigationTrace
  ingestion/
    open_targets_client.py         OTP GraphQL client — get_evidence_for_datasource (evidences()) + get_pathway_evidence (Target.pathways, real Reactome membership) — live-tested, working
    literature_client.py           PubMed/NCBI E-utilities client — live-tested, working (second, independent literature source)
  core/
    scoring/
      harmonic_sum.py              Tested, working
      dimension_scoring.py         Tested, working, wired to real ingested data via scripts/ingest_evidence.py
      evidence_profile.py          Consistency + Maturity — tested, working, wired into scoring.py
    verification/
      contradiction_classifier.py  Tested, working, source-type-aware + null-handling fix (see discovery section above)
    gaps/
      gap_taxonomy.py              Tested, working
    narration/
      agent_narrator.py            Real LLM-backed narration (Groq, openai/gpt-oss-20b — interim) — grounded, mocked-tested, verified live
  agent/
    tools.py                       Read-only DB wrappers for the narration/orchestration layer (no computation) — NOT the investigation tools, see below
    orchestrator.py                Key-free narration: build_context() + swappable narrator (_template_narrate() default)
    investigation_tools.py         4 tools wrapping existing ingestion functions for the autonomous investigation loop — verified live
    investigation_loop.py          investigate_target() — autonomous, LLM-controlled tool-calling loop, hard-capped, verified live 3x for SOD1
    pipeline_handoff.py            Hands agent-gathered evidence to the UNMODIFIED deterministic pipeline, scored in memory (not persisted — see docstring)
  core/
    llm_client.py                  call_llm_with_tools() — Groq tool-calling, separate from agent_narrator.py's plain-text _call_llm()
  api/routes/
    targets.py                     GET /targets/, POST /targets/seed — working
    evidence.py                    GET /evidence/target/{id} — working, real data loaded
    scoring.py                     POST /scoring/target/{id}/compute — working, real Strength/Consistency/Maturity
    contradictions.py              POST /contradictions/target/{id}/run — working, tested against real evidence
    gaps.py                        POST /gaps/target/{id}/run — working, real wiring, clears-before-inserting (bug fixed)
    narrative.py                   GET /narrative/target/{id} — key-free template narrative, working
    narration.py                   GET /narration/target/{id} — real LLM narrative, grounded + mocked-tested, verified live
    agent.py                       POST /agent/investigate/{target_id} — autonomous investigation loop, verified live 3x for SOD1
  models/schemas.py                Pydantic response models
scripts/
  ingest_evidence.py               Real ingestion for all 5 genes, 6 OTP datasources + PubMed + real Reactome pathway — working, 1,858 rows ingested
tests/
  test_core_logic.py               21 passing tests across all deterministic modules + the template narrator
  test_agent_narrator.py           6 passing tests for the real-LLM narrator (mocked _call_llm, in-memory SQLite fixture)
docs/                              00_INDEX.md + numbered planning docs; 06_evidence_heterogeneity_discovery.md is the
                                    live-updated record of every GraphQL-introspection finding — read this alongside CLAUDE.md
streamlit_app.py                   Streamlit UI — thin client over the API only, verified live in a browser
docker-compose.yml                 api + ui services from one image — written and YAML-validated, NOT run end-to-end (no Docker in this dev env)
requirements.txt
Dockerfile
README.md
```

## How to run
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
# Visit http://localhost:8000/docs

# In a second terminal, with the backend still running:
streamlit run streamlit_app.py
# Visit http://localhost:8501
```

Or via Docker Compose (backend + UI together — see item 7 caveat, not yet verified end-to-end in this environment):
```bash
docker compose up --build
# API: http://localhost:8000/docs   UI: http://localhost:8501
```

## Immediate next task (suggested starting point)
1. ~~Get a real LLM narrative and sanity-check it~~ DONE — `GROQ_API_KEY` now loads via `.env`/`python-dotenv`. Real narrative verified for SOD1, every number traced back to the grounding data. Two real bugs fixed along the way (see "Environment setup: python-dotenv + .env" above) — check those first if Groq calls start failing again after a dependency update.
2. **Decide whether to build the literature contradiction proposer.** Named in the architecture (Stage 5) and requested once, but paused mid-clarification and never resumed — see "How an LLM touches this system" above for exactly what's missing (`literature_text_client.py`, the proposer/verifier modules, `ContradictionLog` schema additions). Now that a real API key works, there's no blocker left to finishing it if it's still wanted.
3. **Re-run the investigation loop more times / on other genes before treating order-invariance as demonstrated.** All 3 SOD1 runs picked an identical tool sequence — a real, positive result, but it only shows the scoring is reproducible given the same evidence, not that the profile stays stable when the agent explores in a different order. Try NEK1 (weaker genetic signal, might change what the model considers "enough") or lower `max_iterations` to force an earlier stop.
4. **Verify Docker actually works.** Run `docker compose up --build` somewhere Docker is installed, confirm both services come up, the UI reaches the API by service name, and fix whatever breaks (a slim-image build failure for one of streamlit's heavier deps — pyarrow/pandas/numpy — is the most likely failure mode, not the compose wiring itself).
5. **Report-writing pass.** Several findings in this file and in `docs/06_evidence_heterogeneity_discovery.md` are report-worthy original contributions in their own right (the source-type-heterogeneity discovery, the null-handling bug catch, Consistency reading 1.0 because real ClinVar data has no mixed-direction pairs for these genes rather than because nothing was tested, the empty-per-step-reasoning finding on the investigation loop) — make sure the report states these as findings, not just as "it works."
6. **Companion minor project** (drug displacement/confound analysis, mentioned in "What this project is") is explicitly out of scope for this codebase — don't pull it in without being asked.
7. Anything new that comes up from mentor/reviewer feedback.

No open correctness questions remain in the codebase as of this update — everything flagged across this file and `docs/06_evidence_heterogeneity_discovery.md`'s "Open items" has been either resolved or explicitly documented as a stated limitation of the real dataset.
