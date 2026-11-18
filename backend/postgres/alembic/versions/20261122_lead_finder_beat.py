"""A lead finder run's heartbeat.

A release restart ends a running finder thread, but its run row stayed 'running', and the case could not look for
leads again for 3 hours (followups, 18 Nov: run 6ee64ad1 on Phone reference 1 died at 12:39 and blocked the case until
15:05). A live run now stamps ``beat_at`` every minute; a running row whose beat is 15 minutes old is shown as stopped.
"""
import sqlalchemy as sa
from alembic import op

revision = "20261122_lead_finder_beat"
down_revision = "20261121_relay_interaction_idx"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("lead_finder_runs", sa.Column("beat_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("lead_finder_runs", "beat_at")
