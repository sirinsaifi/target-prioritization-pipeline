"""
Literature contradiction verifier — the deterministic rule layer that must
confirm an LLM-proposed literature contradiction before it is trusted (Stage
5: "LLM proposes -> deterministic rule layer checks true comparability").
See literature_contradiction_proposer.py for the proposal step this
verifies; nothing here calls an LLM, and every check is a plain, auditable
Python condition — same "deterministic modules compute every number/verdict"
principle as app/core/verification/contradiction_classifier.py.

What this actually checks, deliberately narrow and mechanical: both
EvidenceRecord rows genuinely belong to the SAME target (i.e. the same
gene+disease pair — Target already pins both, so this is one equality
check, not a fuzzy text-similarity judgment), both rows have real,
non-empty abstract text (never verify a contradiction proposed over missing
or empty text), both are real literature-dimension rows (not accidentally
handed a genetic/clinical record), and the proposer's own classification is
literally "CONTRADICT" (SUPPORT/UNRELATED are not contradiction candidates
at all — see the route, which never calls this verifier for those).
"""

from dataclasses import dataclass

from app.db.models import EvidenceRecord


@dataclass
class VerificationResult:
    verified: bool
    reason: str


def verify_literature_contradiction(
    record_a: EvidenceRecord, record_b: EvidenceRecord, proposed_classification: str | None,
) -> VerificationResult:
    """
    Deterministic checks only — no LLM call. Returns verified=True only if
    every real, checkable condition holds; otherwise verified=False with a
    plain-English reason naming exactly which check failed, so a rejected
    proposal is always explainable, not just discarded silently.
    """
    if proposed_classification != "CONTRADICT":
        return VerificationResult(
            verified=False,
            reason=f"Proposer's classification was {proposed_classification!r}, not CONTRADICT — nothing to verify.",
        )

    if record_a.target_id != record_b.target_id:
        return VerificationResult(
            verified=False,
            reason=(
                f"Records belong to different targets (target_id {record_a.target_id} vs "
                f"{record_b.target_id}) — not genuinely about the same gene and disease."
            ),
        )

    if record_a.dimension != "literature" or record_b.dimension != "literature":
        return VerificationResult(
            verified=False,
            reason=(
                f"Expected both records to be dimension='literature', got "
                f"{record_a.dimension!r} and {record_b.dimension!r}."
            ),
        )

    if not (record_a.abstract_text and record_a.abstract_text.strip()):
        return VerificationResult(verified=False, reason="Record A has no real abstract text to verify against.")
    if not (record_b.abstract_text and record_b.abstract_text.strip()):
        return VerificationResult(verified=False, reason="Record B has no real abstract text to verify against.")

    return VerificationResult(
        verified=True,
        reason=(
            f"Same target_id ({record_a.target_id}, same gene+disease pair), both records are "
            f"real dimension='literature' rows with non-empty real abstract text, and the "
            f"proposer's classification was CONTRADICT."
        ),
    )
