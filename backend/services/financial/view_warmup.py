"""After a start, compute the slowest first-load Financial views once in the background.

Every release restarts the backend, and the first account history afterwards read every saved statement again
(d5b330d1: 53 s); the first Transactions read took 53-184 s and the statement file list 46-104 s. One worker
process computes each case's account history, Transactions and statement file list, shortly after start, through
the routes' own cached views: the same code, parameters and snapshot as a person's first request, so the same
bytes. The computed views are saved (view_cache saves every slow view) and the account history's per-statement
results too (view_cache.VersionMemo), so every worker serves them after checking that no row they were computed
from has changed. One worker at a time, one case at a time, largest first; a failure is logged and the next view
continues. Nothing is written to the database.
FINANCIAL_VIEW_WARMUP=0 turns it off.

After that first pass the warm-up runs again whenever a table its views read has been written since its last pass
(PostgreSQL's per-table insert/update/delete counters, checked once a minute, at most one pass every
REWARM_MIN_SECONDS, one worker per host): a view whose rows changed is computed again and saved, so the next visitor
does not wait for it (a batch round's or a sweep's writes otherwise left d5b330d1's statement files, review queue and
batch list for the first visitor after them: 34.4, 28.0 and 11.7 s, 2026-10-31 01:0x). An unchanged view costs a
fingerprint check (0.13 s average, measured); with no writes nothing runs. FINANCIAL_VIEW_REWARM=0 turns this off.

The computing runs in a short-lived child process (``python -m services.financial.view_warmup``) that only fills
the saved views and per-statement results. Computed inside a worker it left that worker gigabytes larger for the
rest of its life (memory freed by Python stays with the process); the child's memory goes back to the system when
it exits. Each worker's first request then reads the saved copies.
"""
import asyncio
import functools
import logging
import os
import time

# Its INFO lines (served unchanged / from the saved copy / computed, with times) reach the service journal, so a
# slow first load can be explained from the journal.
from services.financial.journal import journal  # noqa: E402
logger = journal(__name__)

WARM_DELAY_SECONDS = 20


CHILD_FLAG = '--lock-held'


REWARM_CHECK_SECONDS = 60
REWARM_MIN_SECONDS = 300
REWARM_STATE = 'rewarm-state.json'


async def warm_views_once():
    if os.environ.get('FINANCIAL_VIEW_WARMUP', '1') == '0':
        return
    await asyncio.sleep(WARM_DELAY_SECONDS)
    lock = await asyncio.to_thread(_take_lock)
    if lock is not None:
        with lock:
            await _run_child()
    if os.environ.get('FINANCIAL_VIEW_REWARM', '1') == '0':
        return
    while True:
        await asyncio.sleep(REWARM_CHECK_SECONDS)
        try:
            lock = await asyncio.to_thread(_take_lock)
            if lock is None:
                continue  # another worker on this host is warming or checking
            with lock:
                if not process_shutdown_requested() and await asyncio.to_thread(_rewarm_due):
                    await _run_child()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning('Financial view re-warm check failed', exc_info=True)


async def warm_case_files_once():
    """Each worker loads the evidence-file copies of the cases with the most files once, right after start.

    ``source_lineage.case_files`` keeps those copies per process (CASE_FILES_KEPT cases), so the shared warm-up
    above, which runs in a child process, cannot fill them. Without this every worker's first statement open,
    review queue or activity request on d5b330d1 loaded its 6,108 files: 3.91 s, against 0.07 s once held
    (measured 2026-10-31, live data). The copies are checked against each row's version on every use, so loading
    them early changes no result. FINANCIAL_CASE_FILES_WARMUP=0 turns it off.
    """
    if os.environ.get('FINANCIAL_CASE_FILES_WARMUP', '1') == '0':
        return
    try:
        started = time.monotonic()
        cases = await asyncio.to_thread(warm_case_files)
        if cases:
            logger.info('Evidence-file copies loaded for %d cases in %.2f s', len(cases), time.monotonic() - started)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning('Evidence-file copy warm-up failed', exc_info=True)


