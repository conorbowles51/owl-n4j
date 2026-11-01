"""Phone capture schema (docs/cellebrite/01-intake-capture-storage.md section 6.2, unit 1.1).

Ten tables of 01 section 6.2 plus the two that hold PA's record-to-source information (``extraInfos``, 01
sections 1.8 and 1.9, decision D24): ``phone_extra_infos`` (one row per ``extraInfo``, its full element as the
body) and ``phone_extra_info_nodes`` (one row per ``nodeInfo`` inside it, resolved to a tagged file).
``phone_files.parent_ordinal`` holds the owner of a ``RelatedNodes/file`` child (decision D23).

The extraction is unique per (case_id, report_set_sha256); ``root_path`` belongs to each container link (D22).
It also merges the two heads the tree had when it was written (ui_problem_reports, timeline_view_instants).
Downgrade drops every table and both types; it refuses while any extraction exists.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261101_phone_capture"
down_revision = ("20261101_ui_problem_reports", "20261101_timeline_view_instants")
branch_labels = None
depends_on = None

CAPTURE_STATES = ("received", "detecting", "not_readable", "counting", "capturing", "reconciling", "captured",
                  "captured_incomplete", "reconciliation_failed", "failed", "cancelled")

UPGRADE = r"""
CREATE TYPE phone_capture_state AS ENUM (%(states)s);
CREATE TYPE phone_extraction_standing AS ENUM ('pending', 'active', 'superseded');

