"""The account-history warm-up after a start: one worker, every case largest first, through the route itself.

Opt-in PostgreSQL checks (FINANCIAL_VIEW_CACHE_TEST_DATABASE_URL, a disposable schema per test)."""
import fcntl
import json
import os
import time
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from services import process_shutdown
from services.financial import view_warmup

URL = os.environ.get('FINANCIAL_VIEW_CACHE_TEST_DATABASE_URL')
needs_pg = pytest.mark.skipif(not URL, reason='Requires an explicit local PostgreSQL test connection')


SUMMARY_VIEWS = (('get_ledger_summary', 'summary'), ('get_working_ledger_summary', 'working-summary'))
FULL_RANGE_VIEWS = (('get_working_ledger_analysis', 'working'), ('get_ledger_posting_graph', 'graph'), ('get_counterparty_party_analysis', 'cpa'),
                    ('get_ledger_timeline', 'timeline'), ('get_ledger_transfer_candidates', 'transfers'),
                    ('get_pattern_review', 'patterns'))
PER_CASE = 29  # views warmed for each case
GRAPH = {}  # the graph database's last commit as the tests set it (never a real graph database)


def _stub_every_view(monkeypatch, calls):
    """Every view the warm-up computes, recording its call instead: a view missing here runs for real in the tests."""
    import routers.financial_ledger
    monkeypatch.setattr(routers.financial_ledger, 'get_account_history', lambda **kw: calls.append(kw))
    monkeypatch.setattr(routers.financial_ledger, 'get_ledger_transactions', lambda **kw: calls.append(dict(kw, view='transactions')))
    monkeypatch.setattr(routers.financial_ledger, 'get_ledger_overview', lambda **kw: calls.append(dict(kw, view='overview')))
    monkeypatch.setattr(routers.financial_ledger, 'get_ledger_overview_panels', lambda **kw: calls.append(dict(kw, view='panels')))
    monkeypatch.setattr(routers.financial_ledger, 'get_ledger_overview_panel_figures',
                        lambda **kw: calls.append(dict(kw, view='panel-figures')))
    monkeypatch.setattr(routers.financial_ledger, 'get_ledger_first_view', lambda **kw: calls.append(dict(kw, view='first-view')))
    monkeypatch.setattr(routers.financial_ledger, 'get_ledger_trends_view', lambda **kw: calls.append(dict(kw, view='trends')))
    monkeypatch.setattr(routers.financial_ledger, 'get_ledger_people_view', lambda **kw: calls.append(dict(kw, view='people')))
    import routers.financial_statement_import
    monkeypatch.setattr(routers.financial_statement_import, 'files', lambda **kw: calls.append(dict(kw, view='files')))
    import routers.evidence
    monkeypatch.setattr(routers.evidence, 'list_evidence', lambda **kw: calls.append(dict(kw, view='evidence')))
    monkeypatch.setattr(routers.evidence, 'list_statement_register', lambda **kw: calls.append(dict(kw, view='register')))
    monkeypatch.setattr(routers.financial_ledger, 'get_account_parties', lambda **kw: calls.append(dict(kw, view='parties')))
    monkeypatch.setattr(routers.financial_statement_import, 'account_types', lambda **kw: calls.append(dict(kw, view='types')))
    monkeypatch.setattr(routers.financial_ledger, 'get_account_consolidations',
                        lambda **kw: calls.append(dict(kw, view='consolidations')))
    monkeypatch.setattr(routers.financial_statement_import, 'list_financial_batches',
                        lambda **kw: calls.append(dict(kw, view='batches')))
    from services.financial import review_queue
    monkeypatch.setattr(review_queue, 'warm', lambda **kw: calls.append(dict(kw, view='queue')))
    from services.financial import batch_import_history
    monkeypatch.setattr(batch_import_history, 'warm', lambda **kw: calls.append(dict(kw, view='receipts')))
    for route, view in SUMMARY_VIEWS + FULL_RANGE_VIEWS:
        monkeypatch.setattr(routers.financial_ledger, route, lambda view=view, **kw: calls.append(dict(kw, view=view)))
    # The graph records read (its own saved copies, graph_read_cache); never a real graph database here.
    import routers.financial
    monkeypatch.setattr(routers.financial, 'get_financial_transactions',
                        lambda **kw: calls.append(dict(kw, view='graph-' + kw['mode'])))
    # The Graph and Timeline pages' saved responses (graph_response_cache); never a real graph database here.
    import routers.graph
    import routers.timeline
    monkeypatch.setattr(routers.graph, 'warm_graph_page', lambda **kw: calls.append(dict(kw, view='graph-page')))
    monkeypatch.setattr(routers.timeline, 'warm_timeline_page', lambda **kw: calls.append(dict(kw, view='timeline-page')))


