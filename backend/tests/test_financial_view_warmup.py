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
needs_pg = pytest.mark.skipif(not URL, reason='Requires an explicit local PostgreSQL test connection')


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
    monkeypatch.setattr(routers.financial_ledger, 'get_ledger_transactions', lambda **kw: calls.append(dict(kw, view='transactions')))
    import routers.financial_statement_import
    monkeypatch.setattr(routers.financial_statement_import, 'files', lambda **kw: calls.append(dict(kw, view='files')))
    import routers.evidence
    monkeypatch.setattr(routers.evidence, 'list_evidence', lambda **kw: calls.append(dict(kw, view='evidence')))

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


@needs_pg
def test_every_case_is_warmed_largest_first_with_the_routes_defaults(periods):
    add, calls, _ = periods
    small, large = uuid.uuid4(), uuid.uuid4()
    add(small, 1); add(large, 3)
    view_warmup.warm_account_history()
    assert [(str(call['case_id']), call.get('view')) for call in calls] == [
        (str(large), None), (str(large), 'transactions'), (str(large), 'files'), (str(large), 'evidence'),
        (str(small), None), (str(small), 'transactions'), (str(small), 'files'), (str(small), 'evidence')]
    assert calls[3]['case_id'] == str(large)  # as text, as FastAPI gives the evidence listing
    assert {key: value for key, value in calls[0].items() if key != 'db'} == dict(
        case_id=large, account_id=None, account_ids=None, account_holders=None, start_date=None, end_date=None)
    assert {key: value for key, value in calls[1].items() if key != 'db'} == dict(
        case_id=large, source_document_id=None, account_id=None, ledger_status=None, start_date=None, end_date=None,
        account_ids=None, account_holders=None, view='transactions')


@needs_pg
def test_only_one_worker_warms_at_a_time(periods):
    add, calls, directory = periods
    add(uuid.uuid4(), 1)
    with open(directory / 'warmup.lock', 'a') as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        view_warmup.warm_account_history()
    assert calls == []
    view_warmup.warm_account_history()
    assert len(calls) == 4


@needs_pg
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
    assert [str(call['case_id']) for call in calls] == [str(first)] * 4 + [str(second)] * 4
    calls.clear()
    monkeypatch.setattr(process_shutdown, 'requested', type('Set', (), dict(is_set=lambda self: True))())
    view_warmup.warm_account_history()
    assert calls == []


@needs_pg
def test_off_when_the_memo_directory_is_off(periods, monkeypatch):
    add, calls, _ = periods
    add(uuid.uuid4(), 1)
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', '')
    view_warmup.warm_account_history()
    assert calls == []


# The warm-up runs in a child process so the worker does not keep its memory. No database needed below.
import asyncio
import sys


@pytest.fixture
def memo_dir(tmp_path, monkeypatch):
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path))
    monkeypatch.setattr(view_warmup, 'WARM_DELAY_SECONDS', 0)
    return tmp_path


def test_the_warm_up_runs_in_a_child_process_holding_the_lock(memo_dir, monkeypatch):
    seen = memo_dir / 'seen'
    script = ("import fcntl, os, sys; lock = open(sys.argv[1] + '/warmup.lock', 'a')\n"
              "try:\n    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); held = 'free'\n"
              "except OSError:\n    held = 'held'\n"
              "open(sys.argv[1] + '/seen', 'w').write(f'{os.getpid()} {held} {sys.argv[2]}')")
    monkeypatch.setattr(view_warmup, '_child_command',
                        lambda: [sys.executable, '-c', script, str(memo_dir), view_warmup.CHILD_FLAG])
    asyncio.run(view_warmup.warm_views_once())
    pid, held, flag = seen.read_text().split()
    assert int(pid) != os.getpid() and held == 'held' and flag == view_warmup.CHILD_FLAG
    assert view_warmup._take_lock() is not None  # released once the child has finished


