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


FULL_RANGE_VIEWS = (('get_working_ledger_analysis', 'working'), ('get_ledger_posting_graph', 'graph'), ('get_counterparty_party_analysis', 'cpa'),
                    ('get_ledger_timeline', 'timeline'), ('get_ledger_transfer_candidates', 'transfers'),
                    ('get_pattern_review', 'patterns'))
PER_CASE = 15  # views warmed for each case


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
    monkeypatch.setattr(routers.financial_ledger, 'get_account_parties', lambda **kw: calls.append(dict(kw, view='parties')))
    monkeypatch.setattr(routers.financial_statement_import, 'account_types', lambda **kw: calls.append(dict(kw, view='types')))
    monkeypatch.setattr(routers.financial_ledger, 'get_account_consolidations',
                        lambda **kw: calls.append(dict(kw, view='consolidations')))
    monkeypatch.setattr(routers.financial_statement_import, 'list_financial_batches',
                        lambda **kw: calls.append(dict(kw, view='batches')))
    from services.financial import review_queue
    monkeypatch.setattr(review_queue, 'warm', lambda **kw: calls.append(dict(kw, view='queue')))
    for route, view in FULL_RANGE_VIEWS:
        monkeypatch.setattr(routers.financial_ledger, route, lambda view=view, **kw: calls.append(dict(kw, view=view)))

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
        (str(large), 'parties'), (str(large), 'types'), (str(large), 'consolidations'), (str(large), 'queue'),
        (str(large), 'batches'),
        (str(small), None), (str(small), 'transactions'), (str(small), 'files'), (str(small), 'evidence'),
        (str(small), 'parties'), (str(small), 'types'), (str(small), 'consolidations'), (str(small), 'queue'),
        (str(small), 'batches'),
        # The full-range analyses in a second pass, after every case's views above (the release warm-up's cap).
        (str(large), 'working'), (str(large), 'graph'), (str(large), 'cpa'), (str(large), 'timeline'),
        (str(large), 'transfers'), (str(large), 'patterns'),
        (str(small), 'working'), (str(small), 'graph'), (str(small), 'cpa'), (str(small), 'timeline'),
        (str(small), 'transfers'), (str(small), 'patterns')]
    # The batch list takes only the case, as a UUID (FastAPI's type for it): the same cached-view key.
    assert {key: value for key, value in calls[8].items() if key != 'db'} == dict(case_id=large, view='batches')
    # The three account views take only the case: the same cached-view key as a first visit.
    assert {key for key in calls[4] if key != 'db'} == {'case_id', 'view'}
    assert calls[3]['case_id'] == str(large)  # as text, as FastAPI gives the evidence listing
    assert {key: value for key, value in calls[0].items() if key != 'db'} == dict(
        case_id=large, account_id=None, account_ids=None, account_holders=None, start_date=None, end_date=None)
    assert {key: value for key, value in calls[1].items() if key != 'db'} == dict(
        case_id=large, source_document_id=None, account_id=None, ledger_status=None, start_date=None, end_date=None,
        account_ids=None, account_holders=None, view='transactions')


@needs_pg
def test_the_full_range_views_get_the_routes_own_defaults(periods):
    # The page asks these with grouping=counterparty (working analysis), population=working, window_days=3, tolerance_days=3, cross_account=false and no
    # dates or accounts: each route's own defaults. Any other value would warm a key no first visit asks for.
    import inspect
    import routers.financial_ledger as ledger
    add, calls, _ = periods
    case = uuid.uuid4()
    add(case, 1)
    paths = dict(working='/ledger-working-analysis', graph='/ledger-posting-graph', cpa='/counterparty-party-analysis', timeline='/ledger-timeline',
                 transfers='/ledger-transfer-candidates', patterns='/pattern-review')
    # The endpoints FastAPI serves (the fixture replaced the module's names).
    served = {route.path.rsplit('/financial', 1)[-1]: route.endpoint for route in ledger.router.routes
              if 'GET' in getattr(route, 'methods', ())}
    routes = {view: served[path] for view, path in paths.items()}
    view_warmup.warm_account_history()
    by_view = {call['view']: call for call in calls if call.get('view') in routes}
    assert set(by_view) == set(routes)
    for view, route in routes.items():
        expected = {name: getattr(parameter.default, 'default', parameter.default)
                    for name, parameter in inspect.signature(inspect.unwrap(route)).parameters.items()
                    if name not in ('case_id', 'db')}
        if view == 'working':
            expected['grouping'] = 'counterparty'  # the counterparty tab's first request: grouping=counterparty
        assert {key: value for key, value in by_view[view].items() if key not in ('db', 'view', 'case_id')} == expected, view
        assert by_view[view]['case_id'] == case
    assert by_view['timeline']['population'] == 'working' and by_view['patterns']['window_days'] == 3
    assert by_view['transfers']['tolerance_days'] == 3 and by_view['patterns']['cross_account'] is False


