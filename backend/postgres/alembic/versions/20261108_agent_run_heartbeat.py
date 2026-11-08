"""agent_runs.heartbeat_at: beaten while a run's worker lives, so a restart-killed run can be settled.

A run executes inside its web request; a release restart killed the worker and left the row ``running`` for ever
(10 such rows on live, 8 Nov 2026). services.agent.run_settle beats this column and marks runs whose beat stopped
as ``interrupted``.
"""
import sqlalchemy as sa
from alembic import op

revision = "20261108_agent_run_heartbeat"
down_revision = "20261108_page_start_marks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "heartbeat_at")
