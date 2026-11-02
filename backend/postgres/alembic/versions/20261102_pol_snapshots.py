"""Frozen pattern results for collecting (docs/cellebrite/07 section 6.4 item 13; 04 section 9.6).

A ``phone_analysis`` link points at a snapshot that freezes kind, subject, window, parameters, mapping versions, the
record ids behind the result and summary counts. The id is the snapshot's own hash, so the same inputs and result
give the same id and a recompute that differs is a different snapshot. Rows are never updated.
"""
from alembic import op

revision = "20261102_pol_snapshots"
down_revision = "20261102_phone_screens_read"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE pol_analysis_snapshot (
  id               varchar(80) PRIMARY KEY CHECK (id LIKE 'pa\\_%'),
  case_id          uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  kind             varchar(32) NOT NULL CHECK (kind IN ('day', 'window', 'grid', 'places')),
  label            varchar(512) NOT NULL,
  snapshot         jsonb NOT NULL,
  record_count     integer NOT NULL CHECK (record_count >= 0),
  created_by_user_id uuid,
  created_by_name  varchar(255),
  created_at       timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX ix_pol_analysis_snapshot_case ON pol_analysis_snapshot (case_id, created_at);
""")


def downgrade():
    import sqlalchemy as sa
    n = op.get_bind().execute(sa.text("SELECT count(*) FROM pol_analysis_snapshot")).scalar_one()
    if n:
        raise RuntimeError("%d pattern results are frozen and may be linked; removing the table would break the links." % n)
    op.execute("DROP TABLE pol_analysis_snapshot")