def warm_case_files():
    """Load ``case_files`` for the CASE_FILES_KEPT cases with the most evidence files; returns their ids."""
    from sqlalchemy import func, select
    from postgres.models.evidence import EvidenceFile
    from postgres.session import _get_session_local
    from services.financial import source_lineage
    with _get_session_local()() as db:
        cases = list(db.scalars(select(EvidenceFile.case_id).group_by(EvidenceFile.case_id)
                                .order_by(func.count().desc(), EvidenceFile.case_id)
                                .limit(source_lineage.CASE_FILES_KEPT)))
        warmed = []
        # Smallest first, so the largest case is the most recently used one and the last to be dropped.
        for case_id in reversed(cases):
            if process_shutdown_requested():
                break
            source_lineage.case_files(db, case_id)
            db.rollback()
            warmed.append(case_id)
    return warmed


def _write_counts(connection, tables=None):
    """{table: inserts + updates + deletes so far} from PostgreSQL's statistics, for ``tables`` (default all)."""
    from sqlalchemy import text
    rows = connection.execute(text('SELECT relname, n_tup_ins + n_tup_upd + n_tup_del FROM pg_stat_user_tables '
                                   'WHERE schemaname = current_schema()')).all()
    return {name: int(count) for name, count in rows if tables is None or name in tables}


def _graph_now():
    """The graph database's last committed transaction as a list (graph_read_cache's key), or None. Never raises."""
    try:
        from services.neo4j.driver import driver
        from services.neo4j.graph_read_cache import graph_bookmark
        with driver.session() as session:
            return list(graph_bookmark(session))
    except Exception:  # noqa: BLE001 - the graph then starts no pass of its own
        logger.warning('Financial view re-warm: graph state unavailable', exc_info=True)
        return None


def _rewarm_due(now=None):
    """True if the last pass finished at least REWARM_MIN_SECONDS ago and a table its views read was written since
    it started, or the graph database committed since (the graph records the pass reads, graph_read_cache). False
    with no record of a pass (the first pass writes it), or on any doubt."""
    import json
    from services.financial import view_cache
    directory = view_cache._memo_dir()
    try:
        state = json.loads((directory / REWARM_STATE).read_text())
    except (OSError, ValueError, TypeError):
        return False
    if not isinstance(state, dict) or not state.get('tables') or (now or time.time()) - state.get('finished', 0) < REWARM_MIN_SECONDS:
        return False
    if _preparing():
        return False  # a release is preparing the next code's views: this code's are about to be replaced
    from postgres.session import _get_engine
    with _get_engine().connect() as connection:
        current = _write_counts(connection, set(state['tables']))
    if current == state.get('counts'):
        graph = state.get('graph')
        if graph is None:
            return False
        now_graph = _graph_now()
        if now_graph is None or now_graph == graph:
            return False
    # A release writes the next code to disk before preparing it: this process's views are about to be replaced
    # (seen live 2026-10-31 02:57: a pass began 3 s after a prepare ended, before the restart).
    on_disk = view_cache._identity_now()
    if on_disk == view_cache.code_identity():
        return True
    global _skipped_for
    if on_disk != _skipped_for:
        _skipped_for = on_disk
        logger.info('Financial view re-warm skipped: the code on disk (%s) is not the code this process runs (%s)',
                    (on_disk or 'unreadable')[:12], (view_cache.code_identity() or 'unreadable')[:12])
    return False


_skipped_for = None  # the disk identity last reported as skipped (one journal line per change)


def _record_pass(counts, started, graph=None):
    """After a pass: the tables its views read and their write counts taken before it started, and the graph's last
    commit then (``graph``), so a write during the pass starts the next one."""
    import json
    from services.financial import view_cache
    directory = view_cache._memo_dir()
    tables = sorted(view_cache.tables_read)
    state = dict(tables=tables, counts={table: counts[table] for table in tables if table in counts},
                 started=started, finished=time.time(), graph=graph)
    temporary = directory / (REWARM_STATE + '.%d.tmp' % os.getpid())
    temporary.write_text(json.dumps(state, sort_keys=True))
    os.replace(temporary, directory / REWARM_STATE)


