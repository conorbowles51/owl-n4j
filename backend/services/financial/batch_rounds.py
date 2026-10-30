"""Batch upkeep rounds (automatic reading, release re-checks, held re-preparation, reader gaps, readiness and the
save sweeps) in their own process, one per host.

Run inside the request workers, both workers ran every round. Measured live 2026-10-30 14:45-14:48 (thread dumps
every 3 s for 150 s, 8 min after a restart, no page open): one worker was in queue_save.sweep_backlog in 46 % of
samples, on CPU, and the other in held_reprepare.sweep in 46 %; the workers averaged 51 % and 61 % of a CPU, and a
d5b330d1 return to the Transactions tab stretched to 1.21 s. The rounds now run in one child process per host that
holds a lock (as the page-image rounds do, vision_rounds), so requests no longer share a worker's interpreter lock
with them, and each round runs once per host instead of once per worker. The rounds were already safe with two
workers running them at once (claims are compare-and-set; vision_rounds' successor child may overlap the old one's
last step for the same reason).

Stopping keeps the workers' behaviour: a step that has started finishes (each is one atomic unit) for at most
``process_shutdown.BACKGROUND_STOP_SECONDS``; past that the process ends and its open transaction rolls back, and
the durable record (claimed item, stored readiness) is taken up again by the next round.

The review-queue precompute stays in the workers: it fills their in-memory queue cache (review_queue.prewarm).
Without a lock location the rounds run in the worker as before.
"""
import asyncio
import logging
import signal
import threading
import time

# The same logger as when the rounds ran in import_batches: the journal lines keep their name.
log = logging.getLogger('services.financial.import_batches')

CHILD_FLAG = '--lock-held'
LOCK_NAME = 'batch-rounds.lock'
PAUSE_SECONDS = 5
RETRY_SECONDS = 30
FIRST_DELAY_SECONDS = 60
AUTO_READ_SECONDS = 10
READER_RELEASE_SECONDS = 120
READINESS_SECONDS = 60


def _auto_read(factory, resolve_path):
    # Statement files that entered Financial (or were recognised in an Evidence upload) join the case's automatic
    # batch.
    from services.financial.auto_read import sweep
    swept = sweep(factory, resolve_path)
    if swept['checked'] or swept['added']:
        log.info('Automatic statement reading: %s', swept)


def _reader_release(factory, resolve_path):
    # After a release that reads statements differently, prepared files of unfinished batches are prepared again
    # (no click).
    from services.financial.reader_release import sweep
    released = sweep(factory)
    if released['rechecked'] or released['compared']:
        log.info('Statement files checked again after a release: %s', released)


def _held_reprepare(factory, resolve_path):
    # Held statements prepared by an earlier backend reader are prepared again from their saved reading, a few at
    # a time.
    from services.financial.held_reprepare import sweep
    reprepared = sweep(factory)
    if reprepared['handed'] or reprepared['verdicts']:
        log.info('Held statements checked against the deployed reader: %s', reprepared)


def _reader_gaps(factory, resolve_path):
    # Held statements the reader got nothing out of (pages with text): registered and reported (journal WARNING
    # for each newly seen one).
    from services.financial import reader_gaps
    reader_gaps.sweep(factory)


def _refresh_readiness(factory, resolve_path):
    # Batch reads never re-read PDFs. Inputs changed by paths without their own refresh are brought current here.
    from services.financial.import_batches import refresh_stale_readiness
    refreshed = refresh_stale_readiness(factory)
    if refreshed:
        log.info('Stored batch readiness refreshed: %s', refreshed)


def _sweep_save(factory, resolve_path):
    # Statements that became ready since their file was prepared, or whose automatic save failed, are saved as at
    # preparation.
    from services.financial.queue_save import sweep_save
    sweep_save(factory)


def _autofill_reapply(factory, resolve_path):
    # Held statements whose reading is current and whose only questions their account's saved statements answer
    # are filled as System; the backlog round below saves those that then check out completely.
    from services.financial.autofill_reapply import sweep
    sweep(factory)


def _sweep_backlog(factory, resolve_path):
    # Statements ready from before automatic save (no preparation mark): saved under the same rule, a few per round.
    from services.financial.queue_save import sweep_backlog
    sweep_backlog(factory)


def _reader_gaps_seconds():
    from services.financial import reader_gaps
    return reader_gaps.SWEEP_SECONDS


# (name, seconds between runs, first run after start, steps, message when a step fails). A failed step ends its
# group for that run (the readiness group: as when the four ran in sequence in the worker loop).
GROUPS = (
    ('auto_read', lambda: AUTO_READ_SECONDS, 0, (_auto_read,),
     'Automatic statement reading round failed; it will retry'),
    ('reader_release', lambda: READER_RELEASE_SECONDS, FIRST_DELAY_SECONDS, (_reader_release,),
     'Re-checking statement files after a release failed; it will retry'),
    ('held_reprepare', lambda: READER_RELEASE_SECONDS, FIRST_DELAY_SECONDS, (_held_reprepare,),
     'Preparing held statements again after a reader change failed; it will retry'),
    ('reader_gaps', _reader_gaps_seconds, FIRST_DELAY_SECONDS, (_reader_gaps,),
     'Reader-gap round failed; it will retry'),
    ('readiness', lambda: READINESS_SECONDS, FIRST_DELAY_SECONDS,
     (_refresh_readiness, _sweep_save, _autofill_reapply, _sweep_backlog),
     'Financial batch processing interrupted; will resume'),
)


class Schedule:
    """When each group runs next (monotonic seconds)."""

    def __init__(self, now=None):
        now = time.monotonic() if now is None else now
        self.next = {name: now + first for name, _, first, _, _ in GROUPS}

    def due(self):
        """The groups due now, each moved to its next time as it is handed out (as the worker loop did)."""
        for name, every, _, steps, failure in GROUPS:
            now = time.monotonic()
            if now >= self.next[name]:
                self.next[name] = now + every()
                yield name, steps, failure


