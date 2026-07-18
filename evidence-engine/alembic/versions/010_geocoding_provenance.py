"""Add geocoding provenance fields

Revision ID: 010
Revises: 009
Create Date: 2026-07-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS geocoding_cache (
            provider VARCHAR(64) NOT NULL,
            normalized_query TEXT NOT NULL,
            original_query TEXT NOT NULL,
            status VARCHAR(32) NOT NULL,
            latitude FLOAT NULL,
            longitude FLOAT NULL,
            formatted_address TEXT NULL,
            confidence VARCHAR(16) NULL,
            raw_response JSONB NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            PRIMARY KEY (provider, normalized_query)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_geocoding_cache_status ON geocoding_cache (status)")
    op.execute("ALTER TABLE geocoding_cache ALTER COLUMN status TYPE VARCHAR(32)")
    op.execute("ALTER TABLE geocoding_cache ADD COLUMN IF NOT EXISTS geocoder VARCHAR(64) NULL")
    op.execute("ALTER TABLE geocoding_cache ADD COLUMN IF NOT EXISTS query TEXT NULL")
    op.execute("ALTER TABLE geocoding_cache ADD COLUMN IF NOT EXISTS precision VARCHAR(32) NULL")
    op.execute("ALTER TABLE geocoding_cache ADD COLUMN IF NOT EXISTS candidates JSONB NULL")
    op.execute("ALTER TABLE geocoding_cache ADD COLUMN IF NOT EXISTS rejection_reason VARCHAR(64) NULL")
    op.execute("ALTER TABLE geocoding_cache ADD COLUMN IF NOT EXISTS provider_error TEXT NULL")
    op.execute("UPDATE geocoding_cache SET geocoder = provider WHERE geocoder IS NULL")
    op.execute("UPDATE geocoding_cache SET query = original_query WHERE query IS NULL")


def downgrade() -> None:
    op.drop_column("geocoding_cache", "provider_error")
    op.drop_column("geocoding_cache", "rejection_reason")
    op.drop_column("geocoding_cache", "candidates")
    op.drop_column("geocoding_cache", "precision")
    op.drop_column("geocoding_cache", "query")
    op.drop_column("geocoding_cache", "geocoder")
    op.execute("ALTER TABLE geocoding_cache ALTER COLUMN status TYPE VARCHAR(16)")
