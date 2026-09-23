"""Durable pause requests for ingestion; uploaded files and checkpoints stay put."""
from alembic import op
import sqlalchemy as sa

revision = '20260922_ingestion_pause'
down_revision = '20260922_financial_operations'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('jobs', sa.Column('pause_requested', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('jobs', sa.Column('paused', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('jobs', sa.Column('resumable', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('jobs', sa.Column('resume_generation', sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    for name in ('resume_generation', 'resumable', 'paused', 'pause_requested'):
        op.drop_column('jobs', name)
