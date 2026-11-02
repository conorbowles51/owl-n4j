"""Corrections on phone data (docs/cellebrite/02 section 10.2).

``phone_value_corrections``: one row per correction of one captured value (a record's field path and value index),
written after its ``correct_phone_value`` decision in the same transaction. The machine text is kept on every row;
an undo is a new correction back to the machine text, and the earlier row points at the one that replaced it
(``superseded_by_id``), so the chain stays readable. Derived rows hold the machine value and the effective value
(``phone_time_values.effective_instant``, ``phone_texts.effective_value``); only the effective one is read.
"""
from alembic import op

revision = "20261102_phone_corrections"
down_revision = "20261102_phone_decisions"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE phone_value_corrections (
  id                uuid PRIMARY KEY,
  case_id           uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  extraction_id     uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  record_uid        uuid NOT NULL,
  field_path        text NOT NULL,
  value_index       integer NOT NULL DEFAULT 0,
  value_type        varchar(32) NOT NULL,
  machine_text      text,
  corrected_text    text NOT NULL,
  decision_id       uuid NOT NULL REFERENCES adjudications(id) ON DELETE RESTRICT,
  superseded_by_id  uuid REFERENCES phone_value_corrections(id),
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_phone_value_corrections_extraction ON phone_value_corrections (extraction_id)
  WHERE superseded_by_id IS NULL;
CREATE UNIQUE INDEX uq_phone_value_corrections_current ON phone_value_corrections (record_uid, field_path, value_index)
  WHERE superseded_by_id IS NULL;
"""

DOWNGRADE = """
DROP TABLE IF EXISTS phone_value_corrections;
"""


def upgrade():
    op.execute(UPGRADE)


def downgrade():
    op.execute(DOWNGRADE)
