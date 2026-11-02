"""Pattern of life: together-and-apart runs and their pairs (04 sections 7.7, 8.4).

A run is stored with its subjects, window and parameters; every compared pair is an item with its verdict, distance,
radii sum, time gap and basis. Nothing is capped: large runs are background jobs and pages carry the total.
Downgrade drops both tables.
"""
from alembic import op

revision = "20261102_pol_colocation"
down_revision = "20261102_pol_places"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE pol_colocation_run (
  id            uuid PRIMARY KEY,
  case_id       uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  subjects      jsonb NOT NULL,
  window_start  timestamptz NOT NULL,
  window_end    timestamptz NOT NULL,
  params        jsonb NOT NULL,
  status        varchar(12) NOT NULL CHECK (status IN ('queued','running','done','failed')),
  started_at    timestamptz NOT NULL DEFAULT now(),
  finished_at   timestamptz,
  counts        jsonb NOT NULL DEFAULT '{}'::jsonb,
  episodes      jsonb NOT NULL DEFAULT '[]'::jsonb,
  error         text,
  requested_by  varchar(255) NOT NULL
);
CREATE INDEX ix_pol_colocation_run_case ON pol_colocation_run (case_id, started_at);

CREATE TABLE pol_colocation_item (
  run_id            uuid NOT NULL REFERENCES pol_colocation_run(id) ON DELETE CASCADE,
  ordinal           integer NOT NULL,
  a_observation_id  bigint,
  b_observation_id  bigint,
  a_ref             text,
  b_ref             text,
  at_utc            timestamptz NOT NULL,
  verdict           varchar(12) NOT NULL CHECK (verdict IN ('compatible','separated','undetermined')),
  distance_m        double precision,
  radii_sum_m       double precision,
  dt_s              double precision NOT NULL,
  basis             varchar(16) NOT NULL,
  tight             boolean NOT NULL DEFAULT false,
  assumed           boolean NOT NULL DEFAULT false,
  flags             text[] NOT NULL DEFAULT '{}',
  PRIMARY KEY (run_id, ordinal)
);
"""


def upgrade():
    op.execute(UPGRADE)


def downgrade():
    op.execute("DROP TABLE IF EXISTS pol_colocation_item")
    op.execute("DROP TABLE IF EXISTS pol_colocation_run")
