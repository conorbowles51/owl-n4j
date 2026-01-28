"""add guest role

Revision ID: 20260126201653
Revises: 4ade48544c21
Create Date: 2026-01-26 20:16:53

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '20260126201653'
down_revision: Union[str, Sequence[str]] = '4ade48544c21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 'guest' value to global_role enum."""
    op.execute("ALTER TYPE global_role ADD VALUE IF NOT EXISTS 'guest'")


def downgrade() -> None:
    """Cannot remove enum values in PostgreSQL."""
    raise NotImplementedError("Cannot remove enum values in PostgreSQL")
