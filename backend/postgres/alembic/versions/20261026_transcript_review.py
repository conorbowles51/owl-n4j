"""Add preserved audio sources, revisions, approvals and processing receipts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = '20261026_transcript_review'
down_revision = '20261019_workspace_setup'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('evidence_transcription_sources',
        sa.Column('id', UUID(), primary_key=True),
        sa.Column('evidence_file_id', UUID(), sa.ForeignKey('evidence_files.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('case_id', UUID(), nullable=False, index=True),
        sa.Column('engine_job_id', sa.String(64), unique=True, nullable=False),
        sa.Column('source_sha256', sa.String(64), nullable=False), sa.Column('text', sa.Text(), nullable=False),
        sa.Column('segments', JSONB(), nullable=False), sa.Column('metadata', JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table('evidence_transcript_revisions',
        sa.Column('id', UUID(), primary_key=True),
        sa.Column('evidence_file_id', UUID(), sa.ForeignKey('evidence_files.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('case_id', UUID(), nullable=False, index=True),
        sa.Column('source_id', UUID(), sa.ForeignKey('evidence_transcription_sources.id'), nullable=False),
        sa.Column('parent_id', UUID()), sa.Column('payload', JSONB(), nullable=False),
        sa.Column('digest', sa.String(64), nullable=False), sa.Column('author_id', UUID()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table('evidence_transcript_state',
        sa.Column('evidence_file_id', UUID(), sa.ForeignKey('evidence_files.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('case_id', UUID(), nullable=False, index=True), sa.Column('source_id', UUID(), nullable=False),
        sa.Column('working_revision_id', UUID(), nullable=False), sa.Column('reviewed_revision_id', UUID()),
        sa.Column('published_revision_id', UUID()), sa.Column('review_required', sa.Boolean(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False))
    op.create_table('evidence_transcript_reviews',
        sa.Column('id', UUID(), primary_key=True),
        sa.Column('evidence_file_id', UUID(), sa.ForeignKey('evidence_files.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('revision_id', UUID(), sa.ForeignKey('evidence_transcript_revisions.id'), nullable=False),
        sa.Column('actor_id', UUID(), nullable=False), sa.Column('request_key', sa.String(128), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('evidence_file_id', 'request_key'))
    op.create_table('evidence_processing_plans', sa.Column('id', UUID(), primary_key=True),
        sa.Column('case_id', UUID(), sa.ForeignKey('cases.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('actor_id', UUID(), nullable=False), sa.Column('payload', JSONB(), nullable=False),
        sa.Column('execution', JSONB()), sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.execute('''CREATE FUNCTION protect_audio_revision() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'Audio sources, revisions and review receipts are immutable'; END $$''')
    for table in ('evidence_transcription_sources', 'evidence_transcript_revisions', 'evidence_transcript_reviews'):
        op.execute(f'CREATE TRIGGER immutable_audio_record BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION protect_audio_revision()')
    op.execute("CREATE INDEX ix_evidence_audio_review_state ON evidence_files (case_id, folder_id, ((metadata->'transcript_review'->>'review_state')))")


def downgrade():
    bind = op.get_bind()
    if bind.scalar(sa.text('SELECT count(*) FROM evidence_transcription_sources')):
        raise RuntimeError('Saved transcripts exist. Keep the additive schema during rollback.')
    op.drop_index('ix_evidence_audio_review_state', table_name='evidence_files')
    for table in ('evidence_processing_plans', 'evidence_transcript_reviews', 'evidence_transcript_state',
                  'evidence_transcript_revisions', 'evidence_transcription_sources'):
        op.drop_table(table)
    op.execute('DROP FUNCTION protect_audio_revision()')
