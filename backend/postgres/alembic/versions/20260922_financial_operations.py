"""Durable receipts for each investigator's batch import submission."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20260922_financial_operations'
down_revision = '20260922_timeline_entries'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('financial_import_operations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('cases.id', ondelete='CASCADE'), nullable=False),
        sa.Column('batch_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('financial_import_batches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('expected_revision', sa.String(64), nullable=False),
        sa.Column('actor', postgresql.JSONB(), nullable=False),
        sa.Column('outcomes', postgresql.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index('ix_financial_import_operations_case_id', 'financial_import_operations', ['case_id'])
    op.create_index('ix_financial_import_operations_batch_id', 'financial_import_operations', ['batch_id'])


def downgrade():
    op.drop_table('financial_import_operations')
