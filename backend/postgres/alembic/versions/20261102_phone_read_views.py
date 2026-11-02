"""Phone read views, first part (docs/cellebrite/02 section 12; contract of 03 section 1.2).

Views over the current generation of the derived tables (02 section 5.7) and only extractions that stand
``active`` (a superseded extraction keeps its rows but leaves every view, 02 decision 36): ``pv_record``,
``pv_time``, ``pv_timeline_entry``, ``pv_location_point``, ``pv_text``. Later migrations replace these and add
the communication, identity and coverage views as their tables land. ``pv_timeline_entry.activity_class`` is
``unknown`` until spec 04's strength rows are loaded (04-U1).
"""
from alembic import op

revision = "20261102_phone_read_views"
down_revision = "20261102_phone_generic"
branch_labels = None
depends_on = None

CURRENT = """JOIN phone_interpretation_state st ON st.extraction_id = t.extraction_id AND st.generation = t.generation
  JOIN phone_extractions e ON e.id = t.extraction_id AND e.standing = 'active'"""

VIEWS = {
    "pv_record": """
SELECT t.record_uid, t.extraction_id, t.case_id, r.source_model_id AS cellebrite_id, t.model_type,
       t.parent_record_uid, t.deleted_state, t.decoding_confidence, t.source_index, t.file_id,
       false AS is_carved, t.locator, t.title, t.first_instant, t.has_time, t.has_point, t.is_top_level,
       t.root_record_uid, t.document_index, t.ordinal
  FROM phone_record_summaries t %(current)s
  JOIN phone_records r ON r.extraction_id = t.extraction_id AND r.document_index = t.document_index
       AND r.ordinal = t.ordinal""",
    "pv_time": """
SELECT t.time_uid, t.record_uid, t.extraction_id, t.case_id, t.field_path, t.value_index,
       t.effective_instant AS instant, t.original_text, t.original_offset_minutes, t.offset_present,
       t.instant AS machine_instant, t.instant_basis, t.producer_format, t.format_mismatch, t.local_wall_time,
       t.offset_state
  FROM phone_time_values t %(current)s""",
    "pv_timeline_entry": """
SELECT t.time_uid AS entry_uid, t.record_uid, t.root_record_uid, t.extraction_id, t.case_id, t.model_type,
       t.field_path, t.field_meaning, t.semantics, t.effective_instant AS instant, t.is_event_time,
       'unknown'::text AS activity_class, s.title AS summary,
       COALESCE((SELECT array_agg(DISTINCT p.identity_key) FROM phone_participations p
                  WHERE p.generation = t.generation AND p.identity_key IS NOT NULL
                    AND p.record_uid IN (t.record_uid, t.root_record_uid)), '{}'::text[]) AS identity_keys,
       t.interpretation_level, t.mapping_version_id, t.deleted_state
  FROM phone_time_values t %(current)s
  LEFT JOIN phone_record_summaries s ON s.record_uid = t.record_uid AND s.generation = t.generation""",
    "pv_location_point": """
SELECT t.point_uid, t.record_uid, t.coordinate_record_uid, t.extraction_id, t.case_id, t.model_type, t.lat, t.lon,
       t.accuracy_m, t.accuracy_basis, t.precision_text, t.source_kind, t.affiliation, t.instant, t.end_instant,
       t.time_field, t.flags, t.interpretation_level, t.deleted_state
  FROM phone_location_points t %(current)s""",
    "pv_text": """
SELECT t.text_uid, t.record_uid, t.extraction_id, t.case_id, t.model_type, t.field_path, t.value_index,
       t.effective_value AS value, t.value AS machine_value, t.value_folded, t.is_sensitive
  FROM phone_texts t %(current)s""",
}


def upgrade():
    for name, sql in VIEWS.items():
        op.execute("CREATE VIEW %s AS %s" % (name, sql % {"current": CURRENT}))


def downgrade():
    for name in reversed(list(VIEWS)):
        op.execute("DROP VIEW IF EXISTS %s" % name)
