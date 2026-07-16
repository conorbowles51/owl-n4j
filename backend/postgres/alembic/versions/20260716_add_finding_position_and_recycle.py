"""add finding position and recycle fields

Revision ID: 20260716_finding_position_recycle
Revises: 20260705_timeline_views
Create Date: 2026-07-16 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_finding_position_recycle"
down_revision: Union[str, None] = "20260705_timeline_views"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workspace_findings",
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "workspace_findings",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workspace_findings",
        sa.Column("deleted_by", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_workspace_findings_deleted_at",
        "workspace_findings",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        "ix_workspace_findings_case_active_position",
        "workspace_findings",
        ["case_id", "deleted_at", "position"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_workspace_findings_case_active_position", table_name="workspace_findings")
    op.drop_index("ix_workspace_findings_deleted_at", table_name="workspace_findings")
    op.drop_column("workspace_findings", "deleted_by")
    op.drop_column("workspace_findings", "deleted_at")
    op.drop_column("workspace_findings", "position")