class _NoDatabaseSession:
    """One case to warm and no database: for the checks that need no PostgreSQL."""

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
    # The pass takes its write counts through _get_engine (view_warmup._counts_now): the same disposable schema, never
    # whatever DATABASE_URL the environment holds (unset: no counts, so no pass was recorded).
    monkeypatch.setattr(postgres.session, '_get_engine', lambda: engine)
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path))
    calls = []
    _stub_every_view(monkeypatch, calls)
    GRAPH['now'] = ['FB:1']
    monkeypatch.setattr(view_warmup, '_graph_now', lambda: GRAPH['now'] and list(GRAPH['now']))

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
        (str(large), None), (str(large), 'transactions'), (str(large), 'overview'), (str(large), 'panels'), (str(large), 'panel-figures'),
        (str(large), 'first-view'), (str(large), 'trends'), (str(large), 'files'), (str(large), 'evidence'), (str(large), 'register'),
        (str(large), 'parties'), (str(large), 'people'), (str(large), 'types'), (str(large), 'consolidations'), (str(large), 'queue'), (str(large), 'receipts'),
        (str(large), 'batches'), (str(large), 'summary'), (str(large), 'working-summary'),
        (str(large), 'graph-transactions'), (str(large), 'graph-intelligence'),
        (str(large), 'graph-page'), (str(large), 'timeline-page'),
        (str(small), None), (str(small), 'transactions'), (str(small), 'overview'), (str(small), 'panels'), (str(small), 'panel-figures'),
        (str(small), 'first-view'), (str(small), 'trends'), (str(small), 'files'), (str(small), 'evidence'), (str(small), 'register'),
        (str(small), 'parties'), (str(small), 'people'), (str(small), 'types'), (str(small), 'consolidations'), (str(small), 'queue'), (str(small), 'receipts'),
        (str(small), 'batches'), (str(small), 'summary'), (str(small), 'working-summary'),
        (str(small), 'graph-transactions'), (str(small), 'graph-intelligence'),
        (str(small), 'graph-page'), (str(small), 'timeline-page'),
        # The full-range analyses in a second pass, after every case's views above (the release warm-up's cap).
        (str(large), 'working'), (str(large), 'graph'), (str(large), 'cpa'), (str(large), 'timeline'),
        (str(large), 'transfers'), (str(large), 'patterns'),
        (str(small), 'working'), (str(small), 'graph'), (str(small), 'cpa'), (str(small), 'timeline'),
        (str(small), 'transfers'), (str(small), 'patterns')]
    # The batch list takes only the case, as a UUID (FastAPI's type for it): the same cached-view key.
    assert {key: value for key, value in calls[16].items() if key != 'db'} == dict(case_id=large, view='batches')
    # The three account views take only the case: the same cached-view key as a first visit.
    assert {key for key in calls[10] if key != 'db'} == {'case_id', 'view'}
    assert calls[8]['case_id'] == str(large)  # as text, as FastAPI gives the evidence listing
    assert {key: value for key, value in calls[9].items() if key != 'db'} == dict(case_id=str(large), view='register')
    # The graph records as a first visit asks for them (case as text, every filter unset): the same cached-view key.
    assert {key: value for key, value in calls[19].items() if key != 'db'} == dict(
        case_id=str(large), mode='transactions', types=None, start_date=None, end_date=None, categories=None,
        view='graph-transactions')
    # The Graph and Timeline pages' reads take only the case; each builds the route's own key (routers.graph/timeline).
    assert [{key: value for key, value in calls[index].items() if key != 'db'} for index in (21, 22)] == [
        dict(case_id=large, view='graph-page'), dict(case_id=large, view='timeline-page')]
    assert {key: value for key, value in calls[0].items() if key != 'db'} == dict(
        case_id=large, account_id=None, account_ids=None, account_holders=None, start_date=None, end_date=None)
    assert {key: value for key, value in calls[1].items() if key != 'db'} == dict(
        case_id=large, source_document_id=None, account_id=None, ledger_status=None, start_date=None, end_date=None,
        account_ids=None, account_holders=None, view='transactions')
    # The Overview's top card as a first visit asks for it: the transactions' defaults and no categories.
    assert {key: value for key, value in calls[2].items() if key != 'db'} == dict(
        case_id=large, source_document_id=None, account_id=None, ledger_status=None, start_date=None, end_date=None,
        account_ids=None, account_holders=None, categories=None, view='overview')
    # Its lower panels likewise.
    assert {key: value for key, value in calls[3].items() if key != 'db'} == dict(
        case_id=large, source_document_id=None, account_id=None, ledger_status=None, start_date=None, end_date=None,
        account_ids=None, account_holders=None, categories=None, view='panels')
    # What the Overview asks for first: the same key as the panels', counted (the same cached-view key as a visit).
    assert {key: value for key, value in calls[4].items() if key != 'db'} == dict(
        case_id=large, source_document_id=None, account_id=None, ledger_status=None, start_date=None, end_date=None,
        account_ids=None, account_holders=None, categories=None, view='panel-figures')
    # The Transactions page's first view as a first visit asks for it: the first page at the table's default size.
    assert {key: value for key, value in calls[5].items() if key != 'db'} == dict(
        case_id=large, source_document_id=None, account_id=None, ledger_status=None, start_date=None, end_date=None,
        page=0, page_size=50, account_ids=None, account_holders=None, view='first-view')
    # The Trends and People & businesses pages' answers as each opens: every group, period and category unset.
    assert {key: value for key, value in calls[6].items() if key != 'db'} == dict(
        case_id=large, source_document_id=None, account_id=None, ledger_status=None, start_date=None, end_date=None,
        group=None, earlier_start=None, earlier_end=None, later_start=None, later_end=None, account_ids=None,
        account_holders=None, categories=None, view='trends')
    assert {key: value for key, value in calls[11].items() if key != 'db'} == dict(
        case_id=large, source_document_id=None, account_id=None, ledger_status=None, start_date=None, end_date=None,
        group=None, account_ids=None, account_holders=None, categories=None, view='people')


