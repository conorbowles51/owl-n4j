"""Dated "what changed" briefs per case (services/agent/briefs.py) and the requests that ask for one.

``case_briefs``: one row per brief: the snapshot it read (pinned to its ledger revision), the changes from the brief
before, what it covered and what it cost. Rows are added, never edited, except ``checked_at``/``coverage``/``cost``/
``evidence_stamp`` when a later run finds nothing changed. ``case_brief_requests``: one row per case asked for after an
import, removed when the brief is written.
"""
from alembic import op

revision = "20261103_case_briefs"
down_revision = "20261103_phone_result_snapshots"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE case_briefs (
            id uuid PRIMARY KEY,
            case_id uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            checked_at timestamptz NOT NULL DEFAULT now(),
            trigger varchar(40) NOT NULL,
            ledger_revision varchar(64) NOT NULL,
            input_revision varchar(64) NOT NULL,
            previous_id uuid NULL REFERENCES case_briefs(id) ON DELETE SET NULL,
            snapshot jsonb NOT NULL,
            changes jsonb NOT NULL,
            coverage jsonb NOT NULL,
            cost jsonb NOT NULL,
            evidence_stamp jsonb NOT NULL DEFAULT '{}'::jsonb
        )""")
    op.execute("CREATE INDEX ix_case_briefs_case_created ON case_briefs (case_id, created_at DESC)")
    op.execute("""
        CREATE TABLE case_brief_requests (
            case_id uuid PRIMARY KEY REFERENCES cases(id) ON DELETE CASCADE,
            first_requested_at timestamptz NOT NULL DEFAULT now(),
            last_requested_at timestamptz NOT NULL DEFAULT now(),
            reason varchar(40) NOT NULL DEFAULT 'import'
        )""")


def downgrade():
    op.execute("DROP TABLE case_brief_requests")
    op.execute("DROP TABLE case_briefs")
