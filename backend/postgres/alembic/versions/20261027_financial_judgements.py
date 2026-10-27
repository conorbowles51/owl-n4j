"""The processor's judgement calls (financial_judgements): additive."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261027_financial_judgements"
down_revision = "20261019_workspace_setup"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'financial_judgements',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('cases.id', ondelete='CASCADE'), nullable=False),
        sa.Column('subject_type', sa.String(24), nullable=False),
        sa.Column('subject_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_document_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('statement_period_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('rule_id', sa.String(64), nullable=False),
        sa.Column('target_key', sa.String(48), nullable=False, server_default=''),
        sa.Column('reading', sa.String(80), nullable=False, server_default=''),
        sa.Column('origin', sa.String(16), nullable=False, server_default='processor'),
        sa.Column('strength', sa.String(16), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('evidence', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('status', sa.String(16), nullable=False, server_default='open'),
        sa.Column('resolved_by', sa.String(255), nullable=True),
        sa.Column('resolved_by_email', sa.String(255), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolution_reason', sa.Text(), nullable=True),
        sa.Column('adjudication_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("subject_type IN ('transaction', 'statement_period', 'source_document', 'account', 'evidence_file')",
                           name='ck_financial_judgements_subject'),
        sa.CheckConstraint("strength IN ('proved', 'inferred')", name='ck_financial_judgements_strength'),
        sa.CheckConstraint("status IN ('open', 'confirmed', 'corrected')", name='ck_financial_judgements_status'),
        sa.CheckConstraint("origin IN ('processor', 'agent')", name='ck_financial_judgements_origin'),
        sa.UniqueConstraint('subject_type', 'subject_id', 'rule_id', 'target_key', 'reading',
                            name='uq_financial_judgements_reading'),
    )
    op.create_index('ix_financial_judgements_case', 'financial_judgements', ['case_id', 'status'])
    op.create_index('ix_financial_judgements_document', 'financial_judgements', ['source_document_id'])
    op.create_index('ix_financial_judgements_subject', 'financial_judgements', ['subject_type', 'subject_id'])


def downgrade():
    op.drop_table('financial_judgements')
