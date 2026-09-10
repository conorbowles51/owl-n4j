"""Exercise audit migration, serialization and atomicity in a disposable PG schema.

Synthetic rows only. Existing local case fixtures and source files are untouched.
"""
import importlib.util
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError
from alembic.migration import MigrationContext
from alembic.operations import Operations
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from services.financial.audit_chain import capture_financial_audit_chain

engine = create_engine('postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local')
schema = 'audit_acceptance_' + uuid4().hex
case, other, mapping, candidate = uuid4(), uuid4(), uuid4(), uuid4()
path = Path(__file__).resolve().parents[1] / 'backend/postgres/alembic/versions/20260910_financial_audit_chain.py'
spec = importlib.util.spec_from_file_location('audit_migration',path)
migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
state_spec=importlib.util.spec_from_file_location('audit_states',path.with_name('20260910_audit_state_changes.py'))
state_migration=importlib.util.module_from_spec(state_spec);state_spec.loader.exec_module(state_migration)
source_spec=importlib.util.spec_from_file_location('audit_sources',path.with_name('20260910_audit_source_exports.py'))
source_migration=importlib.util.module_from_spec(source_spec);source_spec.loader.exec_module(source_migration)


def configure(connection):
    connection.execute(text(f'SET LOCAL search_path TO {schema}'))


def insert(connection, table='adjudications', scope=case, **fields):
    # All identifiers are fixed below; values are bound.
    values=dict(id=uuid4(),case_id=scope,reason='Synthetic audit acceptance',**fields)
    columns=','.join(values)
    placeholders=','.join(':'+key for key in values)
    connection.execute(text(f'INSERT INTO {table} ({columns}) VALUES ({placeholders})'),values)
    return values['id']

