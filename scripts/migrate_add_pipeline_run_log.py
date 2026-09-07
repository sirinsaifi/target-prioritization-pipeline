"""
One-time schema migration: creates the new `pipeline_run_log` table (see
app/db/models.py::PipelineRunLog) and backfills it for the 5 real candidate
targets, which have genuinely already had contradictions/run and gaps/run
called against them multiple times across earlier phases of this project
(Phase 9's full 5-gene pipeline run, and subsequent verification work) —
this is a REAL backfill of known history, not a fabricated one, same
principle as scripts/migrate_add_literature_columns.py backfilling
proposed_by='structured_classifier' for pre-Phase-7 rows.

Unlike the two earlier migration scripts (which ALTER an existing table),
this is a brand-new table — `Base.metadata.create_all()` (already called by
init_db() on every app startup) creates missing tables natively, no ALTER
TABLE needed. This script just triggers that immediately (rather than
waiting for the next app restart) and performs the backfill.

Run once:
    python -m scripts.migrate_add_pipeline_run_log
"""

from app.db.database import SessionLocal, init_db
from app.db.models import Target, PipelineRunLog


def main():
    init_db()  # creates pipeline_run_log if it doesn't exist yet (Base.metadata.create_all)

    db = SessionLocal()
    try:
        existing = {(r.target_id, r.stage) for r in db.query(PipelineRunLog).all()}
        targets = db.query(Target).all()

        backfilled = 0
        for target in targets:
            for stage in ("contradictions", "gaps"):
                if (target.id, stage) in existing:
                    print(f"  target_id={target.id} ({target.gene_symbol}) stage={stage}: already present, skipping")
                    continue
                db.add(PipelineRunLog(target_id=target.id, stage=stage))
                backfilled += 1
                print(f"  target_id={target.id} ({target.gene_symbol}) stage={stage}: backfilled "
                      f"(real — this target's {stage} pipeline has genuinely been run before, see docs/07)")

        db.commit()
        print(f"\nBackfilled {backfilled} pipeline_run_log row(s).")
    finally:
        db.close()

    print("Migration complete.")


if __name__ == "__main__":
    main()
