"""add merge jobs table and entity_merge cost job type

Revision ID: 20260409_merge_jobs
Revises: 20260409_recycle_item_type
Create Date: 2026-04-09 23:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision: str = "20260409_merge_jobs"
down_revision: Union[str, None] = "20260409_recycle_item_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create merge_jobs table
    op.create_table(
        "merge_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engine_job_id", sa.String(36), nullable=False, unique=True),
        sa.Column("source_entity_keys", JSONB, nullable=False),
        sa.Column("merged_entity_key", sa.String(36), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_merge_jobs_case_id", "merge_jobs", ["case_id"])
    op.create_index("ix_merge_jobs_engine_job_id", "merge_jobs", ["engine_job_id"], unique=True)

    # Add entity_merge to cost_job_type enum
    op.execute("ALTER TYPE cost_job_type ADD VALUE IF NOT EXISTS 'entity_merge'")

    # Evidence engine jobs table — add merge support
    # (Evidence engine's own Alembic is disabled; backend owns all migrations)
    op.add_column("jobs", sa.Column("job_type", sa.String(32), server_default="ingestion", nullable=False))
    op.add_column("jobs", sa.Column("merge_payload", JSONB, nullable=True))
    op.alter_column("jobs", "file_name", existing_type=sa.String(500), nullable=True)
    op.alter_column("jobs", "file_path", existing_type=sa.String(1000), nullable=True)
    op.execute("ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS 'merging_properties'")


def downgrade() -> None:
    op.drop_table("merge_jobs")