try:
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA {schema}'))
        configure(connection)
        for table in [item[0] for item in migration.TARGETS]+[item[0] for item in state_migration.TARGETS]:
            connection.execute(text(f'''CREATE TABLE {table} (id uuid PRIMARY KEY, case_id uuid,
              actor jsonb, actor_name text, actor_email text, actor_user_id uuid, outcome_actor jsonb,
              reason text, status text, candidate_id uuid, config jsonb, error text, notes text, started_by_user_id uuid, started_by_email text, stored_path text, metadata jsonb, last_error text, last_processed_profile_snapshot jsonb)'''))
        connection.execute(text('CREATE TABLE financial_extraction_candidates (id uuid PRIMARY KEY, mapping_id uuid NOT NULL)'))
        connection.execute(text('CREATE TABLE evidence_document_texts (evidence_file_id uuid PRIMARY KEY REFERENCES evidence_files(id) ON DELETE CASCADE, content text, content_sha256 text, processing_manifest jsonb)'))
        connection.execute(text('CREATE TABLE evidence_table_geometry (evidence_file_id uuid REFERENCES evidence_files(id) ON DELETE CASCADE, page_number integer, payload jsonb, PRIMARY KEY(evidence_file_id,page_number))'))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade();state_migration.upgrade();source_migration.upgrade()
    with engine.begin() as connection:
        configure(connection)
        with Session(bind=connection) as db:
            assert capture_financial_audit_chain(db,case_id=case)['entries']==[]
        insert(connection, actor_name='Synthetic reviewer',actor_email='nobody@example.invalid')
        connection.execute(text('INSERT INTO financial_candidate_mappings(id,case_id,actor,reason) VALUES (:id,:case,CAST(:actor AS jsonb),:reason)'),
            dict(id=mapping,case=case,actor='{"name":"Synthetic mapper"}',reason='Synthetic mapping'))
        connection.execute(text('INSERT INTO financial_extraction_candidates VALUES (:id,:mapping)'),dict(id=candidate,mapping=mapping))
        insert(connection,'financial_candidate_reviews',scope=None,candidate_id=candidate)
        insert(connection,'financial_candidate_finalizations')
        attempt=insert(connection,'financial_pdf_nominations',actor_name='Synthetic requester',status='pending')
        connection.execute(text("UPDATE financial_pdf_nominations SET status='completed', actor=CAST(:actor AS jsonb),outcome_actor=CAST(:outcome AS jsonb) WHERE id=:id"),
            dict(id=attempt,actor='{"name":"Requester"}',outcome='{"name":"Synthetic completer"}'))
        run=insert(connection,'financial_ingestion_runs',status='pending',error='PRIVATE_ERROR_MUST_NOT_EXPORT',notes='PRIVATE_NOTE_MUST_NOT_EXPORT')
        connection.execute(text("UPDATE financial_ingestion_runs SET status='completed' WHERE id=:id"),dict(id=run))
        connection.execute(text('UPDATE financial_ingestion_runs SET status=status WHERE id=:id'),dict(id=run))
        with Session(bind=connection) as db:
            capture=capture_financial_audit_chain(db,case_id=case)
            assert len(capture['entries'])==8
            assert 'PRIVATE_ERROR_MUST_NOT_EXPORT' not in str(capture) and 'PRIVATE_NOTE_MUST_NOT_EXPORT' not in str(capture)
            import json
            values=[json.loads(row['payload_text']) for row in capture['entries']]
            assert values[2]['case_id']==str(case) and values[2]['actor_basis']=='not_recorded'
            assert values[5]['actor']['name']=='Synthetic completer'
            assert values[7]['before']['status']=='pending' and values[7]['after']['status']=='completed'
    for sql in ('UPDATE financial_audit_events SET payload_text=payload_text','DELETE FROM financial_audit_events','TRUNCATE financial_audit_events','TRUNCATE financial_transactions','TRUNCATE evidence_files CASCADE',
                "INSERT INTO financial_audit_events VALUES (:case,999,repeat('0',64),repeat('0',64),'{}')"):
        try:
            with engine.begin() as connection:
                configure(connection);connection.execute(text(sql),dict(case=case))
        except DBAPIError: pass
        else:raise AssertionError('Audit mutation unexpectedly accepted')
    with engine.connect() as connection:
        transaction=connection.begin();configure(connection)
        insert(connection,scope=other)
        assert connection.scalar(text('SELECT count(*) FROM financial_audit_events WHERE case_id=:case'),dict(case=other))==1
        transaction.rollback()
    with engine.begin() as connection:
        configure(connection)
        assert connection.scalar(text('SELECT count(*) FROM financial_audit_events WHERE case_id=:case'),dict(case=other))==0
        connection.execute(text("ALTER TABLE financial_audit_events ADD CONSTRAINT injected_failure CHECK (payload_text NOT LIKE '%INJECTED_FAILURE%')"))
    try:
        with engine.begin() as connection:
            configure(connection);insert(connection,scope=other,actor_name='INJECTED_FAILURE')
    except DBAPIError: pass
    else:raise AssertionError('Injected audit failure was accepted')
    with engine.begin() as connection:
        configure(connection)
        assert connection.scalar(text('SELECT count(*) FROM adjudications WHERE case_id=:case'),dict(case=other))==0
        connection.execute(text('ALTER TABLE financial_audit_events DROP CONSTRAINT injected_failure'))
    def writer(index):
        with engine.begin() as connection:
            configure(connection)
            for _ in range(10):insert(connection,scope=other,actor_name=f'Synthetic concurrent writer {index}')
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(writer,range(2)))
    with engine.begin() as connection:
        configure(connection)
        with Session(bind=connection) as db:
            assert capture_financial_audit_chain(db,case_id=other)['verification']['event_count']==20
            assert capture_financial_audit_chain(db,case_id=case)['verification']['event_count']==8
    state_case=uuid4()
    with engine.begin() as connection:
        configure(connection)
        expected=0
        for table, operations in state_migration.TARGETS:
            identity=insert(connection,table,scope=state_case,stored_path='PRIVATE_LOCAL_PATH',last_error='PRIVATE_EVIDENCE_ERROR')
            expected+=1
            if 'UPDATE' in operations:
                connection.execute(text(f"UPDATE {table} SET status='changed' WHERE id=:id"),dict(id=identity));expected+=1
            if 'DELETE' in operations:
                connection.execute(text(f'DELETE FROM {table} WHERE id=:id'),dict(id=identity));expected+=1
        with Session(bind=connection) as db:
            captured=capture_financial_audit_chain(db,case_id=state_case)
            assert captured['verification']['event_count']==expected==26
            events=[json.loads(row['payload_text']) for row in captured['entries']]
            evidence=[event for event in events if event['source_table']=='evidence_files']
            assert 'PRIVATE_LOCAL_PATH' not in str(evidence) and 'PRIVATE_EVIDENCE_ERROR' not in str(evidence)
            assert evidence[-1]['before']['id'] and evidence[-1]['after'] is None
    from postgres.audit_context import set_authorized_audit_context
    from types import SimpleNamespace
    context_case,unrelated_case=uuid4(),uuid4()
    user=SimpleNamespace(id=uuid4(),name='Synthetic authorized operator',email='synthetic@example.invalid')
    with Session(engine) as db:
        db.execute(text(f'SET LOCAL search_path TO {schema}'))
        set_authorized_audit_context(db,case_id=context_case,user=user)
        insert(db.connection(),'financial_transactions',scope=context_case)
        db.commit()
        db.execute(text(f'SET LOCAL search_path TO {schema}'))
        insert(db.connection(),'financial_transactions',scope=context_case)
        insert(db.connection(),'financial_transactions',scope=unrelated_case)
        captured=capture_financial_audit_chain(db,case_id=context_case)
        assert len(captured['entries'])==2
        for entry in captured['entries']:
            value=json.loads(entry['payload_text'])
            assert value['actor_basis']=='authorized_request' and value['actor']['user_id']==str(user.id)
        assert json.loads(capture_financial_audit_chain(db,case_id=unrelated_case)['entries'][0]['payload_text'])['actor_basis']=='not_recorded'
        db.commit()
    with engine.begin() as connection:
        assert connection.scalar(text("SELECT current_setting('loupe.audit_context',true)")) in (None,'')
        configure(connection)
        identity=insert(connection,'financial_transactions',scope=context_case)
    try:
        with engine.begin() as connection:
            configure(connection)
            connection.execute(text('UPDATE financial_transactions SET case_id=:case WHERE id=:id'),dict(case=unrelated_case,id=identity))
    except DBAPIError:pass
    else:raise AssertionError('In-place case ownership change bypassed the audit boundary')
    source_case=uuid4()
    with engine.begin() as connection:
        configure(connection)
        source_file=insert(connection,'evidence_files',scope=source_case)
        connection.execute(text("INSERT INTO evidence_document_texts VALUES (:file,'PRIVATE_SOURCE_TEXT','recorded-hash',NULL)"),dict(file=source_file))
        connection.execute(text("UPDATE evidence_document_texts SET content='REPLACEMENT_SOURCE_TEXT' WHERE evidence_file_id=:file"),dict(file=source_file))
        connection.execute(text("INSERT INTO evidence_table_geometry VALUES (:file,1,'[]'::jsonb)"),dict(file=source_file))
        connection.execute(text("UPDATE evidence_table_geometry SET payload=CAST(:payload AS jsonb) WHERE evidence_file_id=:file"),dict(file=source_file,payload=json.dumps([{'synthetic':1}])))
        connection.execute(text('DELETE FROM evidence_files WHERE id=:file'),dict(file=source_file))
        with Session(bind=connection) as db:
            captured=capture_financial_audit_chain(db,case_id=source_case)
            assert captured['verification']['event_count']==8
            assert 'PRIVATE_SOURCE_TEXT' not in str(captured) and 'REPLACEMENT_SOURCE_TEXT' not in str(captured)
            events=[json.loads(entry['payload_text']) for entry in captured['entries']]
            assert {e['source_table'] for e in events[-3:]}=={'evidence_files','evidence_document_texts','evidence_table_geometry'}
            assert all(e['operation']=='DELETE' and e['after'] is None for e in events[-3:])
            import hashlib
            assert events[1]['after']['omitted_content_sha256']==hashlib.sha256(b'PRIVATE_SOURCE_TEXT').hexdigest()
    from services.financial.export_audit import record_prepared_export
    scoped_engine=create_engine('postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local',connect_args={'options':f'-csearch_path={schema}'})
    export_case=uuid4()
    try:
        receipt=record_prepared_export(scoped_engine,case_id=export_case,kind='ledger_exports',content=b'SYNTHETIC archive bytes',scope={'snapshot_sha256':'a'*64},actor={'id':str(user.id),'name':user.name,'email':user.email})
        with Session(scoped_engine) as db:
            captured=capture_financial_audit_chain(db,case_id=export_case)
            assert captured['verification']['event_count']==1 and captured['verification']['head_sha256']==receipt['entry_sha256']
            event=json.loads(captured['entries'][0]['payload_text'])
            assert event['source_id']==receipt['export_id']
            assert event['after']['artifact_sha256']==hashlib.sha256(b'SYNTHETIC archive bytes').hexdigest()
            assert event['after']['delivery_status']=='prepared_not_delivery_confirmed'
        with scoped_engine.begin() as connection:
            connection.execute(text("ALTER TABLE financial_audit_events ADD CONSTRAINT export_failure CHECK (payload_text NOT LIKE '%SYNTHETIC_EXPORT_FAIL%')"))
        try:
            record_prepared_export(scoped_engine,case_id=export_case,kind='trace_support_exports',content=b'SYNTHETIC archive bytes',scope={},actor={'id':str(user.id),'name':'SYNTHETIC_EXPORT_FAIL','email':user.email})
        except DBAPIError:pass
        else:raise AssertionError('Audit failure did not refuse prepared export')
        with Session(scoped_engine) as db:assert capture_financial_audit_chain(db,case_id=export_case)['verification']['event_count']==1
    finally:scoped_engine.dispose()
    print('PASS: prepared text and geometry replacements and cascading deletion; actual omitted-content hashes; prepared-export receipt bytes/actor/head and injected failure rollback.')
    print('PASS: ten additional state targets,26events; deletion before-state; private evidence fields excluded; authorized actor retained across commits, scoped to its case and cleared from pooled connections; in-place case ownership change refused.')
    print('PASS: all six trigger targets; exact hash verification; source-derived actor and before/after; no-op exclusion; update/delete/truncate/bad append refused; atomic rollback and injected-failure rollback; two concurrent writers, twenty ordered events; case isolation.')
finally:
    with engine.begin() as connection:connection.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
    engine.dispose()
print('Disposable schema removed; no existing case/source writes or external provider calls.')
