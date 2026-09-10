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
        for table, _, _ in migration.TARGETS:
            connection.execute(text(f'''CREATE TABLE {table} (id uuid PRIMARY KEY, case_id uuid,
              actor jsonb, actor_name text, actor_email text, actor_user_id uuid, outcome_actor jsonb,
              reason text, status text, candidate_id uuid, config jsonb, error text, notes text, started_by_user_id uuid, started_by_email text)'''))
        connection.execute(text('CREATE TABLE financial_extraction_candidates (id uuid PRIMARY KEY, mapping_id uuid NOT NULL)'))
        with Operations.context(MigrationContext.configure(connection)): migration.upgrade()
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
    for sql in ('UPDATE financial_audit_events SET payload_text=payload_text','DELETE FROM financial_audit_events','TRUNCATE financial_audit_events',
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
    print('PASS: all six trigger targets; exact hash verification; source-derived actor and before/after; no-op exclusion; update/delete/truncate/bad append refused; atomic rollback and injected-failure rollback; two concurrent writers, twenty ordered events; case isolation.')
finally:
    with engine.begin() as connection:connection.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
    engine.dispose()
print('Disposable schema removed; no existing case/source writes or external provider calls.')
