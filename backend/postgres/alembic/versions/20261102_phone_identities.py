"""Phone identities, sightings, each phone's names and owner candidates (docs/cellebrite/02 sections 8.5, 8.6).

- ``phone_identities``: one row per (case, identity key); id = uuid5 of case and key, so stable across rebuilds.
  Never deleted while a decision may name it: a key no longer seen keeps its row with ``sighting_count = 0``.
- ``phone_identity_sightings``: one identifier value seen in one record (or the report header) on one phone, per
  generation, with its context (``party``, ``owner_party``, ``listed_on_card``, ``account_field``, ``header``).
- ``phone_identity_names``: each phone's names for an identity (``contact``, ``contact_entry``,
  ``name_in_record``) with counts; ``is_phone_name`` marks the one the 8.5 rule 3 shows.
- ``phone_owner_candidates``: every owner candidate with tier, count and basis: numbers (tier 1 header, tier 2
  inference), owner names and the owner's app identities.

Views ``pv_identity_sighting``, ``pv_identity_name`` and ``pv_owner_candidate`` read the current generation of
active extractions, as the other ``pv_*`` views do.
"""
from alembic import op

revision = "20261102_phone_identities"
down_revision = "20261102_phone_identifiers"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE phone_identities (
  id               uuid PRIMARY KEY,
  case_id          uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  identity_key     text NOT NULL,
  kind             varchar(16) NOT NULL CHECK (kind IN ('phone','app_user','email','other')),
  subkind          varchar(32),
  value_normalised text NOT NULL,
  value_display    text NOT NULL,
  sighting_count   integer NOT NULL DEFAULT 0,
  phone_count      integer NOT NULL DEFAULT 0,
  first_instant    timestamptz,
  last_instant     timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_phone_identities UNIQUE (case_id, identity_key)
);

CREATE TABLE phone_identity_sightings (
  sighting_uid     uuid NOT NULL,
  case_id          uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  extraction_id    uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  identity_id      uuid NOT NULL REFERENCES phone_identities(id),
  identity_key     text NOT NULL,
  record_uid       uuid,
  root_record_uid  uuid,
  card_record_uid  uuid,
  card_type        varchar(128),
  field_path       text NOT NULL,
  identifier_raw   text NOT NULL,
  context          varchar(16) NOT NULL
                   CHECK (context IN ('party','owner_party','listed_on_card','account_field','header')),
  name_alongside   text,
  region_basis     varchar(24),
  instant          timestamptz,
  generation       integer NOT NULL,
  PRIMARY KEY (sighting_uid, generation)
);
CREATE INDEX ix_phone_identity_sightings_ext ON phone_identity_sightings (case_id, extraction_id, context);
CREATE INDEX ix_phone_identity_sightings_identity ON phone_identity_sightings (identity_id, extraction_id);
CREATE INDEX ix_phone_identity_sightings_record ON phone_identity_sightings (record_uid);

CREATE TABLE phone_identity_names (
  case_id          uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  extraction_id    uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  identity_id      uuid NOT NULL REFERENCES phone_identities(id),
  name             text NOT NULL,
  basis            varchar(16) NOT NULL CHECK (basis IN ('contact','contact_entry','name_in_record')),
  occurrences      integer NOT NULL,
  latest_modified  timestamptz,
  first_record_uid uuid,
  is_phone_name    boolean NOT NULL DEFAULT false,
  generation       integer NOT NULL,
  PRIMARY KEY (extraction_id, identity_id, basis, name, generation)
);
CREATE INDEX ix_phone_identity_names_identity ON phone_identity_names (case_id, identity_id);

CREATE TABLE phone_owner_candidates (
  case_id          uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  extraction_id    uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  candidate_kind   varchar(16) NOT NULL CHECK (candidate_kind IN ('number','name','account')),
  identity_id      uuid REFERENCES phone_identities(id),
  identity_key     text,
  name             text,
  tier             smallint,
  occurrences      integer NOT NULL,
  basis            varchar(16) NOT NULL CHECK (basis IN ('extracted','inferred','name','account')),
  basis_detail     jsonb NOT NULL DEFAULT '{}'::jsonb,
  generation       integer NOT NULL
);
CREATE INDEX ix_phone_owner_candidates_ext ON phone_owner_candidates (case_id, extraction_id, generation);
"""

CURRENT = """JOIN phone_interpretation_state s ON s.extraction_id = %(a)s.extraction_id AND s.generation = %(a)s.generation
JOIN phone_extractions e ON e.id = %(a)s.extraction_id AND e.standing = 'active'"""

VIEWS = """
CREATE VIEW pv_identity_sighting AS
SELECT x.sighting_uid, x.case_id, x.extraction_id, x.identity_id, x.identity_key, i.kind, i.subkind,
       i.value_display, x.record_uid, x.root_record_uid, x.card_record_uid, x.card_type, x.field_path,
       x.identifier_raw, x.context, x.name_alongside, x.region_basis, x.instant
  FROM phone_identity_sightings x JOIN phone_identities i ON i.id = x.identity_id %(cx)s;

CREATE VIEW pv_identity_name AS
SELECT n.case_id, n.extraction_id, n.identity_id, i.identity_key, n.name, n.basis, n.occurrences,
       n.latest_modified, n.first_record_uid, n.is_phone_name
  FROM phone_identity_names n JOIN phone_identities i ON i.id = n.identity_id %(cn)s;

CREATE VIEW pv_owner_candidate AS
SELECT o.case_id, o.extraction_id, o.candidate_kind, o.identity_id, o.identity_key, o.name, o.tier,
       o.occurrences, o.basis, o.basis_detail
  FROM phone_owner_candidates o %(co)s;
"""


def upgrade():
    op.execute(UPGRADE)
    op.execute(VIEWS % {"cx": CURRENT % {"a": "x"}, "cn": CURRENT % {"a": "n"}, "co": CURRENT % {"a": "o"}})


def downgrade():
    op.execute("DROP VIEW pv_owner_candidate; DROP VIEW pv_identity_name; DROP VIEW pv_identity_sighting;")
    op.execute("DROP TABLE phone_owner_candidates; DROP TABLE phone_identity_names; "
               "DROP TABLE phone_identity_sightings; DROP TABLE phone_identities;")