@needs_pg
def test_the_full_range_views_get_the_routes_own_defaults(periods):
    # The page asks these with grouping=counterparty (working analysis), population=working, window_days=3, tolerance_days=3, cross_account=false and no
    # dates or accounts: each route's own defaults. Any other value would warm a key no first visit asks for.
    import inspect
    import routers.financial_ledger as ledger
    add, calls, _ = periods
    case = uuid.uuid4()
    add(case, 1)
    paths = dict(summary='/ledger-summary', **{'working-summary': '/ledger-working-summary'},
                 working='/ledger-working-analysis', graph='/ledger-posting-graph', cpa='/counterparty-party-analysis', timeline='/ledger-timeline',
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
        if view in ('summary', 'working-summary'):
            expected['include_contributions'] = True  # LedgerSummaryPanel asks include_contributions=true
        if view == 'graph':
            expected['label_origins'] = False  # LedgerPostingGraph asks label_origins=false
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
def test_a_pass_is_due_only_after_a_write_to_a_table_its_views_read(periods, monkeypatch):
    # The real child path: a cached view reads `payments`; the pass records it with its write count. A write
    # elsewhere starts no pass, a write to `payments` does (after REWARM_MIN_SECONDS), a running prepare holds it.
    import time as clock
    from fastapi import HTTPException
    import postgres.session
    import routers.financial_ledger
    from services.financial import view_cache
    add, calls, directory = periods
    case = uuid.uuid4()
    add(case, 1)
    engine = postgres.session._get_session_local()().get_bind()
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE payments (id serial PRIMARY KEY, case_id uuid NOT NULL)'))
        connection.execute(text('CREATE TABLE notes (id serial PRIMARY KEY)'))
        connection.execute(text('INSERT INTO payments (case_id) VALUES (:c)'), dict(c=case))

    @view_cache.cached_view('ledger-timeline')
    def timeline(case_id, db, **kw):
        return dict(count=db.execute(text('SELECT count(*) FROM payments WHERE case_id = :c'), dict(c=case_id)).scalar())
    monkeypatch.setattr(routers.financial_ledger, 'get_ledger_timeline', timeline)
    monkeypatch.setattr(postgres.session, '_get_engine', lambda: engine)

    def write(sql):
        with engine.connect() as connection:
            connection.execute(text(sql), dict(c=case))
            connection.commit()
            connection.execute(text('SELECT pg_stat_force_next_flush()'))
        with engine.connect() as connection:  # a statement after the flush request flushes the counts
            connection.execute(text('SELECT 1'))
        clock.sleep(1.2)
    write('SELECT 1')  # the setup's writes reach the statistics before the pass takes its counts
    view_cache.clear()
    view_cache._tables_cache.clear()
    view_cache.tables_read.clear()
    try:
        assert view_warmup._rewarm_due() is False  # no pass recorded yet
        view_warmup.warm_account_history(lock_held=True)
        state = json.loads((directory / view_warmup.REWARM_STATE).read_text())
        assert state['tables'] == ['payments'] and set(state['counts']) == {'payments'}
        later = clock.time() + view_warmup.REWARM_MIN_SECONDS + 1
        assert view_warmup._rewarm_due(now=later) is False  # nothing written
        write('INSERT INTO notes DEFAULT VALUES')
        assert view_warmup._rewarm_due(now=later) is False  # a table no view read
        write('INSERT INTO payments (case_id) VALUES (:c)')
        assert view_warmup._rewarm_due(now=clock.time()) is False  # too soon after the last pass
        # (This test changed the environment, which the identity includes: the code on disk is pinned as unchanged.)
        monkeypatch.setattr(view_cache, '_identity_now', lambda: view_cache.code_identity())
        assert view_warmup._rewarm_due(now=later) is True
        # A backend running from its tree sees no new code on disk: the release says so.
        staged = os.path.join(view_cache._memo_dir(), '.release-staged')
        monkeypatch.setattr(view_warmup, 'RELEASE_STAGED', staged)
        open(staged, 'w').close()
        assert view_warmup._rewarm_due(now=later) is False
        ancient = clock.time() - view_warmup.RELEASE_STAGED_MAX_AGE_SECONDS - 1
        os.utime(staged, (ancient, ancient))
        assert view_warmup._rewarm_due(now=later) is True  # a killed release left it behind
        os.unlink(staged)
        monkeypatch.setattr(view_cache, '_identity_now', lambda: 'the next release, written to disk')
        assert view_warmup._rewarm_due(now=later) is False  # this process's code is about to be replaced
        monkeypatch.setattr(view_cache, '_identity_now', lambda: view_cache.code_identity())
        with open(directory / view_warmup.PREPARE_LOCK, 'a') as preparing:
            fcntl.flock(preparing, fcntl.LOCK_EX)
            assert view_warmup._rewarm_due(now=later) is False  # a release is preparing
    finally:
        view_cache.clear()
        view_cache._tables_cache.clear()


@needs_pg
def test_a_graph_commit_since_the_last_pass_starts_a_pass(periods, monkeypatch):
    """The pass reads the graph records (graph_read_cache, saved per graph commit): a graph write with no
    PostgreSQL write must still have them read again before a person opens the tab."""
    from services.financial import view_cache
    add, calls, directory = periods
    add(uuid.uuid4(), 1)
    monkeypatch.setattr(view_cache, '_identity_now', lambda: view_cache.code_identity())
    view_cache.clear()
    view_cache.tables_read.add('financial_statement_periods')
    try:
        view_warmup.warm_account_history(lock_held=True)
        state = json.loads((directory / view_warmup.REWARM_STATE).read_text())
        assert state['graph'] == ['FB:1']
        later = time.time() + view_warmup.REWARM_MIN_SECONDS + 1
        assert view_warmup._rewarm_due(now=later) is False  # nothing committed anywhere
        GRAPH['now'] = None
        assert view_warmup._rewarm_due(now=later) is False  # graph state unknown: no pass on doubt
        GRAPH['now'] = ['FB:2']
        assert view_warmup._rewarm_due(now=later) is True
    finally:
        view_cache.clear()
        view_cache.tables_read.discard('financial_statement_periods')


@needs_pg
def test_the_after_start_pass_stops_when_a_release_starts_preparing(periods):
    add, calls, directory = periods
    add(uuid.uuid4(), 1)
    with open(directory / view_warmup.PREPARE_LOCK, 'a') as preparing:
        fcntl.flock(preparing, fcntl.LOCK_EX)
        view_warmup.warm_account_history(lock_held=True)
    assert calls == [] and not (directory / view_warmup.REWARM_STATE).exists()
    view_warmup.warm_account_history(lock_held=True)
    assert len(calls) == PER_CASE


def test_a_staged_release_counts_until_its_mark_is_too_old(tmp_path, monkeypatch):
    staged = tmp_path / '.release-staged'
    monkeypatch.setattr(view_warmup, 'RELEASE_STAGED', str(staged))
    assert view_warmup._release_staged() is False
    staged.touch()
    assert view_warmup._release_staged() is True
    ancient = time.time() - view_warmup.RELEASE_STAGED_MAX_AGE_SECONDS - 1
    os.utime(staged, (ancient, ancient))
    assert view_warmup._release_staged() is False


def test_the_staged_mark_is_read_beside_the_trees():
    # services/financial/view_warmup.py in <trees>/<tree>/backend: deploy/backend-tree.sh writes <trees>/.release-staged
    assert view_warmup.RELEASE_STAGED.endswith(os.path.join('financial', '..', '..', '..', '..', '.release-staged'))


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


@needs_pg
def test_a_process_takes_every_task_no_other_process_took(periods, tmp_path):
    # Live 2026-11-02 05:06: with every third task fixed per process, one process computed 581 s of views while
    # another sat idle from 05:13:14 and the unit was stopped at its cap. A process now takes whatever is left.
    add, calls, _ = periods
    first, second = uuid.uuid4(), uuid.uuid4()
    add(first, 2); add(second, 1)
    claims = str(tmp_path / 'claims')
    assert view_warmup._warm_cases(share=(0, 3), claims=claims) == (2 * PER_CASE, 0)
    assert view_warmup._warm_cases(share=(1, 3), claims=claims) == (0, 0)  # nothing left for a second process
    assert view_warmup._claimed_counts(claims) == (2 * PER_CASE, 2 * PER_CASE, 2 * PER_CASE, 0)
    seen = [(str(call['case_id']), call.get('view') or 'history') for call in calls]
    assert len(seen) == len(set(seen)) == 2 * PER_CASE


@needs_pg
def test_no_view_is_started_after_the_deadline(periods, monkeypatch):
    add, calls, _ = periods
    add(uuid.uuid4(), 1)
    assert view_warmup._warm_cases(deadline=time.time() - 1) == (0, 0) and calls == []
    monkeypatch.setattr(view_warmup, '_migrations_pending', lambda: '')
    monkeypatch.setattr(view_warmup, '_prepare_cap', lambda: 0)
    summary = view_warmup.prepare(processes=1)
    assert summary.startswith('prepare: 0 views warmed in ') and 'stopped at the 0 s limit' in summary


def _fake_children(monkeypatch, events, running=False, statuses=(0, 0, 1)):
    """subprocess.Popen replaced by children that write ``events`` to the prepare's claims file and either end with
    ``statuses`` or (``running``) never end."""
    import subprocess
    started, killed = [], []

    class Child:
        def __init__(self, argv, **kw):
            started.append(argv)
            self.index = len(started) - 1
            claims = argv[argv.index(view_warmup.CLAIMS_FLAG) + 1]
            with open(claims, 'a') as shared:
                shared.write(''.join(line + '\n' for line in events[self.index]))
            self.returncode = None if running else statuses[self.index]

        def poll(self):
            return self.returncode

        def kill(self):
            killed.append(self.index)
            self.returncode = -9

        def wait(self):
            return self.returncode
    monkeypatch.setattr(subprocess, 'Popen', Child)
    return started, killed


def test_prepare_splits_over_child_processes_and_sums_them(monkeypatch, tmp_path):
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path))
    monkeypatch.setattr(view_warmup, '_migrations_pending', lambda: '')
    events = [['total 9'] + ['claim a%d' % k, 'warmed a%d' % k] + (['claim f', 'failed f'] if k == 0 else [])
              for k in range(3)]
    started, _ = _fake_children(monkeypatch, events)
    summary = view_warmup.prepare(processes=3)
    assert [argv[3:5] for argv in started] == [[view_warmup.SHARE_FLAG, '%d/3' % k] for k in range(3)]
    assert all(view_warmup.DEADLINE_FLAG in argv for argv in started)
    # Counted from the shared claims file; the child that ended with an error counts as one failure.
    assert summary.startswith('prepare: 3 views warmed in ') and '(2 failed, 3 processes, code ' in summary
    assert 'limit' not in summary


