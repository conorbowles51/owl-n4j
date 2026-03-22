"""Add folder_context and sibling_files columns to jobs table

Revision ID: 005
Revises: 004
Create Date: 2026-03-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("folder_context", sa.Text, nullable=True))
    op.add_column("jobs", sa.Column("sibling_files", postgresql.JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "sibling_files")
    op.drop_column("jobs", "folder_context")
