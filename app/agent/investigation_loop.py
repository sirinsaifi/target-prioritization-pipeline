"""
Autonomous investigation loop — the agent controls WHICH evidence tools to
call and WHEN to stop investigating a target. This is a NEW, separate path
alongside the existing fixed-pipeline ingestion (scripts/ingest_evidence.py,
which always calls every configured datasource in a fixed order for every
gene) — not a replacement. Both remain available so the fixed pipeline
stays the safe, reproducible default while this path is evaluated.

Distinguishing this from the OTHER LLM-touching components in this codebase
(see CLAUDE.md, which documents all of these explicitly):
- Deterministic scoring/classification/gaps: the LLM is never involved at all.
- Narration layer (app/agent/orchestrator.py, app/core/narration/): the LLM
  only rephrases already-computed values into prose. It never chooses what
  to look at or makes a judgment call.
- Literature contradiction proposer (planned, not yet built as of this
  module): the LLM makes ONE judgment call per excerpt pair (does this
  contradict?), but does not control sequencing or scope.
- THIS module: the LLM decides, step by step, which tool to call next and
  when it has gathered enough evidence to stop. This is the one place
  "the agent controls the investigation" is literally true, not just a
  narration framing.

What the agent does NOT control: scoring, classification, or gap logic.
Once the loop ends, whatever evidence rows were gathered are handed to the
EXISTING deterministic pipeline (dimension_scoring.py,
contradiction_classifier.py, gap_taxonomy.py) completely unmodified — see
run_investigation_and_score(). The agent's authority is scoped to WHAT gets
investigated and WHEN to stop; HOW anything is scored is never touched.

Hard safety cap: max_iterations bounds the loop in code (a plain Python
counter), not just via the prompt's instruction — the model asking for one
more tool call after the cap is simply not honored, regardless of what it
says.
"""

import json
from dataclasses import dataclass, field

from app.agent.investigation_tools import TOOL_SCHEMAS, TOOL_FUNCTIONS
from app.core.llm_client import call_llm_with_tools

SYSTEM_PROMPT_TEMPLATE = (
    "You are investigating target {gene} for {disease}. Call tools to gather evidence. "
    "After each tool result, state your reasoning for what to do next in a short sentence "
    "before deciding whether to call another tool. "
    "Stop calling tools once you have gathered genetic evidence, literature evidence, and "
    "at least one more evidence type (clinical or pathway), or after {max_iterations} tool "
    "calls, whichever comes first. "
    "You never compute a score yourself — you only decide which real evidence sources to "
    "check and when you have enough coverage to stop. When you decide to stop, reply with "
    "a short final message summarizing what you gathered and why you stopped, without "
    "making any tool calls."
)

# THREE separate attempts to populate per-step agent_reasoning with real
# text have now failed for openai/gpt-oss-20b, each in a different way (see
# CLAUDE.md / docs/07 for full failure logs):
#   1. Reasoning + tool call combined in one turn, strong "MANDATORY FORMAT"
#      wording -> the model merged the reasoning sentence INTO the tool-call
#      arguments JSON itself, corrupting it.
#   2. Same combined-turn approach, wording clarified to say reasoning goes
#      "ONLY in content, never in arguments" -> the model instead leaked an
#      internal "<|channel|>commentary" formatting token (its own internal
#      Harmony response-format artifact) into the function name.
#   3. A fully SEPARATE, tools-disabled call before the tool-calling turn
#      (call_llm_plain(), no `tools` param at all, per the user's own
#      diagnosis that separating the two response formats should fix it)
#      -> the model attempted a tool call anyway, hallucinating a tool name
#      that doesn't exist in this codebase ("ncbi_gene"), rejected by Groq
#      with "Tool choice is none, but model called a tool". It appears
#      that once the conversation history contains earlier real tool calls,
#      this model keeps trying to continue that pattern even on a call
#      where no tools are registered at all.
# Reverted to the original prompt each time rather than force a fourth
# variant. agent_reasoning remains empty at every intermediate step in
# practice; only the model's final stop message contains real reasoning
# text. This looks like a genuine limitation of this specific free-tier
# model's tool-calling behavior, not a prompt-wording problem — a different
# model (or accepting empty per-step reasoning as a known limitation) may
# be the real fix, not another prompt variant.


@dataclass
class ToolCallStep:
    step_number: int
    tool_called: str
    tool_input: dict
    tool_result_summary: str
    agent_reasoning: str


