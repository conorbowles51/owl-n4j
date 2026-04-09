"""add graph recycle bin items

Revision ID: 20260409_graph_recycle_bin
Revises: 20260408_add_ai_cost_tracking
Create Date: 2026-04-09 10:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260409_graph_recycle_bin"
down_revision: Union[str, Sequence[str], None] = "20260408_add_ai_cost_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "graph_recycle_bin_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recycle_key", sa.String(length=512), nullable=False),
        sa.Column("original_key", sa.String(length=512), nullable=False),
        sa.Column("original_name", sa.Text(), nullable=True),
        sa.Column("original_type", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.String(length=512), nullable=False),
        sa.Column("deleted_by", sa.String(length=255), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("relationship_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending_delete"),
        sa.Column("snapshot", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending_delete', 'active', 'restoring', 'restored', 'purged')",
            name="ck_graph_recycle_bin_items_status",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recycle_key", name="uq_graph_recycle_bin_items_recycle_key"),
    )
    op.create_index(
        "ix_graph_recycle_bin_items_case_status_deleted",
        "graph_recycle_bin_items",
        ["case_id", "status", "deleted_at"],
        unique=False,
    )
    op.create_index(
        "ix_graph_recycle_bin_items_original_key",
        "graph_recycle_bin_items",
        ["case_id", "original_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_graph_recycle_bin_items_original_key", table_name="graph_recycle_bin_items")
    op.drop_index("ix_graph_recycle_bin_items_case_status_deleted", table_name="graph_recycle_bin_items")
    op.drop_table("graph_recycle_bin_items")
