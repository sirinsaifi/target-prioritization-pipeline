"""
One-time schema migration: adds `GapRecord.why_it_matters` and
`GapRecord.decision_impact` (plain, guarded `ALTER TABLE`, same
non-destructive pattern as scripts/migrate_add_external_id.py) — the two
new parts of the "fully actionable gap" decision-layer feature (Gap Type ->
Evidence -> Why it matters -> Next investigation -> Decision impact; see
app/core/gaps/gap_taxonomy.py's WHY_IT_MATTERS/DECISION_IMPACT dicts).

Does NOT backfill existing GapRecord rows with real text — unlike
PipelineRunLog's backfill (which restated a real, already-true fact),
these two fields are gap-type-specific templated sentences that require
re-running gap analysis (POST /gaps/target/{id}/run) to populate
correctly, since the templating logic lives in identify_gaps(), not in
this migration. Existing rows keep why_it_matters/decision_impact=NULL
until the next real gap-analysis run.

Run once:
    python -m scripts.migrate_add_gap_decision_fields
"""

from sqlalchemy import inspect, text

from app.db.database import engine


def main():
    with engine.begin() as conn:
        existing_columns = {col["name"] for col in inspect(conn).get_columns("gap_records")}
        for column in ("why_it_matters", "decision_impact"):
            if column in existing_columns:
                print(f"gap_records.{column}: already exists, skipping")
            else:
                conn.execute(text(f"ALTER TABLE gap_records ADD COLUMN {column} TEXT"))
                print(f"gap_records.{column}: added (NULL for all existing rows — re-run "
                      f"POST /gaps/target/{{id}}/run to populate it for real, see module docstring)")

    print("\nMigration complete.")


if __name__ == "__main__":
    main()
