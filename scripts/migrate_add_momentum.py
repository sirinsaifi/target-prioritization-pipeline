"""
One-time schema migration for Evidence Momentum:
  1. Adds `EvidenceRecord.publication_year` (plain, guarded `ALTER TABLE`,
     same non-destructive pattern as scripts/migrate_add_consistency_breakdown.py).
  2. Creates the new `momentum_scores` table (Base.metadata.create_all()
     handles a brand-new table natively, same pattern as
     scripts/migrate_add_pipeline_run_log.py).

Does NOT backfill `publication_year` for existing rows — unlike
PipelineRunLog's backfill (which used genuinely known real history),
there is no way to derive a real publication/study year for an
already-ingested row without re-fetching it from OTP/PubMed, and
guessing one would be fabrication. Existing rows simply keep
publication_year=NULL until the next real `python -m scripts.ingest_evidence`
re-ingestion populates it for real.

Run once:
    python -m scripts.migrate_add_momentum
"""

from sqlalchemy import inspect, text

from app.db.database import engine, init_db


def main():
    with engine.begin() as conn:
        existing_columns = {col["name"] for col in inspect(conn).get_columns("evidence_records")}
        if "publication_year" in existing_columns:
            print("evidence_records.publication_year: already exists, skipping")
        else:
            conn.execute(text("ALTER TABLE evidence_records ADD COLUMN publication_year INTEGER"))
            print("evidence_records.publication_year: added (NULL for all existing rows — re-run "
                  "ingest_evidence to populate it for real, see module docstring)")

    init_db()  # creates momentum_scores (and any other new tables) if missing
    print("momentum_scores table: created if it didn't already exist")

    print("\nMigration complete.")


if __name__ == "__main__":
    main()
