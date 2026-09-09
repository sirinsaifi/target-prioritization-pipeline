"""
Agent narration layer — turns real, already-computed scores/classifications/
gaps into an explainable narrative via a real LLM call.

Design constraint (CLAUDE.md core principle): the LLM must NEVER invent or
adjust a score, weight, or classification. It only narrates values already
present in PriorityScore, ContradictionLog, and GapRecord. The prompt built
here contains ONLY those real values, retrieved by fetch_grounding_data()
and never modified afterward, plus an explicit instruction not to go beyond
them. Nothing in this module computes anything — every number the LLM can
possibly reference was already written to the database by a deterministic
module elsewhere in this project.

This module makes a live network call to the Groq API (OpenAI-compatible,
via the `groq` Python package) and requires GROQ_API_KEY to be set in the
environment. No key is bundled, guessed, or hardcoded here — if the
variable is unset, generate_target_narrative() raises a clear RuntimeError
rather than silently falling back or fabricating output. A fully
deterministic, key-free alternative narrator already exists in this
codebase at app/agent/orchestrator.py (GET /narrative/target/{id}) for
demos where no API key is available.

Model choice — interim, not final (see CLAUDE.md): Groq deprecated
llama-3.1-8b-instant and llama-3.3-70b-versatile to Enterprise-only pricing
in June 2026 (confirmed live against console.groq.com/docs — both model IDs
still resolve but require a committed-spend contract, so they are NOT
usable on this project's free/developer-tier key). The Llama 3 request from
CLAUDE.md is therefore not achievable as originally asked; the closest
available free-tier general-purpose model is `openai/gpt-oss-20b`
(confirmed free-tier accessible with a 30 RPM / 1K RPD / 8K TPM rate limit
— generous enough for this project's per-target, on-demand usage pattern).
Swapping in a biomedical-specialized model (BioMistral / OpenBioLLM via
HuggingFace) instead of or alongside this general-purpose interim choice is
named as a planned next step in CLAUDE.md, not urgent for now.
"""

import json
import os
import re

from sqlalchemy.orm import Session

from app.db.models import Target, PriorityScore, ContradictionLog, GapRecord, MomentumScore, EvidenceRecord, PipelineRunLog
from app.config import (
    MVP_DIMENSIONS,
    WHY_THIS_TARGET_UNCERTAINTY_GAP_PRIORITY, WHY_THIS_TARGET_UNCERTAINTY_EXCLUDED_GAP_TYPES,
    DIMENSIONS_WITH_SCORING_FORMULA_LIMITATIONS,
)
from app.core.gaps.gap_taxonomy import describe_investigation_coverage
from app.core.scoring.tiers import confidence_tier, maturity_tier

SYSTEM_PROMPT = (
    "You are a scientific narration assistant for a target-prioritization pipeline. "
    "You will be given ONLY real, already-computed values: evidence scores, "
    "contradiction classifications, and research gaps for one gene target. "
    "Write a short paragraph (3-5 sentences) explaining why this target has its "
    "current evidence profile, in plain scientific language suitable for a research "
    "report.\n\n"
    "Rules you must follow exactly:\n"
    "- Only reference the scores, classifications, and gap types provided in the data below.\n"
    "- Do not invent evidence, scores, or conclusions not present in this data.\n"
    "- Do not state a number that does not appear verbatim in the data below.\n"
    "- If a section of the data is empty or a value is null, say so explicitly "
    "rather than omitting it silently or guessing a plausible-sounding value.\n"
    "- Do not propose a new score, weight, or classification of your own — you are "
    "explaining conclusions that were already reached deterministically, not reaching "
    "new ones.\n"
    "- The data includes `investigation_coverage` (how many of the 4 evidence "
    "dimensions were actually checked) and `dimensions_not_explored` (which ones "
    "were not). If investigation_coverage starts with \"partial\", you MUST end "
    "your paragraph with a short parenthetical caveat naming exactly the "
    "dimensions_not_explored values, e.g. \"(based on a partial investigation; "
    "human_clinical evidence was not queried in this run)\" — do not omit this "
    "caveat, and do not add it if investigation_coverage is \"complete\".\n\n"
    "The data may also include a `momentum` section — a real, purely factual trend "
    "in evidence volume over time (e.g. publication counts per year), independent of "
    "evidence quality or priority. If present and not \"insufficient_data\", you may "
    "mention it factually (e.g. citing the real per-year counts or the real "
    "momentum_score ratio given), but you MUST NOT describe a declining or stable "
    "trend as a weakness, nor an accelerating trend as a strength or validation — "
    "state the real trend and real numbers only, never characterize what it implies "
    "about the target's evidence quality or priority."
)


