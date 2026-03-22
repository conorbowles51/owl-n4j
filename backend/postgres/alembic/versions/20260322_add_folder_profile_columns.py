"""add folder profile columns

Revision ID: 20260322_folder_profiles
Revises: 20260321_add_engine_job_id
Create Date: 2026-03-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260322_folder_profiles'
down_revision: Union[str, None] = '20260321_add_engine_job_id'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add context_instructions and profile_overrides to evidence_folders."""
    op.add_column(
        'evidence_folders',
        sa.Column('context_instructions', sa.Text(), nullable=True),
    )
    op.add_column(
        'evidence_folders',
        sa.Column('profile_overrides', postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    """Remove context_instructions and profile_overrides from evidence_folders."""
    op.drop_column('evidence_folders', 'profile_overrides')
    op.drop_column('evidence_folders', 'context_instructions')
