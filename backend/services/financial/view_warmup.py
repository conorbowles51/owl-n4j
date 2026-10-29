"""After a start, compute the slowest first-load Financial view once in the background.

Every release restarts the backend, and the first account history afterwards read every saved statement again
(d5b330d1: 53 s). One worker process computes each case's account history once, shortly after start, through
the route's own cached view: the same code, parameters and snapshot as a person's first request, so the same
bytes. Its per-statement results are saved (view_cache.VersionMemo), so the other workers reuse them instead of
reading every statement again. One worker at a time, one case at a time, largest first; a failure is logged and
the next case continues. Nothing is written to the database. FINANCIAL_VIEW_WARMUP=0 turns it off.
"""
import asyncio
import logging
import os
import time

logger = logging.getLogger(__name__)

WARM_DELAY_SECONDS = 20


async def warm_views_once():
    if os.environ.get('FINANCIAL_VIEW_WARMUP', '1') == '0':
        return
    await asyncio.sleep(WARM_DELAY_SECONDS)
    await asyncio.to_thread(warm_account_history)


def warm_account_history():
    """Compute every case's full account history once, if no other worker on this host is doing it now."""
    import fcntl
    from services.financial import view_cache
    directory = view_cache._memo_dir()
    if directory is None:
        return
    try:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = open(directory / 'warmup.lock', 'a')
    except OSError:
        logger.warning('Financial view warm-up skipped: no memo directory', exc_info=True)
        return
    with lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return  # another worker is warming
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
