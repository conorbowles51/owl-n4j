"""The account-history warm-up after a start: one worker, every case largest first, through the route itself.

Opt-in PostgreSQL checks (FINANCIAL_VIEW_CACHE_TEST_DATABASE_URL, a disposable schema per test)."""
import fcntl
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from services import process_shutdown
from services.financial import view_warmup

URL = os.environ.get('FINANCIAL_VIEW_CACHE_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires an explicit local PostgreSQL test connection')


@pytest.fixture
def periods(tmp_path, monkeypatch):
    admin = create_engine(URL)
    schema = 'view_warmup_test_' + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(URL, connect_args={'options': f'-csearch_path={schema}'})
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE financial_statement_periods (id serial PRIMARY KEY, case_id uuid NOT NULL)'))
    import postgres.session
    monkeypatch.setattr(postgres.session, '_get_session_local', lambda: sessionmaker(bind=engine))
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path))
    calls = []
    import routers.financial_ledger
    monkeypatch.setattr(routers.financial_ledger, 'get_account_history', lambda **kw: calls.append(kw))

    def add(case, count):
        with engine.begin() as connection:
            for _ in range(count):
                connection.execute(text('INSERT INTO financial_statement_periods (case_id) VALUES (:c)'), dict(c=case))
    try:
        yield add, calls, tmp_path
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_every_case_is_warmed_largest_first_with_the_routes_defaults(periods):
    add, calls, _ = periods
    small, large = uuid.uuid4(), uuid.uuid4()
    add(small, 1); add(large, 3)
    view_warmup.warm_account_history()
    assert [call['case_id'] for call in calls] == [large, small]
    assert {key: value for key, value in calls[0].items() if key != 'db'} == dict(
        case_id=large, account_id=None, account_ids=None, account_holders=None, start_date=None, end_date=None)


def test_only_one_worker_warms_at_a_time(periods):
    add, calls, directory = periods
    add(uuid.uuid4(), 1)
    with open(directory / 'warmup.lock', 'a') as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        view_warmup.warm_account_history()
    assert calls == []
    view_warmup.warm_account_history()
    assert len(calls) == 1


def test_a_failing_case_does_not_stop_the_others_and_shutdown_stops_the_rest(periods, monkeypatch):
    add, calls, _ = periods
    first, second = uuid.uuid4(), uuid.uuid4()
    add(first, 2); add(second, 1)
    import routers.financial_ledger

    def failing(**kw):
        calls.append(kw)
        if kw['case_id'] == first:
            raise RuntimeError('synthetic failure')
    monkeypatch.setattr(routers.financial_ledger, 'get_account_history', failing)
    view_warmup.warm_account_history()
    assert [call['case_id'] for call in calls] == [first, second]
    calls.clear()
    monkeypatch.setattr(process_shutdown, 'requested', type('Set', (), dict(is_set=lambda self: True))())
    view_warmup.warm_account_history()
    assert calls == []


def test_off_when_the_memo_directory_is_off(periods, monkeypatch):
    add, calls, _ = periods
    add(uuid.uuid4(), 1)
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', '')
    view_warmup.warm_account_history()
    assert calls == []
