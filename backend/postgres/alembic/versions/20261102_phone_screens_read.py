"""Phone screens: the rest of the read contract, the case time zone and the stream indexes (docs/cellebrite/03
sections 1.2, 4.6, 4.7; 02 section 12.2).

- Views ``pv_extraction``, ``pv_identity``, ``pv_file`` and ``pv_attachment_link`` (02 section 12.2's columns that
  SQL can give; the phone label and the owner are computed in Python by ``readings.phone_labels`` and
  ``identities.owner``, because both replay decisions, and are added by ``services.phone.records.phones``).
- ``case_display_settings``: the case's time zone for phone data (03 section 4.6).
- The comm event indexes of 03 section 4.7: per phone, per thread and case-wide, each ending in
  ``(sort_instant, event_uid)`` so a day window is an index range read in display order.

Downgrade drops them.
"""
from alembic import op

revision = "20261102_phone_screens_read"
down_revision = "20261102_pol_colocation"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE case_display_settings (
  case_id    uuid PRIMARY KEY REFERENCES cases(id) ON DELETE CASCADE,
  time_zone  text NOT NULL,
  updated_by uuid NOT NULL REFERENCES users(id),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_phone_comm_events_phone_stream ON phone_comm_events (case_id, extraction_id, sort_instant, event_uid);
CREATE INDEX ix_phone_comm_events_thread_stream ON phone_comm_events (case_id, thread_key, sort_instant, event_uid);
CREATE INDEX ix_phone_comm_events_case_stream ON phone_comm_events (case_id, sort_instant, event_uid);
CREATE INDEX ix_phone_comm_events_dup ON phone_comm_events (extraction_id, dup_group_uid) WHERE dup_group_uid IS NOT NULL;

CREATE VIEW pv_extraction AS
SELECT e.id AS extraction_id, e.case_id,
       CASE WHEN e.standing = 'superseded' THEN 'replaced'
            WHEN e.capture_state IN ('failed', 'not_readable', 'reconciliation_failed', 'cancelled') THEN 'failed'
            WHEN e.capture_state NOT IN ('captured', 'captured_incomplete') THEN 'capturing'
            WHEN s.status = 'failed' THEN 'failed'
            WHEN s.status IS NULL OR s.status IN ('pending', 'running', 'held') THEN 'interpreting'
            WHEN s.texts_at IS NULL OR s.projected_at IS NULL THEN 'building_views'
            WHEN e.capture_state = 'captured_incomplete' THEN 'partial'
            ELSE 'ingested' END AS state,
       e.capture_state::text AS capture_state, e.standing::text AS standing, s.status AS interpretation_status,
       e.form, e.report_version, e.producer_version AS producer, e.extraction_type,
       coalesce(s.device_zone, e.device_zone) AS device_zone,
       coalesce(s.device_zone_basis, e.device_zone_source) AS device_zone_basis, s.examiner_zone,
       c.sha256 AS container_sha256, c.original_name AS container_name, e.report_set_sha256 AS report_sha256,
       e.captured_at AS ingested_at, e.created_at, e.record_count, e.file_count, e.flags AS selection,
       (SELECT CASE WHEN count(*) = 0 THEN NULL WHEN bool_and(r.result = 'exact') THEN 'exact' ELSE 'failed' END
          FROM (SELECT DISTINCT ON (document_index) result FROM phone_reconciliations
                 WHERE extraction_id = e.id ORDER BY document_index, ran_at DESC) r) AS reconciliation_state
  FROM phone_extractions e
  JOIN phone_extraction_containers c ON c.id = e.first_container_id
  LEFT JOIN phone_interpretation_state s ON s.extraction_id = e.id;

CREATE VIEW pv_identity AS
SELECT i.id AS identity_id, i.identity_key, i.case_id, i.kind, i.subkind, i.value_normalised, i.value_display,
       i.sighting_count, i.phone_count, i.first_instant, i.last_instant, l.dossier_id AS person_id
  FROM phone_identities i LEFT JOIN phone_identity_links l ON l.identity_id = i.id;

CREATE VIEW pv_file AS
SELECT f.file_uid, f.extraction_id, e.case_id, f.source_file_id AS cellebrite_file_id, f.tags AS category,
       f.local_path, coalesce(f.disk_size, f.declared_size) AS size, f.declared_size, f.disk_size,
       coalesce(f.disk_md5, f.declared_md5) AS md5, coalesce(f.disk_sha256, f.declared_sha256) AS sha256,
       f.declared_md5, f.declared_sha256, f.disk_md5, f.disk_sha256,
       CASE WHEN f.disk_sha256 IS NOT NULL OR f.disk_md5 IS NOT NULL THEN 'disk' ELSE 'declared' END AS hash_basis,
       f.outcome AS verification, f.body -> 1 ->> 'deleted' AS deleted_state, false AS is_carved, f.disk_relpath,
       f.document_index, f.ordinal
  FROM phone_files f JOIN phone_extractions e ON e.id = f.extraction_id AND e.standing = 'active';

CREATE VIEW pv_attachment_link AS
SELECT s.record_uid, r.extraction_id, s.case_id, f.file_uid,
       CASE r.mechanism WHEN 'jumptarget' THEN 'jump_target' WHEN 'file_id_attribute' THEN 'attachment_field'
            ELSE 'tagged_file' END AS mechanism,
       r.body_path, CASE WHEN r.mechanism = 'extracted_path_value' THEN r.reference_text END AS extracted_path,
       r.reference_text, r.resolution, r.resolution <> 'unresolved' AS resolved, r.ambiguous
  FROM phone_file_references r
  JOIN phone_record_summaries s ON s.extraction_id = r.extraction_id AND s.document_index = r.document_index
       AND s.ordinal = r.record_ordinal
  JOIN phone_interpretation_state st ON st.extraction_id = s.extraction_id AND st.generation = s.generation
  JOIN phone_extractions e ON e.id = r.extraction_id AND e.standing = 'active'
  LEFT JOIN phone_files f ON f.extraction_id = r.extraction_id AND f.document_index = r.file_document_index
       AND f.ordinal = r.file_ordinal;
"""

DOWNGRADE = """
DROP VIEW IF EXISTS pv_attachment_link; DROP VIEW IF EXISTS pv_file; DROP VIEW IF EXISTS pv_identity;
DROP VIEW IF EXISTS pv_extraction;
DROP INDEX IF EXISTS ix_phone_comm_events_dup;
DROP INDEX IF EXISTS ix_phone_comm_events_case_stream; DROP INDEX IF EXISTS ix_phone_comm_events_thread_stream;
DROP INDEX IF EXISTS ix_phone_comm_events_phone_stream;
DROP TABLE IF EXISTS case_display_settings;
"""


def upgrade():
    op.execute(UPGRADE)


def downgrade():
    op.execute(DOWNGRADE)
