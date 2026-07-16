"""add workspace findings lifecycle columns

Revision ID: 20260716_findings_lifecycle
Revises: 20260705_timeline_views
Create Date: 2026-07-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260716_findings_lifecycle"
down_revision: Union[str, None] = "20260705_timeline_views"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workspace_findings",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "workspace_findings",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workspace_findings",
        sa.Column(
            "deleted_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_workspace_findings_case_id_deleted_at",
        "workspace_findings",
        ["case_id", "deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_workspace_findings_case_id_deleted_at", table_name="workspace_findings")
    op.drop_column("workspace_findings", "deleted_by_user_id")
    op.drop_column("workspace_findings", "deleted_at")
    op.drop_column("workspace_findings", "version")
