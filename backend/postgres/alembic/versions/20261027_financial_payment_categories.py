"""Stored payment categories and the model's per-description cache: additive."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261027_financial_payment_categories"
down_revision = "20261027_financial_judgements"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'financial_payment_categories',
        sa.Column('transaction_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('financial_transactions.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('cases.id', ondelete='CASCADE'), nullable=False),
        sa.Column('category', sa.String(120), nullable=False, server_default=''),
        sa.Column('origin', sa.String(16), nullable=False),
        sa.Column('basis', sa.String(160), nullable=False, server_default=''),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('why', sa.Text(), nullable=True),
        sa.Column('stem', sa.String(200), nullable=False, server_default=''),
        sa.Column('set_by', sa.String(255), nullable=True),
        sa.Column('set_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("origin IN ('person', 'rule', 'model', 'learned')",
                           name='ck_financial_payment_categories_origin'),
    )
    op.create_index('ix_financial_payment_categories_case_category', 'financial_payment_categories', ['case_id', 'category'])
    op.create_index('ix_financial_payment_categories_case_stem', 'financial_payment_categories', ['case_id', 'stem'])
    op.create_table(
        'financial_category_model_cache',
        sa.Column('stem', sa.String(200), primary_key=True),
        sa.Column('direction', sa.String(8), primary_key=True),
        sa.Column('category', sa.String(120), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('why', sa.Text(), nullable=False, server_default=''),
        sa.Column('model', sa.String(120), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table('financial_category_model_cache')
    op.drop_index('ix_financial_payment_categories_case_stem', table_name='financial_payment_categories')
    op.drop_index('ix_financial_payment_categories_case_category', table_name='financial_payment_categories')
    op.drop_table('financial_payment_categories')