def test_a_prepare_at_its_time_limit_stops_its_children_and_says_what_was_not_warmed(monkeypatch, tmp_path):
    # Live 2026-11-02 05:16:57 (release 33501a69): the unit was killed at its 600 s cap with ~221 of 240 views warmed
    # and the release log said only 'ended without a summary'.
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path))
    events = [['total 10', 'claim a', 'warmed a', 'claim b'], ['total 10', 'claim c', 'warmed c'], ['total 10']]
    _, killed = _fake_children(monkeypatch, events, running=True)
    warmed, failed, stopped = view_warmup._warm_in_processes(3, deadline=time.time() - view_warmup.PREPARE_MARGIN_SECONDS)
    assert killed == [0, 1, 2] and (warmed, failed) == (2, 0)
    assert stopped.startswith('stopped at the %d s limit: 8 of 10 views not warmed (7 not reached, 1 stopped while '
                              'computing)' % view_warmup._prepare_cap())
    monkeypatch.setattr(view_warmup, '_migrations_pending', lambda: '')
    monkeypatch.setattr(view_warmup, '_prepare_cap', lambda: 0)  # the deadline has passed when the children start
    _fake_children(monkeypatch, events, running=True)
    summary = view_warmup.prepare(processes=3)
    assert summary.startswith('prepare: 2 views warmed in ') and '8 of 10 views not warmed' in summary