def fetch_grounding_data(db: Session, target_id: int) -> dict | None:
    """
    Pull every real, already-computed value needed to narrate one target.
    This is the ONLY data the LLM will ever see for this call — nothing is
    computed or derived here, only fetched and reshaped for the prompt.
    Returns None if the target doesn't exist.
    """
    target = db.query(Target).filter_by(id=target_id).first()
    if target is None:
        return None

    priority = (
        db.query(PriorityScore)
        .filter(PriorityScore.target_id == target_id)
        .order_by(PriorityScore.computed_at.desc())
        .first()
    )

    contradictions = db.query(ContradictionLog).filter_by(target_id=target_id).all()
    gaps = db.query(GapRecord).filter_by(target_id=target_id).all()
    # Real, already-persisted Evidence Momentum — read-only here, same
    # "nothing computed in this function" rule as everything else:
    # fetch_grounding_data() never calls compute_momentum() itself, only
    # reads whatever the latest GET /momentum/target/{id} call last
    # persisted. None if momentum has never been computed for this target
    # yet — the narrator is told explicitly to omit it in that case (see
    # below), not to fabricate a trend.
    momentum = (
        db.query(MomentumScore)
        .filter(MomentumScore.target_id == target_id)
        .order_by(MomentumScore.computed_at.desc())
        .first()
    )

    # This function only ever reads the fixed pipeline's persisted tables
    # (scripts/ingest_evidence.py queries all 4 MVP dimensions
    # unconditionally), so coverage is always complete here — same
    # describe_investigation_coverage() helper app/api/routes/gaps.py uses,
    # not a separately hardcoded string. Contrast with
    # build_investigation_grounding_data() below, where this can be partial.
    coverage_label, dimensions_not_explored = describe_investigation_coverage(MVP_DIMENSIONS, verb="queried")

    return {
        "gene_symbol": target.gene_symbol,
        "ensembl_id": target.ensembl_id,
        "disease_efo_id": target.disease_efo_id,
        "investigation_coverage": coverage_label,
        "dimensions_not_explored": dimensions_not_explored,
        "priority_score": {
            "evidence_strength": priority.evidence_strength,
            "evidence_consistency": priority.evidence_consistency,
            "evidence_maturity": priority.evidence_maturity,
            "priority_score": priority.priority_score,
            "dimension_breakdown": json.loads(priority.dimension_breakdown or "{}"),
        } if priority is not None else None,
        "contradictions": [
            {
                "classification": c.classification,
                "evidence_record_a_id": c.evidence_record_a_id,
                "evidence_record_b_id": c.evidence_record_b_id,
                "matched_fields": json.loads(c.matched_fields or "[]"),
                "mismatched_fields": json.loads(c.mismatched_fields or "[]"),
            }
            for c in contradictions
        ],
        "gaps": [
            {
                "gap_type": g.gap_type,
                "rationale": g.rationale,
                "investigation_suggestion": g.investigation_suggestion,
            }
            for g in gaps
        ],
        # None if momentum has never been computed for this target (real
        # "never checked" state, GET /momentum/target/{id} not called
        # yet) — the model is instructed above to only mention this
        # section when present.
        "momentum": {
            "trend": momentum.trend,
            "momentum_score": momentum.momentum_score,
            "yearly_counts": json.loads(momentum.yearly_counts),
            "recent_window_count": momentum.recent_window_count,
            "prior_window_count": momentum.prior_window_count,
        } if momentum is not None else None,
    }