async def _run_child():
    """The warm-up in a child process with this worker's interpreter, code and environment (the saved results are
    keyed on all three). Stopped with the worker; its exit status is logged, never raised."""
    from pathlib import Path
    backend = Path(__file__).resolve().parents[2]
    child = await asyncio.create_subprocess_exec(*_child_command(), cwd=str(backend), preexec_fn=functools.partial(_end_with_parent, os.getpid()))
    try:
        code = await child.wait()
    except asyncio.CancelledError:
        if child.returncode is None:
            child.terminate()
            try:
                await asyncio.wait_for(child.wait(), 10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                child.kill()
        raise
    if code:
        logger.warning('Financial view warm-up process ended with status %s', code)


def _load_libc(name):
    import ctypes
    try:
        return getattr(ctypes.CDLL('libc.so.6', use_errno=True), name)
    except (OSError, AttributeError):
        return None


# Resolved once in the worker: the child must not ask the loader for libc between fork and exec (another worker
# thread may have held the loader's lock at the fork).
_PRCTL = _load_libc('prctl')
_SYSCALL = _load_libc('syscall')

# Background children (page-image rounds, batch rounds, view warm-up) share the web workers' cgroup, so only their
# own priority ranks them below request threads: nice 15 weighs 36 against a request thread's 1024.
BACKGROUND_NICE = 15
_SYS_IOPRIO_SET = 251  # x86_64
_IOPRIO_WHO_PROCESS = 1
_IOPRIO_IDLE = 3 << 13


def _lower_priority():
    """Nice 15 and the idle IO class for this process (never raises; a nicer process stays as nice)."""
    try:
        if os.getpriority(os.PRIO_PROCESS, 0) < BACKGROUND_NICE:
            os.setpriority(os.PRIO_PROCESS, 0, BACKGROUND_NICE)
    except OSError:
        pass
    if _SYSCALL is not None:
        _SYSCALL(_SYS_IOPRIO_SET, _IOPRIO_WHO_PROCESS, 0, _IOPRIO_IDLE)


def _end_with_parent(parent=None):
    """In the child before it starts: end it if the worker dies (a killed worker cannot terminate it, and its
    lock is gone, so a restarted worker would start a second warm-up beside it), and rank it below the request
    threads it shares the service with."""
    import signal
    if _PRCTL is not None:
        _PRCTL(1, signal.SIGTERM)  # PR_SET_PDEATHSIG
    if parent is not None and os.getppid() != parent:
        os._exit(0)  # the worker died before the signal was set
    _lower_priority()


def _child_command():
    import sys
    return [sys.executable, '-m', 'services.financial.view_warmup', CHILD_FLAG]


PREPARE_LOCK = 'prepare.lock'


def _take_lock(wait=False, name='warmup.lock'):
    """The host-wide warm-up lock, held open, or None if the memo is off or another worker holds it (``wait``:
    wait for it instead)."""
    import fcntl
    from services.financial import view_cache
    directory = view_cache._memo_dir()
    if directory is None:
        return None
    try:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = open(directory / name, 'a')
    except OSError:
        logger.warning('Financial view warm-up skipped: no memo directory', exc_info=True)
        return None
    try:
        fcntl.flock(lock, fcntl.LOCK_EX if wait else fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        return None  # another worker is warming
    return lock


def warm_account_history(lock_held=False):
    """Compute every case's full account history once, if no other worker on this host is doing it now
    (``lock_held``: the parent worker holds the lock for this process)."""
    if lock_held:
        from services.financial import view_cache
        if view_cache._memo_dir() is None:
            return
        counts, graph, started = _counts_now(), _graph_now(), time.time()
        computed = view_cache.stats['misses']
        warmed, failed = _warm_cases(stop_if_preparing=True)
        if counts is not None and not process_shutdown_requested() and not _preparing():
            _record_pass(counts, started, graph)
        logger.info('Financial view warm-up pass: %d views in %.0f s, %d computed again, %d failed', warmed + failed,
                    time.time() - started, view_cache.stats['misses'] - computed, failed)
        return
    lock = _take_lock()
    if lock is None:
        return
    with lock:
        _warm_cases()


def _counts_now():
    """Every table's write count now (None on a database without these statistics)."""
    from postgres.session import _get_engine
    try:
        with _get_engine().connect() as connection:
            if connection.dialect.name != 'postgresql':
                return None
            return _write_counts(connection)
    except Exception:
        logger.warning('Financial view re-warm: write counts unavailable', exc_info=True)
        return None


def _preparing():
    """True while a release prepares the next code's views (it holds prepare.lock)."""
    lock = _take_lock(name=PREPARE_LOCK)
    if lock is None:
        return True
    lock.close()
    return False


def process_shutdown_requested():
    from services import process_shutdown
    return process_shutdown.requested.is_set()


VISITED_MAX_AGE_SECONDS = 24 * 3600
VISITED_MAX_VIEWS = 200


def _prune_visits(directory, now):
    """Remove visit notes older than VISITED_MAX_AGE_SECONDS and temporary files a killed writer left an hour ago."""
    try:
        for entry in os.scandir(directory):
            try:
                age = now - entry.stat().st_mtime
                if (entry.name.endswith('.visit') and age > VISITED_MAX_AGE_SECONDS) or (
                        entry.name.endswith('.tmp') and age > 3600):
                    os.unlink(entry.path)
            except FileNotFoundError:
                continue
    except OSError:
        logger.warning('Could not prune Financial view visit notes', exc_info=True)


def _visited_views(listed):
    """(case_id, (name, route, {})) for each view a person opened in the last VISITED_MAX_AGE_SECONDS whose key is not
    one the fixed lists warm (``listed``: (case_id, route, parameters) as they call it), newest first, at most
    VISITED_MAX_VIEWS. The route is called with the saved key's own parameters. Never raises: an unreadable copy is
    skipped."""
    import functools
    import json
    from uuid import UUID
    from services.financial import view_cache, view_refresh
    # The visits people made (view_cache.note_visit); before any was noted, the saved copies' times.
    memo = view_cache._memo_dir()
    if memo is None:
        return []
    directory, suffix = memo / view_cache.VISITED_DIR, '.visit'
    if not directory.is_dir():
        directory, suffix = view_cache._saved_dir(), '.view'
    for module in view_refresh.ROUTE_MODULES:
        __import__(module)
    listed_keys = set()
    for case_id, route, parameters in listed:
        name = next((n for n, handler in view_cache.handlers.items() if handler is route), None)
        if name is not None:
            listed_keys.add(view_cache.view_key(name, dict(parameters, case_id=case_id)))
    found, seen = [], set()
    now = time.time()
    try:
        entries = sorted(((entry.stat().st_mtime, entry.path) for entry in os.scandir(directory)
                          if entry.name.endswith(suffix)), reverse=True)
    except OSError:
        return []
    if suffix == '.visit':
        _prune_visits(directory, now)
    for mtime, path in entries:
        if now - mtime > VISITED_MAX_AGE_SECONDS or len(found) >= VISITED_MAX_VIEWS:
            break
        try:
            with open(path, 'rb') as saved:
                key = tuple(json.loads(saved.readline())['key'])
            name, parameters = key[0], json.loads(key[1])
            handler = view_cache.handlers.get(name)
            if handler is None or key in seen or key in listed_keys:
                continue
            seen.add(key)
            arguments = view_refresh._typed(handler, parameters)
            if view_cache.view_key(name, arguments) != key:
                continue
            case_id = arguments.get('case_id')
            if case_id is None:
                continue
            def call(case_id, db, _handler=handler, _arguments=arguments):
                return _handler(**_arguments, db=db)
            found.append((UUID(str(case_id)), ('visited ' + name, call, {})))
        except Exception:  # noqa: BLE001 - a copy that cannot be read back is not warmed
            continue
    return found


def _graph_records(case_id, mode, db=None):
    """The "Other financial records" tab's graph read (GET /api/financial, no filters), saved for the workers and
    the next start (graph_read_cache) while the graph is unchanged. Measured live 2026-10-31 09:09, first visit
    after a release: d5b330d1 14.0 s (7.8 s of it the graph read), 49494305 4.1 s."""
    from services.neo4j_service import neo4j_service
    neo4j_service.get_financial_transactions(case_id=str(case_id), mode=mode)


def _warm_cases(share=None, stop_if_preparing=False):
    """``share`` (k, n): only every n-th case-and-view task from the k-th, for a prepare split over n processes."""
    from services.financial import view_cache
    token = view_cache.not_a_visit.set(True)  # warming a view is not a person opening it
    try:
        return _warm_cases_now(share, stop_if_preparing)
    finally:
        view_cache.not_a_visit.reset(token)


def _warm_cases_now(share, stop_if_preparing):
    from sqlalchemy import func, select
    from postgres.models.financial import FinancialStatementPeriod as Period
    from postgres.session import _get_session_local
    from routers.financial_ledger import get_account_history
    SessionLocal = _get_session_local()
    with SessionLocal() as db:
        if db.get_bind().dialect.name != 'postgresql':
            return 0, 0
        cases = [case for case, _ in db.execute(select(Period.case_id, func.count()).group_by(Period.case_id)
            .order_by(func.count().desc(), Period.case_id))]
    warmed = failed = 0
    from routers.financial_ledger import get_ledger_transactions
    from routers.financial_statement_import import files as get_statement_files
    from routers.evidence import list_evidence
    from routers.financial_ledger import get_account_consolidations, get_account_parties
    from routers.financial_statement_import import account_types as get_account_types
    from routers.financial_statement_import import list_financial_batches
    from services.financial.review_queue import warm as warm_review_queue
    from routers.financial_ledger import (get_counterparty_party_analysis, get_ledger_posting_graph,
                                          get_ledger_timeline, get_ledger_transfer_candidates, get_pattern_review,
                                          get_ledger_summary, get_working_ledger_analysis, get_working_ledger_summary)
    from fastapi import HTTPException
    from services import process_shutdown
    full_range_dates = dict(account_id=None, start_date=None, end_date=None)
    full_range = dict(full_range_dates, population='working')
    # Each route with its defaults, as FastAPI passes them for a first visit: the same cached-view key.
    views = (
        ('account history', get_account_history, dict(account_id=None, account_ids=None, account_holders=None,
                                                       start_date=None, end_date=None)),
        ('transactions', get_ledger_transactions, dict(source_document_id=None, account_id=None, ledger_status=None,
                                                       start_date=None, end_date=None, account_ids=None,
                                                       account_holders=None)),
        ('statement files', get_statement_files, {}),
        # The Financial page's statement register asks for every reading version of its files.
        ('statement register files', list_evidence, dict(status_filter=None, include_cellebrite_artifacts=False,
                                                         include_reading_versions=True, financial_only=True)),
        # Measured live 2026-10-30 17:52-18:00, first call after a start (load 12-19): d5b330d1 58 / 43 / 38 s,
        # 49494305 63 / 34 / 25 s; then 0.1-1.2 s. Saved copies do not outlive a release (new code identity).
        ('account parties', get_account_parties, {}),
        ('account types', get_account_types, {}),
        ('account consolidations', get_account_consolidations, {}),
        # Its own cache (review_queue), saved to disk for the workers; first read after a start was 54.1 s on
        # d5b330d1 and 15.7 s on 49494305 (live 2026-10-30 18:29).
        ('review queue', warm_review_queue, {}),
        # Every call recomputed it: d5b330d1 10-39 s live (request_speed, 6 h to 19:00 2026-10-30), 49494305 ~5 s.
        ('batch list', list_financial_batches, {}),
        # The summary panel of the Ledger, Trends and People tabs (LedgerSummaryPanel, include_contributions); the
        # Ledger tab opens with the working summary. Computed for the first visitor before: 1.9-4.1 s (journal,
        # 2026-10-30 19:42) and 4.2-4.7 s live (22:11).
        ('ledger summary', get_ledger_summary, dict(full_range_dates, include_contributions=True, account_ids=None,
                                                    account_holders=None)),
        ('working ledger summary', get_working_ledger_summary, dict(full_range_dates, include_contributions=True,
                                                                    account_ids=None, account_holders=None)),
        ('graph records', _graph_records, dict(mode='transactions')),
        ('graph intelligence records', _graph_records, dict(mode='intelligence')),
    )
    # The full-range analyses as the page first asks for them (the counterparty tab opens on the working analysis
    # by counterparty; the identities analysis is one tick away). First visit on d5b330d1 live 2026-10-30
    # 20:22-20:26: 23.7 s (counterparty-party analysis) to 50.5 s (transfer candidates), mostly name inference in a
    # request worker that starts empty; a refusal at the view's own row limit is kept and saved like a result.
    # A second pass after every case's views above: the release's warm-up has a time cap, and these come last.
    analyses = (
        ('working counterparty analysis', get_working_ledger_analysis, dict(full_range_dates, grouping='counterparty',
                                                                           account_ids=None, account_holders=None)),
        ('posting graph', get_ledger_posting_graph, dict(full_range, account_ids=None, account_holders=None,
                                                         label_origins=False)),
        ('counterparty-party analysis', get_counterparty_party_analysis, dict(full_range, account_ids=None,
                                                                             account_holders=None)),
        ('timeline', get_ledger_timeline, dict(full_range, account_ids=None, account_holders=None)),
        ('transfer candidates', get_ledger_transfer_candidates, dict(start_date=None, end_date=None,
                                                                     population='working', tolerance_days=3)),
        ('pattern review', get_pattern_review, dict(full_range, window_days=3, threshold_minor=None,
                                                    threshold_currency=None, cross_account=False, account_ids=None,
                                                    account_holders=None)),
    )
    order = [(case_id, view) for group in (views, analyses) for case_id in cases for view in group]
    # Last: every other view a person opened in the last day (its saved copy, under any code), with the exact
    # parameters it was opened with, so a first visit after a release finds it ready however the page asked for it
    # (measured live 2026-10-31 09:10, first visit after the release: statement coverage on 49494305 13.9 s, a view
    # no fixed list named). Each is rebuilt from its key as the refresh process does (view_refresh._typed).
    order += _visited_views([(case_id, route, defaults) for case_id, (_, route, defaults) in order])
    for task, (case_id, (name, route, defaults)) in enumerate(order):
        if share is not None and task % share[1] != share[0]:
            continue
        if process_shutdown.requested.is_set():
            return warmed, failed
        if stop_if_preparing and _preparing():
            logger.info('Financial view warm-up stopped: a release is preparing the next code')
            return warmed, failed
        started = time.perf_counter()
        try:
            with SessionLocal() as db:
                # Each route gets case_id as FastAPI gives it (the evidence listing declares it as text).
                route(case_id=str(case_id) if route is list_evidence else case_id, **defaults, db=db)
            logger.info('Financial %s warmed for case %s (%.1f s)', name, case_id, time.perf_counter() - started)
            warmed += 1
        except HTTPException as refusal:
            if refusal.status_code != 422:
                logger.warning('Financial %s warm-up failed for case %s (%s: %s)', name, case_id,
                               refusal.status_code, refusal.detail)
                failed += 1
                continue
            # The view's own answer for these rows (e.g. its row limit); kept like a result.
            logger.info('Financial %s warmed for case %s (%.1f s, refused: %s)', name, case_id,
                        time.perf_counter() - started, refusal.detail)
            warmed += 1
        except Exception:
            logger.warning('Financial %s warm-up failed for case %s', name, case_id, exc_info=True)
            failed += 1
    return warmed, failed


PREPARE_FLAG = '--prepare'


def prepare(processes=None):
    """Before a release restarts the service: the same warm-up for the code now on disk, so the saved copies exist
    when the new service starts (otherwise the first visits after every release wait minutes, d5b330d1 account
    history 61 s). Run in a unit of its own with the service's user, environment file and settings
    (services/financial/view_prepare.py), while the old service still serves: the saved copies are keyed on the
    code identity, which this process takes from the files on disk, as the started service will.

    Skipped while the database is behind the code's migrations: deploy.sh migrates after this runs, and views computed
    against the old schema must not be saved under the new code. One prepare at a time (its own lock); it does not
    wait for the old service's after-start warm-up, which computes views for the code being replaced: measured live
    2026-10-30 21:33-21:41, a prepare queued 8.7 min behind one (then ran 18 s), which would use up the release's
    10-minute cap on back-to-back releases. Returns the summary line; never raises."""
    started = time.perf_counter()
    processes = PREPARE_PROCESSES if processes is None else processes
    try:
        from services.financial import view_cache
        if view_cache._memo_dir() is None or view_cache.code_identity() is None:
            return 'prepare: skipped, saved views are off or the code identity is unreadable'
        pending = _migrations_pending()
        if pending:
            return 'prepare: skipped, database migrations pending (%s)' % pending
        lock = _take_lock(wait=True, name=PREPARE_LOCK)
        if lock is None:
            return 'prepare: skipped, no memo directory'
        with lock:
            warmed, failed = _warm_cases() if processes == 1 else _warm_in_processes(processes)
        return 'prepare: %d views warmed in %d s (%d failed, %d processes, code %s)' % (
            warmed, round(time.perf_counter() - started), failed, processes, view_cache.code_identity()[:12])
    except Exception:
        logger.warning('Financial view prepare failed', exc_info=True)
        return 'prepare: failed after %d s (see the unit journal)' % round(time.perf_counter() - started)


# The release waits for the prepare (deploy.sh, before the frontend stops). Run as one process it took 420 s on
# 2026-10-30 21:47 (deploy.sh waited 393 s); the views are independent, so the tasks are split over processes.
PREPARE_PROCESSES = 3
SHARE_FLAG = '--prepare-share'


def _warm_in_processes(processes):
    """Every case-and-view task once, split over ``processes`` children (each has this process's interpreter,
    code and environment, so the same code identity); returns the summed (warmed, failed)."""
    import subprocess
    import sys
    from pathlib import Path
    backend = Path(__file__).resolve().parents[2]
    children = [subprocess.Popen([sys.executable, '-m', 'services.financial.view_warmup', SHARE_FLAG,
                                  '%d/%d' % (share, processes)], cwd=str(backend), stdout=subprocess.PIPE, text=True)
                for share in range(processes)]
    warmed = failed = 0
    for child in children:
        out, _ = child.communicate()
        counts = [line.split() for line in out.splitlines() if line.startswith('share ')]
        if child.returncode or not counts:
            logger.warning('Financial view prepare share ended with status %s', child.returncode)
            failed += 1
            continue
        warmed += int(counts[-1][1])
        failed += int(counts[-1][2])
    return warmed, failed


def _migrations_pending():
    """The code's migration heads the database has not reached yet, as text; empty if none."""
    from pathlib import Path
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from postgres.session import _get_engine
    backend = Path(__file__).resolve().parents[2]
    heads = set(ScriptDirectory.from_config(Config(str(backend / 'alembic.ini'))).get_heads())
    with _get_engine().connect() as connection:
        current = set(MigrationContext.configure(connection).get_current_heads())
    return ', '.join(sorted(heads - current))


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
    if PREPARE_FLAG in sys.argv[1:]:
        print(prepare(), flush=True)
    elif SHARE_FLAG in sys.argv[1:]:
        share, processes = map(int, sys.argv[sys.argv.index(SHARE_FLAG) + 1].split('/'))
        print('share %d %d' % _warm_cases(share=(share, processes)), flush=True)
    else:
        warm_account_history(lock_held=CHILD_FLAG in sys.argv[1:])