def test_the_prepare_stops_inside_the_units_cap_counted_from_the_releases_start(monkeypatch, tmp_path):
    from services.financial import view_prepare
    assert view_warmup._prepare_cap() == view_prepare.PREPARE_CAP_SECONDS
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path))
    monkeypatch.setattr(view_warmup, '_migrations_pending', lambda: '')
    deadlines = []
    monkeypatch.setattr(view_warmup, '_warm_in_processes', lambda processes, deadline: deadlines.append(deadline) or (0, 0, None))
    released = time.time() - 7  # the unit was started 7 s before this process entered prepare()
    monkeypatch.setenv(view_warmup.STARTED_ENV, '%.3f' % released)
    view_warmup.prepare(processes=3)
    assert abs(deadlines[-1] - (released + view_prepare.PREPARE_CAP_SECONDS - view_warmup.PREPARE_MARGIN_SECONDS)) < 0.01
    # Children are stopped half the margin after the deadline: still inside the cap.
    assert deadlines[-1] + view_warmup.PREPARE_MARGIN_SECONDS / 2 < released + view_prepare.PREPARE_CAP_SECONDS
    monkeypatch.delenv(view_warmup.STARTED_ENV)  # run by hand: start-up is assumed to have used the allowance
    view_warmup.prepare(processes=3)
    assert deadlines[-1] <= time.time() + view_prepare.PREPARE_CAP_SECONDS - view_warmup.PREPARE_MARGIN_SECONDS \
        - view_warmup.STARTUP_ALLOWANCE_SECONDS + 1


