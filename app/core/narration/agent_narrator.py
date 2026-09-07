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

from sqlalchemy.orm import Session

from app.db.models import Target, PriorityScore, ContradictionLog, GapRecord, MomentumScore
from app.config import MVP_DIMENSIONS
from app.core.gaps.gap_taxonomy import describe_investigation_coverage

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


def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """
    Isolated on purpose: this is the ONE function that talks to the network.
    Tests mock this function directly rather than the whole Groq client, so
    they verify grounding-data assembly and prompt construction without
    making a real API call or requiring a key.
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
        max_tokens=400,
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
