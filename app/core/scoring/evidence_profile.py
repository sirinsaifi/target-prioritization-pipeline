"""
Evidence Profile — Consistency and Maturity scoring.

Kept explicitly separate from Evidence Strength (harmonic_sum.py) per the
project's design principle: Strength / Consistency / Maturity are reported
as three distinct, non-collapsed numbers, not merged into one score. This
is one of the project's original contributions (see CLAUDE.md).

Neither formula comes from OTP — OTP does not publish a per-target
consistency or maturity score. Both are original, documented here with
their rationale so they're auditable/falsifiable rather than ad hoc.
"""

from collections import Counter
from math import comb

from app.config import CONTRADICTION_SEVERITY_WEIGHTS, DIMENSION_MATURITY_LADDER


def comparable_pair_count(source_types: list) -> int:
    """
    Total within-source-type pairs among a set of evidence records — the
    same "only compare within the same group" rule the contradiction
    classifier applies (its step 0). Used as the Consistency denominator, so
    cross-type pairs — which were never a real comparability attempt — don't
    dilute the score in either direction.
    """
    group_sizes = Counter(t for t in source_types if t)
    return sum(comb(n, 2) for n in group_sizes.values())


def compute_evidence_consistency(classification_counts: dict, total_within_type_pairs: int) -> float:
    """
    STRUCTURED-evidence Consistency sub-score: how much confirmed conflict
    exists among structured (genetic/experimental/clinical) evidence pairs,
    relative to how many such pairs were actually comparable (the
    contradiction classifier's own within-source-type rule — see
    comparable_pair_count() above).

    Severity weighting (see CONTRADICTION_SEVERITY_WEIGHTS): a direct
    contradiction (same context, opposite direction) is the strongest
    signal of a genuine conflict; population-heterogeneity and
    methodological-disagreement are softer, explainable by real context
    differences rather than a true conflict; unclassified sits in between.

    Returns 1.0 (fully consistent) when there are no comparable pairs at
    all — absence of an opportunity to conflict isn't evidence of conflict.

    Deliberately does NOT accept `literature_contradiction` counts here —
    see compute_literature_consistency() and combine_consistency_scores()
    below. Structured pairs are ALL real comparable pairs among direction-
    labeled records (an exhaustive count); literature pairs (Phase 7's
    proposer/verifier) are a small, deliberately bounded SAMPLE
    (config.LITERATURE_CONTRADICTION_MAX_RECORDS), not every real literature
    pair for the target. Pooling their raw counts into one denominator
    would silently treat "we checked 10 of a possible ~24,000 pairs" as
    equivalent evidence weight to "we checked every real structured pair" —
    dividing each classification's own weighted-conflict count by its OWN
    correctly-scoped denominator first, then combining the two resulting
    scores (not the raw counts) by how much real evidence backed each, is
    what actually respects that difference.
    """
    if total_within_type_pairs <= 0:
        return 1.0

    weighted_conflict = sum(
        CONTRADICTION_SEVERITY_WEIGHTS.get(classification, 0.0) * count
        for classification, count in classification_counts.items()
        if classification != "literature_contradiction"
    )
    consistency = 1.0 - (weighted_conflict / total_within_type_pairs)
    return round(max(0.0, min(1.0, consistency)), 4)


def compute_literature_consistency(literature_contradiction_count: int, literature_pairs_evaluated: int) -> float:
    """
    LITERATURE-evidence Consistency sub-score — same formula shape as
    compute_evidence_consistency(), applied to Phase 7's literature
    contradiction proposer/verifier output instead of the structured
    classifier's. `literature_pairs_evaluated` is the real number of
    excerpt pairs the proposer actually examined for this target (bounded
    by config.LITERATURE_CONTRADICTION_MAX_RECORDS — see
    app/api/routes/scoring.py for how this is reproduced deterministically
    from stored EvidenceRecord.abstract_text), NOT comparable_pair_count()'s
    structured-pair denominator.

    Returns 1.0 when no literature pairs were ever evaluated for this
    target (the literature-contradiction route hasn't been run yet, or no
    literature records had fetchable abstract text) — same "no opportunity
    to conflict isn't evidence of conflict" convention as the structured
    score, and the reason this sub-score is a safe no-op by construction
    whenever Phase 7's route hasn't been exercised for a target.
    """
    if literature_pairs_evaluated <= 0:
        return 1.0

    weight = CONTRADICTION_SEVERITY_WEIGHTS.get("literature_contradiction", 1.0)
    weighted_conflict = weight * literature_contradiction_count
    consistency = 1.0 - (weighted_conflict / literature_pairs_evaluated)
    return round(max(0.0, min(1.0, consistency)), 4)


def combine_consistency_scores(
    structured_consistency: float, structured_pair_count: int,
    literature_consistency: float, literature_pair_count: int,
) -> float:
    """
    Combines the two Consistency sub-scores into the single
    `evidence_consistency` number the rest of the pipeline (composite
    priority_score, the Evidence-Consistency gap) still expects — the
    single-number contract everywhere else in this codebase is unchanged,
    only how it's assembled changed.

    Weighted by how much real evidence backed each sub-score (its own pair
    count), NOT a plain average of the two scores — a literature check
    that only ever examines a handful of pairs (see
    compute_literature_consistency()'s docstring) should not be able to
    move the overall score as much as a structured check backed by
    hundreds of real comparable pairs. When one side has zero pairs, this
    reduces to exactly the other side's score — the literature-aware
    formula is a strict superset of the pre-Phase-7 behavior, not a
    replacement of it; a target that has never had the literature route
    run for it scores identically to before this change.
    """
    total_pairs = structured_pair_count + literature_pair_count
    if total_pairs <= 0:
        return 1.0

    weighted = (
        structured_pair_count * structured_consistency + literature_pair_count * literature_consistency
    ) / total_pairs
    return round(max(0.0, min(1.0, weighted)), 4)


def compute_evidence_maturity(dimensions_with_evidence: set) -> float:
    """
    Evidence Maturity: how far along the translational-evidence ladder a
    target's evidence reaches (see DIMENSION_MATURITY_LADDER). Uses the
    single most advanced dimension reached, not an average or count, since
    maturity is about how far the evidence has progressed, not how many
    dimensions happen to have data.
    """
    if not dimensions_with_evidence:
        return 0.0
    return max(DIMENSION_MATURITY_LADDER.get(d, 0.0) for d in dimensions_with_evidence)
