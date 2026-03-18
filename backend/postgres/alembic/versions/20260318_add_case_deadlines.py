"""add case deadlines

Revision ID: 20260318_add_case_deadlines
Revises: 20260129_add_cost_records
Create Date: 2026-03-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260318_add_case_deadlines'
down_revision: Union[str, None] = '20260129_add_cost_records'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('case_deadlines',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_case_deadlines_case_id'), 'case_deadlines', ['case_id'], unique=False)
    op.create_index(op.f('ix_case_deadlines_due_date'), 'case_deadlines', ['due_date'], unique=False)
    op.create_index(op.f('ix_case_deadlines_created_by_user_id'), 'case_deadlines', ['created_by_user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_case_deadlines_created_by_user_id'), table_name='case_deadlines')
    op.drop_index(op.f('ix_case_deadlines_due_date'), table_name='case_deadlines')
    op.drop_index(op.f('ix_case_deadlines_case_id'), table_name='case_deadlines')
    op.drop_table('case_deadlines')
