"""Chain ledger state, evidence registration and Workspace state prospectively."""
from alembic import op
import sqlalchemy as sa
revision='20260910_audit_state_changes'
down_revision='20260910_pdf_processing_manifest'
branch_labels=None
depends_on=None

TARGETS=(
    ('financial_source_documents','INSERT OR UPDATE OR DELETE'),
    ('financial_accounts','INSERT OR UPDATE OR DELETE'),
    ('financial_statement_periods','INSERT OR UPDATE OR DELETE'),
    ('financial_transactions','INSERT OR UPDATE OR DELETE'),
    ('financial_statement_review_drafts','INSERT OR UPDATE OR DELETE'),
    ('evidence_files','INSERT OR UPDATE OR DELETE'),
    ('workspace_entries','INSERT OR UPDATE OR DELETE'),
    ('workspace_entry_revisions','INSERT'),
    ('workspace_entry_links','INSERT OR UPDATE OR DELETE'),
    ('workspace_entry_events','INSERT'),
)


def upgrade():
    op.execute('''CREATE OR REPLACE FUNCTION capture_financial_audit_event() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
      current_row jsonb := to_jsonb(NEW);
      previous_row jsonb := NULL;
      audit_case uuid;
      previous_hash text;
      next_sequence bigint;
      payload text;
      recorded_actor jsonb;
      actor_basis text;
      request_context jsonb;
      private_fields text[];
      private_values jsonb;
    BEGIN
      IF TG_OP='DELETE' THEN current_row := to_jsonb(OLD); previous_row := current_row; END IF;
      IF TG_OP = 'UPDATE' THEN
        previous_row := to_jsonb(OLD);
        IF (current_row->>'case_id') IS DISTINCT FROM (previous_row->>'case_id') THEN
          RAISE EXCEPTION 'Tracked financial and evidence records cannot change case ownership in place';
        END IF;
        IF current_row = previous_row THEN RETURN NEW; END IF;
      END IF;
      IF TG_ARGV[0] = 'candidate' THEN
        SELECT m.case_id INTO audit_case FROM financial_extraction_candidates c
          JOIN financial_candidate_mappings m ON m.id=c.mapping_id
          WHERE c.id=(current_row->>'candidate_id')::uuid;
      ELSE audit_case := (current_row->>'case_id')::uuid;
      END IF;
      IF audit_case IS NULL THEN RAISE EXCEPTION 'Financial audit event has no case'; END IF;
      -- Held until transaction completion. Rolled-back changes cannot leave events.
      -- Unique (case, sequence) is the second line of concurrency protection.
      PERFORM pg_advisory_xact_lock(hashtextextended('loupe.financial.audit:' || audit_case::text, 0));
      SELECT sequence+1, entry_sha256 INTO next_sequence, previous_hash
        FROM financial_audit_events WHERE case_id=audit_case ORDER BY sequence DESC LIMIT 1;
      next_sequence := COALESCE(next_sequence, 1);
      previous_hash := COALESCE(previous_hash, repeat('0',64));
      IF current_row->'actor' IS NOT NULL AND current_row->'actor' <> 'null'::jsonb THEN
        recorded_actor := current_row->'actor'; actor_basis := 'source_record';
        IF TG_OP='UPDATE' AND current_row->'outcome_actor' IS NOT NULL AND current_row->'outcome_actor' <> 'null'::jsonb THEN
          recorded_actor := current_row->'outcome_actor';
        END IF;
      ELSIF current_row->>'actor_name' IS NOT NULL THEN
        recorded_actor := jsonb_build_object('name',current_row->>'actor_name','email',current_row->>'actor_email','user_id',current_row->>'actor_user_id');
        actor_basis := 'source_record';
      ELSE recorded_actor := NULL; actor_basis := 'not_recorded'; END IF;
      IF TG_TABLE_NAME='financial_ingestion_runs' THEN
        recorded_actor := jsonb_build_object('user_id',current_row->>'started_by_user_id','email',current_row->>'started_by_email');
        actor_basis := 'recorded_run_initiator_not_update_actor';
        current_row := (current_row - 'config' - 'error' - 'notes') || jsonb_build_object(
          'omitted_private_fields_sha256',encode(sha256(convert_to(jsonb_build_object('config',current_row->'config','error',current_row->'error','notes',current_row->'notes')::text,'UTF8')),'hex'));
        IF previous_row IS NOT NULL THEN
          previous_row := (previous_row - 'config' - 'error' - 'notes') || jsonb_build_object(
            'omitted_private_fields_sha256',encode(sha256(convert_to(jsonb_build_object('config',previous_row->'config','error',previous_row->'error','notes',previous_row->'notes')::text,'UTF8')),'hex'));
        END IF;
      END IF;
      IF TG_TABLE_NAME='evidence_files' THEN
        private_fields := ARRAY['stored_path','last_error','last_processed_profile_snapshot','metadata','summary','transcription','transcription_segments'];
        SELECT COALESCE(jsonb_object_agg(key,value),'{}'::jsonb) INTO private_values FROM jsonb_each(current_row) WHERE key=ANY(private_fields);
        current_row := (current_row - private_fields) || jsonb_build_object('omitted_private_fields',private_fields,'omitted_private_fields_sha256',encode(sha256(convert_to(private_values::text,'UTF8')),'hex'));
        IF previous_row IS NOT NULL THEN
          SELECT COALESCE(jsonb_object_agg(key,value),'{}'::jsonb) INTO private_values FROM jsonb_each(previous_row) WHERE key=ANY(private_fields);
          previous_row := (previous_row - private_fields) || jsonb_build_object('omitted_private_fields',private_fields,'omitted_private_fields_sha256',encode(sha256(convert_to(private_values::text,'UTF8')),'hex'));
        END IF;
      END IF;
      request_context := NULLIF(current_setting('loupe.audit_context',true),'')::jsonb;
      IF request_context->>'case_id'=audit_case::text THEN
        recorded_actor := request_context->'actor'; actor_basis := 'authorized_request';
      END IF;
      payload := jsonb_build_object('schema_version','loupe.financial.audit_event/1',
        'case_id',audit_case::text,'sequence',next_sequence,
        'recorded_at',to_char(clock_timestamp() AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
        'capture_policy','20260910_audit_state_changes',
        'source_table',TG_TABLE_NAME,'operation',TG_OP,'source_id',COALESCE(current_row->>'id',current_row->>'evidence_file_id'),
        'database_principal',current_user,'transaction_id',txid_current()::text,
        'actor',recorded_actor,'actor_basis',actor_basis,
        'reason',COALESCE(current_row->>'reason',current_row->>'rationale'),'before',previous_row,'after',CASE WHEN TG_OP='DELETE' THEN NULL ELSE current_row END)::text;
      INSERT INTO financial_audit_events(case_id,sequence,previous_sha256,entry_sha256,payload_text)
        VALUES(audit_case,next_sequence,previous_hash,
          encode(sha256(decode(previous_hash,'hex') || convert_to(payload,'UTF8')),'hex'),payload);
      IF TG_OP='DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END $$''')
    for table, operations in TARGETS:
        op.execute(f"CREATE TRIGGER capture_financial_audit AFTER {operations} ON {table} FOR EACH ROW EXECUTE FUNCTION capture_financial_audit_event('direct')")


def downgrade():
    raise RuntimeError('Audit coverage cannot be silently removed; restore an explicitly reviewed database backup instead.')
