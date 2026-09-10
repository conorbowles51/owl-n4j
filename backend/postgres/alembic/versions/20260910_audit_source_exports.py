"""Capture source replacement and provide atomic prepared-export audit appends."""
from alembic import op
revision='20260910_audit_source_exports'
down_revision='20260910_audit_state_changes'
branch_labels=None
depends_on=None


def upgrade():
    op.execute("CREATE INDEX ix_financial_audit_source_transaction ON financial_audit_events ((payload_text::jsonb->>'source_table'),(payload_text::jsonb->>'source_id'),(payload_text::jsonb->>'transaction_id'))")
    op.execute('''CREATE FUNCTION append_financial_audit_event(audit_case uuid, body jsonb) RETURNS jsonb LANGUAGE plpgsql AS $$
    DECLARE previous_hash text; next_sequence bigint; payload text; entry_hash text;
    BEGIN
      IF audit_case IS NULL OR jsonb_typeof(body) IS DISTINCT FROM 'object'
        OR body->>'source_table' IS NULL OR body->>'source_id' IS NULL OR body->>'operation' IS NULL
      THEN RAISE EXCEPTION 'Malformed financial audit append'; END IF;
      PERFORM pg_advisory_xact_lock(hashtextextended('loupe.financial.audit:' || audit_case::text,0));
      SELECT sequence+1,entry_sha256 INTO next_sequence,previous_hash
        FROM financial_audit_events WHERE case_id=audit_case ORDER BY sequence DESC LIMIT 1;
      next_sequence:=COALESCE(next_sequence,1);previous_hash:=COALESCE(previous_hash,repeat('0',64));
      payload:=(body || jsonb_build_object('schema_version','loupe.financial.audit_event/1','case_id',audit_case::text,
        'sequence',next_sequence,'recorded_at',to_char(clock_timestamp() AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
        'database_principal',current_user,'transaction_id',txid_current()::text))::text;
      entry_hash:=encode(sha256(decode(previous_hash,'hex') || convert_to(payload,'UTF8')),'hex');
      INSERT INTO financial_audit_events(case_id,sequence,previous_sha256,entry_sha256,payload_text)
        VALUES(audit_case,next_sequence,previous_hash,entry_hash,payload);
      RETURN jsonb_build_object('sequence',next_sequence,'entry_sha256',entry_hash);
    END $$''')
    op.execute('''CREATE OR REPLACE FUNCTION capture_financial_audit_event() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
      current_row jsonb := to_jsonb(NEW);
      previous_row jsonb := NULL;
      audit_case uuid;
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
        IF (current_row->>'case_id') IS DISTINCT FROM (previous_row->>'case_id')
          OR (TG_ARGV[0]='prepared_source' AND (current_row->>'evidence_file_id') IS DISTINCT FROM (previous_row->>'evidence_file_id')) THEN
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
      IF TG_ARGV[0]='prepared_source' THEN
        SELECT case_id INTO audit_case FROM evidence_files WHERE id=(current_row->>'evidence_file_id')::uuid;
        IF audit_case IS NULL AND TG_OP='DELETE' THEN
          -- The parent's BEFORE DELETE event precedes cascading child deletes.
          SELECT case_id INTO audit_case FROM financial_audit_events
            WHERE payload_text::jsonb->>'source_table'='evidence_files'
              AND payload_text::jsonb->>'source_id'=current_row->>'evidence_file_id'
              AND payload_text::jsonb->>'operation'='DELETE'
              AND payload_text::jsonb->>'transaction_id'=txid_current()::text
            ORDER BY sequence DESC LIMIT 1;
        END IF;
      END IF;
      IF audit_case IS NULL THEN RAISE EXCEPTION 'Financial audit event has no case'; END IF;
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
      IF TG_TABLE_NAME='evidence_document_texts' THEN
        current_row := (current_row - 'content') || jsonb_build_object('omitted_content_sha256',encode(sha256(convert_to(current_row->>'content','UTF8')),'hex'));
        IF previous_row IS NOT NULL THEN
          previous_row := (previous_row - 'content') || jsonb_build_object('omitted_content_sha256',encode(sha256(convert_to(previous_row->>'content','UTF8')),'hex'));
        END IF;
      ELSIF TG_TABLE_NAME='evidence_table_geometry' THEN
        current_row := (current_row - 'payload') || jsonb_build_object('geometry_payload_sha256',encode(sha256(convert_to((current_row->'payload')::text,'UTF8')),'hex'));
        IF previous_row IS NOT NULL THEN
          previous_row := (previous_row - 'payload') || jsonb_build_object('geometry_payload_sha256',encode(sha256(convert_to((previous_row->'payload')::text,'UTF8')),'hex'));
        END IF;
      END IF;
      request_context := NULLIF(current_setting('loupe.audit_context',true),'')::jsonb;
      IF request_context->>'case_id'=audit_case::text THEN
        recorded_actor := request_context->'actor'; actor_basis := 'authorized_request';
      END IF;
      payload := jsonb_build_object('capture_policy','20260910_audit_source_exports',
        'source_table',TG_TABLE_NAME,'operation',TG_OP,'source_id',COALESCE(current_row->>'id',current_row->>'evidence_file_id'),
        'actor',recorded_actor,'actor_basis',actor_basis,
        'reason',COALESCE(current_row->>'reason',current_row->>'rationale'),'before',previous_row,'after',CASE WHEN TG_OP='DELETE' THEN NULL ELSE current_row END)::text;
      PERFORM append_financial_audit_event(audit_case,payload::jsonb);
      IF TG_OP='DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END $$''')
    op.execute('DROP TRIGGER capture_financial_audit ON evidence_files')
    op.execute("CREATE TRIGGER capture_financial_audit AFTER INSERT OR UPDATE ON evidence_files FOR EACH ROW EXECUTE FUNCTION capture_financial_audit_event('direct')")
    op.execute("CREATE TRIGGER capture_financial_audit_delete BEFORE DELETE ON evidence_files FOR EACH ROW EXECUTE FUNCTION capture_financial_audit_event('direct')")
    for table in ('evidence_document_texts','evidence_table_geometry'):
        op.execute(f"CREATE TRIGGER capture_financial_audit AFTER INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION capture_financial_audit_event('prepared_source')")

    op.execute("CREATE FUNCTION refuse_audited_source_truncate() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Audited source tables require row deletions; truncate would bypass their history'; END $$")
    for table in ('adjudications','financial_candidate_mappings','financial_candidate_reviews','financial_candidate_finalizations',
                  'financial_pdf_nominations','financial_ingestion_runs','financial_source_documents','financial_accounts',
                  'financial_statement_periods','financial_transactions','financial_statement_review_drafts','evidence_files',
                  'workspace_entries','workspace_entry_revisions','workspace_entry_links','workspace_entry_events',
                  'evidence_document_texts','evidence_table_geometry'):
        op.execute(f'CREATE TRIGGER refuse_unaudited_truncate BEFORE TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION refuse_audited_source_truncate()')


def downgrade():
    raise RuntimeError('Source/export audit coverage cannot be silently removed; restore an explicitly reviewed database backup instead.')
