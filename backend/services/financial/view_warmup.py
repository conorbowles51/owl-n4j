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


async def warm_views_once():
    if os.environ.get('FINANCIAL_VIEW_WARMUP', '1') == '0':
        return
    await asyncio.sleep(WARM_DELAY_SECONDS)
    lock = await asyncio.to_thread(_take_lock)
    if lock is None:
        return
    with lock:
        await _run_child()


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


def _load_prctl():
    import ctypes
    try:
        return ctypes.CDLL('libc.so.6', use_errno=True).prctl
    except OSError:
        return None


# Resolved once in the worker: the child must not ask the loader for libc between fork and exec (another worker
# thread may have held the loader's lock at the fork).
_PRCTL = _load_prctl()


def _end_with_parent(parent=None):
    """In the child before it starts: end it if the worker dies (a killed worker cannot terminate it, and its
    lock is gone, so a restarted worker would start a second warm-up beside it)."""
    import signal
    if _PRCTL is not None:
        _PRCTL(1, signal.SIGTERM)  # PR_SET_PDEATHSIG
    if parent is not None and os.getppid() != parent:
        os._exit(0)  # the worker died before the signal was set


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
        _warm_cases()
        return
    lock = _take_lock()
    if lock is None:
        return
    with lock:
        _warm_cases()


def _warm_cases(share=None):
    """``share`` (k, n): only every n-th case-and-view task from the k-th, for a prepare split over n processes."""
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
    from services import process_shutdown
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
    )
    task = -1
    for case_id in cases:
        for name, route, defaults in views:
            task += 1
            if share is not None and task % share[1] != share[0]:
                continue
            if process_shutdown.requested.is_set():
                return warmed, failed
            started = time.perf_counter()
            try:
                with SessionLocal() as db:
                    # Each route gets case_id as FastAPI gives it (the evidence listing declares it as text).
                    route(case_id=str(case_id) if route is list_evidence else case_id, **defaults, db=db)
                logger.info('Financial %s warmed for case %s (%.1f s)', name, case_id, time.perf_counter() - started)
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
