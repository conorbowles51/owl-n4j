"""add triage orchestration tables

Revision ID: 20260515_triage
Revises: 20260515_runtime_state
Create Date: 2026-05-15

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "20260515_triage"
down_revision: Union[str, None] = "20260515_runtime_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "triage_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="created"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("scan_cursor", sa.Text(), nullable=True),
        sa.Column("scan_stats", JSONB, server_default="{}", nullable=False),
        sa.Column("profile", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('created', 'scanning', 'scan_complete', 'classifying', "
            "'classified', 'profiling', 'profiled', 'processing', 'failed')",
            name="ck_triage_cases_status",
        ),
    )
    op.create_index("ix_triage_cases_created_by_created", "triage_cases", ["created_by", "created_at"])
    op.create_index("ix_triage_cases_status", "triage_cases", ["status"])

    op.create_table(
        "triage_stages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "triage_case_id",
            sa.String(36),
            sa.ForeignKey("triage_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("config", JSONB, server_default="{}", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("files_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("files_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("files_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_triage_stages_status",
        ),
        sa.UniqueConstraint("triage_case_id", "order", name="uq_triage_stages_case_order"),
    )
    op.create_index("ix_triage_stages_case_id", "triage_stages", ["triage_case_id"])
    op.create_index("ix_triage_stages_case_type", "triage_stages", ["triage_case_id", "type"])
    op.create_index("ix_triage_stages_case_status", "triage_stages", ["triage_case_id", "status"])

    op.create_table(
        "triage_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(255), nullable=False, server_default=""),
        sa.Column("stages", JSONB, server_default="[]", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_triage_templates_created_by_created", "triage_templates", ["created_by", "created_at"])

    op.create_table(
        "triage_hash_sets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False, server_default=""),
        sa.Column("hashes", JSONB, server_default="[]", nullable=False),
        sa.Column("hash_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", name="uq_triage_hash_sets_name"),
    )
    op.create_index("ix_triage_hash_sets_created_by", "triage_hash_sets", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_triage_hash_sets_created_by", table_name="triage_hash_sets")
    op.drop_table("triage_hash_sets")
    op.drop_index("ix_triage_templates_created_by_created", table_name="triage_templates")
    op.drop_table("triage_templates")
    op.drop_index("ix_triage_stages_case_status", table_name="triage_stages")
    op.drop_index("ix_triage_stages_case_type", table_name="triage_stages")
    op.drop_index("ix_triage_stages_case_id", table_name="triage_stages")
    op.drop_table("triage_stages")
    op.drop_index("ix_triage_cases_status", table_name="triage_cases")
    op.drop_index("ix_triage_cases_created_by_created", table_name="triage_cases")
    op.drop_table("triage_cases")
