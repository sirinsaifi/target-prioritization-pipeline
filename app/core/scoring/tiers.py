"""
Shared High/Medium/Low tiering — the ONE real implementation multiple
features reuse, so they can never silently drift apart on what "High
consistency" or "High maturity" means:

- app/core/narration/agent_narrator.py's "Why This Target?" (confidence/
  evidence_maturity labels).
- app/core/classification/translational_opportunity.py's Translational
  Opportunity classifier (priority/maturity tiers).
- The frontend mirrors these same VALUES independently in
  figma_frontend/.../api.ts (consistencyTier()/maturityTier()/
  priorityTier()) since it can't import Python — if these thresholds ever
  change, that mirror must be updated to match.

Purely deterministic threshold comparisons — never LLM-influenced, never
computed from anything but the three already-established config
constants pairs below.
"""

from app.config import (
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_LOW_THRESHOLD,
    MATURITY_HIGH_THRESHOLD, MATURITY_LOW_THRESHOLD,
    EVIDENCE_STRENGTH_HIGH_THRESHOLD, EVIDENCE_CONSISTENCY_GAP_THRESHOLD,
)


def tier_from_thresholds(value: float | None, high: float, low: float) -> str:
    if value is None:
        return "Low"
    if value >= high:
        return "High"
    if value < low:
        return "Low"
    return "Medium"


def confidence_tier(evidence_consistency: float | None) -> str:
    """Mirrors config.CONFIDENCE_HIGH_THRESHOLD (0.8) / CONFIDENCE_LOW_THRESHOLD (0.5)."""
    return tier_from_thresholds(evidence_consistency, CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_LOW_THRESHOLD)


def maturity_tier(evidence_maturity: float | None) -> str:
    """Mirrors config.MATURITY_HIGH_THRESHOLD (0.9) / MATURITY_LOW_THRESHOLD (0.4)."""
    return tier_from_thresholds(evidence_maturity, MATURITY_HIGH_THRESHOLD, MATURITY_LOW_THRESHOLD)


def priority_tier(priority_score: float | None) -> str:
    """
    Priority is NOT the same metric confidence/maturity were calibrated
    for: priority_score = (evidence_strength + evidence_consistency +
    evidence_maturity) / 3 (see app/api/routes/scoring.py), a broader
    composite. Deliberately uses a DIFFERENT, already-established pair —
    EVIDENCE_STRENGTH_HIGH_THRESHOLD (0.7) / EVIDENCE_CONSISTENCY_GAP_
    THRESHOLD (0.5) — this codebase's own "strong enough"/"concerning"
    bars (used throughout gap_taxonomy.py), not the consistency-specific
    0.8 cutoff. Matches the fix already applied to the frontend's own
    priorityTier() after a real rounding-before-comparing bug was found
    and corrected there.
    """
    return tier_from_thresholds(priority_score, EVIDENCE_STRENGTH_HIGH_THRESHOLD, EVIDENCE_CONSISTENCY_GAP_THRESHOLD)