def test_no_child_while_another_worker_warms(memo_dir, monkeypatch):
    started = []
    monkeypatch.setattr(view_warmup, '_child_command', lambda: started.append(1) or [sys.executable, '-c', ''])
    with open(memo_dir / 'warmup.lock', 'a') as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        asyncio.run(view_warmup.warm_views_once())
    assert started == []


def test_stopping_the_worker_stops_the_child(memo_dir, monkeypatch):
    pid_file = memo_dir / 'pid'
    script = "import os, sys, time; open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(600)"
    monkeypatch.setattr(view_warmup, '_child_command', lambda: [sys.executable, '-c', script, str(pid_file)])

    async def run():
        task = asyncio.create_task(view_warmup.warm_views_once())
        for _ in range(200):
            await asyncio.sleep(0.05)
            if pid_file.exists() and pid_file.read_text():
                break
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    pid = int(pid_file.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    assert view_warmup._take_lock() is not None


def test_the_child_ends_when_its_worker_is_killed(tmp_path):
    """A worker killed outright (no cancel) must not leave its warm-up child running without the lock."""
    import subprocess
    import time
    pid_file = tmp_path / 'child'
    worker = ("import asyncio, sys; sys.path.insert(0, sys.argv[2])\n"
              "from services.financial import view_warmup as w\n"
              "w._child_command = lambda: [sys.executable, '-c', \"import os, sys, time; open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(600)\", sys.argv[1]]\n"
              "asyncio.run(w._run_child())")
    import pathlib
    backend = str(pathlib.Path(view_warmup.__file__).resolve().parents[2])
    process = subprocess.Popen([sys.executable, '-c', worker, str(pid_file), backend], cwd=backend)
    for _ in range(600):
        if pid_file.exists() and pid_file.read_text():
            break
        time.sleep(0.1)
    child = int(pid_file.read_text())
    process.kill(); process.wait()
    for _ in range(50):
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        os.kill(child, 9)
        raise AssertionError('the warm-up child outlived its killed worker')


def test_the_warm_up_passes_every_route_parameter_with_the_value_fastapi_gives_a_first_visit(monkeypatch):
    """The cached-view key is every parameter but db: a missing or different one would warm another key."""
    import inspect
    import routers.financial_ledger
    import routers.financial_statement_import
    calls = []
    import routers.evidence
    routes = dict(get_account_history=routers.financial_ledger, get_ledger_transactions=routers.financial_ledger,
                  files=routers.financial_statement_import, list_evidence=routers.evidence)
    # What the Financial page asks for where it does not use the route's defaults.
    page = dict(list_evidence=dict(include_reading_versions=True, financial_only=True))
    for name, module in routes.items():
        route = getattr(module, name)
        expected = {}
        for parameter in inspect.signature(route).parameters.values():
            if parameter.name in ('case_id', 'db'):
                continue
            default = getattr(parameter.default, 'default', parameter.default)  # Query(None) -> None
            expected[parameter.name] = default
        calls.append((name, {**expected, **page.get(name, {})}))
    seen = {}

    class Session:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_bind(self):
            return type('Bind', (), dict(dialect=type('Dialect', (), dict(name='postgresql'))()))()

        def execute(self, *args, **kwargs):
            return [('case', 1)]
    import postgres.session
    monkeypatch.setattr(postgres.session, '_get_session_local', lambda: Session)
    for name, _ in calls:
        monkeypatch.setattr(routes[name], name,
                            lambda _name=name, **kw: seen.setdefault(_name, {k: v for k, v in kw.items() if k not in ('db', 'case_id')}))
    view_warmup._warm_cases()
    assert seen == dict(calls)


def test_view_reuse_and_warm_up_lines_reach_the_service_journal():
    """Under uvicorn the root logger has no handler, so a plain module logger's INFO lines were dropped in the
    workers: the journal could not say whether a slow first load computed or reused a view."""
    import logging
    from services.financial import view_cache
    for module in (view_cache, view_warmup):
        assert module.logger.isEnabledFor(logging.INFO)
        assert any(getattr(handler, '_loupe_journal', False) for handler in module.logger.handlers)
