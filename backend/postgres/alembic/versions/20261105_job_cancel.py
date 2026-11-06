"""A cancelled engine job: the request survives a worker's own writes, and a cancelled row stays status 'failed'
so every reader of finished jobs (release gate, jobs poll, recovery) treats it as finished without a change."""
import sqlalchemy as sa
from alembic import op

revision = "20261105_job_cancel"
down_revision = "20261108_upload_group_members_total"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jobs", sa.Column("cancel_requested", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("jobs", sa.Column("cancelled_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("jobs", "cancelled_at")
    op.drop_column("jobs", "cancel_requested")
