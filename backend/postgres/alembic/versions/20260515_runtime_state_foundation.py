"""add runtime state tables

Revision ID: 20260515_runtime_state
Revises: 20260429_merge_robust
Create Date: 2026-05-15

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "20260515_runtime_state"
down_revision: Union[str, None] = "20260429_merge_robust"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "background_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_type", sa.String(100), nullable=False),
        sa.Column("task_name", sa.String(255), nullable=False),
        sa.Column("owner", sa.String(255), nullable=True),
        sa.Column("case_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("progress", JSONB, server_default="{}", nullable=False),
        sa.Column("files", JSONB, server_default="[]", nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_background_tasks_status",
        ),
    )
    op.create_index("ix_background_tasks_owner_created", "background_tasks", ["owner", "created_at"])
    op.create_index("ix_background_tasks_case_created", "background_tasks", ["case_id", "created_at"])
    op.create_index("ix_background_tasks_status", "background_tasks", ["status"])
    op.create_index("ix_background_tasks_task_type", "background_tasks", ["task_type"])

    op.create_table(
        "wiretap_processed_folders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(64), nullable=False),
        sa.Column("folder_path", sa.Text, nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("case_id", "folder_path", name="uq_wiretap_processed_case_folder"),
    )
    op.create_index(
        "ix_wiretap_processed_case_processed",
        "wiretap_processed_folders",
        ["case_id", "processed_at"],
    )

    op.create_table(
        "presence_sessions",
        sa.Column("session_id", sa.String(64), primary_key=True),
        sa.Column("case_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("device_info", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_active", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_presence_sessions_case_active", "presence_sessions", ["case_id", "last_active"])
    op.create_index("ix_presence_sessions_user", "presence_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_presence_sessions_user", table_name="presence_sessions")
    op.drop_index("ix_presence_sessions_case_active", table_name="presence_sessions")
    op.drop_table("presence_sessions")
    op.drop_index("ix_wiretap_processed_case_processed", table_name="wiretap_processed_folders")
    op.drop_table("wiretap_processed_folders")
    op.drop_index("ix_background_tasks_task_type", table_name="background_tasks")
    op.drop_index("ix_background_tasks_status", table_name="background_tasks")
    op.drop_index("ix_background_tasks_case_created", table_name="background_tasks")
    op.drop_index("ix_background_tasks_owner_created", table_name="background_tasks")
    op.drop_table("background_tasks")