def build_investigation_grounding_data(evidence_profile: dict) -> dict:
    """
    Reshape app.agent.pipeline_handoff.score_investigation_result()'s
    output into the SAME grounding_data shape fetch_grounding_data()
    produces, so the one narrator (same SYSTEM_PROMPT, same no-invention
    rule) can narrate either evidence-gathering path. The one field that
    genuinely differs from the fixed-pipeline path: investigation_coverage/
    dimensions_not_explored are passed through verbatim from
    evidence_profile — already computed by pipeline_handoff.py from the
    agent's real tool calls — never recomputed or guessed here.
    """
    return {
        "gene_symbol": evidence_profile["gene"],
        "ensembl_id": None,
        "disease_efo_id": None,
        "investigation_coverage": evidence_profile["investigation_coverage"],
        "dimensions_not_explored": evidence_profile["dimensions_not_explored"],
        "priority_score": {
            "evidence_strength": evidence_profile["evidence_strength"],
            "evidence_consistency": evidence_profile["evidence_consistency"],
            "evidence_maturity": evidence_profile["evidence_maturity"],
            "priority_score": evidence_profile["priority_score"],
            "dimension_breakdown": evidence_profile["dimension_breakdown"],
        },
        # The investigation loop never persists per-pair ContradictionLog
        # rows (see pipeline_handoff.py's module docstring) — only
        # aggregate classification counts exist for an in-memory run, a
        # different (smaller) shape than fetch_grounding_data()'s per-pair
        # list. Kept under its own key rather than forced into
        # "contradictions" so the narrator never treats it as the same shape.
        "contradiction_classification_counts": evidence_profile["contradiction_classification_counts"],
        "gaps": evidence_profile["gaps"],
        # Evidence Momentum is computed from PERSISTED, timestamped
        # EvidenceRecord rows (see evidence_momentum.py) — the autonomous
        # investigation loop's evidence is scored in memory and never
        # persisted (see pipeline_handoff.py's module docstring), so there
        # is no real momentum to report for an investigation-loop run.
        # Always None here, not computed or approximated — kept as an
        # explicit key so both grounding-data shapes look the same to the
        # model, which is told above to simply omit any mention when null.
        "momentum": None,
    }


def build_prompt(grounding_data: dict) -> str:
    """
    Build the user-turn prompt: the real grounding data as JSON, plus the
    same no-invention constraint restated inline (belt-and-suspenders
    alongside SYSTEM_PROMPT, since system prompts can be deprioritized by
    some models under long contexts).
    """
    return (
        "Here is the real, already-computed data for this target. Only reference "
        "the scores, classifications, and gap types provided below. Do not invent "
        "evidence, scores, or conclusions not present in this data.\n\n"
        f"{json.dumps(grounding_data, indent=2)}"
    )


GROQ_MODEL = "openai/gpt-oss-20b"


def _call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 400) -> str:
    """
    Isolated on purpose: this is the ONE function that talks to the network.
    Tests mock this function directly rather than the whole Groq client, so
    they verify grounding-data assembly and prompt construction without
    making a real API call or requiring a key.

    `max_tokens` is overridable (default 400, unchanged for the original
    plain-paragraph narrator) because of a REAL bug found and fixed while
    building the "Why This Target?" feature: `openai/gpt-oss-20b` is a
    reasoning model that spends part of its `max_tokens` budget on hidden
    "reasoning" tokens BEFORE producing real `content` (visible via the
    response's own `completion_tokens_details.reasoning_tokens` field, not
    guessed). For SOD1's real, slightly larger grounding data (a long real
    essentiality_note plus 3 top_dimensions), this reasoning overhead
    sometimes consumed the ENTIRE 400-token budget by itself, leaving
    `finish_reason="length"` and `content=""` — a real, intermittent
    (non-zero temperature) truncation, confirmed live: 2 of 3 real repeated
    calls with the exact same real prompt failed this way, 1 succeeded.
    generate_why_this_target_narrative() below passes a higher budget for
    exactly this reason — this is not a hypothetical concern.
    """
    import groq

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. generate_target_narrative() makes a real "
            "LLM call and requires a key — set the environment variable before "
            "calling it. For a narrative with no API key required, use the "
            "deterministic template narrator instead: "
            "app.agent.orchestrator.generate_target_narrative() / "
            "GET /narrative/target/{id}."
        )

    client = groq.Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content


