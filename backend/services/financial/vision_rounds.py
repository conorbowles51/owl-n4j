"""Page-image reading rounds (vision_reader.sweep) in their own process, one per host.

Run inside the workers, each round decided again for every listed statement whether it is due, by reading its
statement import (statement parsing in Python), in both workers at once and again after every restart (the
statements passed over are remembered in memory only). Measured live 2026-10-30: both workers at a full CPU each
with no request in flight; d5b330d1's Financial graph request waited five minutes before it reached the database,
and a thread dump showed the round's threads in statement_engine. The rounds now run in one child process per host
that holds a lock, so requests no longer share a worker's interpreter lock with them. The other worker tries the
lock again after each pause and takes the rounds over when the holder stops. Without a memo directory (where the
lock lives) the rounds run in the worker as before.
"""
import asyncio
import functools
import os
import signal
import time

from services.financial.journal import journal

log = journal(__name__)

CHILD_FLAG = '--lock-held'
PAUSE_SECONDS = 30
LOCK_NAME = 'vision-rounds.lock'


def _lock_directory():
    from services.financial import view_cache
    return view_cache._memo_dir()


def _take_lock(name=LOCK_NAME):
    """The host-wide rounds lock, held open, or None if another worker holds it or there is nowhere to keep it."""
    import fcntl
    directory = _lock_directory()
    if directory is None:
        return None
    try:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = open(directory / name, 'a')
    except OSError:
        log.warning('Rounds lock %s could not be opened; trying again after a pause', name, exc_info=True)
        return None
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        return None
    return lock


def _child_command():
    import sys
    return [sys.executable, '-m', 'services.financial.vision_rounds', CHILD_FLAG]


def _start_child(end_with_parent, parent, blocked_signals):
    """In the forked child before exec (no imports here: another thread may have held the import lock at the fork):
    end with the worker, and start with ``blocked_signals`` blocked (a signal mask survives exec, so every thread
    the program starts, during its imports too, has them blocked)."""
    end_with_parent(parent)
    if blocked_signals:
        signal.pthread_sigmask(signal.SIG_BLOCK, blocked_signals)


async def _run_child(command=None, label='Page-image rounds', stop_seconds=10, blocked_signals=()):
    """The rounds in a child process with this worker's interpreter, code and environment, until it ends or the
    worker stops (then it is asked to stop, and killed after ``stop_seconds``). Its exit status is logged, never
    raised."""
    from pathlib import Path
    from services.financial.view_warmup import _end_with_parent
    backend = Path(__file__).resolve().parents[2]
    child = await asyncio.create_subprocess_exec(*(command or _child_command()), cwd=str(backend),
                                                 preexec_fn=functools.partial(_start_child, _end_with_parent, os.getpid(),
                                                                           tuple(blocked_signals)))
    try:
        code = await child.wait()
    except asyncio.CancelledError:
        if child.returncode is None:
            child.terminate()
            try:
                await asyncio.wait_for(child.wait(), stop_seconds)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                child.kill()
        raise
    log.warning('%s process ended with status %s; started again after a pause', label, code)


async def run_in_child_forever():
    """False when there is no lock location (the caller runs the rounds itself); otherwise never returns while the
    reader is on: this worker runs the child whenever it holds the lock."""
    from services.financial import vision_reader
    if not await asyncio.to_thread(_lock_usable):
        return False
    while vision_reader.ENABLED:
        lock = await asyncio.to_thread(_take_lock)
        if lock is not None:
            with lock:
                try:
                    await _run_child()
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001 - e.g. the fork failed: tried again after the pause
                    log.exception('Page-image rounds process could not be started; trying again after a pause')
        await asyncio.sleep(PAUSE_SECONDS)
    return True


def _lock_usable(name=LOCK_NAME):
    """A lock file can be opened (held by another worker or not); otherwise the worker runs the rounds itself."""
    directory = _lock_directory()
    if directory is None:
        return False
    try:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        open(directory / name, 'a').close()
    except OSError:
        log.warning('Rounds lock %s: no lock directory; the rounds run in this worker', name, exc_info=True)
        return False
    return True


def rounds(stop=None):
    """The child's loop: one round, a pause, again (``stop()`` ends it; tests)."""
    from postgres.session import _get_session_local
    from routers.evidence import _resolve_stored_path
    from services.financial import vision_reader
    while vision_reader.ENABLED and not (stop and stop()):
        try:
            vision_reader.sweep(_get_session_local(), _resolve_stored_path)
        except Exception:  # noqa: BLE001 - a failed round is retried
            log.exception('Page-image reading round failed; it will retry')
        if stop and stop():
            return
        time.sleep(PAUSE_SECONDS)


if __name__ == '__main__':
    import logging
    import sys
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
    if CHILD_FLAG in sys.argv[1:]:
        rounds()