def test_a_prepare_that_finished_every_view_after_the_deadline_is_not_reported_stopped(monkeypatch, tmp_path):
    events = [['total 3', 'claim a', 'warmed a'], ['total 3', 'claim b', 'warmed b'], ['total 3', 'claim c', 'warmed c']]
    _fake_children(monkeypatch, events, statuses=(0, 0, 0))
    assert view_warmup._warm_in_processes(3, deadline=time.time() - 1) == (3, 0, None)
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path))
    monkeypatch.setattr(view_warmup, '_migrations_pending', lambda: '')
    monkeypatch.setenv(view_warmup.STARTED_ENV, '%.3f' % (time.time() - 1000))  # the deadline has passed
    _fake_children(monkeypatch, events, statuses=(0, 0, 0))
    summary = view_warmup.prepare(processes=3)
    assert summary.startswith('prepare: 3 views warmed in ') and 'limit' not in summary


def test_claims_give_each_task_to_one_process_and_record_the_outcome(tmp_path):
    claims = str(tmp_path / 'claims')
    assert view_warmup._claim(claims, 'case-1 history []', 3)
    assert not view_warmup._claim(claims, 'case-1 history []', 3)  # another process took it
    assert view_warmup._claim(claims, 'case-1 files []', 3)
    view_warmup._note(claims, 'warmed', 'case-1 history []')
    assert view_warmup._claimed_counts(claims) == (3, 2, 1, 0)
    assert open(claims).read().count('total 3') == 1


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
    monkeypatch.setenv('FINANCIAL_VIEW_REWARM', '0')  # the first pass only; the re-warm loop has its own tests
    monkeypatch.setattr(view_warmup, 'WARM_DELAY_SECONDS', 0)
    return tmp_path


