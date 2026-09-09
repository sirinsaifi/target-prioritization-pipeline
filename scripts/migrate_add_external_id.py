"""
One-time schema migration: adds `EvidenceRecord.external_id` (plain,
guarded `ALTER TABLE`, same non-destructive pattern as
scripts/migrate_add_momentum.py) — real, clickable source links task (see
CLAUDE.md). Holds a real external identifier some datasources expose that
isn't already captured by an existing field (clinicalReportId for
clinical_precedence, credibleSet.studyLocusId for gwas_credible_sets, the
resolved STRING protein id for string) — see
app/core/presentation/source_links.py's module docstring for the full
per-datasource investigation.

Does NOT backfill existing rows — same reasoning as publication_year's
migration: there is no way to derive this real value for an
already-ingested row without re-fetching it from OTP/STRING, and guessing
would be fabrication. Existing rows keep external_id=NULL (source_url
correctly falls back to None for clinical_precedence/gwas_credible_sets/
string rows ingested before this migration) until the next real
`python -m scripts.ingest_evidence` re-ingestion populates it for real.

Run once:
    python -m scripts.migrate_add_external_id
"""

from sqlalchemy import inspect, text

from app.db.database import engine


def main():
    with engine.begin() as conn:
        existing_columns = {col["name"] for col in inspect(conn).get_columns("evidence_records")}
        if "external_id" in existing_columns:
            print("evidence_records.external_id: already exists, skipping")
        else:
            conn.execute(text("ALTER TABLE evidence_records ADD COLUMN external_id VARCHAR"))
            print("evidence_records.external_id: added (NULL for all existing rows — re-run "
                  "ingest_evidence to populate it for real, see module docstring)")

    print("\nMigration complete.")


if __name__ == "__main__":
    main()
