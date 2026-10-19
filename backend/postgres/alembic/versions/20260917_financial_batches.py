"""Persist financial folder processing and reviewed bulk imports."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '20260917_financial_batches'
down_revision = '20260910_custody'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('financial_import_batches',
        sa.Column('id',postgresql.UUID(as_uuid=True),primary_key=True),
        sa.Column('case_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('cases.id',ondelete='CASCADE'),nullable=False),
        sa.Column('created_by',postgresql.UUID(as_uuid=True),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('status',sa.String(24),nullable=False),sa.Column('files',postgresql.JSONB(),nullable=False),sa.Column('actor',postgresql.JSONB(),nullable=False),
        sa.Column('worker_token',sa.String(36)),sa.Column('lease_until',sa.DateTime(timezone=True)),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_index('ix_financial_import_batches_case_id','financial_import_batches',['case_id'])
    op.create_table('financial_import_batch_items',
        sa.Column('id',postgresql.UUID(as_uuid=True),primary_key=True),
        sa.Column('batch_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('financial_import_batches.id',ondelete='CASCADE'),nullable=False),
        sa.Column('file_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('evidence_files.id',ondelete='CASCADE'),nullable=False),
        sa.Column('statement_key',sa.String(64),nullable=False),sa.Column('status',sa.String(24),nullable=False),
        sa.Column('summary',postgresql.JSONB(),nullable=False),sa.Column('review_request',postgresql.JSONB()),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.UniqueConstraint('batch_id','file_id','statement_key',name='uq_financial_batch_period'))
    op.create_index('ix_financial_import_batch_items_batch_id','financial_import_batch_items',['batch_id'])


def downgrade():
    op.drop_table('financial_import_batch_items')
    op.drop_table('financial_import_batches')
