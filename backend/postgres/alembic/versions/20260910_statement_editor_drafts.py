"""Preserve incomplete statement editor inputs separately from reviewed scopes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '20260910_statement_editor'
down_revision = '20260910_statement_drafts'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('financial_statement_review_drafts', sa.Column('editor_draft', postgresql.JSONB(), nullable=True))

def downgrade():
    op.drop_column('financial_statement_review_drafts', 'editor_draft')
