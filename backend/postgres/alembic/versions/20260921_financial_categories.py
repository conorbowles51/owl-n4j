"""Shared financial category library."""
from alembic import op
import sqlalchemy as sa

revision = '20260921_financial_categories'
down_revision = '20260917_financial_batches'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('financial_categories',
        sa.Column('normalized_name', sa.String(360), primary_key=True),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('color', sa.String(7), nullable=False),
        sa.Column('created_by', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade():
    op.drop_table('financial_categories')
