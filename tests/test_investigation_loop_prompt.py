"""
Regression test for disease-agnosticism of the autonomous investigation
loop's system prompt (app/agent/investigation_loop.py). A prior review
claimed a hardcoded "for ALS" string existed in SYSTEM_PROMPT_TEMPLATE; on
inspection no such string was found — SYSTEM_PROMPT_TEMPLATE already
interpolates `{disease}` and investigate_target()'s `disease` parameter has
no default, so it cannot silently fall back to any value. This test exists
to prove that (and guard against regression) rather than to fix a bug.
"""

from unittest.mock import patch

from app.agent.investigation_loop import SYSTEM_PROMPT_TEMPLATE, investigate_target

LEAKED_ALS_TERMS = ("ALS", "Amyotrophic", "Sclerosis", "SOD1", "C9orf72", "TARDBP", "NEK1")


def test_system_prompt_template_reflects_the_disease_passed_in_not_als():
    prompt = SYSTEM_PROMPT_TEMPLATE.format(gene="ZZZFAKE9", disease="Fictional Test Syndrome", max_iterations=6)
    assert "ZZZFAKE9" in prompt
    assert "Fictional Test Syndrome" in prompt
    for leaked in LEAKED_ALS_TERMS:
        assert leaked not in prompt


def test_investigate_target_sends_the_real_disease_to_the_llm_not_a_hardcoded_one():
    # Mock the one function that talks to the network (same pattern as
    # tests/test_agent_narrator.py) so this proves what's actually built
    # into the messages sent to the model, with no real API call.
    with patch("app.agent.investigation_loop.call_llm_with_tools") as mock_call:
        mock_call.return_value = {"role": "assistant", "content": "stub final message", "tool_calls": None}
        result = investigate_target("ZZZFAKE9", "Fictional Test Syndrome", max_iterations=2)

    assert result.stopped_reason == "model_stopped"
    mock_call.assert_called_once()
    messages, _tool_schemas = mock_call.call_args[0]
    system_message = messages[0]["content"]
    user_message = messages[1]["content"]

    assert "Fictional Test Syndrome" in system_message
    assert "Fictional Test Syndrome" in user_message
    for leaked in LEAKED_ALS_TERMS:
        assert leaked not in system_message
        assert leaked not in user_message
