"""The release re-check sweeps compare a prepared file without holding a database transaction open.

Measured on live 31 Oct 12:12-12:17, after the 12:00 release: one batch_rounds transaction 256 s old while the
sweeps compared prepared files with the new reader. Postgres runs READ COMMITTED, so the open transaction gave the
comparison no consistency; it held the vacuum horizon (those sessions carry backend_xmin) and the read tables'
locks. Each comparison's reads now run each in their own transaction, and a write inside it is refused rather than
committed at once.
"""
import logging
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
from services.financial import held_reprepare as held
from services.financial import read_only_session, reader_release
from tests import test_financial_held_reprepare as held_tests
from tests import test_financial_reader_release as release_tests


def _isolation(session):
    return session.connection().get_execution_options().get('isolation_level')


@pytest.fixture
def released():
    """A file prepared by an older reader; the current reader reads it differently (reader_release 'changed')."""
    fixture = release_tests.ReaderReleaseTests('test_a_statement_waiting_for_a_reader_fix_becomes_ready_after_the_release_with_no_click')
    fixture.setUp()
    try:
        yield SimpleNamespace(f=fixture.f, batch=fixture.prepare_with_old_reader(), fixture=fixture)
    finally:
        fixture.tearDown()
        fixture.doCleanups()


@pytest.fixture
def held_file():
    """A held statement prepared by an earlier backend reader (held_reprepare judges it 'changed')."""
    fixture = held_tests.HeldReprepareTests('test_a_held_statement_the_revision_does_not_see_becomes_ready_after_the_deploy_with_no_click')
    fixture.setUp()
    try:
        yield SimpleNamespace(f=fixture.f, batch=fixture.prepare(), fixture=fixture)
    finally:
        fixture.tearDown()
        fixture.doCleanups()


def _recording_comparison(modes):
    compare = reader_release.reading_changed

    def comparing(session, **kwargs):
        modes.append(_isolation(session))
        return compare(session, **kwargs)
    return patch.object(reader_release, 'reading_changed', comparing)


def _recording_judge(modes):
    judge = held.judge

    def judging(session, *args, **kwargs):
        modes.append(_isolation(session))
        return judge(session, *args, **kwargs)
    return patch.object(held, 'judge', judging)


def test_the_release_comparison_reads_outside_a_transaction_with_the_same_verdict(released):
    modes = []
    with _recording_comparison(modes):
        outcome = reader_release.sweep(released.f.SessionLocal)
    assert modes == ['AUTOCOMMIT']
    assert (outcome['compared'], outcome['rechecked']) == (1, 1)
    assert released.fixture.files(released.batch)[0]['status'] == 'processing'


def test_the_held_judgement_reads_outside_a_transaction_with_the_same_verdict(held_file):
    modes = []
    with _recording_judge(modes):
        outcome = held.sweep(held_file.f.SessionLocal)
    assert modes == ['AUTOCOMMIT']
    assert outcome['verdicts'] == {'changed': 1}
    assert held_file.fixture.files(held_file.batch)[0][held.MARK]['state'] == held.PENDING


def test_a_write_inside_the_comparison_is_refused_and_nothing_is_written(released, caplog):
    """Under autocommit a flush would commit at once (before, the comparison's rollback discarded it)."""
    compare = reader_release.reading_changed

    def writing(session, *, items, **kwargs):
        items[0].status = 'tampered'
        session.flush()
        return compare(session, items=items, **kwargs)

    with released.f.SessionLocal() as db:
        before = db.scalar(select(Item.status).where(Item.batch_id == released.batch))
    with patch.object(reader_release, 'reading_changed', writing), caplog.at_level(logging.ERROR):
        outcome = reader_release.sweep(released.f.SessionLocal)
    assert (outcome['compared'], outcome['rechecked']) == (0, 0)
    assert 'nothing was written' in caplog.text
    with released.f.SessionLocal() as db:
        assert db.scalar(select(Item.status).where(Item.batch_id == released.batch)) == before
    # The file is still stale, so the next sweep compares it again.
    assert reader_release.sweep(released.f.SessionLocal)['rechecked'] == 1


