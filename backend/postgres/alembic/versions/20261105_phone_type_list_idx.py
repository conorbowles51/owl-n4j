"""Indexes for the list of each record type (03 section 7.5): a window in report or time order reads from the index
at its keyset position, and the exact total counts the type's rows of one generation, never the table.

The read views learn about copies from another source (02 decision 39): ``pv_timeline_entry`` leaves out a copy's time
when it repeats its owner's in the same field (one event, not two) and ``pv_text`` shows the row's flags, so a reader
that counts evidence can do the same. ``pv_time`` and every value stay as they were: the record panel still shows them.
"""
from alembic import op

revision = "20261105_phone_type_list_idx"
down_revision = "20261105_pv_identity_seen"
branch_labels = None
depends_on = None


PV_TEXT = """ SELECT t.text_uid, t.record_uid, t.extraction_id, t.case_id, t.model_type, t.field_path, t.value_index,
    t.effective_value AS value, t.value AS machine_value, t.value_folded, t.is_sensitive, t.flags
   FROM ((phone_texts t
     JOIN phone_interpretation_state st ON (((st.extraction_id = t.extraction_id) AND (st.generation = t.generation))))
     JOIN phone_extractions e ON (((e.id = t.extraction_id) AND (e.standing = 'active'::phone_extraction_standing))))"""
PV_TIMELINE_ENTRY = """SELECT t.time_uid AS entry_uid,
    t.record_uid,
    t.root_record_uid,
    t.extraction_id,
    t.case_id,
    t.model_type,
    t.field_path,
    t.field_meaning,
    t.semantics,
    t.effective_instant AS instant,
    t.is_event_time,
    (COALESCE(( SELECT a.activity_class
           FROM pol_activity_event a
          WHERE ((a.extraction_id = t.extraction_id) AND (a.record_uid = t.record_uid) AND (((a.time_field)::text = (t.field_name)::text) OR ((a.end_field)::text = (t.field_name)::text)))
          ORDER BY ((a.time_field)::text = (t.field_name)::text) DESC
         LIMIT 1), 'unknown'::character varying))::text AS activity_class,
    s.title AS summary,
    COALESCE(( SELECT array_agg(DISTINCT p.identity_key) AS array_agg
           FROM phone_participations p
          WHERE ((p.generation = t.generation) AND (p.identity_key IS NOT NULL) AND (p.record_uid = ANY (ARRAY[t.record_uid, t.root_record_uid])))), '{}'::text[]) AS identity_keys,
    t.interpretation_level,
    t.mapping_version_id,
    t.deleted_state,
    t.mapping_row_id,
    t.meaning_mapping_row_id,
    t.meaning_mapping_version_id,
    t.meaning_level
   FROM (((phone_time_values t
     JOIN phone_interpretation_state st ON (((st.extraction_id = t.extraction_id) AND (st.generation = t.generation))))
     JOIN phone_extractions e ON (((e.id = t.extraction_id) AND (e.standing = 'active'::phone_extraction_standing))))
     LEFT JOIN phone_record_summaries s ON (((s.record_uid = t.record_uid) AND (s.generation = t.generation))))
  WHERE NOT ('same_as_owner'::text = ANY (t.flags))"""


def upgrade():
    op.execute("CREATE INDEX IF NOT EXISTS ix_phone_record_summaries_list_report ON phone_record_summaries "
               "(extraction_id, generation, model_type, document_index, ordinal)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_phone_record_summaries_list_time ON phone_record_summaries "
               "(extraction_id, generation, model_type, first_instant, document_index, ordinal)")
    op.execute("CREATE OR REPLACE VIEW pv_text AS " + PV_TEXT)
    op.execute("CREATE OR REPLACE VIEW pv_timeline_entry AS " + PV_TIMELINE_ENTRY)


def downgrade():
    op.execute("CREATE OR REPLACE VIEW pv_timeline_entry AS " + PV_TIMELINE_ENTRY.rsplit(" WHERE ", 1)[0])
    op.execute("DROP VIEW pv_text")
    op.execute("CREATE VIEW pv_text AS " + PV_TEXT.replace(", t.flags", ""))
    op.execute("DROP INDEX IF EXISTS ix_phone_record_summaries_list_time")
    op.execute("DROP INDEX IF EXISTS ix_phone_record_summaries_list_report")
