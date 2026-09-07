"""
Evidence Momentum / Trend Signal — your own contribution, not from OTP.

Purely derived from real, timestamped EvidenceRecord rows already in this
database (real publication years, real trial-start years — see
app/db/models.py's EvidenceRecord.publication_year docstring for exactly
which real sources populate this and which don't). No LLM involvement, no
prediction of future interest — a deterministic summary of a real,
already-happened trend in how much evidence has accumulated year over
year, the same "deterministic modules compute every number" principle
this whole project follows everywhere else.

DELIBERATELY KEPT OUT of gap_taxonomy.py and PriorityScore/priority_score
(explicit instruction, and a real point worth stating plainly): momentum
is independent of evidence QUALITY. A declining trend does not mean the
evidence is weak — it might mean the scientific question is settled, or
that translational focus has moved to later-stage validation instead of
new discovery publications. Wiring this into the priority score or the
gap taxonomy would conflate "is this well-evidenced" with "is this
currently fashionable," which are different questions — kept as a
separate, purely informational dimension (its own table,
app.db.models.MomentumScore, not a PriorityScore column).
"""

from collections import defaultdict
from dataclasses import dataclass

from app.config import (
    MOMENTUM_RECENT_WINDOW_YEARS, MOMENTUM_PRIOR_WINDOW_YEARS,
    MOMENTUM_ACCELERATING_THRESHOLD, MOMENTUM_DECLINING_THRESHOLD,
)
from app.db.models import EvidenceRecord


@dataclass
class MomentumResult:
    yearly_counts: dict          # {"2021": 5, "2022": 12, ...} — combined across all dated dimensions
    yearly_counts_by_dimension: dict  # {"literature": {"2021": 5, ...}, "human_clinical": {...}}
    trend: str                   # "accelerating" | "stable" | "declining" | "emerging" | "insufficient_data"
    momentum_score: float | None  # None for "emerging"/"insufficient_data" — no real ratio to report
    recent_window_count: int
    prior_window_count: int
    reference_year: int | None   # the real max year found in this target's own dated evidence; None if no dated evidence exists at all


def compute_momentum(target_id: int, db) -> MomentumResult:
    """
    Group this target's real, dated EvidenceRecord rows by year (and by
    dimension), and compute a simple, factual recent-vs-prior trend.

    "Now" is anchored on the real maximum publication_year actually
    present in this target's own data, NOT wall-clock date — deliberately
    (see config.py's comment on MOMENTUM_RECENT_WINDOW_YEARS): using
    today's real calendar year would read completely real, unremarkable
    PubMed/ingestion indexing lag as "every target is declining," which
    would be a misleading artifact of when this pipeline was last run,
    not a real signal about scientific interest.

    "emerging" (this task's own definition: very few/no older records but
    a real recent spike) is handled as its own case, not as a very high
    ratio — a zero-record prior window makes the ratio mathematically
    undefined (division by zero), not infinite, so it is deliberately not
    forced through the same accelerating/stable/declining partition.
    """
    records = (
        db.query(EvidenceRecord)
        .filter(EvidenceRecord.target_id == target_id, EvidenceRecord.publication_year.isnot(None))
        .all()
    )

    yearly_counts: dict[str, int] = defaultdict(int)
    yearly_counts_by_dimension: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in records:
        year_key = str(r.publication_year)
        yearly_counts[year_key] += 1
        yearly_counts_by_dimension[r.dimension][year_key] += 1

    if not yearly_counts:
        return MomentumResult(
            yearly_counts={},
            yearly_counts_by_dimension={},
            trend="insufficient_data",
            momentum_score=None,
            recent_window_count=0,
            prior_window_count=0,
            reference_year=None,
        )

    reference_year = max(int(y) for y in yearly_counts)

    recent_years = {str(y) for y in range(reference_year - MOMENTUM_RECENT_WINDOW_YEARS + 1, reference_year + 1)}
    prior_years = {
        str(y) for y in range(
            reference_year - MOMENTUM_RECENT_WINDOW_YEARS - MOMENTUM_PRIOR_WINDOW_YEARS + 1,
            reference_year - MOMENTUM_RECENT_WINDOW_YEARS + 1,
        )
    }
    recent_count = sum(yearly_counts.get(y, 0) for y in recent_years)
    prior_count = sum(yearly_counts.get(y, 0) for y in prior_years)

    if prior_count == 0:
        trend = "emerging" if recent_count > 0 else "insufficient_data"
        momentum_score = None
    else:
        momentum_score = round(recent_count / prior_count, 4)
        if momentum_score > MOMENTUM_ACCELERATING_THRESHOLD:
            trend = "accelerating"
        elif momentum_score < MOMENTUM_DECLINING_THRESHOLD:
            trend = "declining"
        else:
            trend = "stable"

    return MomentumResult(
        yearly_counts=dict(sorted(yearly_counts.items())),
        yearly_counts_by_dimension={dim: dict(sorted(counts.items())) for dim, counts in yearly_counts_by_dimension.items()},
        trend=trend,
        momentum_score=momentum_score,
        recent_window_count=recent_count,
        prior_window_count=prior_count,
        reference_year=reference_year,
    )
