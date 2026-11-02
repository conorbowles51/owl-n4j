"""Phone generic interpretation tables (docs/cellebrite/02-interpretation-identity-projections.md sections 5.6, 5.7).

Case-scoped, derived and rebuildable from the capture: time values, location points, records that cannot be
placed, participations, searchable texts, written addresses and one summary per record, plus the per-extraction
interpretation state. Every row carries the common columns of 5.6 and a ``generation``: a pass writes generation
n+1 and deletes generation n in one transaction (5.7), so a failed pass leaves the previous one readable.
``interpretation_level`` is varchar(24) because ``applied_unconfirmed`` (19 characters) does not fit 5.6's 16
(02 decision 41). Every table cascades from ``phone_extractions``.

Downgrade drops the tables.
"""
from alembic import op

revision = "20261102_phone_generic"
down_revision = "20261102_phone_registry"
branch_labels = None
depends_on = None

COMMON = """
  case_id              uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  extraction_id        uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  document_index       smallint NOT NULL,
  ordinal              integer NOT NULL,
  record_uid           uuid NOT NULL,
  root_record_uid      uuid NOT NULL,
  locator              text NOT NULL,
  model_type           varchar(128) NOT NULL,
  interpretation_level varchar(24) NOT NULL DEFAULT 'generic'
                       CHECK (interpretation_level IN ('captured_only','generic','applied_unconfirmed','reviewed')),
  mapping_version_id   uuid,
  deleted_state        varchar(32),
  decoding_confidence  varchar(32),
  flags                text[] NOT NULL DEFAULT '{}',
  generation           integer NOT NULL"""

TABLES = {
    "phone_time_values": """
  time_uid                uuid NOT NULL,
  body_path               text NOT NULL,
  field_name              varchar(256),
  field_path              text NOT NULL,
  value_index             integer NOT NULL,
  instant                 timestamptz,
  local_wall_time         timestamp,
  original_text           text NOT NULL,
  formatted_text          text,
  original_offset_minutes smallint,
  offset_state            varchar(12) NOT NULL,
  producer_format         varchar(32),
  format_mismatch         boolean NOT NULL DEFAULT false,
  offset_present          boolean NOT NULL,
  effective_instant       timestamptz,
  instant_basis           varchar(16),
  field_meaning           text,
  semantics               text,
  is_event_time           boolean NOT NULL DEFAULT false,
  PRIMARY KEY (time_uid, generation)""",
    "phone_location_points": """
  point_uid             uuid NOT NULL,
  coordinate_record_uid uuid NOT NULL,
  lat                   double precision NOT NULL,
  lon                   double precision NOT NULL,
  lat_text              text,
  lon_text              text,
  elevation_m           numeric,
  accuracy_m            numeric,
  accuracy_basis        varchar(16) NOT NULL,
  precision_text        text,
  source_kind           varchar(160) NOT NULL,
  affiliation           varchar(64),
  instant               timestamptz,
  end_instant           timestamptz,
  time_field            varchar(256),
  PRIMARY KEY (point_uid, generation)""",
    "phone_unplaced_records": """
  reason                varchar(32) NOT NULL,
  PRIMARY KEY (record_uid, generation)""",
    "phone_participations": """
  participation_uid uuid NOT NULL,
  party_record_uid  uuid,
  container_field   varchar(256),
  role              varchar(280) NOT NULL,
  role_basis        varchar(24) NOT NULL,
  role_in_record    varchar(64),
  is_phone_owner    boolean,
  identifier_raw    text,
  name_in_record    text,
  identity_key      text,
  date_read         timestamptz,
  date_delivered    timestamptz,
  date_played       timestamptz,
  PRIMARY KEY (participation_uid, generation)""",
    "phone_texts": """
  text_uid        uuid NOT NULL,
  body_path       text NOT NULL,
  field_name      varchar(256),
  field_path      text NOT NULL,
  value_index     integer NOT NULL,
  value           text NOT NULL,
  value_folded    text NOT NULL,
  effective_value text NOT NULL,
  is_sensitive    boolean NOT NULL DEFAULT false,
  PRIMARY KEY (text_uid, generation)""",
    "phone_address_texts": """
  address_uid  uuid NOT NULL,
  field_path   text NOT NULL,
  address_text text NOT NULL,
  PRIMARY KEY (address_uid, generation)""",
    "phone_record_summaries": """
  parent_record_uid uuid,
  is_top_level      boolean NOT NULL,
  title             text NOT NULL,
  first_instant     timestamptz,
  has_time          boolean NOT NULL,
  has_point         boolean NOT NULL,
  participant_count integer NOT NULL DEFAULT 0,
  direction         varchar(16),
  duration_seconds  numeric(18,7),
  user_mapping      varchar(64),
  source_index      varchar(32),
  file_id           text,
  PRIMARY KEY (record_uid, generation)""",
}

