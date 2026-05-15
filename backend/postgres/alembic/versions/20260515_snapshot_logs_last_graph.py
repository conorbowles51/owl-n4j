"""add snapshot, system log, and last graph runtime state

Revision ID: 20260515_snapshot_logs
Revises: 20260515_runtime_state
Create Date: 2026-05-15

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "20260515_snapshot_logs"
down_revision: Union[str, None] = "20260515_runtime_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "last_graph_states",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("cypher", sa.Text(), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "snapshots",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("owner", sa.String(255), nullable=True),
        sa.Column("case_id", sa.String(64), nullable=True),
        sa.Column("case_version", sa.Integer(), nullable=True),
        sa.Column("case_name", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("snapshot_timestamp", sa.String(64), nullable=True),
        sa.Column("data", JSONB, server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_snapshots_owner_created", "snapshots", ["owner", "created_at"])
    op.create_index("ix_snapshots_case_created", "snapshots", ["case_id", "created_at"])

    op.create_table(
        "system_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("log_type", sa.String(64), nullable=False),
        sa.Column("origin", sa.String(64), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("user", sa.String(255), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("details", JSONB, server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_system_logs_timestamp", "system_logs", ["timestamp"])
    op.create_index("ix_system_logs_type_timestamp", "system_logs", ["log_type", "timestamp"])
    op.create_index("ix_system_logs_origin_timestamp", "system_logs", ["origin", "timestamp"])
    op.create_index("ix_system_logs_user_timestamp", "system_logs", ["user", "timestamp"])
    op.create_index("ix_system_logs_success_timestamp", "system_logs", ["success", "timestamp"])


def downgrade() -> None:
    op.drop_index("ix_system_logs_success_timestamp", table_name="system_logs")
    op.drop_index("ix_system_logs_user_timestamp", table_name="system_logs")
    op.drop_index("ix_system_logs_origin_timestamp", table_name="system_logs")
    op.drop_index("ix_system_logs_type_timestamp", table_name="system_logs")
    op.drop_index("ix_system_logs_timestamp", table_name="system_logs")
    op.drop_table("system_logs")
    op.drop_index("ix_snapshots_case_created", table_name="snapshots")
    op.drop_index("ix_snapshots_owner_created", table_name="snapshots")
    op.drop_table("snapshots")
    op.drop_table("last_graph_states")
