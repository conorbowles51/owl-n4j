"""allow ambiguous geocoding cache results

Revision ID: 20260722_geocode_ambiguous
Revises: 20260721_ingestion_state
Create Date: 2026-07-22

"""
from typing import Sequence, Union

from alembic import op


revision: str = "20260722_geocode_ambiguous"
down_revision: Union[str, Sequence[str], None] = "20260721_ingestion_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE geocoding_cache DROP CONSTRAINT IF EXISTS "
        "ck_geocoding_cache_status"
    )
    op.execute(
        "ALTER TABLE geocoding_cache ADD CONSTRAINT ck_geocoding_cache_status "
        "CHECK (status IN ('success', 'failed', 'ambiguous'))"
    )


def downgrade() -> None:
    op.execute("DELETE FROM geocoding_cache WHERE status = 'ambiguous'")
    op.execute(
        "ALTER TABLE geocoding_cache DROP CONSTRAINT IF EXISTS "
        "ck_geocoding_cache_status"
    )
    op.execute(
        "ALTER TABLE geocoding_cache ADD CONSTRAINT ck_geocoding_cache_status "
        "CHECK (status IN ('success', 'failed'))"
    )
