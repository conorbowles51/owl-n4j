"""allow location relocation recycle-bin items

Revision ID: 20260718_location_relocation
Revises: 20260705_timeline_views
Create Date: 2026-07-18 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "20260718_location_relocation"
down_revision: Union[str, None] = "20260705_timeline_views"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_graph_recycle_bin_items_item_type",
        "graph_recycle_bin_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_graph_recycle_bin_items_item_type",
        "graph_recycle_bin_items",
        "item_type IN ('entity_delete', 'merge_undo', 'location_relocation')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_graph_recycle_bin_items_item_type",
        "graph_recycle_bin_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_graph_recycle_bin_items_item_type",
        "graph_recycle_bin_items",
        "item_type IN ('entity_delete', 'merge_undo')",
    )
