"""Questions asked of a case's phones, with their answers (lx-phoneask D: earlier questions are kept and listed).

Revision ID: 20261125_phone_asks
Revises: 20261125_phone_texts_digits_joined
"""
from alembic import op

revision = "20261125_phone_asks"
down_revision = "20261125_phone_texts_digits_joined"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE phone_asks (
          id             uuid PRIMARY KEY,
          case_id        uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
          question       text NOT NULL,
          phones         jsonb NOT NULL DEFAULT '[]'::jsonb,
          status         varchar(16) NOT NULL DEFAULT 'running'
                           CONSTRAINT ck_phone_asks_status CHECK (status IN ('running', 'done', 'failed')),
          answer         jsonb,
          error          text,
          cost_usd       numeric(12, 6),
          seconds        numeric(10, 2),
          asked_by       uuid REFERENCES users(id) ON DELETE SET NULL,
          asked_by_name  varchar(300) NOT NULL DEFAULT '',
          created_at     timestamptz NOT NULL DEFAULT now(),
          finished_at    timestamptz
        );
        CREATE INDEX ix_phone_asks_case ON phone_asks (case_id, created_at);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS phone_asks")
