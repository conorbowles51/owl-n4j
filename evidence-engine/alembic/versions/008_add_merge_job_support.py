"""Add merge job support: job_type, merge_payload, nullable file fields, new status

Revision ID: 008
Revises: 007
Create Date: 2026-04-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add job_type column
    op.add_column(
        "jobs",
        sa.Column("job_type", sa.String(32), server_default="ingestion", nullable=False),
    )

    # Add merge_payload JSONB column
    op.add_column(
        "jobs",
        sa.Column("merge_payload", postgresql.JSONB, nullable=True),
    )

    # Make file_name and file_path nullable (merge jobs have no file)
    op.alter_column("jobs", "file_name", existing_type=sa.String(500), nullable=True)
    op.alter_column("jobs", "file_path", existing_type=sa.String(1000), nullable=True)

    # Add MERGING_PROPERTIES to jobstatus enum
    op.execute("ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS 'merging_properties'")


def downgrade() -> None:
    op.alter_column("jobs", "file_path", existing_type=sa.String(1000), nullable=False)
    op.alter_column("jobs", "file_name", existing_type=sa.String(500), nullable=False)
    op.drop_column("jobs", "merge_payload")
    op.drop_column("jobs", "job_type")
