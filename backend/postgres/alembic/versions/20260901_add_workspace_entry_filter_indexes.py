"""add Workspace casework filter indexes

Revision ID: 20260901_workspace_filters
Revises: 20260901_workspace_entries
Create Date: 2026-09-01
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "20260901_workspace_filters"
down_revision: Union[str, None] = "20260901_workspace_entries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_workspace_entries_case_significance",
        "workspace_entries",
        ["case_id", "entry_type", "significance"],
        unique=False,
    )
    op.create_index(
        "ix_workspace_entries_case_confidence",
        "workspace_entries",
        ["case_id", "entry_type", "confidence"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_entries_case_confidence", table_name="workspace_entries"
    )
    op.drop_index(
        "ix_workspace_entries_case_significance", table_name="workspace_entries"
    )
