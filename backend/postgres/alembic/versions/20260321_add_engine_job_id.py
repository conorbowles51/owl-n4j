"""add engine_job_id to evidence_files

Revision ID: 20260321_add_engine_job_id
Revises: 20260321_add_workspace_tables
Create Date: 2026-03-21 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260321_add_engine_job_id'
down_revision: Union[str, None] = '20260321_add_workspace_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'evidence_files',
        sa.Column('engine_job_id', sa.String(36), nullable=True),
    )
    op.create_index(
        'ix_evidence_files_engine_job_id',
        'evidence_files',
        ['engine_job_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_evidence_files_engine_job_id', table_name='evidence_files')
    op.drop_column('evidence_files', 'engine_job_id')
