"""
One-time schema migration for Phase 7 (literature contradiction proposer/
verifier) — adds the new columns app/db/models.py now declares, without
dropping/recreating the existing SQLite DB (which would destroy all real
ingested evidence, scores, contradictions, gaps, and investigation traces
built up across every prior phase).

`Base.metadata.create_all()` (init_db()) only creates missing TABLES, never
ALTERs existing ones — this project has no migration tool (Alembic, etc.),
so this is a plain, explicit, one-off SQL script instead. Safe to re-run:
every ALTER is guarded by a check against the live schema, so it's a no-op
on a DB that's already migrated.

Run once:
    python -m scripts.migrate_add_literature_columns
"""

from sqlalchemy import inspect, text

from app.db.database import engine


def _add_column_if_missing(conn, table: str, column: str, ddl_type: str, default_sql: str | None = None):
    existing_columns = {col["name"] for col in inspect(conn).get_columns(table)}
    if column in existing_columns:
        print(f"  {table}.{column}: already exists, skipping")
        return
    default_clause = f" DEFAULT {default_sql}" if default_sql else ""
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}{default_clause}"))
    print(f"  {table}.{column}: added")


def main():
    with engine.begin() as conn:
        print("evidence_records:")
        _add_column_if_missing(conn, "evidence_records", "abstract_text", "TEXT")

        print("contradiction_log:")
        _add_column_if_missing(conn, "contradiction_log", "status", "VARCHAR", default_sql="'confirmed'")
        _add_column_if_missing(conn, "contradiction_log", "proposed_by", "VARCHAR")
        _add_column_if_missing(conn, "contradiction_log", "verification_reason", "TEXT")

        # Backfill: every ContradictionLog row that predates this migration
        # was produced by the structured deterministic classifier
        # (app/api/routes/contradictions.py's POST /run) — never
        # LLM-proposed — so make that explicit rather than leaving
        # proposed_by NULL for them.
        result = conn.execute(text(
            "UPDATE contradiction_log SET proposed_by = 'structured_classifier' "
            "WHERE proposed_by IS NULL"
        ))
        print(f"Backfilled proposed_by='structured_classifier' on {result.rowcount} pre-existing row(s).")

    print("\nMigration complete.")


if __name__ == "__main__":
    main()
