"""add agent artifact lifecycle fields

Revision ID: 20260717_agent_artifact_lifecycle
Revises: 20260716_agent_artifact_approval
Create Date: 2026-07-17 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260717_agent_artifact_lifecycle"
down_revision: Union[str, None] = "20260716_agent_artifact_approval"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_artifacts", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "agent_artifacts",
        sa.Column("deleted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_artifacts_deleted_by_user_id_users",
        "agent_artifacts",
        "users",
        ["deleted_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_agent_artifacts_case_deleted",
        "agent_artifacts",
        ["thread_id", "deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_artifacts_case_deleted", table_name="agent_artifacts")
    op.drop_constraint(
        "fk_agent_artifacts_deleted_by_user_id_users",
        "agent_artifacts",
        type_="foreignkey",
    )
    op.drop_column("agent_artifacts", "deleted_by_user_id")
    op.drop_column("agent_artifacts", "deleted_at")
