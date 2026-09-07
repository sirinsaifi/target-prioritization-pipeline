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

GROQ_MODEL = "openai/gpt-oss-20b"


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