UPGRADE_STATE = """
CREATE TABLE phone_interpretation_state (
  extraction_id         uuid PRIMARY KEY REFERENCES phone_extractions(id) ON DELETE CASCADE,
  case_id               uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  generation            integer NOT NULL DEFAULT 0,
  mapping_set_id        uuid,
  interpreter_version   varchar(32),
  capture_revision      varchar(64),
  registry_observed_at  timestamptz,
  interpreted_at        timestamptz,
  identities_at         timestamptz,
  texts_at              timestamptz,
  projected_at          timestamptz,
  device_zone           varchar(64),
  device_zone_basis     varchar(32),
  examiner_zone         varchar(64),
  decision_revision     varchar(64),
  status                varchar(16) NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','running','done','failed','held')),
  error                 text,
  counts                jsonb NOT NULL DEFAULT '{}'::jsonb,
  started_at            timestamptz,
  updated_at            timestamptz NOT NULL DEFAULT now()
);
"""

INDEXES = """
CREATE INDEX ix_phone_time_values_ext ON phone_time_values (case_id, extraction_id, model_type);
CREATE INDEX ix_phone_time_values_instant ON phone_time_values (case_id, effective_instant, time_uid);
CREATE INDEX ix_phone_time_values_ext_instant ON phone_time_values (case_id, extraction_id, effective_instant);
CREATE INDEX ix_phone_time_values_record ON phone_time_values (record_uid);
CREATE INDEX ix_phone_location_points_ext ON phone_location_points (case_id, extraction_id, model_type);
CREATE INDEX ix_phone_location_points_instant ON phone_location_points (case_id, instant);
CREATE INDEX ix_phone_location_points_geo ON phone_location_points USING gist (point(lon, lat));
CREATE INDEX ix_phone_unplaced_ext ON phone_unplaced_records (case_id, extraction_id, model_type);
CREATE INDEX ix_phone_participations_ext ON phone_participations (case_id, extraction_id, model_type);
CREATE INDEX ix_phone_participations_record ON phone_participations (record_uid);
CREATE INDEX ix_phone_participations_identity ON phone_participations (identity_key, record_uid);
CREATE INDEX ix_phone_texts_ext ON phone_texts (case_id, extraction_id, model_type);
CREATE INDEX ix_phone_texts_record ON phone_texts (record_uid);
CREATE INDEX ix_phone_texts_folded ON phone_texts USING gin (value_folded gin_trgm_ops);
CREATE INDEX ix_phone_address_texts_ext ON phone_address_texts (case_id, extraction_id, model_type);
CREATE INDEX ix_phone_record_summaries_ext ON phone_record_summaries (case_id, extraction_id, model_type);
CREATE INDEX ix_phone_record_summaries_parent ON phone_record_summaries (parent_record_uid);
"""

DROP_ORDER = ("phone_record_summaries", "phone_address_texts", "phone_texts", "phone_participations",
              "phone_unplaced_records", "phone_location_points", "phone_time_values", "phone_interpretation_state")


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for name, cols in TABLES.items():
        op.execute("CREATE TABLE %s (%s,%s\n);" % (name, COMMON, cols))
    op.execute(UPGRADE_STATE)
    op.execute(INDEXES)


def downgrade():
    for t in DROP_ORDER:
        op.execute("DROP TABLE IF EXISTS %s" % t)
