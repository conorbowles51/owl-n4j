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


def _take_lock():
    """The host-wide warm-up lock, held open, or None if the memo is off or another worker holds it."""
    import fcntl
    from services.financial import view_cache
    directory = view_cache._memo_dir()
    if directory is None:
        return None
    try:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = open(directory / 'warmup.lock', 'a')
    except OSError:
        logger.warning('Financial view warm-up skipped: no memo directory', exc_info=True)
        return None
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
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


def _warm_cases():
    from sqlalchemy import func, select
    from postgres.models.financial import FinancialStatementPeriod as Period
    from postgres.session import _get_session_local
    from routers.financial_ledger import get_account_history
    SessionLocal = _get_session_local()
    with SessionLocal() as db:
        if db.get_bind().dialect.name != 'postgresql':
            return
        cases = [case for case, _ in db.execute(select(Period.case_id, func.count()).group_by(Period.case_id)
            .order_by(func.count().desc(), Period.case_id))]
    from routers.financial_ledger import get_ledger_transactions
    from routers.financial_statement_import import files as get_statement_files
    from routers.evidence import list_evidence
    from routers.financial_ledger import get_account_consolidations, get_account_parties
    from routers.financial_statement_import import account_types as get_account_types
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
    )
    for case_id in cases:
        for name, route, defaults in views:
            if process_shutdown.requested.is_set():
                return
            started = time.perf_counter()
            try:
                with SessionLocal() as db:
                    # Each route gets case_id as FastAPI gives it (the evidence listing declares it as text).
                    route(case_id=str(case_id) if route is list_evidence else case_id, **defaults, db=db)
                logger.info('Financial %s warmed for case %s (%.1f s)', name, case_id, time.perf_counter() - started)
            except Exception:
                logger.warning('Financial %s warm-up failed for case %s', name, case_id, exc_info=True)


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
    warm_account_history(lock_held=CHILD_FLAG in sys.argv[1:])