def _narrate_grounding_data(grounding_data: dict) -> dict:
    """Shared tail end for both public entry points below: build the prompt,
    call the LLM, return the standard {error, grounding_data, narrative} shape."""
    user_prompt = build_prompt(grounding_data)
    narrative = _call_llm(SYSTEM_PROMPT, user_prompt)
    return {"error": None, "grounding_data": grounding_data, "narrative": narrative}


def generate_target_narrative(target_id: int, db: Session) -> dict:
    """
    Assemble grounding data from the fixed pipeline's persisted tables, call
    the LLM, and return both the narrative and the raw grounding data it was
    produced from — every claim in the narrative should be checkable against
    `grounding_data`, which is exactly what was sent to the model, unmodified.
    Coverage here is always "complete" — see fetch_grounding_data().
    """
    grounding_data = fetch_grounding_data(db, target_id)
    if grounding_data is None:
        return {"error": "Target not found.", "grounding_data": None, "narrative": None}

    if grounding_data["priority_score"] is None:
        return {
            "error": "No scores computed for this target yet. Run POST /scoring/target/{id}/compute first.",
            "grounding_data": grounding_data,
            "narrative": None,
        }

    return _narrate_grounding_data(grounding_data)


DIMENSION_LABELS = {
    "genetic": "Genetic", "literature": "Literature", "pathway": "Pathway",
    "human_clinical": "Human/Clinical", "omics": "Omics", "experimental": "Experimental",
    "drug_target": "Drug-Target", "tissue_expression": "Tissue Expression", "ppi_network": "PPI Network",
}


def _confidence_label(evidence_consistency: float | None) -> str:
    """High/Medium/Low, from real evidence_consistency. Delegates to the
    shared app/core/scoring/tiers.py implementation (extracted so the
    Translational Opportunity classifier can reuse the exact same
    thresholds without drift — see that module's own docstring). A purely
    deterministic lookup — NEVER asked of the LLM (see this module's core
    design constraint at the top of the file: the model must not originate
    a classification)."""
    return confidence_tier(evidence_consistency)


def _maturity_label(evidence_maturity: float | None) -> str:
    """High/Medium/Low, from real evidence_maturity. Delegates to the
    shared app/core/scoring/tiers.py implementation, same reasoning as
    _confidence_label() above."""
    return maturity_tier(evidence_maturity)