@needs_pg
def test_a_views_own_refusal_counts_as_warmed_and_other_errors_as_failed(periods, monkeypatch):
    from fastapi import HTTPException
    import routers.financial_ledger
    add, calls, _ = periods
    add(uuid.uuid4(), 1)

    def refuses(**kw):
        raise HTTPException(status_code=422, detail='More than 1,000 payments match these filters.')

    def breaks(**kw):
        raise HTTPException(status_code=500, detail='broken')
    monkeypatch.setattr(routers.financial_ledger, 'get_ledger_timeline', refuses)
    monkeypatch.setattr(routers.financial_ledger, 'get_pattern_review', breaks)
    monkeypatch.setattr(view_warmup, '_migrations_pending', lambda: '')
    summary = view_warmup.prepare(processes=1)
    assert summary.startswith('prepare: %d views warmed in ' % (PER_CASE - 1)) and '(1 failed, 1 processes, code ' in summary


@needs_pg
def test_only_one_worker_warms_at_a_time(periods):
    add, calls, directory = periods
    add(uuid.uuid4(), 1)
    with open(directory / 'warmup.lock', 'a') as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        view_warmup.warm_account_history()
    assert calls == []
    view_warmup.warm_account_history()
    assert len(calls) == PER_CASE  # the views of one case


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
    assert sorted(str(call['case_id']) for call in calls) == sorted([str(first)] * PER_CASE + [str(second)] * PER_CASE)
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


@needs_pg
def test_prepare_warms_every_view_and_reports_it(periods, monkeypatch):
    add, calls, _ = periods
    add(uuid.uuid4(), 1)
    monkeypatch.setattr(view_warmup, '_migrations_pending', lambda: '')
    summary = view_warmup.prepare(processes=1)
    assert len(calls) == PER_CASE
    assert summary.startswith('prepare: %d views warmed in ' % PER_CASE) and '(0 failed, 1 processes, code ' in summary


@needs_pg
def test_prepare_computes_nothing_while_migrations_are_pending(periods, monkeypatch):
    add, calls, _ = periods
    add(uuid.uuid4(), 1)
    monkeypatch.setattr(view_warmup, '_migrations_pending', lambda: 'abc123')
    assert view_warmup.prepare() == 'prepare: skipped, database migrations pending (abc123)'
    assert calls == []


@needs_pg
def test_prepare_does_not_wait_for_the_old_services_warm_up_but_for_another_prepare(periods, monkeypatch):
    import threading
    add, calls, directory = periods
    add(uuid.uuid4(), 1)
    monkeypatch.setattr(view_warmup, '_migrations_pending', lambda: '')
    with open(directory / 'warmup.lock', 'a') as old_service:
        fcntl.flock(old_service, fcntl.LOCK_EX)
        beside = []
        runner = threading.Thread(target=lambda: beside.append(view_warmup.prepare(processes=1)), daemon=True)
        runner.start()
        runner.join(30)
        assert beside and beside[0].startswith('prepare: %d views warmed' % PER_CASE)
    calls.clear()
    held = open(directory / view_warmup.PREPARE_LOCK, 'a')
    fcntl.flock(held, fcntl.LOCK_EX)
    done = []
    worker = threading.Thread(target=lambda: done.append(view_warmup.prepare(processes=1)))
    worker.start()
    worker.join(1.0)
    assert done == [] and calls == []
    held.close()
    worker.join(30)
    assert len(calls) == PER_CASE and done[0].startswith('prepare: %d views warmed' % PER_CASE)


