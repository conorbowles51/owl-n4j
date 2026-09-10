"""Persist replaceable statement control drafts with optimistic concurrency."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '20260910_statement_drafts'
down_revision = '20260909_preview_merge'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('financial_statement_review_drafts',
        sa.Column('evidence_file_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('evidence_files.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('cases.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('statement_scopes', postgresql.JSONB(), nullable=False),
        sa.Column('actor', postgresql.JSONB(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint('version > 0', name='ck_statement_review_draft_version'))
    op.create_index('ix_financial_statement_review_drafts_case_id', 'financial_statement_review_drafts', ['case_id'])

def downgrade():
    op.drop_table('financial_statement_review_drafts')
