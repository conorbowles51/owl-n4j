"""A person confirms or corrects machine-generated text (03 8.3, 07 4.6 and 5 Media; tests M-6, M-7).

- ``phone_derived_texts`` gains the correction (the corrected text and its folded form, who, when, the typed reason,
  the decision) and the confirmation (who, when, the decision). The machine text in ``text`` is never overwritten:
  it stays visible beside the correction, and only the corrected text is searched (07 4.6).
- The case decision ledger gains the subject ``phone_derived_text`` and the decisions ``correct_machine_text`` and
  ``confirm_machine_text`` (02 8.8: every decision goes through ``decisions.record``).

- ``dossier_assessments.derived_text_id``: an assessment accepted from a machine transcript or image text names it
  (CO-18), stored ``ai_assisted`` and shown "Read by <model>, accepted by <name>".

The constraint lists are read from the database and extended, so values another migration added are kept.
"""
import re

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261103_phone_machine_text_review"
down_revision = "20261103_phone_entry_offsets"
branch_labels = None
depends_on = None

NEW = {"ck_adjudications_subject_type": ("subject_type", ["phone_derived_text"]),
       "ck_adjudications_decision": ("decision", ["correct_machine_text", "confirm_machine_text"])}

COLUMNS = (
    ("corrected_text", sa.Text()), ("corrected_text_folded", sa.Text()),
    ("corrected_at", sa.DateTime(timezone=True)), ("corrected_by_name", sa.Text()),
    ("corrected_by_user_id", postgresql.UUID(as_uuid=True)), ("correction_reason", sa.Text()),
    ("correction_decision_id", postgresql.UUID(as_uuid=True)),
    ("confirmed_at", sa.DateTime(timezone=True)), ("confirmed_by_name", sa.Text()),
    ("confirmed_by_user_id", postgresql.UUID(as_uuid=True)), ("confirm_decision_id", postgresql.UUID(as_uuid=True)),
)


def _values(conn, name):
    d = conn.execute(sa.text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :n AND "
                             "conrelid = 'adjudications'::regclass"), {"n": name}).scalar()
    return re.findall(r"'([^']+)'::", d or "")


def _replace(conn, name, column, values):
    quoted = ", ".join("'%s'" % v for v in values)
    op.execute("ALTER TABLE adjudications DROP CONSTRAINT IF EXISTS %s" % name)
    op.execute("ALTER TABLE adjudications ADD CONSTRAINT %s CHECK (%s IN (%s))" % (name, column, quoted))


def upgrade():
    for name, type_ in COLUMNS:
        op.add_column("phone_derived_texts", sa.Column(name, type_, nullable=True))
    conn = op.get_bind()
    for name, (column, add) in NEW.items():
        have = _values(conn, name)
        if not have:
            raise RuntimeError("constraint %s not found on adjudications" % name)
        _replace(conn, name, column, have + [v for v in add if v not in have])
    op.add_column("dossier_assessments", sa.Column("derived_text_id", postgresql.UUID(as_uuid=True), sa.ForeignKey(
        "phone_derived_texts.id", ondelete="SET NULL", name="fk_dossier_assessments_derived_text"), nullable=True))
    op.create_index("ix_dossier_assessments_derived_text", "dossier_assessments", ["derived_text_id"])


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_dossier_assessments_derived_text")
    op.execute("ALTER TABLE dossier_assessments DROP COLUMN IF EXISTS derived_text_id")
    conn = op.get_bind()
    for name, (column, add) in NEW.items():
        _replace(conn, name, column, [v for v in _values(conn, name) if v not in add])
    for name, _ in reversed(COLUMNS):
        op.drop_column("phone_derived_texts", name)
