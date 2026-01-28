"""add rejected_merge_pairs table

Revision ID: 20260128_rejected_pairs
Revises: 20260126201653
Create Date: 2026-01-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '20260128_rejected_pairs'
down_revision: Union[str, Sequence[str]] = '20260126201653'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create rejected_merge_pairs table."""
    op.create_table(
        'rejected_merge_pairs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('case_id', sa.UUID(), nullable=False),
        sa.Column('entity_key_1', sa.String(length=255), nullable=False),
        sa.Column('entity_key_2', sa.String(length=255), nullable=False),
        sa.Column('rejected_by_user_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['rejected_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('case_id', 'entity_key_1', 'entity_key_2', name='uq_rejected_pair'),
    )
    op.create_index(op.f('ix_rejected_merge_pairs_case_id'), 'rejected_merge_pairs', ['case_id'], unique=False)
    op.create_index(op.f('ix_rejected_merge_pairs_rejected_by_user_id'), 'rejected_merge_pairs', ['rejected_by_user_id'], unique=False)
    op.create_index('ix_rejected_pairs_case_keys', 'rejected_merge_pairs', ['case_id', 'entity_key_1', 'entity_key_2'], unique=False)


def downgrade() -> None:
    """Drop rejected_merge_pairs table."""
    op.drop_index('ix_rejected_pairs_case_keys', table_name='rejected_merge_pairs')
    op.drop_index(op.f('ix_rejected_merge_pairs_rejected_by_user_id'), table_name='rejected_merge_pairs')
    op.drop_index(op.f('ix_rejected_merge_pairs_case_id'), table_name='rejected_merge_pairs')
    op.drop_table('rejected_merge_pairs')
