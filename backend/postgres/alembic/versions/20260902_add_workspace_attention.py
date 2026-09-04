"""add per-user workspace attention state

Revision ID: 20260902_workspace_attention
Revises: 20260902_case_work
Create Date: 2026-09-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260902_workspace_attention"
down_revision: Union[str, None] = "20260902_case_work"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "workspace_attention_states",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "case_id",
            UUID,
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attention_key", sa.String(768), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "case_id",
            "user_id",
            "attention_key",
            name="uq_workspace_attention_user_item",
        ),
    )
    op.create_index(
        "ix_workspace_attention_states_case_id",
        "workspace_attention_states",
        ["case_id"],
    )
    op.create_index(
        "ix_workspace_attention_states_user_id",
        "workspace_attention_states",
        ["user_id"],
    )
    op.create_index(
        "ix_workspace_attention_case_user_snooze",
        "workspace_attention_states",
        ["case_id", "user_id", "snoozed_until"],
    )


def downgrade() -> None:
    op.drop_table("workspace_attention_states")
