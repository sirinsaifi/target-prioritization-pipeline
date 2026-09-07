"""
One-command demo setup: fresh, empty database -> seeded targets -> real
ingested evidence -> a fully analyzed (contradictions, scoring, gaps) demo
state for all 5 real ALS candidate genes.

Pure orchestration — every step below calls the SAME real function the
corresponding API route or script already uses (imported directly from
app/, not called over HTTP, so this works standalone without uvicorn
running). No new scoring/classification logic lives in this file.

Correct call order (see docs/07 Phase 10 follow-up): structured
contradictions BEFORE scoring (app/api/routes/scoring.py's own docstring:
Consistency reads whatever ContradictionLog rows already exist, it does
not run the classifier itself), scoring BEFORE gaps (POST
/gaps/target/{id}/run 400s without a PriorityScore already computed).

Like app/main.py, this script calls load_dotenv() itself, first — a
standalone script that never imports app.main does not get .env loaded for
free (see CLAUDE.md "Environment setup: python-dotenv + .env"), and
GROQ_API_KEY specifically is read from the environment by
app/core/llm_client.py.

Run:
    python -m scripts.setup_demo
"""

import os
import time

from dotenv import load_dotenv
load_dotenv()

from fastapi import HTTPException

from app.config import CANDIDATE_TARGETS
from app.db.database import SessionLocal, init_db
from app.db.models import Target, EvidenceRecord
from app.api.routes.targets import seed_targets
from app.api.routes.contradictions import run_contradiction_check, run_literature_contradiction_check
from app.api.routes.scoring import compute_scores
from app.api.routes.gaps import run_gap_analysis
from app.api.routes.momentum import get_momentum
from scripts.ingest_evidence import ingest_target

# Deliberate prototype-scale mitigation, not a full retry/backoff strategy
# (this file is orchestration, not new logic) — spaces out the real LLM
# calls POST /contradictions/target/{id}/run-literature makes across genes,
# reducing the chance of hitting Groq's documented free-tier rate limit
# (8,000 TPM on openai/gpt-oss-20b — see docs/07 Phase 7) when running all
# 5 genes back-to-back. Only applied when a real key is present.
LITERATURE_CHECK_SLEEP_SECONDS = 5


def _new_summary_row(gene_symbol: str) -> dict:
    return {
        "gene": gene_symbol,
        "priority_score": None,
        "contradictions": None,
        "gaps": None,
        "literature_check": None,
        "momentum_trend": None,
        "momentum_score": None,
        "error": None,
    }


