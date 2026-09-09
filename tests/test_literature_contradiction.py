"""
Tests for Phase 7: the literature contradiction proposer/verifier pipeline
(app/core/verification/literature_contradiction_proposer.py,
_verifier.py, and POST /contradictions/target/{id}/run-literature).

All LLM-touching tests mock `call_llm_plain` (the one function that talks to
the network) — same pattern as tests/test_agent_narrator.py mocking
`_call_llm`. Real-LLM verification (a real contradiction pair and a real
non-contradiction pair, actually run against Groq) is done separately, live,
outside this file — see docs/07 Phase 7 for that output.
"""

import json
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.verification.literature_contradiction_proposer import (
    _parse_response, _configured_provider, propose_literature_contradiction,
)
from app.core.verification.literature_contradiction_verifier import verify_literature_contradiction
from app.core.scoring.evidence_profile import compute_evidence_consistency
from app.core.llm_client import call_llm_plain_biomedical, HUGGINGFACE_ROUTER_URL
from app.db.models import EvidenceRecord


def _make_groq_rate_limit_error():
    """A real groq.RateLimitError, constructed the way the groq SDK itself
    requires (message + a real httpx.Response) — used to simulate the
    documented, repeatedly-real 429 this project's free-tier Groq key hits
    (see CLAUDE.md)."""
    import groq

    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status_code=429, request=request, json={"error": {"message": "rate limit"}})
    return groq.RateLimitError("Rate limit reached", response=response, body=None)


# --- Plain-text response parsing (the design lesson from Phase 8: no JSON, no tool-calling) ---

def test_parse_response_extracts_classification_and_reason():
    raw = "CLASSIFICATION: CONTRADICT\nREASON: Excerpt B reports a protective effect while Excerpt A reports a risk effect."
    classification, reason = _parse_response(raw)
    assert classification == "CONTRADICT"
    assert reason.startswith("Excerpt B reports a protective effect")


def test_parse_response_is_case_insensitive_and_tolerates_extra_whitespace():
    raw = "  classification:   support  \n   reason:   Both excerpts agree.  "
    classification, reason = _parse_response(raw)
    assert classification == "SUPPORT"
    assert reason == "Both excerpts agree."


def test_parse_response_rejects_a_classification_word_outside_the_three_allowed():
    raw = "CLASSIFICATION: MAYBE\nREASON: Unclear relationship."
    classification, reason = _parse_response(raw)
    assert classification is None  # never guessed/defaulted to a "safe" value
    assert reason == "Unclear relationship."  # reason is still surfaced for debugging


def test_parse_response_returns_none_for_a_response_that_does_not_match_the_format_at_all():
    # e.g. the model ignored the format instruction entirely — must fail
    # the parse cleanly, not raise, not guess.
    classification, reason = _parse_response("I think these two excerpts might be related somehow.")
    assert classification is None
    assert reason is None


def test_parse_response_takes_only_the_first_line_of_a_reason_that_ran_on():
    raw = "CLASSIFICATION: UNRELATED\nREASON: They discuss different genes.\nExtra unrequested commentary here."
    _, reason = _parse_response(raw)
    assert reason == "They discuss different genes."


def test_parse_response_strips_a_leaked_chat_template_closing_tag():
    # Real artifact, found live testing the biomedical model
    # (Intelligent-Internet/II-Medical-8B via HuggingFace): it sometimes
    # wraps its reply in its own internal "<Answer>...</Answer>" tag; the
    # closing tag lands on the same line as REASON's text and must not leak
    # into the stored reason.
    raw = "<Answer>CLASSIFICATION: UNRELATED  \nREASON: Different topics entirely.</Answer>"
    classification, reason = _parse_response(raw)
    assert classification == "UNRELATED"
    assert reason == "Different topics entirely."


# --- propose_literature_contradiction(): plain-text call, no tool-calling involved ---

def test_propose_literature_contradiction_builds_the_exact_requested_prompt_and_parses_the_mocked_reply():
    with patch("app.core.verification.literature_contradiction_proposer.call_llm_plain") as mock_call:
        mock_call.return_value = "CLASSIFICATION: CONTRADICT\nREASON: Opposite direction of effect reported."
        result = propose_literature_contradiction(
            "SOD1", "Amyotrophic Lateral Sclerosis", "Excerpt text A here.", "Excerpt text B here.",
        )

    assert result["classification"] == "CONTRADICT"
    assert result["reason"] == "Opposite direction of effect reported."
    assert result["raw_response"] == mock_call.return_value

    mock_call.assert_called_once()
    (messages,) = mock_call.call_args[0]
    # No `tools` argument anywhere in this call — plain completion only,
    # the whole point of dodging Phase 8's tool-calling failure modes.
    assert "tools" not in mock_call.call_args.kwargs
    user_content = messages[1]["content"]
    assert "SOD1" in user_content
    assert "Amyotrophic Lateral Sclerosis" in user_content
    assert "Excerpt text A here." in user_content
    assert "Excerpt text B here." in user_content
    assert "CLASSIFICATION: <one word>" in user_content
    assert "REASON: <one sentence>" in user_content


