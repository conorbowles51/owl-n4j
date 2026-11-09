"""significant relationships: a case-level mark on a relationship, beside significant entities (GR-01)

A relationship has no stable id in the graph reads (they return source key, type and target key), so the mark is
keyed by that triple within the case. Rows are kept when a mark is removed, with who and when, as for entities.

Revision ID: 20261109_significant_relationships
Revises: 20261109_guidance_and_steps
Create Date: 2026-11-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20261109_significant_relationships"
down_revision: Union[str, None] = "20261109_guidance_and_steps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "significant_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_key", sa.String(length=512), nullable=False),
        sa.Column("rel_type", sa.String(length=255), nullable=False),
        sa.Column("target_key", sa.String(length=512), nullable=False),
        sa.Column("added_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("addition_source", sa.String(length=32), server_default="manual", nullable=False),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"),
                  nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("removal_reason", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["added_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["removed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "source_key", "rel_type", "target_key",
                            name="uq_significant_relationships_case_triple"),
    )
    op.create_index("ix_significant_relationships_case_active", "significant_relationships",
                    ["case_id", "removed_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_significant_relationships_case_active", table_name="significant_relationships")
    op.drop_table("significant_relationships")
