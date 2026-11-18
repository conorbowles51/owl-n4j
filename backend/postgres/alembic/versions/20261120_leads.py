"""Leads: a saved Corroborate question grows into a lead (lx-leads A). One store: corroborate_watches.

A lead says where it came from (found by Loupe, asked by a person, suggested by the agent), the state a person put it
in (append-only history), the people, period, record kinds and records it rests on, and what raises and lowers it.
It is a reading by Loupe until a person confirms it into the theory; that person and the time are kept on the row,
and the finding it became is linked. ``lead_finder_runs`` records each run of the lead finder (when, how
long, what it saved), so the Leads page can say when the case was last checked. A person's correction is kept beside Loupe's words, never over them.

Revision ID: 20261120_leads
Revises: 20261119_document_date_readings
"""
from alembic import op

revision = "20261120_leads"
down_revision = "20261119_document_date_readings"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE corroborate_watches
          ADD COLUMN origin            varchar(16) NOT NULL DEFAULT 'asked'
                     CONSTRAINT ck_corroborate_watches_origin CHECK (origin IN ('found_by_loupe', 'asked', 'agent')),
          ADD COLUMN state             varchar(16) NOT NULL DEFAULT 'new'
                     CONSTRAINT ck_corroborate_watches_state CHECK (state IN ('new', 'looking', 'in_theory', 'not_relevant')),
          ADD COLUMN state_history     jsonb NOT NULL DEFAULT '[]'::jsonb,
          ADD COLUMN title             text NOT NULL DEFAULT '',
          ADD COLUMN summary           text NOT NULL DEFAULT '',
          ADD COLUMN people            jsonb NOT NULL DEFAULT '[]'::jsonb,
          ADD COLUMN period            jsonb NOT NULL DEFAULT '{}'::jsonb,
          ADD COLUMN kinds             jsonb NOT NULL DEFAULT '[]'::jsonb,
          ADD COLUMN record_refs       jsonb NOT NULL DEFAULT '[]'::jsonb,
          ADD COLUMN raises            jsonb NOT NULL DEFAULT '[]'::jsonb,
          ADD COLUMN lowers            jsonb NOT NULL DEFAULT '[]'::jsonb,
          ADD COLUMN searched          jsonb NOT NULL DEFAULT '{}'::jsonb,
          ADD COLUMN detail            jsonb NOT NULL DEFAULT '{}'::jsonb,
          ADD COLUMN corrections       jsonb NOT NULL DEFAULT '[]'::jsonb,
          ADD COLUMN read_by           varchar(120) NOT NULL DEFAULT 'Corroborate',
          ADD COLUMN finder_key        varchar(200),
          ADD COLUMN run_id            uuid,
          ADD COLUMN finding_id        uuid,
          ADD COLUMN confirmed_by      uuid REFERENCES users(id) ON DELETE SET NULL,
          ADD COLUMN confirmed_by_name varchar(300),
          ADD COLUMN confirmed_at      timestamptz;
        CREATE UNIQUE INDEX ux_corroborate_watches_finder_key ON corroborate_watches (case_id, finder_key)
          WHERE finder_key IS NOT NULL;
        CREATE INDEX ix_corroborate_watches_case_state ON corroborate_watches (case_id, state);
        CREATE TABLE lead_finder_runs (
          id            uuid PRIMARY KEY,
          case_id       uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
          status        varchar(16) NOT NULL DEFAULT 'queued'
                          CONSTRAINT ck_lead_finder_runs_status CHECK (status IN ('queued', 'running', 'done', 'failed')),
          step          text NOT NULL DEFAULT '',
          trigger       varchar(16) NOT NULL DEFAULT 'button',
          counts        jsonb NOT NULL DEFAULT '{}'::jsonb,
          material      jsonb NOT NULL DEFAULT '{}'::jsonb,
          error         text,
          requested_by  uuid REFERENCES users(id) ON DELETE SET NULL,
          started_at    timestamptz NOT NULL DEFAULT now(),
          finished_at   timestamptz
        );
        CREATE INDEX ix_lead_finder_runs_case ON lead_finder_runs (case_id, started_at);
    """)


def downgrade():
    op.execute("""
        DROP TABLE IF EXISTS lead_finder_runs;
        DROP INDEX IF EXISTS ix_corroborate_watches_case_state;
        DROP INDEX IF EXISTS ux_corroborate_watches_finder_key;
        ALTER TABLE corroborate_watches
          DROP COLUMN confirmed_at, DROP COLUMN confirmed_by_name, DROP COLUMN confirmed_by, DROP COLUMN finding_id,
          DROP COLUMN run_id, DROP COLUMN finder_key, DROP COLUMN read_by, DROP COLUMN corrections, DROP COLUMN detail,
          DROP COLUMN searched, DROP COLUMN lowers, DROP COLUMN raises, DROP COLUMN record_refs, DROP COLUMN kinds,
          DROP COLUMN period, DROP COLUMN people, DROP COLUMN summary, DROP COLUMN title, DROP COLUMN state_history,
          DROP COLUMN state, DROP COLUMN origin;
    """)