def build_why_this_target_grounding_data(db: Session, target_id: int) -> dict | None:
    """
    Assemble ONLY real, already-computed values needed for the "Why This
    Target?" structured narrative (decision-layer strategy, priority #1).
    Same discipline as fetch_grounding_data() above: nothing is computed
    here beyond simple sorting/lookup/thresholding of values a
    deterministic module already wrote to the database. Returns None if
    the target doesn't exist.

    DELIBERATE SCOPE DECISION: `confidence`, `evidence_maturity`, and
    `main_remaining_uncertainty` are fully decided HERE, in Python, via
    documented thresholds/priority order (config.py) — not left for the
    LLM to classify. Only the 3 narrative bullets (dimensions, caution
    flags, contradiction status) are handed to the LLM for wording, and
    even those are built from facts already decided below; the LLM may
    only phrase them, never reclassify them (see generate_why_this_target_
    narrative()'s SYSTEM_PROMPT_WHY_THIS_TARGET, which restates this).
    """
    target = db.query(Target).filter_by(id=target_id).first()
    if target is None:
        return None

    priority = (
        db.query(PriorityScore)
        .filter(PriorityScore.target_id == target_id)
        .order_by(PriorityScore.computed_at.desc())
        .first()
    )
    if priority is None:
        return {"gene_symbol": target.gene_symbol, "priority_score": None}

    dimension_breakdown: dict = json.loads(priority.dimension_breakdown or "{}")
    ranked_dimensions = sorted(dimension_breakdown.items(), key=lambda kv: kv[1], reverse=True)
    top_dimensions = [
        {"dimension": key, "label": DIMENSION_LABELS.get(key, key), "score": score}
        for key, score in ranked_dimensions[:3]
    ]

    # Real Known Safety Events (dimension="safety_signal", one row per real
    # documented event — see scripts/ingest_evidence.py's
    # _build_safety_signal_fields()). Zero rows for a target that HAS been
    # ingested is a real, honest "checked, clean" result in this dataset —
    # but EvidenceRecord rows alone can't distinguish that from "safety
    # ingestion never ran for this gene at all" (no per-event row is ever
    # written for a clean result). The genetic_constraint row IS always
    # written (one per gene, unconditionally) by the SAME
    # get_prioritisation_and_safety() call that also fetches safety data
    # (see that function's docstring) — so its real presence is used here
    # as an honest proxy for "the safety query for this gene was actually
    # run", exactly the kind of real-fact-based inference this project
    # prefers over guessing from an empty result alone.
    safety_records = db.query(EvidenceRecord).filter_by(target_id=target_id, dimension="safety_signal").all()
    safety_checked = db.query(EvidenceRecord).filter_by(
        target_id=target_id, dimension="genetic", data_source="ot_genetic_constraint",
    ).first() is not None
    safety_events = [
        r.notes.split(";")[0].removeprefix("event=") for r in safety_records if r.notes
    ]

    # Real Gene Essentiality (dimension="essentiality_risk") — ONE real row
    # per gene, ALWAYS inserted regardless of the real value (see
    # _build_essentiality_fields()'s docstring), so the row's own presence
    # IS the real "checked" marker here — no proxy needed, unlike safety.
    essentiality_record = db.query(EvidenceRecord).filter_by(
        target_id=target_id, dimension="essentiality_risk",
    ).first()
    essentiality_checked = essentiality_record is not None
    is_essential = bool(
        essentiality_record and essentiality_record.raw_value is not None and essentiality_record.raw_value < 0
    )

    # Real contradiction status — PipelineRunLog(stage="contradictions")
    # distinguishes "checked, zero found" from "never checked at all",
    # same principle as GET /contradictions/target/{id} (see
    # app/api/routes/contradictions.py).
    contradictions_checked = db.query(PipelineRunLog).filter_by(
        target_id=target_id, stage="contradictions",
    ).first() is not None
    contradictions = db.query(ContradictionLog).filter_by(target_id=target_id).all()
    contradiction_classifications = sorted({c.classification for c in contradictions})

    # Real open gaps — "main remaining uncertainty" only ever names an
    # EVIDENCE-COMPLETENESS gap type (see
    # config.WHY_THIS_TARGET_UNCERTAINTY_GAP_PRIORITY's own docstring for
    # why the two risk-flag gap types are excluded: they're already
    # reported via the caution-flags bullet above, not as a "gap").
    gaps = db.query(GapRecord).filter_by(target_id=target_id).all()
    uncertainty_gaps = {
        g.gap_type: g for g in gaps if g.gap_type not in WHY_THIS_TARGET_UNCERTAINTY_EXCLUDED_GAP_TYPES
    }
    main_uncertainty = None
    for gap_type in WHY_THIS_TARGET_UNCERTAINTY_GAP_PRIORITY:
        if gap_type in uncertainty_gaps:
            g = uncertainty_gaps[gap_type]
            main_uncertainty = {
                "source": "gap", "gap_type": g.gap_type, "rationale": g.rationale,
            }
            break
    if main_uncertainty is None:
        # No open evidence-completeness gap — real fallback: the real
        # lowest-scoring dimension this target actually has a score for,
        # EXCLUDING any dimension with a known scoring-formula limitation
        # (see config.DIMENSIONS_WITH_SCORING_FORMULA_LIMITATIONS's own
        # docstring) — a real, live-confirmed case found this fallback
        # previously named ppi_network as the "uncertainty" for a gene
        # with 10 real high-confidence STRING partners, purely because
        # score_ppi_hub() divides by an arbitrary 100-partner ceiling, not
        # because that interactome is actually weak or uncertain. Picking
        # the next-lowest GENUINELY meaningful score instead avoids
        # mis-attributing uncertainty to a formula artifact.
        meaningful_dimensions = [
            (key, score) for key, score in ranked_dimensions
            if key not in DIMENSIONS_WITH_SCORING_FORMULA_LIMITATIONS
        ]
        if meaningful_dimensions:
            lowest_key, lowest_score = meaningful_dimensions[-1]
            main_uncertainty = {
                "source": "lowest_dimension",
                "dimension": lowest_key, "label": DIMENSION_LABELS.get(lowest_key, lowest_key),
                "score": lowest_score,
            }
        elif ranked_dimensions:
            # Edge case: every scored dimension this target has is in the
            # known-formula-limitation set — forcing a pick here would be
            # exactly the misleading behavior this fix removes, so this is
            # reported plainly instead of guessing.
            main_uncertainty = {"source": "none"}

    return {
        "gene_symbol": target.gene_symbol,
        "priority_score": priority.priority_score,
        "evidence_strength": priority.evidence_strength,
        "evidence_consistency": priority.evidence_consistency,
        "evidence_maturity": priority.evidence_maturity,
        "top_dimensions": top_dimensions,
        "caution_flags": {
            "safety_checked": safety_checked,
            "safety_events": safety_events,
            "essentiality_checked": essentiality_checked,
            "is_essential": is_essential,
            "essentiality_note": essentiality_record.notes if (is_essential and essentiality_record) else None,
        },
        "contradiction_status": {
            "checked": contradictions_checked,
            "count": len(contradictions),
            "classifications": contradiction_classifications,
        },
        "confidence": _confidence_label(priority.evidence_consistency),
        "evidence_maturity_label": _maturity_label(priority.evidence_maturity),
        "main_remaining_uncertainty": main_uncertainty,
    }


