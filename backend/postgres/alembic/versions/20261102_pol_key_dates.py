"""Key dates and case terms (docs/cellebrite/04 section 8.6; 07 section 5).

A key date is a Workspace entry (a note tagged "key date") with this marker holding the instant and its zone; a
case term is the same with a keyword or phrase. The marker belongs to the entry: deleting the entry removes the
key date. The foreign key is deferred so the entry and its marker are written in one transaction.
"""
from alembic import op

revision = "20261102_pol_key_dates"
down_revision = "20261102_pol_snapshots"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE pol_key_date (
  entry_id     uuid PRIMARY KEY REFERENCES workspace_entries(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
  case_id      uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  kind         varchar(8) NOT NULL CHECK (kind IN ('date', 'term')),
  label        varchar(240) NOT NULL,
  instant_utc  timestamptz,
  zone         varchar(64),
  term         varchar(240),
  created_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT ck_pol_key_date_shape CHECK (
    (kind = 'date' AND instant_utc IS NOT NULL AND zone IS NOT NULL AND term IS NULL) OR
    (kind = 'term' AND term IS NOT NULL AND instant_utc IS NULL AND zone IS NULL))
);
CREATE INDEX ix_pol_key_date_case ON pol_key_date (case_id, kind, instant_utc);
""")


def downgrade():
    import sqlalchemy as sa
    n = op.get_bind().execute(sa.text("SELECT count(*) FROM pol_key_date")).scalar_one()
    if n:
        raise RuntimeError("%d key dates or case terms are stored; removing the table would leave their Workspace "
                           "notes without the instant they hold." % n)
    op.execute("DROP TABLE pol_key_date")
