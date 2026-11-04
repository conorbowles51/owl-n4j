"""Searches run over a case's phone records, for the review coverage summary (07 J-13 step 6).

``phone_search_runs``: one row per person, case, search text and exactness, with how often it was run, when first
and last, where (Conversations or Loupe-wide Search) and the hit total of the last run. Nothing else records the
searches people run (0 audit or log rows before this table, measured 2026-11-03). Rows are counted, never edited by
hand; a case's rows go with the case.
"""
from alembic import op

revision = "20261103_phone_search_runs"
down_revision = "20261103_phone_keyword_lists"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE phone_search_runs (
            id uuid PRIMARY KEY,
            case_id uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            user_id uuid NULL REFERENCES users(id) ON DELETE SET NULL,
            query text NOT NULL,
            query_hash varchar(64) NOT NULL,
            exact boolean NOT NULL DEFAULT false,
            surface varchar(24) NOT NULL,
            run_count integer NOT NULL DEFAULT 1,
            last_hits integer NULL,
            first_run_at timestamptz NOT NULL DEFAULT now(),
            last_run_at timestamptz NOT NULL DEFAULT now()
        )""")
    op.execute("CREATE UNIQUE INDEX uq_phone_search_runs ON phone_search_runs "
               "(case_id, user_id, query_hash, exact, surface)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS phone_search_runs")
