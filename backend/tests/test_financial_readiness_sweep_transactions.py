"""The background readiness sweep holds no transaction open across its Python work.

Measured on live 31 Oct 02:45: one batch_rounds transaction stayed open 270-337 s inside refresh_stale_readiness
(pg_stat_activity + pg_locks), holding locks on financial_import_batches and its items, which made a release's
VACUUM FULL skip. Postgres runs READ COMMITTED, so the open transaction gave the sweep no consistency: each
statement reads its own snapshot either way. The sweep now reads with each statement committed on its own and
writes through the same locked, checked transaction as before.
"""
import os
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
from services.financial import import_batches as service
from tests import test_financial_import_batches as fixtures


@pytest.fixture
def stale():
    """A case whose batch item's stored readiness is out of date (a write without its own refresh)."""
    fixture = fixtures.BatchImportTests()
    fixture.setUp()
    try:
        batch = fixture.create()
        fixture.advance(batch)
        with patch.object(service, 'refresh_file_readiness'):
            fixture.f.confirm()
        yield SimpleNamespace(f=fixture.f, batch=batch)
    finally:
        fixture.tearDown()


def _isolation(session):
    return session.connection().get_execution_options().get('isolation_level')


def _record(calls):
    """Wrap the projection (the long Python work) and the checked write, recording each one's connection mode."""
    project, write = service._project_item, service._write_checked

    def projecting(session, *args, **kwargs):
        calls.append(('read', _isolation(session)))
        return project(session, *args, **kwargs)

    def writing(session, updates, apply):
        result = write(session, updates, apply)
        calls.append(('write', _isolation(session) if session.in_transaction() else 'committed', len(updates)))
        return result

    def locked_write(session, updates, apply):
        calls.append(('write-start', _isolation(session)))
        return writing(session, updates, apply)

    return patch.multiple(service, _project_item=projecting, _write_checked=locked_write)


def test_the_sweep_reads_outside_a_transaction_and_writes_inside_one(stale):
    calls = []
    with _record(calls):
        outcome = service.refresh_stale_readiness(stale.f.SessionLocal, budget_seconds=60)
    assert outcome[str(stale.f.case.id)]['refreshed'] == 1
    reads = [mode for kind, mode, *_ in calls if kind == 'read']
    writes = [mode for kind, mode, *_ in calls if kind == 'write-start']
    assert reads and set(reads) == {'AUTOCOMMIT'}
    assert writes and 'AUTOCOMMIT' not in writes
    with stale.f.SessionLocal() as db:
        item = db.scalar(select(Item).where(Item.batch_id == stale.batch))
        assert item.summary['readiness']['state'] == 'imported'


def test_other_callers_keep_one_transaction(stale):
    """Only the background sweep opts in; a request's refresh keeps its transaction as before."""
    calls = []
    with _record(calls), stale.f.SessionLocal() as db:
        service.refresh_case_readiness(db, case_id=stale.f.case.id)
    assert [mode for kind, mode, *_ in calls if kind == 'read'] and \
        'AUTOCOMMIT' not in [mode for kind, mode, *_ in calls]


@pytest.mark.skipif(os.getenv('LOUPE_TEST_LOCAL_POSTGRES') != '1', reason='Requires isolated local PostgreSQL')
def test_on_postgres_the_sweep_is_never_idle_in_transaction_during_its_work(stale, caplog):
    url = make_url(os.environ['LOUPE_TEST_LOCAL_POSTGRES_URL'])
    assert (url.host, url.database) == ('127.0.0.1', 'loupe_local')
    schema = 'readiness_sweep_' + uuid4().hex
    name = 'loupe-synthetic-readiness-' + uuid4().hex[:8]
    admin = create_engine(url, connect_args={'connect_timeout': 2})
    engine = create_engine(url, connect_args={'connect_timeout': 2, 'application_name': name,
        'options': '-csearch_path=' + schema + ' -cstatement_timeout=20000 -clock_timeout=5000'})
    names = set(inspect(stale.f.engine).get_table_names())
    from postgres.models.financial_judgements import FinancialJudgement
    from services.financial import judgements
    # The judgements table exists on live: the statement reader's model-work read runs inside the sweep's reads.
    tables = [table for table in Base.metadata.sorted_tables
              if table.name in names or table.name == FinancialJudgement.__tablename__]
    states, model_work = [], []
    view = judgements.statement_model_work_view

    def viewing(session, *args, **kwargs):
        model_work.append(_isolation(session))
        return view(session, *args, **kwargs)

    project = service._project_item

    def projecting(session, *args, **kwargs):
        result = project(session, *args, **kwargs)
        with admin.connect() as watcher:
            states.append(watcher.scalar(text('SELECT state FROM pg_stat_activity WHERE application_name = :n'),
                                         {'n': name}))
        return result

    try:
        with admin.begin() as db:
            db.execute(text('CREATE SCHEMA ' + schema))
        Base.metadata.create_all(engine, tables=tables)
        with stale.f.engine.connect() as source, engine.begin() as target:
            for table in tables:
                if table.name not in names:
                    continue
                rows = [dict(row) for row in source.execute(select(table)).mappings()]
                if rows:
                    target.execute(table.insert(), rows)
        with patch.object(service, '_project_item', projecting), \
                patch.object(judgements, 'statement_model_work_view', viewing):
            outcome = service.refresh_stale_readiness(sessionmaker(bind=engine, autoflush=False), budget_seconds=60)
        assert outcome[str(stale.f.case.id)]['refreshed'] == 1
        assert states and set(states) == {'idle'}, states
        # A savepoint is refused outside a transaction; the model-work read must not try one there.
        assert model_work and set(model_work) == {'AUTOCOMMIT'}, model_work
        assert not [r for r in caplog.records if 'model work' in r.getMessage()], caplog.text
        with engine.connect() as db:
            summary = db.scalar(select(Item.summary).where(Item.batch_id == stale.batch))
        assert summary['readiness']['state'] == 'imported'
    finally:
        engine.dispose()
        with admin.begin() as db:
            db.execute(text('DROP SCHEMA IF EXISTS ' + schema + ' CASCADE'))
        admin.dispose()
