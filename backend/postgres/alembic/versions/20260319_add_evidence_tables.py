"""add evidence tables

Revision ID: 20260319_add_evidence_tables
Revises: 20260318_add_case_deadlines
Create Date: 2026-03-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260319_add_evidence_tables'
down_revision: Union[str, None] = '20260318_add_case_deadlines'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create evidence_folders, evidence_files, and ingestion_logs tables."""

    # --- evidence_folders ---
    op.create_table(
        'evidence_folders',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('disk_path', sa.Text(), nullable=True),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_id'], ['evidence_folders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('case_id', 'parent_id', 'name', name='uq_evidence_folders_case_parent_name'),
    )
    op.create_index('ix_evidence_folders_case_id', 'evidence_folders', ['case_id'], unique=False)
    op.create_index('ix_evidence_folders_parent_id', 'evidence_folders', ['parent_id'], unique=False)
    # Partial unique index: root-level folders must have unique names per case
    op.execute(
        "CREATE UNIQUE INDEX uq_evidence_folders_case_root_name "
        "ON evidence_folders (case_id, name) WHERE parent_id IS NULL"
    )

    # --- evidence_files ---
    op.create_table(
        'evidence_files',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('folder_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('original_filename', sa.String(length=512), nullable=False),
        sa.Column('stored_path', sa.Text(), nullable=False),
        sa.Column('size', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='unprocessed'),
        sa.Column('is_duplicate', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('duplicate_of_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('is_relevant', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('owner', sa.String(length=255), nullable=True),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('legacy_id', sa.String(length=64), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "status IN ('unprocessed', 'processing', 'processed', 'failed')",
            name='ck_evidence_files_status',
        ),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['folder_id'], ['evidence_folders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['duplicate_of_id'], ['evidence_files.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('legacy_id', name='uq_evidence_files_legacy_id'),
    )
    op.create_index('ix_evidence_files_case_id', 'evidence_files', ['case_id'], unique=False)
    op.create_index('ix_evidence_files_folder_id', 'evidence_files', ['folder_id'], unique=False)
    op.create_index('ix_evidence_files_sha256', 'evidence_files', ['sha256'], unique=False)
    op.create_index('ix_evidence_files_case_status', 'evidence_files', ['case_id', 'status'], unique=False)
    op.create_index('ix_evidence_files_legacy_id', 'evidence_files', ['legacy_id'], unique=False)

    # --- ingestion_logs ---
    op.create_table(
        'ingestion_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('evidence_file_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('level', sa.String(length=20), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('filename', sa.String(length=512), nullable=True),
        sa.Column('extra', postgresql.JSONB(), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['evidence_file_id'], ['evidence_files.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ingestion_logs_case_id', 'ingestion_logs', ['case_id'], unique=False)
    op.create_index('ix_ingestion_logs_case_created', 'ingestion_logs', ['case_id', 'created_at'], unique=False)


def downgrade() -> None:
    """Drop evidence tables."""
    op.drop_index('ix_ingestion_logs_case_created', table_name='ingestion_logs')
    op.drop_index('ix_ingestion_logs_case_id', table_name='ingestion_logs')
    op.drop_table('ingestion_logs')

    op.drop_index('ix_evidence_files_legacy_id', table_name='evidence_files')
    op.drop_index('ix_evidence_files_case_status', table_name='evidence_files')
    op.drop_index('ix_evidence_files_sha256', table_name='evidence_files')
    op.drop_index('ix_evidence_files_folder_id', table_name='evidence_files')
    op.drop_index('ix_evidence_files_case_id', table_name='evidence_files')
    op.drop_table('evidence_files')

    op.execute("DROP INDEX IF EXISTS uq_evidence_folders_case_root_name")
    op.drop_index('ix_evidence_folders_parent_id', table_name='evidence_folders')
    op.drop_index('ix_evidence_folders_case_id', table_name='evidence_folders')
    op.drop_table('evidence_folders')
