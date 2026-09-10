"""Retain prospective processing/merge/recovery records, not inferred graph commits."""
from alembic import op
revision='20260910_audit_graph_jobs'
down_revision='20260910_audit_source_exports'
branch_labels=None
depends_on=None
TARGETS=('jobs','merge_jobs','graph_recycle_bin_items','rejected_merge_pairs')


def upgrade():
    op.execute('''CREATE FUNCTION capture_graph_processing_audit() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE current_row jsonb; previous_row jsonb; audit_case uuid; private_fields text[];
      private_values jsonb; context jsonb; actor jsonb; actor_basis text := 'not_recorded';
    BEGIN
      current_row:=CASE WHEN TG_OP='DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
      previous_row:=CASE WHEN TG_OP IN ('UPDATE','DELETE') THEN to_jsonb(OLD) ELSE NULL END;
      IF TG_OP='UPDATE' THEN
        IF current_row->>'case_id' IS DISTINCT FROM previous_row->>'case_id' THEN
          RAISE EXCEPTION 'Audited job and recovery records cannot change case ownership in place';
        END IF;
        IF current_row=previous_row THEN RETURN NEW; END IF;
        IF TG_TABLE_NAME='jobs' AND (current_row - ARRAY['progress','updated_at'])=(previous_row - ARRAY['progress','updated_at']) THEN RETURN NEW; END IF;
      END IF;
      BEGIN audit_case:=(current_row->>'case_id')::uuid;
      EXCEPTION WHEN invalid_text_representation THEN
        -- The engine historically accepts non-case labels. They are outside
        -- the relational case audit scope, never assigned a fabricated UUID.
        IF TG_TABLE_NAME='jobs' THEN RETURN NEW; ELSE RAISE; END IF;
      END;
      IF audit_case IS NULL THEN
        IF TG_TABLE_NAME='jobs' THEN RETURN NEW; ELSE RAISE EXCEPTION 'Graph audit record has no case'; END IF;
      END IF;
      private_fields:=CASE TG_TABLE_NAME
        WHEN 'jobs' THEN ARRAY['file_path','file_name','merge_payload','llm_profile','folder_context','sibling_files','effective_context','effective_mandatory_instructions','effective_special_entity_types','document_summary','transcription','transcription_segments','pipeline_state','quality_report','error_message']
        WHEN 'merge_jobs' THEN ARRAY['error_message']
        WHEN 'graph_recycle_bin_items' THEN ARRAY['snapshot']
        ELSE ARRAY[]::text[] END;
      IF cardinality(private_fields)>0 THEN
        SELECT COALESCE(jsonb_object_agg(key,value),'{}'::jsonb) INTO private_values FROM jsonb_each(current_row) WHERE key=ANY(private_fields);
        current_row:=(current_row-private_fields)||jsonb_build_object('omitted_fields',private_fields,'omitted_fields_sha256',encode(sha256(convert_to(private_values::text,'UTF8')),'hex'));
        IF previous_row IS NOT NULL THEN
          SELECT COALESCE(jsonb_object_agg(key,value),'{}'::jsonb) INTO private_values FROM jsonb_each(previous_row) WHERE key=ANY(private_fields);
          previous_row:=(previous_row-private_fields)||jsonb_build_object('omitted_fields',private_fields,'omitted_fields_sha256',encode(sha256(convert_to(private_values::text,'UTF8')),'hex'));
        END IF;
      END IF;
      context:=NULLIF(current_setting('loupe.audit_context',true),'')::jsonb;
      IF context->>'case_id'=audit_case::text THEN actor:=context->'actor';actor_basis:='authorized_request';
      ELSIF current_row->>'requested_by_user_id' IS NOT NULL THEN
        actor:=jsonb_build_object('requested_by_user_id',current_row->>'requested_by_user_id');actor_basis:='recorded_requester_not_worker_identity';
      ELSIF current_row->>'rejected_by_user_id' IS NOT NULL THEN
        actor:=jsonb_build_object('rejected_by_user_id',current_row->>'rejected_by_user_id');actor_basis:='recorded_rejector_not_update_actor';
      END IF;
      PERFORM append_financial_audit_event(audit_case,jsonb_build_object(
        'capture_policy','20260910_audit_graph_jobs','source_table',TG_TABLE_NAME,'source_id',current_row->>'id',
        'operation',TG_OP,'actor',actor,'actor_basis',actor_basis,'reason',current_row->>'reason',
        'before',previous_row,'after',CASE WHEN TG_OP='DELETE' THEN NULL ELSE current_row END,
        'limitation','Recorded PostgreSQL job, merge decision or recovery state; not proof of an atomic Neo4j/PostgreSQL commit or the actual graph contents. Private execution inputs and recovery snapshots are represented by a digest.'));
      IF TG_OP='DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END $$''')
    for table in TARGETS:
        op.execute(f'CREATE TRIGGER capture_graph_processing_audit AFTER INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION capture_graph_processing_audit()')
        op.execute(f'CREATE TRIGGER refuse_unaudited_truncate BEFORE TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION refuse_audited_source_truncate()')


def downgrade():
    raise RuntimeError('Processing/merge audit coverage cannot be silently removed; restore an explicitly reviewed database backup instead.')
