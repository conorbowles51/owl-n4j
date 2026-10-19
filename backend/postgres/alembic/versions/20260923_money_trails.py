"""Reviewed transfers and onward allocations with retained source snapshots."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '20260923_money_trails'
down_revision = '20260922_resumable_uploads'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('financial_money_trails',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('case_id', UUID(as_uuid=True), sa.ForeignKey('cases.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('details', JSONB(), nullable=False),
        sa.Column('history', JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index('ix_financial_money_trails_case_id', 'financial_money_trails', ['case_id'])


def downgrade():
    op.drop_table('financial_money_trails')
