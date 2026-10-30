"""After a start, compute the slowest first-load Financial view once in the background.

Every release restarts the backend, and the first account history afterwards read every saved statement again
(d5b330d1: 53 s). One worker process computes each case's account history once, shortly after start, through
the route's own cached view: the same code, parameters and snapshot as a person's first request, so the same
bytes. Its per-statement results are saved (view_cache.VersionMemo), so the other workers reuse them instead of
reading every statement again. One worker at a time, one case at a time, largest first; a failure is logged and
the next case continues. Nothing is written to the database. FINANCIAL_VIEW_WARMUP=0 turns it off.

The computing runs in a short-lived child process (``python -m services.financial.view_warmup``) that only fills
the saved per-statement results. Computed inside a worker it left that worker gigabytes larger for the rest of its
life (memory freed by Python stays with the process); the child's memory goes back to the system when it exits.
Each worker's first account history then reads the saved results.
"""
import asyncio
import logging
import os
import time

logger = logging.getLogger(__name__)

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
    child = await asyncio.create_subprocess_exec(*_child_command(), cwd=str(backend), preexec_fn=_end_with_parent)
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


def _end_with_parent():
    """In the child before it starts: end it if the worker dies (a killed worker cannot terminate it, and its
    lock is gone, so a restarted worker would start a second warm-up beside it)."""
    import ctypes
    import signal
    try:
        ctypes.CDLL('libc.so.6', use_errno=True).prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG
    except OSError:
        pass


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
    from services import process_shutdown
    for case_id in cases:
        if process_shutdown.requested.is_set():
            return
        started = time.perf_counter()
        try:
            with SessionLocal() as db:
                # The route's defaults, as FastAPI passes them: the same cached-view key as a first visit.
                get_account_history(case_id=case_id, account_id=None, account_ids=None, account_holders=None,
                                    start_date=None, end_date=None, db=db)
            logger.info('Financial account history warmed for case %s (%.1f s)', case_id, time.perf_counter() - started)
        except Exception:
            logger.warning('Financial account history warm-up failed for case %s', case_id, exc_info=True)


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
    warm_account_history(lock_held=CHILD_FLAG in sys.argv[1:])