def test_after_the_first_pass_a_child_runs_again_only_when_a_pass_is_due(memo_dir, monkeypatch):
    monkeypatch.setenv('FINANCIAL_VIEW_REWARM', '1')
    monkeypatch.setattr(view_warmup, 'REWARM_CHECK_SECONDS', 0)
    runs, answers = [], iter([False, True, False, True])

    async def child():
        runs.append(view_warmup._take_lock() is None)  # the lock is held while a child runs

    def due():
        try:
            return next(answers)
        except StopIteration:
            raise asyncio.CancelledError
    monkeypatch.setattr(view_warmup, '_run_child', child)
    monkeypatch.setattr(view_warmup, '_rewarm_due', due)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(view_warmup.warm_views_once())
    assert runs == [True, True, True]  # the first pass, then the two checks that found a pass due


def test_no_re_warm_check_while_another_worker_holds_the_lock(memo_dir, monkeypatch):
    monkeypatch.setenv('FINANCIAL_VIEW_REWARM', '1')
    monkeypatch.setattr(view_warmup, 'REWARM_CHECK_SECONDS', 0)
    checks = []

    async def child():
        pass

    def due():
        checks.append(1)
        raise asyncio.CancelledError
    monkeypatch.setattr(view_warmup, '_run_child', child)
    monkeypatch.setattr(view_warmup, '_rewarm_due', due)
    calls = []
    real_sleep = asyncio.sleep

    async def sleep(seconds):
        calls.append(seconds)
        if len(calls) == 3:
            raise asyncio.CancelledError
        await real_sleep(0)
    monkeypatch.setattr(view_warmup.asyncio, 'sleep', sleep)
    with open(memo_dir / 'warmup.lock', 'a') as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(view_warmup.warm_views_once())
    assert checks == []


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

    import postgres.session
    monkeypatch.setattr(postgres.session, '_get_session_local', lambda: _NoDatabaseSession)
    for name, _ in calls:
        monkeypatch.setattr(routes[name], name,
                            lambda _name=name, **kw: seen.setdefault(_name, {k: v for k, v in kw.items() if k not in ('db', 'case_id')}))
    view_warmup._warm_cases()
    assert seen == dict(calls)


