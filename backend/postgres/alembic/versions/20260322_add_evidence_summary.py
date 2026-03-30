"""add summary column to evidence_files

Revision ID: 20260322_evidence_summary
Revises: 20260322_folder_profiles
Create Date: 2026-03-22 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260322_evidence_summary'
down_revision: Union[str, None] = '20260322_folder_profiles'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add summary column to evidence_files."""
    op.add_column(
        'evidence_files',
        sa.Column('summary', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove summary column from evidence_files."""
    op.drop_column('evidence_files', 'summary')
