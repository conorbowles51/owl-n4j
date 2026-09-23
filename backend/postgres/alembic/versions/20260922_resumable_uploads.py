"""Byte-verified resumable uploads with atomic registration receipts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision = '20260922_resumable_uploads'
down_revision = '20260922_ingestion_pause'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('evidence_upload_sessions',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('case_id', pg.UUID(as_uuid=True), sa.ForeignKey('cases.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', pg.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('folder_id', pg.UUID(as_uuid=True), sa.ForeignKey('evidence_folders.id', ondelete='CASCADE')),
        sa.Column('filename', sa.String(1024), nullable=False),
        sa.Column('size', sa.BigInteger(), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('chunk_size', sa.Integer(), nullable=False),
        sa.Column('chunks', pg.JSONB(), nullable=False),
        sa.Column('evidence_id', pg.UUID(as_uuid=True), sa.ForeignKey('evidence_files.id', ondelete='SET NULL')),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('ix_evidence_upload_sessions_case_id', 'evidence_upload_sessions', ['case_id'])


def downgrade():
    op.drop_table('evidence_upload_sessions')
