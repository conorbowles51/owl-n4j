"""Add document_summary column to jobs table

Revision ID: 006
Revises: 005
Create Date: 2026-03-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("document_summary", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "document_summary")
