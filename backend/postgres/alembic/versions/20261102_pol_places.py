"""Pattern of life: place observations, offline cell reference data and WiFi anchors (04 sections 6, 7.3, 7.6).

``pol_place_observation``: every place-bearing record as an area in time (kind, source kind, radius and its basis).
``pol_reference_dataset`` / ``pol_cell_reference``: each offline cell-tower import kept as a dated version, never
overwritten; nothing is fetched at query time. ``pol_case_cell_dataset``: the version a case uses, chosen by a person
(none until Neil rules on the licence question; towers then stay "not placed"). ``pol_unplaced_tower``: every tower
with its key and why it has no position. ``pol_wifi_anchor``: BSSID positions derived from the case's own GPS fixes.

All are projections except the reference datasets and the case's choice. Downgrade drops them.
"""
from alembic import op

revision = "20261102_pol_places"
down_revision = "20261102_pol_timeline_class"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE pol_reference_dataset (
  id                uuid PRIMARY KEY,
  kind              varchar(8) NOT NULL CHECK (kind IN ('cell')),
  name              text NOT NULL,
  licence           text NOT NULL,
  attribution       text NOT NULL,
  source_note       text,
  file_sha256       char(64) NOT NULL,
  retrieved_on      date NOT NULL,
  imported_at       timestamptz NOT NULL DEFAULT now(),
  row_count         bigint NOT NULL DEFAULT 0,
  duplicate_rows    bigint NOT NULL DEFAULT 0,
  rejected_rows     bigint NOT NULL DEFAULT 0,
  imported_by_name  varchar(255) NOT NULL,
  imported_by_email varchar(255) NOT NULL
);

CREATE TABLE pol_cell_reference (
  dataset_id  uuid NOT NULL REFERENCES pol_reference_dataset(id) ON DELETE CASCADE,
  radio       varchar(8) NOT NULL,
  mcc         integer NOT NULL,
  mnc         integer NOT NULL,
  lac         bigint NOT NULL,
  cid         bigint NOT NULL,
  lat         double precision NOT NULL,
  lon         double precision NOT NULL,
  range_m     integer,
  samples     integer,
  updated_at  timestamptz,
  PRIMARY KEY (dataset_id, radio, mcc, mnc, lac, cid)
);
CREATE INDEX ix_pol_cell_reference_key ON pol_cell_reference (dataset_id, mcc, mnc, lac, cid);

CREATE TABLE pol_case_cell_dataset (
  case_id     uuid PRIMARY KEY REFERENCES cases(id) ON DELETE CASCADE,
  dataset_id  uuid NOT NULL REFERENCES pol_reference_dataset(id),
  decision_id uuid,
  chosen_by   varchar(255) NOT NULL,
  chosen_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE pol_wifi_anchor (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  case_id        uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  bssid_norm     varchar(17) NOT NULL,
  lat            double precision NOT NULL,
  lon            double precision NOT NULL,
  radius_m       double precision NOT NULL,
  support_days   integer NOT NULL,
  support_points integer NOT NULL,
  status         varchar(12) NOT NULL CHECK (status IN ('anchored','tentative')),
  computed_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_pol_wifi_anchor UNIQUE (case_id, bssid_norm)
);

CREATE TABLE pol_place_observation (
  id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  case_id               uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  extraction_id         uuid REFERENCES phone_extractions(id) ON DELETE CASCADE,
  record_uid            uuid,
  coordinate_record_uid uuid,
  field_path            varchar(512),
  record_type           varchar(64),
  kind                  varchar(16) NOT NULL CHECK (kind IN ('presence','searched','planned','declared','media',
                                                             'transaction')),
  source_kind           varchar(24) NOT NULL,
  lat                   double precision NOT NULL,
  lon                   double precision NOT NULL,
  radius_m              double precision,
  radius_reported       double precision,
  radius_basis          varchar(32) NOT NULL,
  start_utc             timestamptz NOT NULL,
  end_utc               timestamptz NOT NULL,
  offset_status         varchar(8) NOT NULL,
  time_semantics        varchar(24) NOT NULL,
  presence_basis        varchar(32),
  attribution_flags     text[] NOT NULL DEFAULT '{}',
  reference_dataset_id  uuid REFERENCES pol_reference_dataset(id),
  wifi_anchor_id        bigint,
  decision_id           uuid,
  source_app            varchar(128)
);
CREATE INDEX ix_pol_place_observation_ext ON pol_place_observation (extraction_id, start_utc);
CREATE INDEX ix_pol_place_observation_case ON pol_place_observation (case_id, start_utc);
CREATE INDEX ix_pol_place_observation_range ON pol_place_observation
  USING gist (tstzrange(start_utc, end_utc, '[]'));

CREATE TABLE pol_unplaced_tower (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  case_id       uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  extraction_id uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  record_uid    uuid NOT NULL,
  radio         varchar(8),
  mcc           integer,
  mnc           integer,
  lac           bigint,
  cid           bigint,
  instant_utc   timestamptz,
  reason        varchar(40) NOT NULL CHECK (reason IN ('no_reference_dataset','tower_not_in_reference_data',
                                                       'key_incomplete','no_time'))
);
CREATE INDEX ix_pol_unplaced_tower_ext ON pol_unplaced_tower (extraction_id);
"""


def upgrade():
    op.execute(UPGRADE)


def downgrade():
    for t in ("pol_unplaced_tower", "pol_place_observation", "pol_wifi_anchor", "pol_case_cell_dataset",
              "pol_cell_reference", "pol_reference_dataset"):
        op.execute("DROP TABLE IF EXISTS %s" % t)
