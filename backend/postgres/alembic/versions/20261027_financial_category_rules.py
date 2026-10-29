"""People's category rules for future statements: additive."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261027_financial_category_rules"
down_revision = "20261027_financial_payment_categories"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'financial_category_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('cases.id', ondelete='CASCADE'), nullable=False),
        sa.Column('match_kind', sa.String(16), nullable=False),
        sa.Column('match_value', sa.String(200), nullable=False),
        sa.Column('example', sa.Text(), nullable=False, server_default=''),
        sa.Column('category', sa.String(120), nullable=False),
        sa.Column('from_transaction_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_by', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("match_kind IN ('description', 'counterparty')", name='ck_financial_category_rules_kind'),
    )
    op.create_index('ix_financial_category_rules_case_match', 'financial_category_rules',
                    ['case_id', 'match_kind', 'match_value'], unique=True)


def downgrade():
    op.drop_index('ix_financial_category_rules_case_match', table_name='financial_category_rules')
    op.drop_table('financial_category_rules')