def test_propose_literature_contradiction_handles_an_unparseable_reply_without_raising():
    with patch("app.core.verification.literature_contradiction_proposer.call_llm_plain") as mock_call:
        mock_call.return_value = "Sorry, I cannot classify this."
        result = propose_literature_contradiction("SOD1", "ALS", "text a", "text b")

    assert result["classification"] is None
    assert result["raw_response"] == "Sorry, I cannot classify this."


def test_propose_literature_contradiction_defaults_to_groq_provider(monkeypatch):
    monkeypatch.delenv("LITERATURE_LLM_PROVIDER", raising=False)
    with patch("app.core.verification.literature_contradiction_proposer.call_llm_plain") as mock_call:
        mock_call.return_value = "CLASSIFICATION: SUPPORT\nREASON: Same direction reported."
        result = propose_literature_contradiction("SOD1", "ALS", "text a", "text b")

    assert result["provider"] == "groq"
    mock_call.assert_called_once()


# --- Biomedical LLM option (new task): additional provider, not a
# replacement — see app/config.py's "biomedical LLM option" comment for the
# real, live-confirmed model-availability finding behind BIOMEDICAL_LLM_MODEL ---

def test_configured_provider_defaults_to_groq_when_env_var_unset(monkeypatch):
    monkeypatch.delenv("LITERATURE_LLM_PROVIDER", raising=False)
    assert _configured_provider() == "groq"


def test_configured_provider_reads_biomedical_from_env(monkeypatch):
    monkeypatch.setenv("LITERATURE_LLM_PROVIDER", "biomedical")
    assert _configured_provider() == "biomedical"


def test_configured_provider_is_case_insensitive_and_tolerates_whitespace(monkeypatch):
    monkeypatch.setenv("LITERATURE_LLM_PROVIDER", "  BioMedical  ")
    assert _configured_provider() == "biomedical"


def test_configured_provider_falls_back_to_groq_for_an_unrecognized_value(monkeypatch):
    # Never silently guess a provider the code doesn't actually implement.
    monkeypatch.setenv("LITERATURE_LLM_PROVIDER", "chatgpt")
    assert _configured_provider() == "groq"


def test_propose_literature_contradiction_uses_biomedical_llm_when_configured(monkeypatch):
    monkeypatch.setenv("LITERATURE_LLM_PROVIDER", "biomedical")
    with patch("app.core.verification.literature_contradiction_proposer._call_biomedical_llm") as mock_bio, \
         patch("app.core.verification.literature_contradiction_proposer.call_llm_plain") as mock_groq:
        mock_bio.return_value = "CLASSIFICATION: CONTRADICT\nREASON: Domain-specific reasoning here."
        result = propose_literature_contradiction("SOD1", "ALS", "text a", "text b")

    assert result["classification"] == "CONTRADICT"
    assert result["provider"] == "biomedical"
    mock_bio.assert_called_once()
    mock_groq.assert_not_called()  # groq path never touched at all when biomedical is configured


