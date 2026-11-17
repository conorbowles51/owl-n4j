"""Corroborate: case facts a person records, and saved results that keep watching (lx-corroengine H).

Revision ID: 20261117_corroborate_facts
Revises: 20261116_embed_items
"""
from alembic import op

revision = "20261117_corroborate_facts"
down_revision = "20261116_embed_items"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE corroborate_case_facts (
          id                uuid PRIMARY KEY,
          case_id           uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
          kind              varchar(32) NOT NULL CONSTRAINT ck_corroborate_case_facts_kind CHECK (kind IN
                              ('live_together', 'work_group', 'routine_phrase', 'routine_place', 'same_person',
                               'not_same_person', 'other')),
          text              text NOT NULL,
          people            jsonb NOT NULL DEFAULT '[]'::jsonb,
          phrase            text,
          state             varchar(16) NOT NULL DEFAULT 'active'
                              CONSTRAINT ck_corroborate_case_facts_state CHECK (state IN ('active', 'withdrawn')),
          source_run_id     uuid,
          created_by        uuid REFERENCES users(id) ON DELETE SET NULL,
          created_by_name   varchar(300) NOT NULL DEFAULT '',
          created_at        timestamptz NOT NULL DEFAULT now(),
          withdrawn_by_name varchar(300),
          withdrawn_at      timestamptz
        );
        CREATE INDEX ix_corroborate_case_facts_case ON corroborate_case_facts (case_id, created_at);
        CREATE TABLE corroborate_watches (
          id            uuid PRIMARY KEY,
          case_id       uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
          selection_id  uuid NOT NULL REFERENCES case_selections(id) ON DELETE CASCADE,
          question      jsonb NOT NULL DEFAULT '{}'::jsonb,
          level         jsonb NOT NULL DEFAULT '{}'::jsonb,
          material      jsonb NOT NULL DEFAULT '{}'::jsonb,
          history       jsonb NOT NULL DEFAULT '[]'::jsonb,
          unseen        boolean NOT NULL DEFAULT false,
          active        boolean NOT NULL DEFAULT true,
          created_by    uuid REFERENCES users(id) ON DELETE SET NULL,
          created_at    timestamptz NOT NULL DEFAULT now(),
          checked_at    timestamptz
        );
        CREATE INDEX ix_corroborate_watches_case ON corroborate_watches (case_id, active);
    """)


def downgrade():
    op.execute("DROP TABLE corroborate_watches")
    op.execute("DROP TABLE corroborate_case_facts")