CREATE TABLE phone_extraction_containers (
  id                 uuid PRIMARY KEY,
  case_id            uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  evidence_file_id   uuid REFERENCES evidence_files(id) ON DELETE SET NULL,
  upload_group_id    uuid REFERENCES evidence_upload_groups(id) ON DELETE SET NULL,
  container_kind     varchar(20) NOT NULL CHECK (container_kind IN ('ufdr','zip','folder','single_document')),
  stored_path        text NOT NULL,
  original_name      varchar(1024) NOT NULL,
  size_bytes         bigint NOT NULL,
  sha256             char(64) NOT NULL,
  md5                char(32) NOT NULL,
  upload_sha256      char(64),
  intake_outcome     varchar(40) NOT NULL,
  classification     jsonb NOT NULL,
  received_at        timestamptz NOT NULL DEFAULT now(),
  received_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX ix_phone_containers_case ON phone_extraction_containers(case_id);
CREATE INDEX ix_phone_containers_sha ON phone_extraction_containers(case_id, sha256);

CREATE TABLE phone_extractions (
  id                    uuid PRIMARY KEY,
  case_id               uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  report_set_sha256     char(64) NOT NULL,
  first_container_id    uuid NOT NULL REFERENCES phone_extraction_containers(id),
  form                  varchar(20) NOT NULL CHECK (form IN ('full','split_sections','ufdr')),
  capture_state         phone_capture_state NOT NULL DEFAULT 'received',
  standing              phone_extraction_standing NOT NULL DEFAULT 'pending',
  supersedes_id         uuid REFERENCES phone_extractions(id),
  superseded_at         timestamptz,
  superseded_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  superseded_reason     text,                -- the typed reason for Replace or Retire (01 section 10.7, D35)
  report_version        varchar(32),
  producer_version      varchar(64),
  extraction_type       varchar(64),
  device_zone           varchar(64),
  device_zone_source    varchar(64) CHECK (device_zone_source IS NULL OR device_zone_source IN ('device_metadata','decision')),
  flags                 jsonb NOT NULL DEFAULT '{}',
  record_count          integer,
  file_count            integer,
  engine_job_id         uuid REFERENCES jobs(id) ON DELETE SET NULL,
  capture_code_version  varchar(32) NOT NULL,
  created_at            timestamptz NOT NULL DEFAULT now(),
  captured_at           timestamptz,
  CONSTRAINT uq_phone_extraction_report UNIQUE (case_id, report_set_sha256)
);
CREATE UNIQUE INDEX uq_phone_extraction_supersedes ON phone_extractions(supersedes_id) WHERE supersedes_id IS NOT NULL;
CREATE INDEX ix_phone_extractions_case_standing ON phone_extractions(case_id, standing);

CREATE TABLE phone_extraction_container_links (
  extraction_id uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  container_id  uuid NOT NULL REFERENCES phone_extraction_containers(id) ON DELETE CASCADE,
  root_path     text NOT NULL,
  linked_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (extraction_id, container_id, root_path)
);

CREATE TABLE phone_extraction_documents (
  extraction_id    uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  document_index   smallint NOT NULL,
  path             text NOT NULL,
  role             varchar(20) NOT NULL,
  size_bytes       bigint NOT NULL,
  sha256           char(64) NOT NULL,
  md5              char(32) NOT NULL,
  root_element     varchar(64),
  parse_state      varchar(16) NOT NULL DEFAULT 'pending' CHECK (parse_state IN ('pending','complete','truncated','empty')),
  truncation       jsonb,
  skeleton         jsonb,
  source_counts    jsonb,
  capture_cursor   jsonb NOT NULL DEFAULT '{"record_ordinal":0,"file_ordinal":0,"extra_ordinal":0}',
  PRIMARY KEY (extraction_id, document_index)
);

CREATE TABLE phone_records (
  extraction_id    uuid NOT NULL,
  document_index   smallint NOT NULL,
  ordinal          integer NOT NULL,
  parent_ordinal   integer,
  top_ordinal      integer NOT NULL,
  depth            smallint NOT NULL,
  model_type       varchar(128) NOT NULL,
  source_model_id  varchar(128),
  deleted_state    varchar(32),
  is_partial       boolean NOT NULL DEFAULT false,
  body             jsonb NOT NULL,
  PRIMARY KEY (extraction_id, document_index, ordinal),
  FOREIGN KEY (extraction_id, document_index) REFERENCES phone_extraction_documents ON DELETE CASCADE
);
CREATE INDEX ix_phone_records_type ON phone_records(extraction_id, model_type);
CREATE INDEX ix_phone_records_top ON phone_records(extraction_id, document_index, top_ordinal);
CREATE INDEX ix_phone_records_source_id ON phone_records(extraction_id, source_model_id);

CREATE TABLE phone_files (
  extraction_id    uuid NOT NULL,
  document_index   smallint NOT NULL,
  ordinal          integer NOT NULL,
  file_uid         uuid NOT NULL,          -- 02 section 1.2: uuid5 of the positional key, written at capture
  parent_ordinal   integer,
  source_file_id   varchar(128),
  local_path       text,
  declared_size    bigint,
  declared_md5     varchar(64),
  declared_sha256  varchar(128),
  tags             varchar(64),
  is_partial       boolean NOT NULL DEFAULT false,
  body             jsonb NOT NULL,
  disk_relpath     text,
  disk_size        bigint,
  disk_md5         char(32),
  disk_sha256      char(64),
  outcome          varchar(24) CHECK (outcome IS NULL OR outcome IN ('no_local_path','missing','empty_placeholder','size_mismatch','match','mismatch','no_hash')),
  verified_at      timestamptz,
  PRIMARY KEY (extraction_id, document_index, ordinal),
  FOREIGN KEY (extraction_id, document_index) REFERENCES phone_extraction_documents ON DELETE CASCADE
);
CREATE INDEX ix_phone_files_source_id ON phone_files(extraction_id, source_file_id);
CREATE UNIQUE INDEX uq_phone_files_file_uid ON phone_files(file_uid);
CREATE INDEX ix_phone_files_path ON phone_files(extraction_id, lower(replace(local_path, '\', '/')));
CREATE INDEX ix_phone_files_content ON phone_files(disk_sha256) WHERE disk_sha256 IS NOT NULL;

CREATE TABLE phone_container_entries (
  extraction_id uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  relpath       text NOT NULL,
  size_bytes    bigint NOT NULL,
  sha256        char(64),
  md5           char(32),
  PRIMARY KEY (extraction_id, relpath)
);

CREATE TABLE phone_file_references (
  extraction_id   uuid NOT NULL,
  document_index  smallint NOT NULL,
  record_ordinal  integer NOT NULL,
  body_path       text NOT NULL,
  mechanism       varchar(24) NOT NULL CHECK (mechanism IN ('jumptarget','file_id_attribute','extracted_path_value')),
  reference_text  text NOT NULL,
  file_document_index smallint,
  file_ordinal    integer,
  container_relpath text,
  resolution      varchar(24) NOT NULL CHECK (resolution IN ('tagged_file','container_entry','model','unresolved')),
  ambiguous       boolean NOT NULL DEFAULT false,
  PRIMARY KEY (extraction_id, document_index, record_ordinal, body_path, mechanism),
  FOREIGN KEY (extraction_id, document_index) REFERENCES phone_extraction_documents ON DELETE CASCADE
);
CREATE INDEX ix_phone_file_refs_file ON phone_file_references(extraction_id, file_document_index, file_ordinal);

CREATE TABLE phone_timestamps (
  extraction_id   uuid NOT NULL,
  document_index  smallint NOT NULL,
  owner_kind      varchar(8) NOT NULL CHECK (owner_kind IN ('record','file','skeleton')),
  owner_ordinal   integer NOT NULL,
  body_path       text NOT NULL,
  model_type      varchar(128),
  field_name      varchar(256),
  value_type      varchar(64) NOT NULL,
  original_text   text NOT NULL,
  formatted_text  text,
  instant         timestamptz,
  local_wall_time timestamp,
  original_offset_minutes smallint,
  offset_state    varchar(12) NOT NULL CHECK (offset_state IN ('explicit','absent','unparsed')),
  parse_rule      varchar(48) NOT NULL,
  PRIMARY KEY (extraction_id, document_index, owner_kind, owner_ordinal, body_path),
  FOREIGN KEY (extraction_id, document_index) REFERENCES phone_extraction_documents ON DELETE CASCADE
);
CREATE INDEX ix_phone_timestamps_instant ON phone_timestamps(extraction_id, instant);
CREATE INDEX ix_phone_timestamps_absent ON phone_timestamps(extraction_id) WHERE offset_state <> 'explicit';

CREATE TABLE phone_reconciliations (
  id              uuid PRIMARY KEY,
  extraction_id   uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  document_index  smallint NOT NULL,
  ran_at          timestamptz NOT NULL DEFAULT now(),
  counter_version varchar(32) NOT NULL,
  result          varchar(8) NOT NULL CHECK (result IN ('exact','differs')),
  source_totals   jsonb NOT NULL,
  captured_totals jsonb NOT NULL,
  differences     jsonb NOT NULL DEFAULT '[]',
  difference_count integer NOT NULL DEFAULT 0
);
CREATE INDEX ix_phone_reconciliations_extraction ON phone_reconciliations(extraction_id, document_index, ran_at);

CREATE TABLE phone_extra_infos (
  extraction_id    uuid NOT NULL,
  document_index   smallint NOT NULL,
  ordinal          integer NOT NULL,
  source_id        varchar(128),
  info_type        varchar(128),
  is_partial       boolean NOT NULL DEFAULT false,
  body             jsonb NOT NULL,
  PRIMARY KEY (extraction_id, document_index, ordinal),
  FOREIGN KEY (extraction_id, document_index) REFERENCES phone_extraction_documents ON DELETE CASCADE
);
CREATE INDEX ix_phone_extra_infos_source_id ON phone_extra_infos(extraction_id, source_id);

CREATE TABLE phone_extra_info_nodes (
  extraction_id    uuid NOT NULL,
  document_index   smallint NOT NULL,
  extra_ordinal    integer NOT NULL,
  body_path        text NOT NULL,
  node_id          varchar(128),
  node_name        text,
  node_path        text,
  table_name       varchar(256),
  node_offset      text,
  node_size        text,
  file_document_index smallint,
  file_ordinal     integer,
  resolution       varchar(24) NOT NULL CHECK (resolution IN ('tagged_file_id','tagged_file_path','unresolved')),
  PRIMARY KEY (extraction_id, document_index, extra_ordinal, body_path),
  FOREIGN KEY (extraction_id, document_index) REFERENCES phone_extraction_documents ON DELETE CASCADE
);
CREATE INDEX ix_phone_extra_info_nodes_file ON phone_extra_info_nodes(extraction_id, file_document_index, file_ordinal);
""" % {"states": ", ".join("'%s'" % s for s in CAPTURE_STATES)}

TABLES = ("phone_extra_info_nodes", "phone_extra_infos", "phone_reconciliations", "phone_timestamps",
          "phone_file_references", "phone_container_entries", "phone_files", "phone_records",
          "phone_extraction_documents", "phone_extraction_container_links", "phone_extractions",
          "phone_extraction_containers")


def upgrade():
    op.get_bind().exec_driver_sql(UPGRADE)


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM phone_extractions")).scalar_one():
        raise RuntimeError("Cannot drop the phone capture tables: phone extractions exist.")
    for t in TABLES:
        op.execute("DROP TABLE IF EXISTS %s" % t)
    op.execute("DROP TYPE IF EXISTS phone_extraction_standing")
    op.execute("DROP TYPE IF EXISTS phone_capture_state")
