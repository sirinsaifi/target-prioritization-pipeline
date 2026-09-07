"""
Orchestration layer: gathers the deterministic outputs for a target (via
app.agent.tools) and produces an explainable narrative grounded in them.

Design principle (CLAUDE.md): this layer explains, it does not compute. The
default narrator below (`_template_narrate`) is a deterministic template —
every number it prints is read directly from `build_context()`'s output,
never derived or guessed here. This keeps the "never invent numbers"
guarantee true even without a real LLM wired in (no API key is configured
in this environment/prototype yet).

Swapping in a real LLM call is a drop-in change: write a function with the
same signature as `_template_narrate` (takes the context dict, returns a
string) and pass it as `narrator=` to `generate_target_narrative()`. Such a
function must still treat `context` as the ONLY source of facts — the
prompt it builds should explicitly forbid the model from stating any
number, gene name, or evidence claim not present in `context`, and any
proposed *new* finding (e.g. a candidate contradiction spotted in free
text) must go back through the deterministic verification layer before
being reported as confirmed (see CLAUDE.md "Core design principle").
"""

import json

from sqlalchemy.orm import Session

from app.agent import tools


def _safe_json(raw: str | None) -> dict:
    try:
        return json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}


def build_context(db: Session, target_id: int) -> dict | None:
    """
    Assemble every deterministic fact needed to narrate this target, in one
    place, so any narrator (template or LLM-backed) has a single, auditable
    input — no other data access should happen once this dict is built.
    """
    target = tools.get_target(db, target_id)
    if target is None:
        return None

    priority = tools.get_latest_priority_score(db, target_id)

    return {
        "gene_symbol": target.gene_symbol,
        "ensembl_id": target.ensembl_id,
        "disease_efo_id": target.disease_efo_id,
        "has_scores": priority is not None,
        "evidence_strength": priority.evidence_strength if priority else None,
        "evidence_consistency": priority.evidence_consistency if priority else None,
        "evidence_maturity": priority.evidence_maturity if priority else None,
        "priority_score": priority.priority_score if priority else None,
        "dimension_breakdown": _safe_json(priority.dimension_breakdown) if priority else {},
        "evidence_record_counts": tools.get_evidence_dimension_counts(db, target_id),
        "contradictions": tools.get_contradiction_summary(db, target_id),
        "gaps": tools.get_gaps(db, target_id),
    }


def _template_narrate(context: dict | None) -> str:
    """
    Deterministic fallback narrator — pure string formatting over `context`,
    no computation. Every sentence traces back to a specific field already
    present in `context`; nothing here is inferred, estimated, or invented.
    """
    if context is None:
        return "Target not found."

    gene = context["gene_symbol"]

    if not context["has_scores"]:
        return f"{gene}: no scores computed yet. Run POST /scoring/target/{{id}}/compute first."

    lines = [
        f"{gene} ({context['ensembl_id']}) vs {context['disease_efo_id']} — Evidence Profile",
        f"  Strength: {context['evidence_strength']:.2f}  "
        f"Consistency: {context['evidence_consistency']:.2f}  "
        f"Maturity: {context['evidence_maturity']:.2f}  "
        f"(composite priority: {context['priority_score']:.2f})",
    ]

    if context["dimension_breakdown"]:
        dims = ", ".join(f"{d}={s:.2f}" for d, s in context["dimension_breakdown"].items())
        lines.append(f"  Per-dimension scores: {dims}")

    counts = context["evidence_record_counts"]
    if counts:
        breakdown = ", ".join(f"{n} {d}" for d, n in counts.items())
        lines.append(f"  Evidence records: {breakdown}")

    contra = context["contradictions"]
    if contra["total_logged"] == 0:
        lines.append("  No contradictions logged (either none found, or the classifier has not been run for this target).")
    else:
        cls_summary = ", ".join(f"{n} {c}" for c, n in contra["counts"].items())
        lines.append(f"  Contradictions: {cls_summary} ({contra['total_logged']} total logged)")

    if context["gaps"]:
        for g in context["gaps"]:
            lines.append(f"  Gap [{g['gap_type']}]: {g['investigation_suggestion']}")
    else:
        lines.append("  No research gaps identified (or gap analysis has not been run for this target).")

    return "\n".join(lines)


def generate_target_narrative(db: Session, target_id: int, narrator=_template_narrate) -> dict:
    """
    Build context and narrate it. `narrator` is swappable — pass a function
    with the same signature as `_template_narrate` (e.g. a real LLM call
    grounded strictly to `context`) to upgrade narration quality without
    changing what data it's allowed to see.
    """
    context = build_context(db, target_id)
    narrative = narrator(context)
    return {"context": context, "narrative": narrative}