@needs_pg
def test_split_shares_warm_every_view_exactly_once(periods):
    add, calls, _ = periods
    first, second = uuid.uuid4(), uuid.uuid4()
    add(first, 2); add(second, 1)
    totals = [view_warmup._warm_cases(share=(share, 3)) for share in range(3)]
    assert sum(warmed for warmed, _ in totals) == 2 * PER_CASE
    seen = sorted((str(call['case_id']), call.get('view') or 'history') for call in calls)
    assert len(seen) == 2 * PER_CASE and len(set(seen)) == 2 * PER_CASE


def test_prepare_splits_over_child_processes_and_sums_them(monkeypatch, tmp_path):
    import subprocess
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path))
    monkeypatch.setattr(view_warmup, '_migrations_pending', lambda: '')
    started = []

    class Child:
        def __init__(self, argv, **kw):
            started.append(argv)
            self.returncode = 0 if len(started) < 3 else 1

        def communicate(self):
            return ('INFO x\nshare 4 1\n' if self.returncode == 0 else ''), None
    monkeypatch.setattr(subprocess, 'Popen', Child)
    summary = view_warmup.prepare(processes=3)
    assert [argv[-2:] for argv in started] == [[view_warmup.SHARE_FLAG, '%d/3' % k] for k in range(3)]
    assert summary.startswith('prepare: 8 views warmed in ') and '(3 failed, 3 processes, code ' in summary


def test_prepare_never_raises(monkeypatch, tmp_path):
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path))

    def broken():
        raise RuntimeError('synthetic')
    monkeypatch.setattr(view_warmup, '_migrations_pending', broken)
    assert view_warmup.prepare().startswith('prepare: failed after ')


def test_the_migration_check_reads_the_code_heads(monkeypatch):
    # The real check against this tree's migrations, with a database that is at no revision at all.
    from alembic.runtime import migration
    monkeypatch.setattr(migration.MigrationContext, 'get_current_heads', lambda self: ())
    import postgres.session

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False
    monkeypatch.setattr(postgres.session, '_get_engine', lambda: type('E', (), dict(connect=lambda self: Connection()))())
    monkeypatch.setattr(migration.MigrationContext, 'configure', classmethod(lambda cls, connection: cls.__new__(cls)))
    assert view_warmup._migrations_pending() != ''


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


@needs_pg
def test_a_real_cached_views_refusal_warmed_here_is_answered_from_its_saved_copy(periods, monkeypatch):
    # End to end: the route -> cached_view keeps its 422 and saves it -> the warm-up counts it; a later request in
    # a process that has nothing in memory gets the same refusal from the saved copy, without computing.
    from fastapi import HTTPException
    from sqlalchemy.orm import Session
    import postgres.session
    import routers.financial_ledger
    from services.financial import view_cache
    add, calls, directory = periods
    case = uuid.uuid4()
    add(case, 1)
    engine = postgres.session._get_session_local()().get_bind()
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE payments (id serial PRIMARY KEY, case_id uuid NOT NULL)'))
        connection.execute(text('INSERT INTO payments (case_id) SELECT :c FROM generate_series(1, 3)'), dict(c=case))
    computed = []

    @view_cache.cached_view('ledger-timeline')
    def timeline(case_id, db, **kw):
        computed.append(case_id)
        count = db.execute(text('SELECT count(*) FROM payments WHERE case_id = :c'), dict(c=case_id)).scalar()
        raise HTTPException(status_code=422, detail=f'More than {count - 1} payments match these filters.')
    monkeypatch.setattr(routers.financial_ledger, 'get_ledger_timeline', timeline)
    monkeypatch.setattr(view_cache, 'SAVE_MIN_SECONDS', 0.0)
    view_cache.clear()
    view_cache._tables_cache.clear()
    try:
        warmed, failed = view_warmup._warm_cases()
        assert (warmed, failed) == (PER_CASE, 0) and len(computed) == 1
        view_cache.clear()  # as a new process: only the saved copy is left
        hits = view_cache.stats['saved_hits']
        with Session(engine) as db, pytest.raises(HTTPException) as refusal:
            timeline(case_id=case, account_id=None, start_date=None, end_date=None, population='working',
                     account_ids=None, account_holders=None, db=db)
        assert (refusal.value.status_code, refusal.value.detail) == (422, 'More than 2 payments match these filters.')
        assert view_cache.stats['saved_hits'] == hits + 1 and len(computed) == 1
    finally:
        view_cache.clear()
        view_cache._tables_cache.clear()