SYSTEM_PROMPT_WHY_THIS_TARGET = (
    "You are a scientific narration assistant for a target-prioritization pipeline. "
    "You will be given ONLY real, already-computed, already-CLASSIFIED values for one "
    "gene target — including facts that have already been decided deterministically "
    "(e.g. which gap is the 'main remaining uncertainty', whether a safety/essentiality "
    "flag is real). Your ONLY job is to phrase exactly 3 short bullet sentences from "
    "this data, in this fixed order:\n"
    "1. The strongest supporting evidence dimension(s), naming the real dimension "
    "label(s) and real score(s) from `top_dimensions`.\n"
    "2. Caution flags: if `caution_flags.safety_events` is non-empty, name the real "
    "event(s). If `caution_flags.is_essential` is true, state the real essentiality "
    "flag. If NEITHER is present, write a bullet stating plainly that no real caution "
    "flags were found in the checked data (do not claim they were 'never checked' if "
    "safety_checked/essentiality_checked are true).\n"
    "3. Contradiction status: if `contradiction_status.checked` is false, say "
    "contradiction checking has not been run for this target yet. If checked and "
    "`count` is 0, say plainly that no same-type contradictions were detected. If "
    "checked and count > 0, name the real classification types found.\n\n"
    "Rules you must follow exactly:\n"
    "- Only reference values that appear verbatim in the data below.\n"
    "- Do not invent evidence, scores, gap types, or classifications not present here.\n"
    "- Do not reclassify or restate `confidence`, `evidence_maturity_label`, or "
    "`main_remaining_uncertainty` as your own bullets — those are decided already and "
    "shown separately; your 3 bullets are ONLY the 3 topics listed above.\n"
    "- Respond with ONLY a JSON object of the exact shape {\"bullets\": [\"...\", \"...\", "
    "\"...\"]} — exactly 3 strings, in the order given above. No prose before or after "
    "the JSON, no markdown code fences."
)


