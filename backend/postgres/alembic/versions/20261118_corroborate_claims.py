"""Corroborate: a free-text claim, Loupe's reading of it, and the chips a person confirmed (lx-corrostatement).

Revision ID: 20261118_corroborate_claims
Revises: 20261118_answer_ratings_chat
"""
from alembic import op

revision = "20261118_corroborate_claims"
down_revision = "20261118_answer_ratings_chat"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE corroborate_claims (
          id                uuid PRIMARY KEY,
          case_id           uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
          sentence          text NOT NULL,
          statement_date    varchar(10),
          source            jsonb NOT NULL DEFAULT '{}'::jsonb,
          read              jsonb NOT NULL DEFAULT '{}'::jsonb,
          confirmed         jsonb NOT NULL DEFAULT '{}'::jsonb,
          edited            jsonb NOT NULL DEFAULT '[]'::jsonb,
          status            varchar(16) NOT NULL DEFAULT 'draft'
                              CONSTRAINT ck_corroborate_claims_status CHECK (status IN ('draft', 'confirmed')),
          created_by        uuid REFERENCES users(id) ON DELETE SET NULL,
          created_by_name   varchar(300) NOT NULL DEFAULT '',
          created_at        timestamptz NOT NULL DEFAULT now(),
          confirmed_by      uuid REFERENCES users(id) ON DELETE SET NULL,
          confirmed_by_name varchar(300),
          confirmed_at      timestamptz
        );
        CREATE INDEX ix_corroborate_claims_case ON corroborate_claims (case_id, created_at);
    """)


def downgrade():
    op.execute("DROP TABLE corroborate_claims")
