"""
One-time schema migration: adds `PriorityScore.consistency_breakdown`
(Phase 7 follow-up — wiring literature_contradiction into Consistency
scoring, see docs/07). Same non-destructive pattern as
scripts/migrate_add_literature_columns.py: a plain, guarded `ALTER TABLE`,
safe to re-run, no existing data touched.

Run once:
    python -m scripts.migrate_add_consistency_breakdown
"""

from sqlalchemy import inspect, text

from app.db.database import engine


def main():
    with engine.begin() as conn:
        existing_columns = {col["name"] for col in inspect(conn).get_columns("priority_scores")}
        if "consistency_breakdown" in existing_columns:
            print("priority_scores.consistency_breakdown: already exists, skipping")
        else:
            conn.execute(text("ALTER TABLE priority_scores ADD COLUMN consistency_breakdown TEXT"))
            print("priority_scores.consistency_breakdown: added")

    print("\nMigration complete.")


if __name__ == "__main__":
    main()
