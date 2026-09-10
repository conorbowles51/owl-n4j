"""Chain new financial decisions, PDF review events and processing run changes.

No backfill: historical events are not asserted to have been witnessed by this log.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20260910_financial_audit_chain'
down_revision = '20260910_pdf_nominations'
branch_labels = None
depends_on = None

TARGETS = (
    ('adjudications', 'INSERT', 'direct'),
    ('financial_candidate_mappings', 'INSERT', 'direct'),
    ('financial_candidate_reviews', 'INSERT', 'candidate'),
    ('financial_candidate_finalizations', 'INSERT', 'direct'),
    ('financial_pdf_nominations', 'INSERT OR UPDATE', 'direct'),
    ('financial_ingestion_runs', 'INSERT OR UPDATE', 'direct'),
)


def upgrade():
    op.create_table('financial_audit_events',
        sa.Column('case_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('sequence', sa.BigInteger(), primary_key=True),
        sa.Column('previous_sha256', sa.String(64), nullable=False),
        sa.Column('entry_sha256', sa.String(64), nullable=False),
        sa.Column('payload_text', sa.Text(), nullable=False),
        sa.CheckConstraint('sequence > 0', name='ck_financial_audit_sequence'),
        sa.CheckConstraint('length(previous_sha256)=64 AND length(entry_sha256)=64', name='ck_financial_audit_hashes'))
    op.execute('''CREATE FUNCTION guard_financial_audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'Financial audit history is append-only'; END $$''')
    op.execute('CREATE TRIGGER financial_audit_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON financial_audit_events FOR EACH STATEMENT EXECUTE FUNCTION guard_financial_audit_immutable()')
    op.execute('''CREATE FUNCTION guard_financial_audit_insert() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE previous_hash text; next_sequence bigint; value jsonb;
    BEGIN
      PERFORM pg_advisory_xact_lock(hashtextextended('loupe.financial.audit:' || NEW.case_id::text, 0));
      SELECT sequence+1, entry_sha256 INTO next_sequence, previous_hash
        FROM financial_audit_events WHERE case_id=NEW.case_id ORDER BY sequence DESC LIMIT 1;
      next_sequence := COALESCE(next_sequence,1); previous_hash := COALESCE(previous_hash,repeat('0',64));
      value := NEW.payload_text::jsonb;
      IF NEW.sequence <> next_sequence OR NEW.previous_sha256 <> previous_hash
        OR NEW.entry_sha256 <> encode(sha256(decode(previous_hash,'hex') || convert_to(NEW.payload_text,'UTF8')),'hex')
        OR (value->>'case_id') IS DISTINCT FROM NEW.case_id::text
        OR (value->>'sequence') IS DISTINCT FROM NEW.sequence::text
        OR (value->>'schema_version') IS DISTINCT FROM 'loupe.financial.audit_event/1'
      THEN RAISE EXCEPTION 'Financial audit append is inconsistent'; END IF;
      RETURN NEW;
    END $$''')
    op.execute('CREATE TRIGGER financial_audit_insert BEFORE INSERT ON financial_audit_events FOR EACH ROW EXECUTE FUNCTION guard_financial_audit_insert()')
    op.execute('''CREATE FUNCTION capture_financial_audit_event() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
      current_row jsonb := to_jsonb(NEW);
      previous_row jsonb := NULL;
      audit_case uuid;
      previous_hash text;
      next_sequence bigint;
      payload text;
      recorded_actor jsonb;
      actor_basis text;
    BEGIN
      IF TG_OP = 'UPDATE' THEN
        previous_row := to_jsonb(OLD);
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
      payload := jsonb_build_object('schema_version','loupe.financial.audit_event/1',
        'case_id',audit_case::text,'sequence',next_sequence,
        'recorded_at',to_char(clock_timestamp() AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
        'source_table',TG_TABLE_NAME,'operation',TG_OP,'source_id',current_row->>'id',
        'database_principal',current_user,'transaction_id',txid_current()::text,
        'actor',recorded_actor,'actor_basis',actor_basis,
        'reason',current_row->>'reason','before',previous_row,'after',current_row)::text;
      INSERT INTO financial_audit_events(case_id,sequence,previous_sha256,entry_sha256,payload_text)
        VALUES(audit_case,next_sequence,previous_hash,
          encode(sha256(decode(previous_hash,'hex') || convert_to(payload,'UTF8')),'hex'),payload);
      RETURN NEW;
    END $$''')
    for table, operations, mode in TARGETS:
        op.execute(f"CREATE TRIGGER capture_financial_audit AFTER {operations} ON {table} FOR EACH ROW EXECUTE FUNCTION capture_financial_audit_event('{mode}')")


def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM financial_audit_events')).scalar_one():
        raise RuntimeError('Cannot downgrade while financial audit history exists.')
    for table, _, _ in TARGETS:
        op.execute(f'DROP TRIGGER capture_financial_audit ON {table}')
    op.drop_table('financial_audit_events')
    op.execute('DROP FUNCTION capture_financial_audit_event()')
    op.execute('DROP FUNCTION guard_financial_audit_immutable()')
    op.execute('DROP FUNCTION guard_financial_audit_insert()')
