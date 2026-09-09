"""
Translational Opportunity — a lightweight, DETERMINISTIC, rule-based
category synthesizing values this project ALREADY computes elsewhere:
Priority Score, Evidence Maturity, open Research Gaps, real drug/clinical
evidence presence, and real caution flags (safety_signal/essentiality_risk).

EXPLICITLY A PROTOTYPE FRAMEWORK, NOT A VALIDATED BUSINESS SCORE — every
TranslationalOpportunity carries `is_prototype=True` unconditionally, and
every rationale is a fixed, gene-agnostic template (only {gene}/real
numbers are interpolated), never LLM-generated. This module computes
NOTHING new: every input field was already produced by PriorityScore
(app/api/routes/scoring.py), GapRecord (app/core/gaps/gap_taxonomy.py), or
a real EvidenceRecord presence check (app/api/routes/gaps.py) — this is
purely a combination/labeling layer on top of already-real numbers.

DESIGN REQUIREMENT, enforced structurally, not just by convention: a
target with a real caution flag (documented safety event OR essentiality
risk) can NEVER be classified into a purely positive category. Rule 1
below checks for caution flags FIRST, before any other rule — a caution-
flagged target always lands in "De-risking Needed" regardless of how
strong its priority/maturity/clinical evidence otherwise looks, and the
rationale explicitly states both facts (what's strong AND what the real
flag is) so a reader is never misled into reading this as "weak evidence"
when the underlying evidence may in fact be excellent (see the real SOD1
case below).

Four categories, evaluated in this fixed order (first match wins) —
EXPLICIT, DOCUMENTED rule boundaries, not left implicit:

1. "De-risking Needed" — has_safety_signal OR has_essentiality_risk is
   True. Always wins over every other rule.
2. "Clinical-Stage" — has_known_compound AND has_human_clinical_evidence
   are both True (a real compound AND real human/clinical evidence exist
   — this target has reached actual translational testing).
3. "Preclinical High-Confidence" — priority_tier == "High" AND
   maturity_tier in ("High", "Medium") AND no open evidence-completeness
   gaps remain, but Clinical-Stage's condition was NOT met (no known
   compound/clinical evidence yet) — a well-supported candidate that
   simply hasn't reached the clinic.
4. "Early-Stage Discovery" (fallback) — everything else: lower priority/
   maturity and/or real open evidence-completeness gaps remain.

Priority/Maturity tiers reuse the SAME thresholds already established for
"Why This Target?" (app/core/scoring/tiers.py) — not a new threshold
family invented for this feature.

Real, live-verified result across the 5 ALS candidates (see this
module's own test file / CLAUDE.md for the exact numbers): 3 of the 4
categories are genuinely exercised by real current data (2 De-risking
Needed, 2 Clinical-Stage, 1 Early-Stage Discovery) — "Preclinical
High-Confidence" is real and tested but not hit by any of the 5 real
genes today, same "real but currently unexercised" status as several
other features in this project.
"""

from dataclasses import dataclass, field

from app.core.scoring.tiers import priority_tier, maturity_tier

CATEGORIES = ["De-risking Needed", "Clinical-Stage", "Preclinical High-Confidence", "Early-Stage Discovery"]


@dataclass
class TranslationalOpportunityInput:
    """
    Minimal real inputs needed to classify one target. Every field here is
    already computed elsewhere — this module combines, it never queries a
    database or computes a new number.
    """
    gene_symbol: str
    priority_score: float | None       # raw 0-1, PriorityScore.priority_score
    evidence_maturity: float | None    # raw 0-1, PriorityScore.evidence_maturity
    has_known_compound: bool = False
    has_human_clinical_evidence: bool = False
    has_safety_signal: bool = False
    safety_signal_events: list = field(default_factory=list)
    has_essentiality_risk: bool = False
    essentiality_risk_note: str | None = None
    # Real open gap TYPES, EVIDENCE-COMPLETENESS gaps only (mechanistic,
    # population, modality, validation, evidence_consistency) — safety_signal/
    # essentiality_risk are read from the dedicated flags above instead,
    # same "risk flag, not a coverage gap" distinction
    # config.WHY_THIS_TARGET_UNCERTAINTY_EXCLUDED_GAP_TYPES already
    # established for "Why This Target?"'s own main-uncertainty selection.
    open_evidence_gap_types: list = field(default_factory=list)


@dataclass
class TranslationalOpportunity:
    category: str
    rationale: str
    is_prototype: bool = True  # ALWAYS True — see module docstring


def classify_translational_opportunity(inp: TranslationalOpportunityInput) -> TranslationalOpportunity:
    g = inp.gene_symbol
    p_tier = priority_tier(inp.priority_score)
    m_tier = maturity_tier(inp.evidence_maturity)
    p_score = inp.priority_score if inp.priority_score is not None else 0.0
    m_score = inp.evidence_maturity if inp.evidence_maturity is not None else 0.0

    # Rule 1 — De-risking Needed. ALWAYS evaluated first, and ALWAYS wins
    # over every rule below — see module docstring's design requirement.
    if inp.has_safety_signal or inp.has_essentiality_risk:
        flags = []
        if inp.has_safety_signal:
            events_text = ", ".join(inp.safety_signal_events) or "see detail"
            flags.append(f"documented safety event(s): {events_text}")
        if inp.has_essentiality_risk:
            flags.append("flagged essential by Open Targets/DepMap")
        return TranslationalOpportunity(
            "De-risking Needed",
            f"{g} shows {p_tier.lower()} priority ({p_score:.2f}) and {m_tier.lower()} evidence maturity, but "
            f"carries {len(flags)} real caution flag(s) — {'; '.join(flags)} — that must be weighed before "
            f"advancing. This does not mean the underlying evidence is weak; it means a real, documented risk "
            f"factor exists alongside it and must stay visible, never averaged away.",
        )

    # Rule 2 — Clinical-Stage.
    if inp.has_known_compound and inp.has_human_clinical_evidence:
        return TranslationalOpportunity(
            "Clinical-Stage",
            f"{g} has a real known compound and real human/clinical evidence on record, with {m_tier.lower()} "
            f"evidence maturity — already in active clinical/translational development, not a discovery-stage "
            f"hypothesis.",
        )

    # Rule 3 — Preclinical High-Confidence.
    if p_tier == "High" and m_tier in ("High", "Medium") and not inp.open_evidence_gap_types:
        return TranslationalOpportunity(
            "Preclinical High-Confidence",
            f"{g} shows {p_tier.lower()} priority ({p_score:.2f}) and {m_tier.lower()} evidence maturity with no "
            f"unresolved evidence gaps, but no known compound or human/clinical evidence exists yet — a strong "
            f"discovery-stage candidate that has not yet reached translational testing.",
        )

    # Rule 4 — Early-Stage Discovery (fallback).
    if inp.open_evidence_gap_types:
        gaps_text = f"{len(inp.open_evidence_gap_types)} open evidence gap(s) ({', '.join(inp.open_evidence_gap_types)})"
    else:
        gaps_text = "no open evidence gaps, but priority and/or maturity have not yet reached the high tier"
    return TranslationalOpportunity(
        "Early-Stage Discovery",
        f"{g} shows {p_tier.lower()} priority ({p_score:.2f}) and {m_tier.lower()} evidence maturity, with "
        f"{gaps_text} — earlier-stage discovery work relative to a clinical-stage or high-confidence preclinical "
        f"candidate.",
    )
