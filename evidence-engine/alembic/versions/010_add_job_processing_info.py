"""Add processing_info column to jobs table

Revision ID: 010
Revises: 009
Create Date: 2026-07-18
"""
from typing import Sequence, Union

from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS processing_info JSONB NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS processing_info")
