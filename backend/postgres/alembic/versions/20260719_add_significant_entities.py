"""add durable significant entity manifest

Revision ID: 20260719_significant_entities
Revises: 20260705_timeline_views
Create Date: 2026-07-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260719_significant_entities"
down_revision: Union[str, None] = "20260705_timeline_views"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "significant_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_key", sa.String(length=512), nullable=False),
        sa.Column("added_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "addition_source",
            sa.String(length=32),
            server_default="manual",
            nullable=False,
        ),
        sa.Column(
            "context",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("removal_reason", sa.String(length=32), nullable=True),
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
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["added_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["removed_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "case_id",
            "entity_key",
            name="uq_significant_entities_case_entity",
        ),
    )
    op.create_index(
        "ix_significant_entities_case_active",
        "significant_entities",
        ["case_id", "removed_at"],
        unique=False,
    )
    op.create_index(
        "ix_significant_entities_added_by",
        "significant_entities",
        ["added_by_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_significant_entities_added_by",
        table_name="significant_entities",
    )
    op.drop_index(
        "ix_significant_entities_case_active",
        table_name="significant_entities",
    )
    op.drop_table("significant_entities")
