"""Undo a person's decision on a phone-reading-to-payment match (05 section 4.3.8).

The case decision ledger gains ``undo_phone_result_decision`` on the subject ``phone_analysis_result``: an undo is
appended, the decision it reverses stays. The constraint list is read from the database and extended, so values
another migration added are kept.
"""
import re

import sqlalchemy as sa
from alembic import op

revision = "20261104_phone_match_undo"
down_revision = "20261104_removed_records"
branch_labels = None
depends_on = None

NAME, COLUMN, ADD = "ck_adjudications_decision", "decision", ["undo_phone_result_decision"]


def _values(conn):
    d = conn.execute(sa.text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :n AND "
                             "conrelid = 'adjudications'::regclass"), {"n": NAME}).scalar()
    return re.findall(r"'([^']+)'::", d or "")


def _replace(values):
    quoted = ", ".join("'%s'" % v for v in values)
    op.execute("ALTER TABLE adjudications DROP CONSTRAINT IF EXISTS %s" % NAME)
    op.execute("ALTER TABLE adjudications ADD CONSTRAINT %s CHECK (%s IN (%s))" % (NAME, COLUMN, quoted))


def upgrade():
    have = _values(op.get_bind())
    if not have:
        raise RuntimeError("constraint %s not found on adjudications" % NAME)
    _replace(have + [v for v in ADD if v not in have])


def downgrade():
    conn = op.get_bind()
    if conn.execute(sa.text("SELECT 1 FROM adjudications WHERE decision = ANY(:d) LIMIT 1"), {"d": ADD}).first():
        raise RuntimeError("undo_phone_result_decision decisions exist; they are case records and are not dropped")
    _replace([v for v in _values(conn) if v not in ADD])