async def run_in_worker(factory, resolve_path, finish_atomic, schedule):
    """One pass of the due groups inside a worker (no lock location): each step a separate atomic unit."""
    for name, steps, failure in schedule.due():
        try:
            for step in steps:
                await finish_atomic(step, factory, resolve_path)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception(failure)


async def rounds_forever(factory_source, resolve_path, finish_atomic):
    """The rounds: in the host's child process when there is a lock location (this worker starts it whenever it
    holds the lock), otherwise in this worker every ``PAUSE_SECONDS``."""
    from services.financial import vision_rounds
    if await asyncio.to_thread(vision_rounds._lock_usable, LOCK_NAME):
        await run_in_child_forever()
        return
    schedule = Schedule()
    while True:
        try:
            await run_in_worker(factory_source(), resolve_path, finish_atomic, schedule)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('Financial batch processing interrupted; will resume')
        await asyncio.sleep(PAUSE_SECONDS)


def _child_command():
    import sys
    return [sys.executable, '-m', 'services.financial.batch_rounds', CHILD_FLAG]


async def run_in_child_forever():
    """Never returns: this worker runs the child whenever it holds the host lock, and tries again after a pause."""
    from services import process_shutdown
    from services.financial import vision_rounds
    while True:
        lock = await asyncio.to_thread(vision_rounds._take_lock, LOCK_NAME)
        if lock is not None:
            with lock:
                try:
                    # Blocked from the start: threads started while the package imports (before main()) would
                    # otherwise take a stop or dump signal's default action (immediate end; live 16:02, status -10).
                    await vision_rounds._run_child(_child_command(), 'Batch rounds',
                                                   process_shutdown.BACKGROUND_STOP_SECONDS,
                                                   blocked_signals=STOP_SIGNALS + (DUMP_SIGNAL,))
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001 - e.g. the fork failed: tried again after the pause
                    log.exception('Batch rounds process could not be started; trying again after a pause')
        await asyncio.sleep(RETRY_SECONDS)


def rounds(stop, factory=None, resolve_path=None):
    """The child's loop: the due groups, a pause, again, until ``stop`` (a threading.Event) is set. A step that has
    started runs to its end; the stop is looked at between steps."""
    if factory is None:
        from postgres.session import _get_session_local
        factory = _get_session_local()
    if resolve_path is None:
        from routers.evidence import _resolve_stored_path
        resolve_path = _resolve_stored_path
    schedule = Schedule()
    while not stop.is_set():
        for name, steps, failure in schedule.due():
            try:
                for step in steps:
                    if stop.is_set():
                        return
                    step(factory, resolve_path)
            except Exception:
                log.exception(failure)
        stop.wait(PAUSE_SECONDS)


STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT)
# Taken in the same wait as the stop signals, so no asynchronous handler runs in this process: a Python handler
# interrupting sigtimedwait past its timeout made it return a struct built from uninitialised memory (CPython 3.13,
# measured in review), which was then read as a stop.
DUMP_SIGNAL = signal.SIGUSR1


def _block_stop_signals():
    """Blocked in the calling thread and every thread it starts later, so only sigwait receives them."""
    signal.pthread_sigmask(signal.SIG_BLOCK, STOP_SIGNALS + (DUMP_SIGNAL,))
    return set(STOP_SIGNALS) | {DUMP_SIGNAL}


def _serve_until_signalled(stop, deadline_seconds, exit_process, run, dump=None):
    """``run(stop)`` in a thread; this (main) thread only waits for signals. SIGUSR1 calls ``dump()`` (every
    thread's stack, written from this thread); SIGTERM/SIGINT set ``stop``, let the running step finish for at most
    ``deadline_seconds`` and end the process (an unfinished step's transaction rolls back). The signals are taken
    with sigwait, not a handler: a handler could interrupt Event.wait while it holds the event's lock and deadlock in
    set(), and a handler waits for a blocking call on the main thread."""
    signals = _block_stop_signals()  # before the thread starts: it inherits the mask
    worker = threading.Thread(target=run, args=(stop,), name='batch-rounds', daemon=True)
    worker.start()
    while worker.is_alive():
        received = signal.sigtimedwait(signals, 1.0)
        if received is None:
            continue
        if received.si_signo == DUMP_SIGNAL:
            if dump is not None:
                try:
                    dump()
                except Exception:  # noqa: BLE001 - a failed dump never stops the rounds
                    log.exception('Thread dump failed')
        elif received.si_signo in STOP_SIGNALS:
            break
    stop.set()
    worker.join(deadline_seconds)
    exit_process(0)


def main():
    import os
    # First: threads started by the imports below (e.g. analytics consumers) inherit the blocked mask, so a stop
    # signal never takes its default action (immediate end) in one of them.
    _block_stop_signals()
    from postgres.session import _get_session_local
    from routers.evidence import _resolve_stored_path
    from services import process_shutdown, thread_dump
    factory = _get_session_local()
    # kill -USR1 <child> writes its threads' stacks to the same file as for the workers (services/thread_dump.py).
    _serve_until_signalled(threading.Event(), process_shutdown.BACKGROUND_STOP_SECONDS, os._exit,
                           lambda stop: rounds(stop, factory, _resolve_stored_path), dump=thread_dump.write_dump)


if __name__ == '__main__':
    import sys
    # WARNING and up, as in the workers (uvicorn gives this logger no handler); modules with journal() loggers
    # print their INFO lines themselves.
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(name)s: %(message)s')
    if CHILD_FLAG in sys.argv[1:]:
        main()
