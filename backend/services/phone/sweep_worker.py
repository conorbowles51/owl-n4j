"""The phone interpretation sweep as a process of its own (02 sections 1.3 and 14 decision 1, reversed).

Measured on C6 (694,406 records): one pass in the backend process took 824 s and raised the p95 of a read probe
on the same database from 46.5 ms to 172.4 ms; the backend runs two uvicorn workers and each would also run the
sweep thread beside its API requests. So the sweep runs here: one process for the whole box (a session advisory
lock; a second copy exits with ``EXIT_ALREADY_RUNNING``), at nice 19 and idle I/O class, started and supervised by
the backend (``supervise_forever``) and stopped with it. A pass killed with the process rolls back and the next
start completes it (``tests/test_phone_sweep_runtime.py``).

Run by hand: ``cd backend && python -m services.phone.sweep_worker``.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import signal
import sys
import threading

log = logging.getLogger(__name__)

EXIT_ALREADY_RUNNING = 3
LOCK_KEY = "phone_interpretation_worker"
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RETRY_SECONDS = 60
DEFAULT_PACE = 2.0  # pause twice as long as each write took (02 decision 46: at 1.0 P14 more than doubled a probe's p95)
STOP_GRACE_SECONDS = 8  # inside the backend's 10 s budget for background tasks (process_shutdown)


def main() -> int:
    from sqlalchemy import text

    from postgres.session import _get_engine
    from services.phone import generic, identities, mappings, resolvers, sweep  # noqa: F401  (resolvers: as the backend)
    mappings.install()
    identities.install()  # after the mappings: identities read the comm events
    from services.phone import readings
    readings.install()  # reading, region and owner decisions; the decision revision
    from services.phone import graph_projection
    graph_projection.install()  # the case graph's phone layer, after each pass (02 section 9.5)
    from services.phone import thread_text
    thread_text.install()  # conversations as searchable text (9.7)
    from services.pattern_of_life import activity
    activity.install()  # pattern of life: activity events after each pass (04 section 7.2)
    from services.pattern_of_life import availability
    availability.install()  # availability bands and the hourly rollup, after the activity events (5.3)
    generic.PACE["factor"] = float(os.environ.get("LOUPE_PHONE_SWEEP_PACE", DEFAULT_PACE))
    engine = _get_engine()
    holder = engine.connect()
    if not holder.execute(text("SELECT pg_try_advisory_lock(hashtext(:k))"), {"k": LOCK_KEY}).scalar():
        holder.close()
        return EXIT_ALREADY_RUNNING
    holder.commit()
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    try:
        sweep.sweep_forever(stop, lambda: engine)
    finally:
        holder.close()
    return 0


def command() -> list:
    cmd = [sys.executable, "-m", "services.phone.sweep_worker"]
    if shutil.which("ionice"):
        cmd = [shutil.which("ionice"), "-c3"] + cmd
    return cmd


async def supervise_forever():
    """Started by ``backend/main.py``: keep one worker process running; a copy that finds the lock taken (the other
    uvicorn worker's child holds it) is retried every minute, so the box always has exactly one."""
    failures = 0
    proc = None
    env = dict(os.environ, LOUPE_DB_ROLE="phone-sweep")
    try:
        while True:
            proc = await asyncio.create_subprocess_exec(*command(), cwd=BACKEND_DIR, env=env,
                                                        preexec_fn=lambda: os.nice(19))
            code = await proc.wait()
            proc = None
            if code == EXIT_ALREADY_RUNNING:
                failures = 0
                await asyncio.sleep(RETRY_SECONDS)
            else:
                failures += 1
                log.warning("phone interpretation worker exited with %s", code)
                await asyncio.sleep(min(600, 30 * 2 ** min(failures, 5)))
    except asyncio.CancelledError:
        if proc is not None and proc.returncode is None:
            proc.send_signal(signal.SIGTERM)
            try:
                await asyncio.wait_for(proc.wait(), STOP_GRACE_SECONDS)
            except asyncio.TimeoutError:
                proc.kill()  # the open pass rolls back; the previous generation stays readable
                await proc.wait()
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
