"""add case archived field

Revision ID: 20260319_add_case_archived
Revises: 20260318_add_case_deadlines
Create Date: 2026-03-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260319_add_case_archived'
down_revision: Union[str, None] = '20260318_add_case_deadlines'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cases', sa.Column('archived', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('cases', 'archived')
