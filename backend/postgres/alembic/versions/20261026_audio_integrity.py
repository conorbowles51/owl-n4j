"""Case-scoped audio foreign keys and private revision audit digests."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '20261026_audio_integrity'
down_revision = '20261026_transcript_review'
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint('uq_evidence_file_case', 'evidence_files', ['id', 'case_id'])
    for table, name in [('evidence_transcription_sources', 'source'), ('evidence_transcript_revisions', 'revision')]:
        op.create_unique_constraint(f'uq_audio_{name}_scope', table, ['id', 'evidence_file_id', 'case_id'])
    op.create_foreign_key('fk_audio_source_case', 'evidence_transcription_sources', 'evidence_files',
        ['evidence_file_id', 'case_id'], ['id', 'case_id'], ondelete='CASCADE')
    op.create_foreign_key('fk_audio_revision_source', 'evidence_transcript_revisions', 'evidence_transcription_sources',
        ['source_id', 'evidence_file_id', 'case_id'], ['id', 'evidence_file_id', 'case_id'])
    op.create_foreign_key('fk_audio_revision_parent', 'evidence_transcript_revisions', 'evidence_transcript_revisions',
        ['parent_id', 'evidence_file_id', 'case_id'], ['id', 'evidence_file_id', 'case_id'])
    op.create_foreign_key('fk_audio_state_source', 'evidence_transcript_state', 'evidence_transcription_sources',
        ['source_id', 'evidence_file_id', 'case_id'], ['id', 'evidence_file_id', 'case_id'])
    for field in ('working_revision_id', 'reviewed_revision_id', 'published_revision_id'):
        op.create_foreign_key(f'fk_audio_state_{field}', 'evidence_transcript_state', 'evidence_transcript_revisions',
            [field, 'evidence_file_id', 'case_id'], ['id', 'evidence_file_id', 'case_id'])
    op.add_column('evidence_transcript_reviews', sa.Column('case_id', UUID(), nullable=True))
    # Only this one additive backfill bypasses the update guard. No saved
    # revision, receipt identity or original transcript is changed.
    op.execute('ALTER TABLE evidence_transcript_reviews DISABLE TRIGGER immutable_audio_record')
    op.execute('UPDATE evidence_transcript_reviews r SET case_id=f.case_id FROM evidence_files f WHERE f.id=r.evidence_file_id')
    op.execute('ALTER TABLE evidence_transcript_reviews ENABLE TRIGGER immutable_audio_record')
    op.alter_column('evidence_transcript_reviews', 'case_id', nullable=False)
    op.create_foreign_key('fk_audio_review_revision', 'evidence_transcript_reviews', 'evidence_transcript_revisions',
        ['revision_id', 'evidence_file_id', 'case_id'], ['id', 'evidence_file_id', 'case_id'])
    op.execute('''CREATE FUNCTION capture_audio_review_audit() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE row_data jsonb; old_data jsonb; audit_case uuid;
    BEGIN
      row_data := CASE WHEN TG_OP='DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
      old_data := CASE WHEN TG_OP IN ('UPDATE','DELETE') THEN to_jsonb(OLD) ELSE NULL END;
      IF row_data=old_data THEN RETURN NEW; END IF;
      IF TG_TABLE_NAME='evidence_processing_plans' AND row_data->'execution'='null'::jsonb THEN
        IF TG_OP='DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
      END IF;
      audit_case := (row_data->>'case_id')::uuid;
      PERFORM append_financial_audit_event(audit_case, jsonb_build_object(
        'capture_policy','20261026_audio_integrity','source_table',TG_TABLE_NAME,
        'source_id',coalesce(row_data->>'id',row_data->>'evidence_file_id'),'operation',TG_OP,
        'actor',coalesce(row_data->'author_id',row_data->'actor_id'),
        'before_sha256',CASE WHEN old_data IS NULL THEN NULL ELSE encode(sha256(convert_to(old_data::text,'UTF8')),'hex') END,
        'after_sha256',CASE WHEN TG_OP='DELETE' THEN NULL ELSE encode(sha256(convert_to(row_data::text,'UTF8')),'hex') END,
        'revision_id',coalesce(row_data->>'revision_id',row_data->>'working_revision_id'),
        'limitation','Revision/state receipt digests; transcript bodies and processing context are private and omitted.'));
      IF TG_OP='DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END $$''')
    for table in ('evidence_transcription_sources', 'evidence_transcript_revisions', 'evidence_transcript_state', 'evidence_transcript_reviews', 'evidence_processing_plans'):
        op.execute(f'CREATE TRIGGER capture_audio_review_audit AFTER INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION capture_audio_review_audit()')
        op.execute(f'CREATE TRIGGER refuse_unaudited_truncate BEFORE TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION refuse_audited_source_truncate()')


def downgrade():
    raise RuntimeError('Keep saved transcript revisions and their case audit coverage during application rollback.')
