"""add workspace note theory witness versions

Revision ID: 20260717_workspace_versions
Revises: 20260705_timeline_views
Create Date: 2026-07-17 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260717_workspace_versions"
down_revision: Union[str, Sequence[str], None] = "20260705_timeline_views"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workspace_notes",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "workspace_theories",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "workspace_witnesses",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("workspace_witnesses", "version")
    op.drop_column("workspace_theories", "version")
    op.drop_column("workspace_notes", "version")
