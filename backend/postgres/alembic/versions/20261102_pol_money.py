"""Pattern of life: places a person attaches to a transaction (docs/cellebrite/04 section 8.5, unit U10).

- ``pol_manual_place``: one row per attachment. The current place of a transaction is its row with
  ``removed_decision_id`` null; a replacement or a removal keeps the earlier row and names the decision that ended it.
- Decisions ``attach_transaction_place`` and ``remove_transaction_place`` (subject ``transaction``) join
  ``ck_adjudications_decision``. The constraint is rebuilt from its current definition so no other job's members are
  lost.
"""
import re

from alembic import op
import sqlalchemy as sa

revision = "20261102_pol_money"
down_revision = "20261102_pol_colocation"
branch_labels = None
depends_on = None

NEW = ("attach_transaction_place", "remove_transaction_place")

DDL = """
CREATE TABLE pol_manual_place (
  id                  uuid PRIMARY KEY,
  case_id             uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  target_kind         varchar(20) NOT NULL CHECK (target_kind IN ('transaction')),
  transaction_id      uuid NOT NULL REFERENCES financial_transactions(id),
  lat                 double precision NOT NULL CHECK (lat BETWEEN -90 AND 90),
  lon                 double precision NOT NULL CHECK (lon BETWEEN -180 AND 180),
  radius_m            double precision NOT NULL CHECK (radius_m > 0 AND radius_m <= 50000),
  reason              text NOT NULL CHECK (btrim(reason) <> ''),
  decision_id         uuid NOT NULL,
  removed_decision_id uuid NULL,
  actor_name          varchar(300) NOT NULL,
  actor_email         varchar(300) NOT NULL,
  created_at          timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE UNIQUE INDEX ux_pol_manual_place_current ON pol_manual_place (transaction_id) WHERE removed_decision_id IS NULL;
CREATE INDEX ix_pol_manual_place_case ON pol_manual_place (case_id, transaction_id);
"""


def _members(bind):
    d = bind.execute(sa.text(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_adjudications_decision'")).scalar_one()
    return re.findall(r"'([a-z_]+)'", d)


def _rebuild(members):
    op.drop_constraint("ck_adjudications_decision", "adjudications", type_="check")
    op.create_check_constraint("ck_adjudications_decision", "adjudications",
                               "decision IN (%s)" % ", ".join("'%s'" % m for m in members))


def upgrade():
    bind = op.get_bind()
    have = _members(bind)
    _rebuild(have + [m for m in NEW if m not in have])
    for stmt in [s for s in DDL.split(";") if s.strip()]:
        op.execute(stmt)


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT count(*) FROM adjudications WHERE decision IN :d").bindparams(
            sa.bindparam("d", expanding=True)), {"d": list(NEW)}).scalar_one():
        raise RuntimeError("Transaction place decisions are recorded; removing the members would orphan them.")
    op.execute("DROP TABLE pol_manual_place")
    _rebuild([m for m in _members(bind) if m not in NEW])
