"""add recycle bin item type

Revision ID: 20260409_recycle_item_type
Revises: 20260409_graph_recycle_bin
Create Date: 2026-04-09 21:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260409_recycle_item_type"
down_revision: Union[str, Sequence[str], None] = "20260409_graph_recycle_bin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "graph_recycle_bin_items",
        sa.Column("item_type", sa.String(length=32), nullable=False, server_default="entity_delete"),
    )
    op.create_check_constraint(
        "ck_graph_recycle_bin_items_item_type",
        "graph_recycle_bin_items",
        "item_type IN ('entity_delete', 'merge_undo')",
    )
    op.create_index(
        "ix_graph_recycle_bin_items_case_type_status_deleted",
        "graph_recycle_bin_items",
        ["case_id", "item_type", "status", "deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_graph_recycle_bin_items_case_type_status_deleted", table_name="graph_recycle_bin_items")
    op.drop_constraint("ck_graph_recycle_bin_items_item_type", "graph_recycle_bin_items", type_="check")
    op.drop_column("graph_recycle_bin_items", "item_type")