def test_propose_literature_contradiction_falls_back_to_biomedical_on_groq_rate_limit(monkeypatch):
    # The real, repeatedly-observed scenario this session (Groq's free-tier
    # 200,000 token/day cap hit mid-run) — with a biomedical fallback
    # configured (HUGGINGFACE_API_TOKEN present), the check must not simply
    # fail; it should transparently retry via the biomedical model.
    monkeypatch.delenv("LITERATURE_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("HUGGINGFACE_API_TOKEN", "fake-token-for-test")
    with patch("app.core.verification.literature_contradiction_proposer.call_llm_plain") as mock_groq, \
         patch("app.core.verification.literature_contradiction_proposer._call_biomedical_llm") as mock_bio:
        mock_groq.side_effect = _make_groq_rate_limit_error()
        mock_bio.return_value = "CLASSIFICATION: SUPPORT\nREASON: Both report the same risk direction."
        result = propose_literature_contradiction("SOD1", "ALS", "text a", "text b")

    assert result["classification"] == "SUPPORT"
    assert result["provider"] == "biomedical_fallback"
    mock_groq.assert_called_once()
    mock_bio.assert_called_once()


def test_propose_literature_contradiction_reraises_rate_limit_when_no_fallback_configured(monkeypatch):
    # No HUGGINGFACE_API_TOKEN at all -> nothing to fall back to; the real
    # error must propagate, never be swallowed into a fabricated result.
    monkeypatch.delenv("LITERATURE_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("HUGGINGFACE_API_TOKEN", raising=False)
    with patch("app.core.verification.literature_contradiction_proposer.call_llm_plain") as mock_groq, \
         patch("app.core.verification.literature_contradiction_proposer._call_biomedical_llm") as mock_bio:
        mock_groq.side_effect = _make_groq_rate_limit_error()
        with pytest.raises(Exception):  # groq.RateLimitError, re-raised unchanged
            propose_literature_contradiction("SOD1", "ALS", "text a", "text b")

    mock_bio.assert_not_called()


# --- call_llm_plain_biomedical(): the raw HuggingFace Inference Providers call ---

def test_call_llm_plain_biomedical_raises_without_a_token(monkeypatch):
    monkeypatch.delenv("HUGGINGFACE_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="HUGGINGFACE_API_TOKEN"):
        call_llm_plain_biomedical([{"role": "user", "content": "hi"}])


def test_call_llm_plain_biomedical_calls_the_router_and_parses_the_reply(monkeypatch):
    monkeypatch.setenv("HUGGINGFACE_API_TOKEN", "fake-token-for-test")

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "CLASSIFICATION: UNRELATED\nREASON: Different topic."}}]}

    with patch("requests.post") as mock_post:
        mock_post.return_value = FakeResponse()
        result = call_llm_plain_biomedical([{"role": "user", "content": "hi"}])

    assert result == "CLASSIFICATION: UNRELATED\nREASON: Different topic."
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == HUGGINGFACE_ROUTER_URL
    assert kwargs["headers"]["Authorization"] == "Bearer fake-token-for-test"
    assert ":" in kwargs["json"]["model"]  # "<hf_model_id>:<provider>" addressing


# --- verify_literature_contradiction(): deterministic, no LLM call ---

def _make_record(**overrides):
    defaults = dict(
        id=1, target_id=1, dimension="literature", data_source="europepmc",
        source_record_id="12345678", abstract_text="Some real abstract text.",
    )
    defaults.update(overrides)
    return EvidenceRecord(**defaults)


def test_verify_confirms_when_same_target_both_literature_both_have_real_text():
    a = _make_record(id=1)
    b = _make_record(id=2)
    result = verify_literature_contradiction(a, b, "CONTRADICT")
    assert result.verified is True
    assert "same target_id" in result.reason.lower() or "same target" in result.reason.lower()


def test_verify_rejects_when_classification_is_not_contradict():
    a, b = _make_record(id=1), _make_record(id=2)
    result = verify_literature_contradiction(a, b, "SUPPORT")
    assert result.verified is False
    assert "SUPPORT" in result.reason


def test_verify_rejects_records_from_different_targets():
    a = _make_record(id=1, target_id=1)
    b = _make_record(id=2, target_id=2)
    result = verify_literature_contradiction(a, b, "CONTRADICT")
    assert result.verified is False
    assert "different target" in result.reason.lower()


def test_verify_rejects_when_either_record_has_no_real_abstract_text():
    a = _make_record(id=1, abstract_text=None)
    b = _make_record(id=2)
    result = verify_literature_contradiction(a, b, "CONTRADICT")
    assert result.verified is False
    assert "abstract text" in result.reason.lower()


def test_verify_rejects_a_non_literature_record():
    a = _make_record(id=1, dimension="genetic")
    b = _make_record(id=2)
    result = verify_literature_contradiction(a, b, "CONTRADICT")
    assert result.verified is False
    assert "literature" in result.reason.lower()


# --- Consistency scoring isolation: literature_contradiction must NOT move the score ---

def test_literature_contradiction_classification_has_zero_weight_in_consistency_scoring():
    # Real correctness check: app/api/routes/scoring.py's Consistency
    # denominator (comparable_pair_count) never counts literature pairs
    # (they have no direction_on_trait), so a literature-sourced
    # contradiction must NOT be able to move the Consistency score until
    # that denominator is deliberately extended — see the route's
    # docstring. CONTRADICTION_SEVERITY_WEIGHTS has no "literature_
    # contradiction" entry, so it defaults to weight 0.0.
    consistency = compute_evidence_consistency({"literature_contradiction": 5}, total_within_type_pairs=10)
    assert consistency == 1.0


# --- Full route, real DB (in-memory), LLM mocked ---

@pytest.fixture
def client_with_test_db():
    from app.db.database import Base, get_db
    from app.main import app

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app), TestingSessionLocal
    app.dependency_overrides.clear()


