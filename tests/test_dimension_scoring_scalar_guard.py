"""
Regression tests for the 4th list-vs-scalar risk flagged during the
Parkinson's Disease smoke test bug-fix follow-up (see CLAUDE.md):
score_clinical_precedence() and score_drug_target() both look up a single
clinical-stage string in CLINICAL_STAGE_SCORES. Unlike the field-builder
comparability fields in scripts/ingest_evidence.py (which join list values
into a scalar string via _scalarize()), a scoring function silently
joining a list-valued stage would produce a lookup key that matches
nothing in CLINICAL_STAGE_SCORES and fall back to "unknown" — silently
under-scoring real evidence rather than surfacing a real upstream
data-shape problem. These two functions raise TypeError instead.
"""

import pytest

from app.core.scoring.dimension_scoring import score_clinical_precedence, score_drug_target


def test_score_clinical_precedence_raises_on_list_valued_stage():
    with pytest.raises(TypeError, match="score_clinical_precedence"):
        score_clinical_precedence(["phase_2", "phase_3"])


def test_score_clinical_precedence_still_handles_scalar_stage():
    assert score_clinical_precedence("phase_2") == 0.2


def test_score_drug_target_raises_on_list_valued_stage():
    with pytest.raises(TypeError, match="score_drug_target"):
        score_drug_target(["phase_2", "phase_3"])


def test_score_drug_target_still_handles_scalar_stage():
    assert score_drug_target("phase_3") == 0.7


def test_score_drug_target_still_handles_none():
    assert score_drug_target(None) == 0.01
