"""add geocoding provenance fields

Revision ID: 20260718_geocoding_provenance
Revises: 20260705_timeline_views
Create Date: 2026-07-18 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260718_geocoding_provenance"
down_revision: Union[str, None] = "20260705_timeline_views"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE geocoding_cache DROP CONSTRAINT IF EXISTS ck_geocoding_cache_status")
    op.execute("ALTER TABLE geocoding_cache ALTER COLUMN status TYPE VARCHAR(32)")
    op.add_column("geocoding_cache", sa.Column("geocoder", sa.String(64), nullable=True))
    op.add_column("geocoding_cache", sa.Column("query", sa.Text(), nullable=True))
    op.add_column("geocoding_cache", sa.Column("precision", sa.String(32), nullable=True))
    op.add_column("geocoding_cache", sa.Column("candidates", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("geocoding_cache", sa.Column("rejection_reason", sa.String(64), nullable=True))
    op.add_column("geocoding_cache", sa.Column("provider_error", sa.Text(), nullable=True))
    op.execute("UPDATE geocoding_cache SET geocoder = provider WHERE geocoder IS NULL")
    op.execute("UPDATE geocoding_cache SET query = original_query WHERE query IS NULL")
    op.create_check_constraint(
        "ck_geocoding_cache_status",
        "geocoding_cache",
        "status IN ('success', 'failed', 'mapped', 'rejected', 'unmapped_retriable')",
    )


def downgrade() -> None:
    op.execute("ALTER TABLE geocoding_cache DROP CONSTRAINT IF EXISTS ck_geocoding_cache_status")
    op.drop_column("geocoding_cache", "provider_error")
    op.drop_column("geocoding_cache", "rejection_reason")
    op.drop_column("geocoding_cache", "candidates")
    op.drop_column("geocoding_cache", "precision")
    op.drop_column("geocoding_cache", "query")
    op.drop_column("geocoding_cache", "geocoder")
    op.execute("ALTER TABLE geocoding_cache ALTER COLUMN status TYPE VARCHAR(16)")
    op.create_check_constraint(
        "ck_geocoding_cache_status",
        "geocoding_cache",
        "status IN ('success', 'failed')",
    )
