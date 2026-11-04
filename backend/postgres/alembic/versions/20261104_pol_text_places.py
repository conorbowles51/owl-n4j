"""Pattern of life: text places a person places on the map (docs/cellebrite/04 section 6.5).

- ``pol_text_place``: one row per placement of a written place (a calendar location, a check-in name, a Location's
  written address) on a phone record that carries no coordinate. The current placement of a (record, field) is its
  row with ``removed_decision_id`` null; a replacement or a removal keeps the earlier row and names the decision that
  ended it. ``place_text`` is the text as the record held it when the person placed it, kept visible beside the point.
  ``suggestion`` holds the offline GeoNames candidate the person started from, when they did; the saved point and
  radius are always the person's.
- ``pol_projection_state.text_places_version``: raised by every placement and removal, which rewrite the phone's
  ``person_placed`` observations in the same transaction (the projection is rebuildable from these decisions).
- Decisions ``place_text_place`` and ``remove_text_place`` (subject ``phone_record``) join
  ``ck_adjudications_decision``, rebuilt from its current definition so no other job's members are lost.
"""
import re

from alembic import op
import sqlalchemy as sa

revision = "20261104_pol_text_places"
down_revision = "20261104_phone_views"
branch_labels = None
depends_on = None

NEW = ("place_text_place", "remove_text_place")

DDL = """
CREATE TABLE pol_text_place (
  id                  uuid PRIMARY KEY,
  case_id             uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  extraction_id       uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  record_uid          uuid NOT NULL,
  field_path          text NOT NULL,
  model_type          varchar(128) NOT NULL,
  place_text          text NOT NULL,
  lat                 double precision NOT NULL CHECK (lat BETWEEN -90 AND 90),
  lon                 double precision NOT NULL CHECK (lon BETWEEN -180 AND 180),
  radius_m            double precision NOT NULL CHECK (radius_m >= 1 AND radius_m <= 50000),
  reason              text NOT NULL CHECK (btrim(reason) <> ''),
  suggestion          jsonb NULL,
  decision_id         uuid NOT NULL,
  removed_decision_id uuid NULL,
  actor_name          varchar(300) NOT NULL,
  actor_email         varchar(300) NOT NULL,
  created_at          timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE UNIQUE INDEX ux_pol_text_place_current ON pol_text_place (record_uid, field_path) WHERE removed_decision_id IS NULL;
CREATE INDEX ix_pol_text_place_ext ON pol_text_place (extraction_id, record_uid);
CREATE INDEX ix_pol_text_place_case ON pol_text_place (case_id);
ALTER TABLE pol_projection_state ADD COLUMN IF NOT EXISTS text_places_version integer NOT NULL DEFAULT 0
"""


def _members(bind):
    d = bind.execute(sa.text(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_adjudications_decision'")).scalar_one()
    return re.findall(r"'([a-z_]+)'", d)


def _rebuild(members):
    op.drop_constraint("ck_adjudications_decision", "adjudications", type_="check")
    op.create_check_constraint("ck_adjudications_decision", "adjudications",
                               "decision IN (%s)" % ", ".join("'%s'" % m for m in members))


def upgrade():
    bind = op.get_bind()
    have = _members(bind)
    _rebuild(have + [m for m in NEW if m not in have])
    for stmt in [s for s in DDL.split(";") if s.strip()]:
        op.execute(stmt)


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT count(*) FROM adjudications WHERE decision IN :d").bindparams(
            sa.bindparam("d", expanding=True)), {"d": list(NEW)}).scalar_one():
        raise RuntimeError("Text place decisions are recorded; removing the members would orphan them.")
    op.execute("DELETE FROM pol_place_observation WHERE source_kind = 'person_placed'")
    op.execute("ALTER TABLE pol_projection_state DROP COLUMN IF EXISTS text_places_version")
    op.execute("DROP TABLE pol_text_place")
    _rebuild([m for m in _members(bind) if m not in NEW])