def test_a_write_inside_a_held_judgement_leaves_no_mark_and_is_judged_again(held_file, caplog):
    """A refused write is not a verdict: no 'left' mark is recorded, and the next sweep judges the file."""
    judge = held.judge

    def writing(session, case_id, source_id, *args, **kwargs):
        item = session.scalar(select(Item).where(Item.batch_id == held_file.batch))
        item.status = 'tampered'
        session.flush()
        return judge(session, case_id, source_id, *args, **kwargs)

    with patch.object(held, 'judge', writing), caplog.at_level(logging.ERROR):
        outcome = held.sweep(held_file.f.SessionLocal)
    assert outcome['verdicts'] == {}
    assert 'nothing was written' in caplog.text
    assert held.MARK not in held_file.fixture.files(held_file.batch)[0]
    assert [i.status for i in held_file.fixture.items(held_file.batch)] == ['attention']
    assert held.sweep(held_file.f.SessionLocal)['verdicts'] == {'changed': 1}


def test_the_switch_off_keeps_the_old_transaction(released):
    modes = []
    with patch.object(read_only_session, 'ENABLED', False), _recording_comparison(modes):
        outcome = reader_release.sweep(released.f.SessionLocal)
    assert modes and 'AUTOCOMMIT' not in modes
    assert (outcome['compared'], outcome['rechecked']) == (1, 1)


@pytest.mark.skipif(os.getenv('LOUPE_TEST_LOCAL_POSTGRES') != '1', reason='Requires isolated local PostgreSQL')
@pytest.mark.parametrize('sweep', ['reader_release', 'held_reprepare'])
def test_on_postgres_the_comparison_is_never_idle_in_transaction(sweep, request, caplog):
    case = request.getfixturevalue('released' if sweep == 'reader_release' else 'held_file')
    url = make_url(os.environ['LOUPE_TEST_LOCAL_POSTGRES_URL'])
    assert (url.host, url.database) == ('127.0.0.1', 'loupe_local')
    schema = 'sweep_reads_' + uuid4().hex
    name = 'loupe-synthetic-sweep-' + uuid4().hex[:8]
    admin = create_engine(url, connect_args={'connect_timeout': 2})
    engine = create_engine(url, connect_args={'connect_timeout': 2, 'application_name': name,
        'options': '-csearch_path=' + schema + ' -cstatement_timeout=20000 -clock_timeout=5000'})
    source_engine = case.f.SessionLocal.kw['bind']
    names = set(inspect(source_engine).get_table_names())
    from postgres.models.financial_judgements import FinancialJudgement
    # The judgements table exists on live: the statement reader's model-work read runs inside the comparison.
    tables = [table for table in Base.metadata.sorted_tables
              if table.name in names or table.name == FinancialJudgement.__tablename__]
    from services.financial import statement_import
    reader = statement_import.read_statement_import
    states = []

    def reading(session, *args, **kwargs):
        result = reader(session, *args, **kwargs)
        with admin.connect() as watcher:
            states.extend(watcher.scalars(text('SELECT state FROM pg_stat_activity WHERE application_name = :n'),
                                          {'n': name}))
        return result

    try:
        with admin.begin() as db:
            db.execute(text('CREATE SCHEMA ' + schema))
        Base.metadata.create_all(engine, tables=tables)
        with source_engine.connect() as source, engine.begin() as target:
            for table in tables:
                if table.name not in names:
                    continue
                rows = [dict(row) for row in source.execute(select(table)).mappings()]
                if rows:
                    target.execute(table.insert(), rows)
        factory = sessionmaker(bind=engine, autoflush=False)
        with patch.object(statement_import, 'read_statement_import', reading), caplog.at_level(logging.WARNING):
            if sweep == 'reader_release':
                outcome = reader_release.sweep(factory)
                assert (outcome['compared'], outcome['rechecked']) == (1, 1)
            else:
                outcome = held.sweep(factory)
                assert outcome['verdicts'] == {'changed': 1}
        assert states and 'idle in transaction' not in states, states
        # A savepoint is refused outside a transaction: nothing on the comparison's path may log a failed read.
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING], caplog.text
    finally:
        engine.dispose()
        with admin.begin() as db:
            db.execute(text('DROP SCHEMA IF EXISTS ' + schema + ' CASCADE'))
        admin.dispose()
