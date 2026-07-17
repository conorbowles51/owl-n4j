"""add saved agent artifacts

Revision ID: 20260716_saved_agent_artifacts
Revises: 20260705_timeline_views
Create Date: 2026-07-16 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260716_saved_agent_artifacts"
down_revision: Union[str, None] = "20260705_timeline_views"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "saved_agent_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("destination", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("artifact_type", sa.String(length=32), nullable=False),
        sa.Column("artifact_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("artifact_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_thread_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "destination IN ('workspace', 'report')",
            name="ck_saved_agent_artifacts_destination",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_artifact_id"], ["agent_artifacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_thread_id"], ["agent_threads.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_saved_agent_artifacts_case_id", "saved_agent_artifacts", ["case_id"], unique=False)
    op.create_index("ix_saved_agent_artifacts_created_by_user_id", "saved_agent_artifacts", ["created_by_user_id"], unique=False)
    op.create_index("ix_saved_agent_artifacts_destination", "saved_agent_artifacts", ["destination"], unique=False)
    op.create_index("ix_saved_agent_artifacts_artifact_type", "saved_agent_artifacts", ["artifact_type"], unique=False)
    op.create_index("ix_saved_agent_artifacts_source_thread_id", "saved_agent_artifacts", ["source_thread_id"], unique=False)
    op.create_index("ix_saved_agent_artifacts_source_run_id", "saved_agent_artifacts", ["source_run_id"], unique=False)
    op.create_index("ix_saved_agent_artifacts_source_artifact_id", "saved_agent_artifacts", ["source_artifact_id"], unique=False)
    op.create_index(
        "ix_saved_agent_artifacts_case_destination_created",
        "saved_agent_artifacts",
        ["case_id", "destination", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_saved_agent_artifacts_case_destination_created", table_name="saved_agent_artifacts")
    op.drop_index("ix_saved_agent_artifacts_source_artifact_id", table_name="saved_agent_artifacts")
    op.drop_index("ix_saved_agent_artifacts_source_run_id", table_name="saved_agent_artifacts")
    op.drop_index("ix_saved_agent_artifacts_source_thread_id", table_name="saved_agent_artifacts")
    op.drop_index("ix_saved_agent_artifacts_artifact_type", table_name="saved_agent_artifacts")
    op.drop_index("ix_saved_agent_artifacts_destination", table_name="saved_agent_artifacts")
    op.drop_index("ix_saved_agent_artifacts_created_by_user_id", table_name="saved_agent_artifacts")
    op.drop_index("ix_saved_agent_artifacts_case_id", table_name="saved_agent_artifacts")
    op.drop_table("saved_agent_artifacts")