@dataclass
class InvestigationResult:
    gene: str
    disease: str
    steps: list = field(default_factory=list)  # list[ToolCallStep]
    gathered_evidence: dict = field(default_factory=dict)  # tool_name -> list of raw rows, merged across calls
    stopped_reason: str = ""
    final_message: str = ""


def _summarize_tool_result(tool_name: str, result: dict) -> str:
    """Short, human-readable summary for the trace log — the full raw result
    still goes into `gathered_evidence`; this is only for the audit trail."""
    if "error" in result:
        return f"error: {result['error']}"
    return f"{result.get('total_rows', 0)} row(s) returned"


# Cap on how many raw rows go INTO THE MODEL'S CONTEXT per tool call. This
# is purely a context-size limit for the LLM conversation — it does NOT
# limit what gets stored in InvestigationResult.gathered_evidence, which
# always keeps the tool function's full, real return value for the later
# handoff to the deterministic scoring pipeline (see module docstring,
# "the agent controls WHAT/WHEN, never HOW"). Found necessary the hard way:
# search_genetic_evidence('SOD1') alone returns 285 real rows, which
# serialized whole blew a single free-tier Groq call from ~1K to ~55K
# tokens against an 8K TPM rate limit — an LLM should never need every raw
# row to decide what to investigate next, only enough to judge coverage.
MAX_ROWS_SHOWN_TO_MODEL = 5


def _summarize_for_model(result: dict) -> dict:
    """
    Trim a tool result down to something small enough to send back to the
    model as a tool message — full row count preserved, but only a bounded
    sample of the actual rows, since the model needs to judge coverage
    (how much evidence exists, roughly what it looks like), not audit every
    record (that's what gathered_evidence + the deterministic pipeline are
    for afterward).
    """
    if "rows" not in result:
        return result

    total = len(result["rows"])
    trimmed = dict(result)
    trimmed["rows"] = result["rows"][:MAX_ROWS_SHOWN_TO_MODEL]
    if total > MAX_ROWS_SHOWN_TO_MODEL:
        trimmed["_note"] = (
            f"Showing {MAX_ROWS_SHOWN_TO_MODEL} of {total} real rows "
            f"(truncated for context size — total_rows above is the real, untruncated count)."
        )
    return trimmed


def investigate_target(gene: str, disease: str, max_iterations: int = 6) -> InvestigationResult:
    """
    Run the autonomous tool-calling loop for one (gene, disease) pair.
    Hard-caps at `max_iterations` tool calls regardless of what the model
    requests — see module docstring.
    """
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(gene=gene, disease=disease, max_iterations=max_iterations)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Begin investigating {gene} for {disease}."},
    ]

    result = InvestigationResult(gene=gene, disease=disease)
    iterations = 0

    while iterations < max_iterations:
        response_message = call_llm_with_tools(messages, TOOL_SCHEMAS)
        messages.append(response_message)

        tool_calls = response_message.get("tool_calls")
        if not tool_calls:
            # Model chose to stop rather than call another tool.
            result.final_message = response_message.get("content") or ""
            result.stopped_reason = "model_stopped"
            return result

        # Reasoning text the model produced alongside/before this batch of
        # tool calls (may be empty for models that call tools with no
        # accompanying content) — logged verbatim, never paraphrased. See
        # module docstring: THREE separate approaches to populate this with
        # real per-step text have now failed for openai/gpt-oss-20b, each
        # differently — reverted to this original, reliably-working form.
        reasoning = response_message.get("content") or ""

        for tool_call in tool_calls:
            if iterations >= max_iterations:
                break

            tool_name = tool_call["function"]["name"]
            try:
                tool_args = json.loads(tool_call["function"]["arguments"])
            except json.JSONDecodeError:
                tool_args = {}

            tool_function = TOOL_FUNCTIONS.get(tool_name)
            if tool_function is None:
                tool_result = {"error": f"Unknown tool {tool_name!r} requested by model."}
            else:
                tool_result = tool_function(**tool_args)

            iterations += 1
            result.steps.append(ToolCallStep(
                step_number=iterations,
                tool_called=tool_name,
                tool_input=tool_args,
                tool_result_summary=_summarize_tool_result(tool_name, tool_result),
                agent_reasoning=reasoning,
            ))
            result.gathered_evidence.setdefault(tool_name, []).append(tool_result)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "name": tool_name,
                # The model sees a trimmed sample (context-size limit only)
                # — result.gathered_evidence above keeps tool_result whole.
                "content": json.dumps(_summarize_for_model(tool_result)),
            })

    result.stopped_reason = f"max_iterations ({max_iterations}) reached"
    return result