def run_gene(db, index: int, total: int, gene_symbol: str, ensembl_id: str, groq_key_present: bool) -> dict:
    prefix = f"[{index}/{total}] {gene_symbol}"
    row = _new_summary_row(gene_symbol)

    try:
        print(f"{prefix}: ingesting evidence...")
        evidence_count = ingest_target(db, gene_symbol, ensembl_id)
        print(f"{prefix}: {evidence_count} evidence records ingested")

        target = db.query(Target).filter_by(ensembl_id=ensembl_id).first()
        target_id = target.id

        print(f"{prefix}: running structured contradiction check...")
        try:
            structured = run_contradiction_check(target_id, db)
            row["contradictions"] = len(structured)
        except HTTPException as exc:
            db.rollback()
            print(f"{prefix}: structured contradiction check skipped ({exc.detail})")
            row["contradictions"] = 0

        if not groq_key_present:
            row["literature_check"] = "skipped (no GROQ_API_KEY)"
        else:
            print(f"{prefix}: running literature contradiction check (real LLM call)...")
            try:
                lit_result = run_literature_contradiction_check(target_id, db)
                lit_count = len(lit_result["contradictions"])
                row["contradictions"] = (row["contradictions"] or 0) + lit_count
                row["literature_check"] = f"ok ({lit_count} found, {lit_result['pairs_evaluated']} pairs evaluated)"
            except HTTPException as exc:
                db.rollback()
                print(f"{prefix}: literature check skipped ({exc.detail})")
                row["literature_check"] = f"skipped ({exc.detail})"
            except Exception as exc:
                # Real, honest handling of a Groq rate limit or any other
                # real API/network failure for this one gene — log it and
                # keep going rather than aborting the whole setup.
                db.rollback()
                print(f"{prefix}: literature check failed ({exc}), continuing")
                row["literature_check"] = f"failed ({exc})"
            if index < total:
                time.sleep(LITERATURE_CHECK_SLEEP_SECONDS)

        print(f"{prefix}: computing scores...")
        try:
            score = compute_scores(target_id, db)
            row["priority_score"] = score.priority_score
        except HTTPException as exc:
            db.rollback()
            print(f"{prefix}: scoring failed ({exc.detail}) — skipping gap analysis for this gene")
            row["error"] = f"scoring failed: {exc.detail}"
            return row

        print(f"{prefix}: running gap analysis...")
        try:
            gaps = run_gap_analysis(target_id, db)
            row["gaps"] = len(gaps["gaps"])
        except HTTPException as exc:
            db.rollback()
            print(f"{prefix}: gap analysis failed ({exc.detail})")
            row["error"] = f"gap analysis failed: {exc.detail}"

        # Evidence Momentum — independent, informational only (see
        # app/core/scoring/evidence_momentum.py's module docstring: NOT
        # wired into scoring/gaps above, deliberately). A pure DB
        # aggregation over already-ingested data, so this can't fail the
        # way an external API/LLM call can — no real query for it to skip
        # gracefully, but wrapped defensively anyway for consistency.
        print(f"{prefix}: computing evidence momentum...")
        try:
            momentum = get_momentum(target_id, db)
            row["momentum_trend"] = momentum.trend
            row["momentum_score"] = momentum.momentum_score
        except Exception as exc:
            db.rollback()
            print(f"{prefix}: momentum computation failed ({exc})")
            row["error"] = row["error"] or f"momentum failed: {exc}"

        print(f"{prefix}: done\n")
    except Exception as exc:
        # Last-resort, defense-in-depth catch — a genuinely unexpected
        # failure (e.g. a DB error) for this one gene should not abort the
        # other 4.
        db.rollback()
        print(f"{prefix}: FAILED ({exc}) — continuing to next gene\n")
        row["error"] = str(exc)

    return row


def print_summary(summary: list[dict]) -> None:
    print("=" * 100)
    print("DEMO SETUP SUMMARY")
    print("=" * 100)
    header = f"{'Gene':<10} {'Priority Score':>14} {'Contradictions':>15} {'Gaps':>6} {'Momentum':>14}  Literature Check"
    print(header)
    print("-" * len(header))
    for row in summary:
        score_str = f"{row['priority_score']:.4f}" if row["priority_score"] is not None else "—"
        contra_str = str(row["contradictions"]) if row["contradictions"] is not None else "—"
        gaps_str = str(row["gaps"]) if row["gaps"] is not None else "—"
        lit_str = row["literature_check"] or "—"
        momentum_str = row["momentum_trend"] or "—"
        if row["momentum_score"] is not None:
            momentum_str += f" ({row['momentum_score']:.2f}x)"
        print(f"{row['gene']:<10} {score_str:>14} {contra_str:>15} {gaps_str:>6} {momentum_str:>14}  {lit_str}")
        if row["error"]:
            print(f"{'':<10} ERROR: {row['error']}")
    print("=" * 100)


def main():
    groq_key_present = bool(os.environ.get("GROQ_API_KEY"))
    if not groq_key_present:
        print(
            "WARNING: GROQ_API_KEY is not set (checked environment and .env) — "
            "the literature contradiction check (a real LLM call) will be skipped "
            "for every gene. Structured contradictions, scoring, and gap analysis "
            "are unaffected and will still run.\n"
        )

    print("Initializing database (creating tables if they don't exist)...")
    init_db()

    db = SessionLocal()
    summary = []
    try:
        print("Seeding candidate targets...")
        seed_targets(db)

        # Clear prior evidence before re-ingesting — same "clear before
        # re-insert" prototype convention as scripts/ingest_evidence.py's
        # own main(), so re-running this script doesn't accumulate
        # duplicate evidence records.
        deleted = db.query(EvidenceRecord).delete()
        if deleted:
            db.commit()
            print(f"Cleared {deleted} existing evidence records before re-ingesting.")
        print()

        genes = list(CANDIDATE_TARGETS.items())
        total = len(genes)
        for index, (gene_symbol, ensembl_id) in enumerate(genes, start=1):
            row = run_gene(db, index, total, gene_symbol, ensembl_id, groq_key_present)
            summary.append(row)
    finally:
        db.close()

    print_summary(summary)


if __name__ == "__main__":
    main()
