"""
Harmonic sum aggregation — reference: Open Targets Platform documentation,
platform-docs.opentargets.org/associations

Method:
1. Sort evidence scores descending, assign positional id (1, 2, 3, ...).
2. Sum each score divided by (position^2).
3. Normalize by dividing by the max theoretical harmonic sum (an infinite
   vector of 1.0s converges to ~1.644; approximated here with a finite sum).

This rewards having several independent supporting pieces of evidence, with
steeply diminishing returns for each additional one — a single strong piece
of evidence dominates the score more than many weak, repeated ones.
"""

from app.config import HARMONIC_SUM_NORMALIZATION_TERMS


def _max_theoretical_harmonic_sum(n_terms: int = HARMONIC_SUM_NORMALIZATION_TERMS) -> float:
    """Sum of 1/position^2 for position 1..n_terms. Converges to pi^2/6 ~= 1.6449."""
    return sum(1.0 / (i ** 2) for i in range(1, n_terms + 1))


# Precomputed once at import time
MAX_THEORETICAL_HARMONIC_SUM = _max_theoretical_harmonic_sum()


def harmonic_sum_score(evidence_scores: list[float]) -> float:
    """
    Combine a list of individual evidence scores (each already 0-1) into a
    single normalized score between 0 and 1, using OTP's harmonic-sum method.

    Example (from OTP docs): scores [1.0, 0.9, 0.8] ->
        1.0/1^2 + 0.9/2^2 + 0.8/3^2 = 1.314
        1.314 / 1.644 ~= 0.80
    """
    if not evidence_scores:
        return 0.0

    sorted_scores = sorted(evidence_scores, reverse=True)
    raw_sum = sum(score / (position ** 2) for position, score in enumerate(sorted_scores, start=1))

    return round(raw_sum / MAX_THEORETICAL_HARMONIC_SUM, 4)


def harmonic_sum_score_scaled_for_type(evidence_scores: list[float]) -> float:
    """
    Data-type-level variant: when combining scores from a small, fixed number
    of sources (e.g. within one evidence dimension), OTP scales the
    normalization constant to the number of sources present, so a dimension
    with only one source isn't unfairly penalized relative to one with many.

    Reference: platform-docs.opentargets.org/associations
    ("Association score by data type scaling")
    """
    if not evidence_scores:
        return 0.0

    n = len(evidence_scores)
    sorted_scores = sorted(evidence_scores, reverse=True)
    raw_sum = sum(score / (position ** 2) for position, score in enumerate(sorted_scores, start=1))
    scaling_factor = sum(1.0 / (i ** 2) for i in range(1, n + 1))

    return round(raw_sum / scaling_factor, 4)


if __name__ == "__main__":
    # Quick sanity check against the worked example in OTP's own documentation
    example = [1.0, 0.9, 0.8]
    result = harmonic_sum_score(example)
    print(f"harmonic_sum_score({example}) = {result}  (OTP docs example ~= 0.80)")