def test_the_stubs_and_the_count_cover_every_view_the_warm_up_computes(tmp_path, monkeypatch):
    """Runs without PostgreSQL: the checks that do are opt-in, so a view added to the warm-up without a stub ran for
    real in them and failed there unseen (29 views, 2 failed, on 5 Nov 2026 with the count at 25)."""
    calls = []
    _stub_every_view(monkeypatch, calls)
    import postgres.session
    monkeypatch.setattr(postgres.session, '_get_session_local', lambda: _NoDatabaseSession)
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path))
    assert view_warmup._warm_cases() == (PER_CASE, 0)
    assert len(calls) == PER_CASE


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


@needs_pg
def test_every_view_the_warm_up_computes_is_saved_however_fast(periods, monkeypatch):
    # Live 2026-10-31 15:12, 49494305: four views the release prepare computed in under SAVE_MIN_SECONDS were not
    # saved, and the first visitor after the restart waited 1.4-2.2 s for each.
    import routers.financial_ledger
    from services.financial import view_cache
    add, calls, _ = periods
    add(uuid.uuid4(), 1)
    seen = []

    def summary(**kw):
        seen.append(view_cache.always_save.get())
    monkeypatch.setattr(routers.financial_ledger, 'get_working_ledger_summary', summary)
    monkeypatch.setattr(view_warmup, '_migrations_pending', lambda: '')
    view_warmup.prepare(processes=1)
    assert seen == [True]
    # Only inside the warm-up: a person's request after it saves only slow views, as before.
    assert view_cache.always_save.get() is False


def test_a_fast_view_computed_with_always_save_is_written_to_disk(tmp_path, monkeypatch):
    from services.financial import view_cache
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path))
    monkeypatch.setattr(view_cache, 'code_identity', lambda: 'code-a')
    monkeypatch.setattr(view_cache, '_raise_high_water', lambda directory, xmax: None)
    entry = view_cache._Entry(('financial_transactions',), (('financial_transactions', 1, 'x'),), b'{}', 200,
                              'application/json', seconds=0.05, computed_at=time.time())
    scope = dict(format=1, database='db', code='code-a')
    key = ('ledger-working-summary', json.dumps(dict(case_id='c1')))
    view_cache._save_if_slow(key, entry, scope, 10, time.perf_counter())
    assert not list(tmp_path.glob('views/*.view'))  # fast and not asked: not saved, as before
    token = view_cache.always_save.set(True)
    try:
        view_cache._save_if_slow(key, entry, scope, 10, time.perf_counter())
    finally:
        view_cache.always_save.reset(token)
    assert len(list((tmp_path / 'views').glob('*.view'))) == 1
