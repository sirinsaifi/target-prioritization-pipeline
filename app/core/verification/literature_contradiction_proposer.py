"""
Literature contradiction proposer — Stage 5 of the architecture ("LLM
proposes candidate conflicting claims -> deterministic rule layer checks
true comparability"), applied to literature evidence specifically: the one
source type with no structured comparability fields
(app.config.COMPARABILITY_FIELDS_BY_SOURCE_TYPE["literature"] == []), so
app/core/verification/contradiction_classifier.py can never classify a
literature-vs-literature pair as anything but "unclassified" (there's
nothing structured to compare). This module is what lets literature
evidence get REAL contradiction-checking, from the actual text — but only
ever as a PROPOSAL. Nothing here writes to ContradictionLog directly or
decides a contradiction is real; see literature_contradiction_verifier.py
for the deterministic confirm/reject step that must run before anything
from this module is trusted (Core design principle, CLAUDE.md: the LLM
never originates a confirmed finding).

DESIGN, defensively, against Phase 8's real failure history: three separate
attempts to get openai/gpt-oss-20b to emit reliable structured output
alongside tool calls all failed differently (JSON corruption, a leaked
internal format token, a phantom tool call once tools were disabled — see
docs/07 Phase 8). This module avoids that whole failure class by construction:
  - No tool-calling is involved AT ALL. `call_llm_with_tools()` /
    `TOOL_SCHEMAS` are never imported here. This is a single plain
    completion via `app.core.llm_client.call_llm_plain()` — the same
    tools-disabled function Phase 8 built and validated works reliably.
  - The requested output is plain text in a fixed two-line format
    ("CLASSIFICATION: <word>\nREASON: <sentence>"), not JSON. Nothing here
    asks the model to emit a JSON object it could corrupt or wrap in stray
    tokens the way the tool-call-arguments failures did.
  - Parsing is a simple regex against that fixed format, not a JSON
    decoder — a malformed/incomplete response fails a match and returns
    classification=None (never guessed), rather than raising or silently
    inventing a value.
"""

import re

from app.core.llm_client import call_llm_plain

VALID_CLASSIFICATIONS = {"CONTRADICT", "SUPPORT", "UNRELATED"}

SYSTEM_PROMPT = (
    "You are a biomedical literature analyst. You will be given two short "
    "excerpts about the same gene's role in the same disease. Classify "
    "the relationship between them and respond in EXACTLY the format "
    "requested, nothing else — no extra commentary before or after."
)

_RESPONSE_PATTERN = re.compile(
    r"CLASSIFICATION:\s*([A-Za-z]+)\s*REASON:\s*(.+)", re.IGNORECASE | re.DOTALL,
)


def _build_prompt(gene: str, disease: str, excerpt_a: str, excerpt_b: str) -> str:
    return (
        f"Here are two excerpts about {gene}'s role in {disease}.\n\n"
        f"Excerpt A: {excerpt_a}\n\n"
        f"Excerpt B: {excerpt_b}\n\n"
        f"Does Excerpt B CONTRADICT, SUPPORT, or say something UNRELATED to Excerpt A "
        f"regarding the gene's effect on the disease?\n"
        f"Respond in exactly this format:\n"
        f"CLASSIFICATION: <one word>\n"
        f"REASON: <one sentence>"
    )


def _parse_response(raw_response: str) -> tuple[str | None, str | None]:
    """
    Simple regex/split parsing, deliberately not JSON (see module
    docstring). Returns (classification, reason); classification is None
    if the response doesn't match the requested format at all, or if the
    matched word isn't one of the three requested classifications — never
    guessed or defaulted to a "safe" value.
    """
    match = _RESPONSE_PATTERN.search(raw_response or "")
    if not match:
        return None, None

    classification = match.group(1).strip().upper()
    reason = match.group(2).strip()
    # Take only the first line of the reason, in case the model kept
    # writing after the requested one sentence.
    reason = reason.splitlines()[0].strip()

    if classification not in VALID_CLASSIFICATIONS:
        return None, reason

    return classification, reason


def propose_literature_contradiction(gene: str, disease: str, excerpt_a: str, excerpt_b: str) -> dict:
    """
    One plain-text LLM call proposing whether excerpt_b contradicts,
    supports, or is unrelated to excerpt_a regarding {gene}'s role in
    {disease}. Returns a dict — NEVER writes to the database and never
    treats its own output as confirmed; see literature_contradiction_verifier.py
    for the required next step before anything here can become a
    ContradictionLog row.

    {
        "classification": "CONTRADICT" | "SUPPORT" | "UNRELATED" | None,
        "reason": str | None,       # the model's one-sentence reason, or None if unparseable
        "raw_response": str,        # exactly what the model returned, for audit/debugging
    }
    """
    prompt = _build_prompt(gene, disease, excerpt_a, excerpt_b)
    raw_response = call_llm_plain([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ])
    classification, reason = _parse_response(raw_response)
    return {"classification": classification, "reason": reason, "raw_response": raw_response}
