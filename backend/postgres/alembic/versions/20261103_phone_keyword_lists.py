"""Saved keyword lists (docs/cellebrite/03 section 11.2; 07 J-6).

A keyword list is a Workspace entry (a note tagged "keyword list", so it shows, is searched and is deleted with the
rest of the Workspace) with this row holding what the list runs: its terms and whether they match exact characters.
The phone worker runs every list on every phone of its case after each pass when the phones or the list changed
(``run_signature``), and keeps the totals per phone, term and group in ``run``. The foreign key is deferred so the
entry and its row are written in one transaction.
"""
from alembic import op

revision = "20261103_phone_keyword_lists"
down_revision = "20261103_agent_proposals"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE phone_keyword_lists (
  entry_id       uuid PRIMARY KEY REFERENCES workspace_entries(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
  case_id        uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  name           varchar(240) NOT NULL,
  terms          jsonb NOT NULL,
  exact          boolean NOT NULL DEFAULT false,
  created_by     varchar(240),
  created_at     timestamptz NOT NULL DEFAULT clock_timestamp(),
  run_signature  varchar(64),
  run_started_at timestamptz,
  last_run_at    timestamptz,
  run            jsonb,
  run_error      text,
  CONSTRAINT ck_phone_keyword_lists_terms CHECK (jsonb_typeof(terms) = 'array' AND jsonb_array_length(terms) > 0)
);
CREATE INDEX ix_phone_keyword_lists_case ON phone_keyword_lists (case_id, created_at);
""")


def downgrade():
    import sqlalchemy as sa
    n = op.get_bind().execute(sa.text("SELECT count(*) FROM phone_keyword_lists")).scalar_one()
    if n:
        raise RuntimeError("%d keyword lists are stored; removing the table would leave their Workspace notes "
                           "without the terms they run." % n)
    op.execute("DROP TABLE phone_keyword_lists")
