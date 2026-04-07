"""Add effective processing snapshot fields to jobs table

Revision ID: 007
Revises: 006
Create Date: 2026-04-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("effective_context", sa.Text, nullable=True))
    op.add_column("jobs", sa.Column("effective_special_entity_types", postgresql.JSONB, nullable=True))
    op.add_column("jobs", sa.Column("source_folder_id", sa.String(length=36), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "source_folder_id")
    op.drop_column("jobs", "effective_special_entity_types")
    op.drop_column("jobs", "effective_context")
