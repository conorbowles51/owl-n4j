"""Phone schema registry (docs/cellebrite/02-interpretation-identity-projections.md section 3, unit 02-U2).

Global and structure only: every record type, field (name, kind, value type), named-set value, nesting relation and
attribute name the reports have been seen to contain, with where each was first seen; per-extraction observation
counts; and the review queue of flags with its append-only event table (the registry is global, so case
adjudications, which need a case, cannot hold its history: 02 section 3.2). No row holds a value from a report
other than named-set vocabulary. Seeded by ``scripts/phone_registry_seed.py``, not by this migration.

Downgrade drops the eight tables; it refuses while any observation exists.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261102_phone_registry"
down_revision = "20261102_batches_status_index"
branch_labels = None
depends_on = None

ORIGIN = "origin varchar(16) NOT NULL CHECK (origin IN ('seed','observed'))"
FIRST_SEEN = """
  first_seen_at               timestamptz NOT NULL DEFAULT now(),
  first_seen_extraction_id    uuid REFERENCES phone_extractions(id) ON DELETE SET NULL,
  first_seen_report_version   varchar(32),
  first_seen_producer_version varchar(64)"""

UPGRADE = r"""
CREATE TABLE phone_schema_types (
  type_name                 varchar(128) PRIMARY KEY,
  %(origin)s,%(first_seen)s,
  seed_report_count         integer NOT NULL DEFAULT 0,
  seed_record_count         bigint NOT NULL DEFAULT 0,
  observed_extraction_count integer NOT NULL DEFAULT 0,
  observed_record_count     bigint NOT NULL DEFAULT 0,
  seen_top_level            boolean NOT NULL DEFAULT false,
  seen_nested               boolean NOT NULL DEFAULT false
);

CREATE TABLE phone_schema_fields (
  id                        bigserial PRIMARY KEY,
  type_name                 varchar(128) NOT NULL REFERENCES phone_schema_types(type_name),
  field_name                varchar(256) NOT NULL,
  field_kind                varchar(16) NOT NULL CHECK (field_kind IN ('field','multiField','nodeField','dataField')),
  value_type                varchar(128) NOT NULL,
  is_named_set              boolean NOT NULL,
  %(origin)s,%(first_seen)s,
  seed_value_count          bigint NOT NULL DEFAULT 0,
  seed_report_count         integer NOT NULL DEFAULT 0,
  observed_value_count      bigint NOT NULL DEFAULT 0,
  observed_empty_count      bigint NOT NULL DEFAULT 0,
  observed_extraction_count integer NOT NULL DEFAULT 0,
  max_values_in_one_field   integer NOT NULL DEFAULT 0,
  CONSTRAINT uq_phone_schema_fields UNIQUE (type_name, field_name, field_kind, value_type)
);

CREATE TABLE phone_schema_nesting (
  id                   bigserial PRIMARY KEY,
  parent_type          varchar(128) NOT NULL,
  field_name           varchar(256) NOT NULL,
  field_kind           varchar(16) NOT NULL CHECK (field_kind IN ('modelField','multiModelField','RelatedModels')),
  child_type           varchar(128) NOT NULL,
  %(origin)s,%(first_seen)s,
  observed_child_count bigint NOT NULL DEFAULT 0,
  CONSTRAINT uq_phone_schema_nesting UNIQUE (parent_type, field_name, field_kind, child_type)
);

CREATE TABLE phone_schema_set_values (
  id             bigserial PRIMARY KEY,
  set_name       varchar(128) NOT NULL,
  value          varchar(512) NOT NULL,
  note           text,
  %(origin)s,%(first_seen)s,
  observed_count bigint NOT NULL DEFAULT 0,
  CONSTRAINT uq_phone_schema_set_values UNIQUE (set_name, value)
);

CREATE TABLE phone_schema_attributes (
  id        bigserial PRIMARY KEY,
  element   varchar(64) NOT NULL,
  attribute varchar(128) NOT NULL,
  %(origin)s,%(first_seen)s,
  CONSTRAINT uq_phone_schema_attributes UNIQUE (element, attribute)
);

CREATE TABLE phone_schema_observations (
  extraction_id  uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  registry_table varchar(32) NOT NULL CHECK (registry_table IN ('types','fields','nesting','set_values','attributes')),
  registry_id    bigint NOT NULL,
  record_count   bigint NOT NULL DEFAULT 0,
  value_count    bigint NOT NULL DEFAULT 0,
  empty_count    bigint NOT NULL DEFAULT 0,
  PRIMARY KEY (extraction_id, registry_table, registry_id)
);

CREATE TABLE phone_schema_flags (
  id                      bigserial PRIMARY KEY,
  flag_kind               varchar(24) NOT NULL CHECK (flag_kind IN ('new_type','new_field','new_value_type',
                            'new_set_value','new_nesting','new_attribute','set_overflow','multi_value_field')),
  registry_table          varchar(32) NOT NULL,
  registry_id             bigint NOT NULL,
  raised_by_extraction_id uuid REFERENCES phone_extractions(id) ON DELETE SET NULL,
  severity                varchar(16) NOT NULL DEFAULT 'info' CHECK (severity IN ('info','blocks_mapping')),
  state                   varchar(16) NOT NULL DEFAULT 'open'
                            CHECK (state IN ('open','acknowledged','mapping_needed','mapped','dismissed')),
  detail                  jsonb NOT NULL DEFAULT '{}'::jsonb,
  raised_at               timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_phone_schema_flags_subject UNIQUE (flag_kind, registry_table, registry_id)
);
CREATE INDEX ix_phone_schema_flags_state ON phone_schema_flags(state);

CREATE TABLE phone_schema_flag_events (
  id            bigserial PRIMARY KEY,
  flag_id       bigint NOT NULL REFERENCES phone_schema_flags(id) ON DELETE CASCADE,
  from_state    varchar(16),
  to_state      varchar(16) NOT NULL,
  reason        text NOT NULL CHECK (btrim(reason) <> ''),
  actor_name    varchar(256),
  actor_email   varchar(320),
  actor_user_id uuid,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_phone_schema_flag_events_flag ON phone_schema_flag_events(flag_id, id);
""" % {"origin": ORIGIN, "first_seen": FIRST_SEEN}

TABLES = ("phone_schema_flag_events", "phone_schema_flags", "phone_schema_observations", "phone_schema_attributes",
          "phone_schema_set_values", "phone_schema_nesting", "phone_schema_fields", "phone_schema_types")


def upgrade():
    op.execute(UPGRADE)


def downgrade():
    bind = op.get_bind()
    n = bind.execute(sa.text("SELECT count(*) FROM phone_schema_observations")).scalar()
    if n:
        raise RuntimeError("phone_schema_observations holds %d rows; refusing to drop the registry" % n)
    for t in TABLES:
        op.execute("DROP TABLE %s" % t)
