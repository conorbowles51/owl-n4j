"""Allow case deadlines to be completed and reopened without removing them.

Revision ID: 20261110_deadline_completion
Revises: 20261109_evidence_delete_fk_indexes_2
"""
from alembic import op
import sqlalchemy as sa

revision = "20261110_deadline_completion"
down_revision = "20261109_evidence_delete_fk_indexes_2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("case_deadlines", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    # Do not silently erase an investigator's recorded completion state.
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM case_deadlines WHERE completed_at IS NOT NULL")):
        raise RuntimeError("Completed deadlines exist. Preserve or reopen them before downgrading.")
    op.drop_column("case_deadlines", "completed_at")