def _parse_why_this_target_bullets(raw_text: str) -> list[str]:
    """
    Parse the LLM's plain-text response into exactly 3 bullet strings.
    Three tiers, each a real fallback for a real failure mode confirmed
    live while building this feature (not hypothetical):

    1. Direct json.loads() — the model was asked to return ONLY JSON, no
       fences, and often does exactly that.
    2. Extract the first {...} block via regex, for a model that added
       stray prose around otherwise-valid JSON.
    3. Real, confirmed-live failure: `openai/gpt-oss-20b` sometimes emits
       JSON with a missing closing bracket (e.g. `"bullets":["a","b","c"}`
       — no `]` before the final `}`), which fails tiers 1-2 even though
       every individual bullet string inside is perfectly well-formed.
       Recovered here by regex-extracting quoted string literals directly
       from within a `"bullets": [...]`-shaped fragment, without requiring
       the surrounding brackets to be valid — confirmed live to correctly
       recover all 3 real bullets from that exact malformed shape.

    If ALL THREE fail, the raw text is wrapped as a single real (not
    fabricated) fallback bullet rather than silently dropping the
    narrative — the caller still gets to see what the model actually said.
    """
    try:
        parsed = json.loads(raw_text)
        bullets = parsed.get("bullets")
        if isinstance(bullets, list) and all(isinstance(b, str) for b in bullets):
            return bullets
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass

    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            bullets = parsed.get("bullets")
            if isinstance(bullets, list) and all(isinstance(b, str) for b in bullets):
                return bullets
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass

    bullets_fragment = re.search(r'"bullets"\s*:\s*\[(.*)', raw_text, re.DOTALL)
    if bullets_fragment:
        quoted_strings = re.findall(r'"((?:[^"\\]|\\.)*)"', bullets_fragment.group(1))
        if quoted_strings:
            def _unescape(s: str) -> str:
                try:
                    return s.encode().decode("unicode_escape")
                except (UnicodeDecodeError, UnicodeEncodeError):
                    return s  # real content preserved as-is rather than risking corruption
            return [_unescape(s) for s in quoted_strings]

    return [raw_text.strip()] if raw_text and raw_text.strip() else []


def generate_why_this_target_narrative(target_id: int, db: Session) -> dict:
    """
    Assemble the "Why This Target?" grounding data, call the LLM for the 3
    bullet sentences only, and return the full structured shape: bullets
    (LLM-phrased) plus confidence/evidence_maturity_label/
    main_remaining_uncertainty (decided deterministically in
    build_why_this_target_grounding_data(), never by the model — see that
    function's own docstring).
    """
    grounding_data = build_why_this_target_grounding_data(db, target_id)
    if grounding_data is None:
        return {"error": "Target not found.", "grounding_data": None, "why_this_target": None}

    if grounding_data.get("priority_score") is None:
        return {
            "error": "No scores computed for this target yet. Run POST /scoring/target/{id}/compute first.",
            "grounding_data": grounding_data,
            "why_this_target": None,
        }

    user_prompt = (
        "Here is the real, already-computed and already-classified data for this "
        "target. Only reference the values provided below. Respond with ONLY the JSON "
        "object described in your instructions.\n\n"
        f"{json.dumps(grounding_data, indent=2)}"
    )
    # Higher budget than the default 400 — see _call_llm()'s own docstring
    # for the real reasoning-token-truncation bug this specifically fixes
    # (confirmed live for SOD1: 2 of 3 real repeated calls at 400 tokens
    # truncated to empty content before this fix).
    raw_response = _call_llm(SYSTEM_PROMPT_WHY_THIS_TARGET, user_prompt, max_tokens=900)
    bullets = _parse_why_this_target_bullets(raw_response)

    return {
        "error": None,
        "grounding_data": grounding_data,
        "why_this_target": {
            "gene_symbol": grounding_data["gene_symbol"],
            "bullets": bullets,
            "confidence": grounding_data["confidence"],
            "evidence_maturity": grounding_data["evidence_maturity_label"],
            "main_remaining_uncertainty": grounding_data["main_remaining_uncertainty"],
        },
    }


def generate_investigation_narrative(evidence_profile: dict) -> dict:
    """
    Same narrator, fed from the autonomous investigation loop's in-memory
    result (app.agent.pipeline_handoff.score_investigation_result()) instead
    of the DB. Unlike generate_target_narrative(), investigation_coverage
    here can genuinely be "partial" — SYSTEM_PROMPT requires the model to
    say so explicitly and name the real dimensions_not_explored value when
    that happens, rather than presenting a partial run's evidence profile
    with the same confidence as the fixed pipeline's exhaustive one.
    """
    grounding_data = build_investigation_grounding_data(evidence_profile)
    return _narrate_grounding_data(grounding_data)
