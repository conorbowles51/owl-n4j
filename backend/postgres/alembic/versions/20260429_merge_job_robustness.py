"""merge job robustness — nullable engine_job_id and recycled_source_keys

Revision ID: 20260429_merge_robust
Revises: 20260410_engine_merge
Create Date: 2026-04-29

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "20260429_merge_robust"
down_revision: Union[str, None] = "20260410_engine_merge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Allow MergeJob row to be created before engine job is started (P0-10).
    # Postgres unique constraints permit multiple NULLs, so the existing
    # unique index on engine_job_id remains correct.
    op.alter_column(
        "merge_jobs",
        "engine_job_id",
        existing_type=sa.String(36),
        nullable=True,
    )

    # Track which source entity keys actually got soft-deleted (P0-6).
    op.add_column(
        "merge_jobs",
        sa.Column("recycled_source_keys", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("merge_jobs", "recycled_source_keys")
    op.alter_column(
        "merge_jobs",
        "engine_job_id",
        existing_type=sa.String(36),
        nullable=False,
    )
