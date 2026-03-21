"""Add resolving_relationships and generating_summaries job status values

Revision ID: 002
Revises: 001
Create Date: 2026-03-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction
    op.execute("ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS 'resolving_relationships'")
    op.execute("ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS 'generating_summaries'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; this is a no-op.
    # To fully revert, recreate the enum type without these values.
    pass
