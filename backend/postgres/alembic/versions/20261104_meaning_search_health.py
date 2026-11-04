"""Meaning-search health (lx-docsearch E).

``service_health_states``: one row per outside service the app depends on, holding whether its last call worked,
the reason when it did not, and since when it has been failing, so the AI settings page can say "down since" without
anyone reading logs. New table; no existing row changes. On live 2026-11-04 the document meaning search (OpenAI
embeddings) had failed with 429 insufficient quota on every call since 2026-10-28 04:30 UTC.
"""
from alembic import op

revision = "20261104_meaning_search_health"
down_revision = "20261103_financial_security_rows"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS service_health_states (
            service varchar(64) PRIMARY KEY,
            status varchar(16) NOT NULL,
            reason_code varchar(64) NULL,
            reason text NULL,
            down_since timestamptz NULL,
            last_failure_at timestamptz NULL,
            last_success_at timestamptz NULL,
            failures_since_down integer NOT NULL DEFAULT 0,
            backfill_pending boolean NOT NULL DEFAULT false,
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_service_health_states_status CHECK (status IN ('up', 'down'))
        )
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS service_health_states")
