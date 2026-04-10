"""add merge support to evidence engine jobs table

Revision ID: 20260410_engine_merge
Revises: 20260409_merge_jobs
Create Date: 2026-04-10

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "20260410_engine_merge"
down_revision: Union[str, None] = "20260409_merge_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Evidence engine jobs table — add merge support columns
    # Uses IF NOT EXISTS / IF NOT NULL checks so this is safe to run
    # even if the columns were already added manually.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'jobs' AND column_name = 'job_type'
            ) THEN
                ALTER TABLE jobs ADD COLUMN job_type VARCHAR(32) DEFAULT 'ingestion' NOT NULL;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'jobs' AND column_name = 'merge_payload'
            ) THEN
                ALTER TABLE jobs ADD COLUMN merge_payload JSONB;
            END IF;
        END $$;
    """)

    # Make file_name and file_path nullable (safe even if already nullable)
    op.execute("ALTER TABLE jobs ALTER COLUMN file_name DROP NOT NULL")
    op.execute("ALTER TABLE jobs ALTER COLUMN file_path DROP NOT NULL")

    # Add MERGING_PROPERTIES to jobstatus enum (IF NOT EXISTS is safe)
    op.execute("ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS 'merging_properties'")


def downgrade() -> None:
    pass
