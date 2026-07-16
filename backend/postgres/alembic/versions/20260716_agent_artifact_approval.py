"""add agent artifact approval fields

Revision ID: 20260716_agent_artifact_approval
Revises: 20260705_timeline_views
Create Date: 2026-07-16 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260716_agent_artifact_approval"
down_revision: Union[str, None] = "20260705_timeline_views"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_artifacts",
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
    )
    op.add_column(
        "agent_artifacts",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "agent_artifacts",
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "agent_artifacts",
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "agent_artifacts",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_artifacts",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_foreign_key(
        "fk_agent_artifacts_approved_by_user_id_users",
        "agent_artifacts",
        "users",
        ["approved_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_agent_artifacts_status", "agent_artifacts", ["status"], unique=False)

    op.alter_column("agent_artifacts", "status", server_default=None)
    op.alter_column("agent_artifacts", "version", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_agent_artifacts_status", table_name="agent_artifacts")
    op.drop_constraint(
        "fk_agent_artifacts_approved_by_user_id_users",
        "agent_artifacts",
        type_="foreignkey",
    )
    op.drop_column("agent_artifacts", "updated_at")
    op.drop_column("agent_artifacts", "approved_at")
    op.drop_column("agent_artifacts", "approved_by_user_id")
    op.drop_column("agent_artifacts", "citations")
    op.drop_column("agent_artifacts", "version")
    op.drop_column("agent_artifacts", "status")
