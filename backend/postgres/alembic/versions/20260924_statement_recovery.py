"""Versioned, resumable recovery of previously prepared financial sources."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '20260924_statement_recovery'
down_revision = '20260923_account_identity'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("financial_recovery_releases",
        sa.Column("release", sa.String(64), primary_key=True),
        sa.Column("cutoff", sa.DateTime(timezone=True), nullable=False))
    op.create_table('financial_recovery_runs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('case_id', UUID(as_uuid=True), sa.ForeignKey('cases.id', ondelete='CASCADE'), nullable=False),
        sa.Column('release', sa.String(64), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('case_id', 'release', name='uq_financial_recovery_release'))
    op.create_index('ix_financial_recovery_runs_case_id', 'financial_recovery_runs', ['case_id'])
    op.create_table('financial_recovery_items',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('run_id', UUID(as_uuid=True), sa.ForeignKey('financial_recovery_runs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('file_id', UUID(as_uuid=True), sa.ForeignKey('evidence_files.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('result', JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('run_id', 'file_id', name='uq_financial_recovery_file'))
    op.create_index('ix_financial_recovery_items_run_id', 'financial_recovery_items', ['run_id'])


def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM financial_recovery_runs')).scalar_one():
        raise RuntimeError('Recovery history must be retained; refusing to remove nonempty recovery tables.')
    op.drop_table('financial_recovery_items')
    op.drop_table('financial_recovery_runs')
    op.drop_table('financial_recovery_releases')
