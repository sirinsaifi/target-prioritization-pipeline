"""
Shared LLM client helper for capabilities beyond the simple text call
already in app/core/narration/agent_narrator.py's `_call_llm()` — currently
just tool-calling support, needed by app/agent/investigation_loop.py.

Same provider/model as the rest of this codebase: Groq, `openai/gpt-oss-20b`
— an interim, not-final choice (see CLAUDE.md "LLM provider choice for
narration" and agent_narrator.py's module docstring for the full reasoning:
Llama 3.1/3.3 were moved to Enterprise-only pricing on Groq in June 2026,
so this is the closest free-tier general-purpose substitute).

Kept separate from agent_narrator.py's `_call_llm()` rather than merged
into one function, since the two have genuinely different shapes (plain
system+user text in / string out, vs. a full messages list + tool schemas
in / a structured assistant-message dict out) — forcing them into one
signature would make both call sites harder to read for no real reuse
benefit. Both still point at the same provider/model constant pattern and
both fail the same way (loud RuntimeError, never fabricated output) when
GROQ_API_KEY is missing.
"""

import os

from app.config import BIOMEDICAL_LLM_MODEL, BIOMEDICAL_LLM_INFERENCE_PROVIDER

GROQ_MODEL = "openai/gpt-oss-20b"

# HuggingFace's current, unified "Inference Providers" API — replaces the
# now-fully-retired `api-inference.huggingface.co` serverless domain (DNS no
# longer resolves at all, confirmed live while building this). OpenAI-
# compatible chat-completions shape, same request/response contract as
# Groq's own API — the model is addressed as "<hf_model_id>:<provider>" so
# HF's router knows which specific Inference Provider to route the call to.
HUGGINGFACE_ROUTER_URL = "https://router.huggingface.co/v1/chat/completions"


def call_llm_with_tools(messages: list, tools: list) -> dict:
    """
    One turn of a tool-calling conversation. Returns the assistant message
    as a plain dict with `content` (may be None/empty when the model only
    calls tools) and, when the model chose to call tools, `tool_calls`
    (each `{"id", "type", "function": {"name", "arguments"}}` — `arguments`
    stays JSON-encoded exactly as the API returns it; callers parse it).

    Requires GROQ_API_KEY in the environment — raises RuntimeError with an
    actionable message if it's missing, same "fail loudly, never fabricate"
    behavior as agent_narrator.py's `_call_llm()`.
    """
    import groq

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. The autonomous investigation loop makes a "
            "real LLM tool-calling call and requires a key — set the environment "
            "variable before calling investigate_target()."
        )

    client = groq.Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        tools=tools,
    )
    message = response.choices[0].message

    result = {"role": "assistant", "content": message.content}
    if message.tool_calls:
        result["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in message.tool_calls
        ]
    return result


def call_llm_plain(messages: list) -> str:
    """
    Plain text turn — no `tools` parameter passed at all, so tool use is
    fully disabled for this call. Used to elicit reasoning as a completely
    separate, format-isolated call before a tool-calling turn (see
    app/agent/investigation_loop.py) — asking for reasoning text AND a tool
    call in the SAME turn caused two real failures for openai/gpt-oss-20b:
    once the model merged the reasoning sentence into the tool-call
    arguments JSON (corrupting it), once it leaked an internal
    "<|channel|>commentary" formatting token (this model's own internal
    response-format artifact) into the function name. Keeping the two
    response formats in fully separate API calls avoids both.

    Same "fail loudly, never fabricate" behavior as call_llm_with_tools()
    when GROQ_API_KEY is missing.
    """
    import groq

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. This call requires a real LLM API key — "
            "set the environment variable before calling it."
        )

    client = groq.Groq(api_key=api_key)
    response = client.chat.completions.create(model=GROQ_MODEL, messages=messages)
    return response.choices[0].message.content or ""


def call_llm_plain_biomedical(messages: list) -> str:
    """
    Plain text turn against a real biomedical-domain LLM, via HuggingFace's
    Inference Providers router (see HUGGINGFACE_ROUTER_URL above) — an
    ADDITIONAL option for app/core/verification/literature_contradiction_proposer.py,
    not a replacement for the Groq path elsewhere in this codebase. This is
    the one place in the project where domain-specific medical knowledge
    genuinely helps the task (judging whether two real literature excerpts
    biologically CONTRADICT/SUPPORT/are UNRELATED), unlike narration or the
    investigation loop, which only need fluent instruction-following over
    facts already computed elsewhere.

    Model/provider are read from app.config (BIOMEDICAL_LLM_MODEL /
    BIOMEDICAL_LLM_INFERENCE_PROVIDER) — see that module for the real,
    live-confirmed availability check behind the current choice.

    Same "fail loudly, never fabricate" behavior as call_llm_plain() above
    when HUGGINGFACE_API_TOKEN is missing — uses plain `requests` (already a
    project dependency) rather than adding `huggingface_hub` for one call.
    """
    import requests

    api_key = os.environ.get("HUGGINGFACE_API_TOKEN")
    if not api_key:
        raise RuntimeError(
            "HUGGINGFACE_API_TOKEN is not set. The biomedical literature-contradiction "
            "LLM path requires a free HuggingFace account + access token — set the "
            "environment variable before calling it (or use LITERATURE_LLM_PROVIDER=groq, "
            "the default, which does not need this token)."
        )

    response = requests.post(
        HUGGINGFACE_ROUTER_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": f"{BIOMEDICAL_LLM_MODEL}:{BIOMEDICAL_LLM_INFERENCE_PROVIDER}",
            "messages": messages,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"] or ""
