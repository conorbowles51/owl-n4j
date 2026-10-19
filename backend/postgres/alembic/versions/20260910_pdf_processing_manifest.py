"""Retain new PDF preparation runtime records; historical values remain unknown."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='20260910_pdf_processing_manifest'
down_revision='20260910_financial_audit_chain'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('evidence_document_texts',sa.Column('processing_manifest',postgresql.JSONB(none_as_null=True),nullable=True))

def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM evidence_document_texts WHERE processing_manifest IS NOT NULL')).scalar_one():
        raise RuntimeError('Cannot remove retained PDF processing provenance.')
    op.drop_column('evidence_document_texts','processing_manifest')
