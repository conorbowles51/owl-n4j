"""add geocoding cache table

Revision ID: 20260407_add_geocoding_cache
Revises: 20260407_instruction_lists
Create Date: 2026-04-07 21:15:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260407_add_geocoding_cache"
down_revision: Union[str, None] = "20260407_instruction_lists"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "geocoding_cache",
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("normalized_query", sa.Text(), nullable=False),
        sa.Column("original_query", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("formatted_address", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=True),
        sa.Column("raw_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('success', 'failed')", name="ck_geocoding_cache_status"),
        sa.PrimaryKeyConstraint("provider", "normalized_query"),
    )
    op.create_index(
        "ix_geocoding_cache_status",
        "geocoding_cache",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_geocoding_cache_status", table_name="geocoding_cache")
    op.drop_table("geocoding_cache")
