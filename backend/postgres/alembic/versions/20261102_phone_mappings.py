"""Phone mappings as versioned data (docs/cellebrite/02 section 6) and their judgement calls.

- ``phone_mapping_versions``: every loaded mapping file version, append only (6.6).
- ``phone_mapping_rows``: every row of every loaded row-table mapping, for SQL joins by spec 04 (6.5b).
- ``phone_mapping_current``: the version of each (kind, name) in force.
- ``phone_mapping_applications``: which version produced which generation of an extraction, with suspensions.
- ``phone_mapping_proposals``: AI drafts and case corrections waiting for an admin (6.8); never read by the applier.
- ``phone_mapping_judgements``: one judgement call per (extraction, mapping rule, mapping version) (Neil,
  2026-10-29: a mapping row is applied at once and shown as a judgement call for a person to confirm or correct),
  modelled on ``financial_judgements``: the rule in plain words, the records it touched (a count and three sample
  record ids), the evidence (the registry fields it rests on), status open, confirmed or corrected.

Every derived table gains ``mapping_row_id`` beside ``mapping_version_id`` (6.7: a derived row names the mapping
rule that produced it).
"""
from alembic import op

revision = "20261102_phone_mappings"
down_revision = "20261102_phone_read_views"
branch_labels = None
depends_on = None

DERIVED = ("phone_time_values", "phone_location_points", "phone_unplaced_records", "phone_participations",
           "phone_texts", "phone_address_texts", "phone_record_summaries")

UPGRADE = """
CREATE TABLE phone_mapping_versions (
  id             uuid PRIMARY KEY,
  kind           varchar(32) NOT NULL,
  name           varchar(128) NOT NULL,
  version        integer NOT NULL,
  content_sha256 char(64) NOT NULL,
  content        jsonb NOT NULL,
  status         varchar(24) NOT NULL CHECK (status IN ('applied_unconfirmed','reviewed')),
  origin         varchar(16) NOT NULL CHECK (origin IN ('human','ai_draft')),
  reviewed_by    varchar(256),
  reviewed_on    date,
  loaded_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_phone_mapping_versions UNIQUE (kind, name, version, content_sha256)
);
CREATE INDEX ix_phone_mapping_versions_name ON phone_mapping_versions (kind, name, version);

CREATE TABLE phone_mapping_rows (
  mapping_version_id uuid NOT NULL REFERENCES phone_mapping_versions(id),
  kind               varchar(32) NOT NULL,
  name               varchar(128) NOT NULL,
  row_id             varchar(128) NOT NULL,
  type_name          varchar(128) NOT NULL,
  field_name         varchar(256),
  predicates         jsonb NOT NULL DEFAULT '[]'::jsonb,
  context            jsonb NOT NULL DEFAULT '[]'::jsonb,
  specificity        integer NOT NULL,
  outputs            jsonb NOT NULL,
  basis              varchar(32) NOT NULL,
  reasoning          text NOT NULL,
  would_change       text NOT NULL,
  PRIMARY KEY (mapping_version_id, row_id)
);
CREATE INDEX ix_phone_mapping_rows_lookup ON phone_mapping_rows (kind, type_name, field_name);

CREATE TABLE phone_mapping_current (
  kind               varchar(32) NOT NULL,
  name               varchar(128) NOT NULL,
  mapping_version_id uuid NOT NULL REFERENCES phone_mapping_versions(id),
  set_at             timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (kind, name)
);

CREATE TABLE phone_mapping_applications (
  extraction_id      uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  mapping_version_id uuid NOT NULL REFERENCES phone_mapping_versions(id),
  generation         integer NOT NULL,
  records_matched    bigint NOT NULL DEFAULT 0,
  records_suspended  bigint NOT NULL DEFAULT 0,
  suspension_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
  applied_at         timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (extraction_id, mapping_version_id, generation)
);

CREATE TABLE phone_mapping_proposals (
  id            uuid PRIMARY KEY,
  kind          varchar(32) NOT NULL,
  name          varchar(128) NOT NULL,
  content       jsonb NOT NULL,
  model         varchar(128),
  model_version varchar(128),
  origin        varchar(24) NOT NULL CHECK (origin IN ('ai_draft','case_correction')),
  decision_id   uuid,
  state         varchar(16) NOT NULL DEFAULT 'draft' CHECK (state IN ('draft','rejected','exported')),
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE phone_mapping_judgements (
  id                  uuid PRIMARY KEY,
  case_id             uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  extraction_id       uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  mapping_version_id  uuid NOT NULL REFERENCES phone_mapping_versions(id),
  mapping_kind        varchar(32) NOT NULL,
  mapping_name        varchar(128) NOT NULL,
  rule_id             varchar(160) NOT NULL,
  type_name           varchar(128) NOT NULL,
  rule_part           varchar(32) NOT NULL,
  summary             text NOT NULL,
  strength            varchar(16) NOT NULL DEFAULT 'inferred' CHECK (strength IN ('proved','inferred')),
  records_touched     bigint NOT NULL DEFAULT 0,
  sample_record_uids  uuid[] NOT NULL DEFAULT '{}',
  evidence            jsonb NOT NULL DEFAULT '{}'::jsonb,
  status              varchar(16) NOT NULL DEFAULT 'open' CHECK (status IN ('open','confirmed','corrected')),
  resolved_by         varchar(255),
  resolved_by_email   varchar(255),
  resolved_at         timestamptz,
  resolution_reason   text,
  adjudication_id     uuid,
  generation          integer NOT NULL,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_phone_mapping_judgements UNIQUE (extraction_id, rule_id, mapping_version_id)
);
CREATE INDEX ix_phone_mapping_judgements_case ON phone_mapping_judgements (case_id, status);
"""


def upgrade():
    op.execute(UPGRADE)
    for t in DERIVED:
        op.execute("ALTER TABLE %s ADD COLUMN mapping_row_id varchar(160)" % t)


def downgrade():
    for t in DERIVED:
        op.execute("ALTER TABLE %s DROP COLUMN mapping_row_id" % t)
    for t in ("phone_mapping_judgements", "phone_mapping_proposals", "phone_mapping_applications",
              "phone_mapping_current", "phone_mapping_rows", "phone_mapping_versions"):
        op.execute("DROP TABLE %s" % t)
