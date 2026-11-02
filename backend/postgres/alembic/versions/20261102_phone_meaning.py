"""Timestamp meaning on every time value (docs/cellebrite/04 section 2.3 via 02 section 6.5b).

``phone_time_values`` gains the meaning row that gave ``field_meaning`` and ``semantics``, its mapping version and
its level (``applied_unconfirmed`` until a person confirms the row), beside the type mapping's own
``mapping_row_id``. ``pv_timeline_entry`` is replaced to carry them, and the type mapping's rule id.
"""
from alembic import op

revision = "20261102_phone_meaning"
down_revision = "20261102_phone_comms"
branch_labels = None
depends_on = None

CURRENT = """JOIN phone_interpretation_state st ON st.extraction_id = t.extraction_id AND st.generation = t.generation
  JOIN phone_extractions e ON e.id = t.extraction_id AND e.standing = 'active'"""

TIMELINE = """
CREATE VIEW pv_timeline_entry AS
SELECT t.time_uid AS entry_uid, t.record_uid, t.root_record_uid, t.extraction_id, t.case_id, t.model_type,
       t.field_path, t.field_meaning, t.semantics, t.effective_instant AS instant, t.is_event_time,
       'unknown'::text AS activity_class, s.title AS summary,
       COALESCE((SELECT array_agg(DISTINCT p.identity_key) FROM phone_participations p
                  WHERE p.generation = t.generation AND p.identity_key IS NOT NULL
                    AND p.record_uid IN (t.record_uid, t.root_record_uid)), '{}'::text[]) AS identity_keys,
       t.interpretation_level, t.mapping_version_id, t.deleted_state%(extra)s
  FROM phone_time_values t %(current)s
  LEFT JOIN phone_record_summaries s ON s.record_uid = t.record_uid AND s.generation = t.generation"""
EXTRA = """, t.mapping_row_id,
       t.meaning_mapping_row_id, t.meaning_mapping_version_id, t.meaning_level"""


def upgrade():
    op.execute("ALTER TABLE phone_time_values ADD COLUMN meaning_mapping_row_id varchar(160), "
               "ADD COLUMN meaning_mapping_version_id uuid, ADD COLUMN meaning_level varchar(24) "
               "CHECK (meaning_level IN ('applied_unconfirmed','reviewed'))")
    op.execute("DROP VIEW pv_timeline_entry")
    op.execute(TIMELINE % {"current": CURRENT, "extra": EXTRA})


def downgrade():
    op.execute("DROP VIEW pv_timeline_entry")
    op.execute(TIMELINE % {"current": CURRENT, "extra": ""})
    op.execute("ALTER TABLE phone_time_values DROP COLUMN meaning_level, DROP COLUMN meaning_mapping_version_id, "
               "DROP COLUMN meaning_mapping_row_id")
