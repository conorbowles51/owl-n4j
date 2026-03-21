"""Add file_size, mime_type, sha256 columns to jobs table

Revision ID: 003
Revises: 002
Create Date: 2026-03-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("file_size", sa.BigInteger, nullable=False, server_default="0"))
    op.add_column("jobs", sa.Column("mime_type", sa.String(100), nullable=True))
    op.add_column("jobs", sa.Column("sha256", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "sha256")
    op.drop_column("jobs", "mime_type")
    op.drop_column("jobs", "file_size")
