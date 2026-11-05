"""What one person has seen of the phone screens, and the record of a bulk add (07 sections 4.7 and 9).

``phone_user_marks``: one row per person and mark ("New" marks hidden, the first-phone card seen), so the choice
follows the person to any browser. ``phone_collect_runs``: a bulk add is sent part by part from the page; this row
keeps its true counts, so the job tray still shows it after a reload. New tables; no existing row changes.
"""
from alembic import op

revision = "20261105_phone_marks_collect_runs"
down_revision = "20261105_phone_type_list_idx"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE phone_user_marks (
          user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          mark    text NOT NULL,
          at      timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (user_id, mark)
        );
        CREATE TABLE phone_collect_runs (
          id             uuid PRIMARY KEY,
          case_id        uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
          user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          target_words   text NOT NULL,
          noun           text NOT NULL,
          total          integer NOT NULL,
          sent           integer NOT NULL DEFAULT 0,
          added          integer NOT NULL DEFAULT 0,
          skipped        integer NOT NULL DEFAULT 0,
          refused        integer NOT NULL DEFAULT 0,
          refused_reason text,
          state          text NOT NULL DEFAULT 'running',
          error          text,
          created_at     timestamptz NOT NULL DEFAULT now(),
          updated_at     timestamptz NOT NULL DEFAULT now(),
          finished_at    timestamptz,
          CHECK (state IN ('running', 'done', 'failed'))
        );
        CREATE INDEX ix_phone_collect_runs_case ON phone_collect_runs (case_id, user_id, created_at DESC);
    """)


def downgrade():
    op.execute("DROP TABLE phone_collect_runs; DROP TABLE phone_user_marks")
