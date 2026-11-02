"""Pattern of life: activity events and their strength (docs/cellebrite/04-pattern-of-life.md sections 3, 4, 7.1, 7.2).

``pol_projection_state`` says which mapping versions and which interpretation generation an extraction's pattern
projection was built from. ``pol_activity_event`` holds one row per (record, time field) whose time meaning is an
activity (all of 2.3 except 3.3), with the class, actor and physical qualifier the reviewed activity-strength rows
decide and the attribution flags of 4.2. Strength is not a column: ``pol_activity_event_v`` computes it from the
columns (04 decision 1), so a mapping change cannot leave a stale strength behind.

``match_facts`` keeps the few field values and computed facts the loaded rows match on, so a new mapping version
re-classifies an extraction without reading its records again (3.4 item 4; 04 decision 19).

Every table cascades from ``cases`` and ``phone_extractions``; the projection is rebuilt from the capture,
interpretation and mappings. Downgrade drops the view and the tables.
"""
from alembic import op

revision = "20261102_pol_activity"
down_revision = "20261102_phone_corrections"
branch_labels = None
depends_on = None

GROUP_A = ("synced_from_account", "other_device_platform", "user_mapping_other", "wearable", "offset_absent")
GROUP_B = ("affiliation_unknown", "account_level", "deleted_record", "low_decoding_confidence", "latest_only",
           "bucketed")


def _arr(names):
    return "ARRAY[%s]::text[]" % ", ".join("'%s'" % n for n in names)


UPGRADE = """
CREATE TABLE pol_projection_state (
  extraction_id               uuid PRIMARY KEY REFERENCES phone_extractions(id) ON DELETE CASCADE,
  case_id                     uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  interpretation_generation   integer,
  activity_mapping_version    uuid,
  meaning_mapping_version     uuid,
  attribution_mapping_version uuid,
  cell_dataset_id             uuid,
  signature                   varchar(64),
  facts_fields                jsonb NOT NULL DEFAULT '{}'::jsonb,
  built_at                    timestamptz,
  event_count                 bigint NOT NULL DEFAULT 0,
  counts                      jsonb NOT NULL DEFAULT '{}'::jsonb,
  status                      varchar(16) NOT NULL DEFAULT 'building'
                              CHECK (status IN ('building','ready','stale','failed')),
  error                       text
);
CREATE INDEX ix_pol_projection_state_case ON pol_projection_state (case_id);

CREATE TABLE pol_activity_event (
  id                        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  case_id                   uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  extraction_id             uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  record_uid                uuid NOT NULL,
  root_record_uid           uuid NOT NULL,
  record_type               varchar(64) NOT NULL,
  time_field                varchar(64) NOT NULL,
  field_path                text NOT NULL,
  end_field                 varchar(64),
  instant_utc               timestamptz NOT NULL,
  end_utc                   timestamptz,
  offset_status             varchar(8) NOT NULL CHECK (offset_status IN ('explicit','absent')),
  instant_basis             varchar(24) NOT NULL,
  original                  text NOT NULL,
  time_semantics            varchar(24) NOT NULL,
  meaning_mapping_row       varchar(160),
  stream_key                varchar(160) NOT NULL,
  family                    varchar(24) NOT NULL,
  value_key                 varchar(160),
  activity_class            varchar(16) NOT NULL
                            CHECK (activity_class IN ('interaction','device_state','passive','unknown')),
  class_basis               varchar(16) NOT NULL CHECK (class_basis IN ('reviewed_mapping','default_unknown')),
  class_level               varchar(24),
  activity_mapping_row      varchar(160),
  activity_mapping_version  uuid,
  actor                     varchar(16) NOT NULL
                            CHECK (actor IN ('owner','counterpart','other_device','account','unknown')),
  counterpart_identity_id   uuid,
  physical                  boolean NOT NULL DEFAULT false,
  attribution_flags         text[] NOT NULL DEFAULT '{}',
  attribution_mapping_rows  text[] NOT NULL DEFAULT '{}',
  deleted_state             varchar(16),
  decoding_confidence       varchar(16),
  source_app                varchar(128),
  match_facts               jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE UNIQUE INDEX uq_pol_activity_event_key ON pol_activity_event (extraction_id, record_uid, time_field);
CREATE INDEX ix_pol_activity_event_ext_instant ON pol_activity_event (extraction_id, instant_utc);
CREATE INDEX ix_pol_activity_event_case_instant ON pol_activity_event (case_id, instant_utc);
CREATE INDEX ix_pol_activity_event_interaction ON pol_activity_event (extraction_id, instant_utc)
  WHERE activity_class = 'interaction';
CREATE INDEX ix_pol_activity_event_counterpart ON pol_activity_event (case_id, counterpart_identity_id, instant_utc);
"""

VIEW = """
CREATE VIEW pol_activity_event_v AS
SELECT x.*,
  CASE
    WHEN x.activity_class = 'interaction' THEN CASE
      WHEN x.time_semantics = 'unknown' THEN 'none'
      WHEN x.flags_a > 0 OR x.flags_b >= 2 OR x.time_semantics IN ('aggregate_bucket','service_observed')
           OR x.actor IN ('other_device','unknown') THEN 'weak'
      WHEN x.flags_b = 1 OR x.time_semantics IN ('latest_of_many','last_modified','first_record')
           OR x.offset_status <> 'explicit' OR coalesce(x.deleted_state, '') <> 'Intact' THEN 'moderate'
      WHEN x.time_semantics IN ('event_instant','interval_start','interval_end','counterpart_action') THEN 'strong'
      ELSE 'moderate' END
    WHEN x.activity_class = 'device_state' THEN CASE
      WHEN x.time_semantics = 'unknown' THEN 'none'
      WHEN x.actor IN ('owner','counterpart') AND x.flags_a + x.flags_b = 0 THEN 'moderate'
      ELSE 'weak' END
    WHEN x.activity_class = 'passive' AND x.physical THEN 'weak'
    ELSE 'none'
  END AS strength,
  CASE WHEN x.actor IN ('owner','counterpart') THEN x.actor ELSE 'none' END AS counts_for
FROM (
  SELECT ev.*,
    cardinality(ARRAY(SELECT unnest(ev.attribution_flags) INTERSECT SELECT unnest(%(a)s))) AS flags_a,
    cardinality(ARRAY(SELECT unnest(ev.attribution_flags) INTERSECT SELECT unnest(%(b)s))) AS flags_b
  FROM pol_activity_event ev
) x;
""" % {"a": _arr(GROUP_A), "b": _arr(GROUP_B)}


def upgrade():
    op.execute(UPGRADE)
    op.execute(VIEW)


def downgrade():
    op.execute("DROP VIEW IF EXISTS pol_activity_event_v")
    op.execute("DROP TABLE IF EXISTS pol_activity_event")
    op.execute("DROP TABLE IF EXISTS pol_projection_state")
