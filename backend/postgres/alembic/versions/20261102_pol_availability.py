"""Pattern of life: data availability bands and the hourly rollup (docs/cellebrite/04-pattern-of-life.md 5, 7.4, 7.5).

``pol_availability_band`` holds, per extraction, the observed segments of each recording stream, the switched-off
periods (stated and inferred) and the time after the extraction started. ``pol_hourly_rollup`` holds per UTC hour
the owner's interactions by strength, the other classes, and the minutes observed (by any recording stream, and by
streams that can show a person's use). Hour states are derived from them on read (5.3 step 6), never stored.

Both are projections rebuilt with the activity events. Downgrade drops them.
"""
from alembic import op

revision = "20261102_pol_availability"
down_revision = "20261102_pol_activity"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE pol_availability_band (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  case_id        uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  extraction_id  uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  family         varchar(24) NOT NULL,
  stream_key     varchar(160),
  band           varchar(24) NOT NULL CHECK (band IN ('observed','powered_off','powered_off_inferred',
                                                      'after_extraction','outside_selection','not_selected')),
  start_utc      timestamptz NOT NULL,
  end_utc        timestamptz NOT NULL,
  event_count    integer NOT NULL DEFAULT 0,
  inferred       boolean NOT NULL DEFAULT false,
  interaction_capable boolean NOT NULL DEFAULT false,
  computed_from  jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX ix_pol_availability_band_ext ON pol_availability_band (extraction_id, start_utc);

CREATE TABLE pol_hourly_rollup (
  extraction_id         uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  case_id               uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  hour_utc              timestamptz NOT NULL,
  interaction_strong    integer NOT NULL DEFAULT 0,
  interaction_moderate  integer NOT NULL DEFAULT 0,
  interaction_weak      integer NOT NULL DEFAULT 0,
  device_state          integer NOT NULL DEFAULT 0,
  passive               integer NOT NULL DEFAULT 0,
  physical              integer NOT NULL DEFAULT 0,
  observed_minutes      smallint NOT NULL DEFAULT 0,
  observed_capable_minutes smallint NOT NULL DEFAULT 0,
  band                  varchar(24),
  PRIMARY KEY (extraction_id, hour_utc)
);
"""


def upgrade():
    op.execute(UPGRADE)


def downgrade():
    op.execute("DROP TABLE IF EXISTS pol_hourly_rollup")
    op.execute("DROP TABLE IF EXISTS pol_availability_band")