def _seed_target_with_literature(SessionLocal, n=3, with_abstract=True):
    from app.db.models import Target
    db = SessionLocal()
    target = Target(gene_symbol="SOD1", ensembl_id="ENSG00000142168", disease_efo_id="MONDO_0004976")
    db.add(target)
    db.flush()
    for i in range(n):
        db.add(EvidenceRecord(
            target_id=target.id, dimension="literature", data_source="europepmc",
            source_record_id=f"1000000{i}", raw_value=1.0, evidence_score=1.0,
            abstract_text=f"Real abstract text number {i}." if with_abstract else None,
        ))
    db.commit()
    target_id = target.id
    db.close()
    return target_id


def test_route_logs_exactly_the_verified_contradict_pairs_and_reports_real_counts(client_with_test_db):
    client, SessionLocal = client_with_test_db
    target_id = _seed_target_with_literature(SessionLocal, n=3)

    # 3 records -> 3 pairs. Make exactly one CONTRADICT, rest SUPPORT/UNRELATED.
    responses = [
        "CLASSIFICATION: CONTRADICT\nREASON: Opposite direction reported.",
        "CLASSIFICATION: SUPPORT\nREASON: Same direction reported.",
        "CLASSIFICATION: UNRELATED\nREASON: Different topic entirely.",
    ]
    with patch("app.core.verification.literature_contradiction_proposer.call_llm_plain") as mock_call:
        mock_call.side_effect = responses
        response = client.post(f"/contradictions/target/{target_id}/run-literature")

    assert response.status_code == 200
    body = response.json()
    assert body["records_considered"] == 3
    assert body["pairs_evaluated"] == 3
    assert body["records_missing_abstract"] == 0
    assert body["proposals_rejected_by_verifier"] == 0
    assert len(body["contradictions"]) == 1
    logged = body["contradictions"][0]
    assert logged["classification"] == "literature_contradiction"
    assert logged["status"] == "confirmed"
    assert logged["proposed_by"] == "llm_proposer"
    assert "Opposite direction reported" not in (logged["verification_reason"] or "")  # verifier's own reason, not the LLM's


def test_route_fetches_and_persists_missing_abstract_text(client_with_test_db):
    client, SessionLocal = client_with_test_db
    target_id = _seed_target_with_literature(SessionLocal, n=2, with_abstract=False)

    with patch("app.api.routes.contradictions.get_abstract_text") as mock_fetch, \
         patch("app.core.verification.literature_contradiction_proposer.call_llm_plain") as mock_call:
        mock_fetch.return_value = "Fetched real abstract text."
        mock_call.return_value = "CLASSIFICATION: UNRELATED\nREASON: No overlap."
        response = client.post(f"/contradictions/target/{target_id}/run-literature")

    assert response.status_code == 200
    assert mock_fetch.call_count == 2  # both records lacked text, both fetched
    db = SessionLocal()
    records = db.query(EvidenceRecord).filter_by(target_id=target_id).all()
    assert all(r.abstract_text == "Fetched real abstract text." for r in records)
    db.close()


def test_route_404s_when_fewer_than_2_records_have_usable_abstract_text(client_with_test_db):
    client, SessionLocal = client_with_test_db
    target_id = _seed_target_with_literature(SessionLocal, n=2, with_abstract=False)

    with patch("app.api.routes.contradictions.get_abstract_text") as mock_fetch:
        mock_fetch.return_value = None  # simulate PMIDs with no fetchable real abstract
        response = client.post(f"/contradictions/target/{target_id}/run-literature")

    assert response.status_code == 404


def test_route_404s_for_unknown_target(client_with_test_db):
    client, _ = client_with_test_db
    response = client.post("/contradictions/target/999/run-literature")
    assert response.status_code == 404


def test_route_records_biomedical_provider_in_proposed_by(client_with_test_db, monkeypatch):
    # When the biomedical LLM actually produced the proposal, the persisted
    # row must say so — distinct from the default "llm_proposer" (Groq)
    # string, same self-describing convention as "structured_classifier" vs
    # "llm_proposer" already documented on ContradictionLog.
    monkeypatch.setenv("LITERATURE_LLM_PROVIDER", "biomedical")
    client, SessionLocal = client_with_test_db
    target_id = _seed_target_with_literature(SessionLocal, n=2)

    with patch("app.core.verification.literature_contradiction_proposer._call_biomedical_llm") as mock_bio:
        mock_bio.return_value = "CLASSIFICATION: CONTRADICT\nREASON: Opposite direction reported."
        response = client.post(f"/contradictions/target/{target_id}/run-literature")

    assert response.status_code == 200
    body = response.json()
    assert len(body["contradictions"]) == 1
    assert body["contradictions"][0]["proposed_by"] == "llm_proposer_biomedical"
