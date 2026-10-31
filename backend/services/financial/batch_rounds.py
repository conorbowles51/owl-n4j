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

The ledger graph follow-ups (graph_followup) run here too, in a thread of their own: run in the workers, each
worker ran its own drift scan and its own projection of the same case (one d5b330d1 snapshot: about 49 CPU-s and
3.5 GB transient memory per worker). The workers hand their requests over as files.

Two host-wide sweeps run here too, in a third thread (HOST_SWEEPS): closing abandoned ingestion runs (run_reaper)
and giving uncategorised payments a category (payment_categories). In the workers both ran in each worker: the
category sweep asked the model about the same new payments once per worker (journal 2026-10-28 05:58-06:08: both
workers, the same case, 10 s apart). Their own thread keeps a model call of several minutes from holding back the
batch rounds. The loops that keep per-worker state stay in the workers: the upload chunk cache, the platform-update
status, the cache warm-ups, the loop-lag probe, the identity sweep (woken in process by the worker's own requests)
and deployment recovery (it starts readings through the worker's evidence pipeline).

The review-queue precompute stays in the workers: it fills their in-memory queue cache (review_queue.prewarm).
Without a lock location the rounds, the host sweeps and the graph follow-ups run in the worker as before.
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


def _run_reaper(factory, resolve_path):
    # Ingestion runs left 'running' by a process killed before it recorded an end are closed as failed.
    from datetime import timedelta
    from config import FINANCIAL_RUN_REAP_INTERVAL_SECONDS, FINANCIAL_RUN_STALE_AFTER_HOURS
    from services.financial.run_reaper import _report, reap_stale_runs
    older_than = timedelta(hours=FINANCIAL_RUN_STALE_AFTER_HOURS)
    # As reap_stale_runs_forever refused to start: a non-positive age would close every run the moment it started.
    if older_than <= timedelta(0) or FINANCIAL_RUN_REAP_INTERVAL_SECONDS <= 0:
        raise ValueError(f'FINANCIAL_RUN_STALE_AFTER_HOURS ({FINANCIAL_RUN_STALE_AFTER_HOURS}) and '
                         f'FINANCIAL_RUN_REAP_INTERVAL_SECONDS ({FINANCIAL_RUN_REAP_INTERVAL_SECONDS}) must be '
                         'positive; no run was closed')
    _report(reap_stale_runs(older_than=older_than), older_than)


def _payment_categories(factory, resolve_path):
    # Current payments without a category get one: rules first, then the model (once per host, not per worker).
    from services.financial.payment_categories import sweep_once
    sweep_once()


def _run_reaper_seconds():
    from config import FINANCIAL_RUN_REAP_INTERVAL_SECONDS
    # A non-positive setting is refused by _run_reaper (logged); it is not retried every pause.
    return FINANCIAL_RUN_REAP_INTERVAL_SECONDS if FINANCIAL_RUN_REAP_INTERVAL_SECONDS > 0 else 300


def _payment_categories_seconds():
    from services.financial.payment_categories import SWEEP_SECONDS
    return SWEEP_SECONDS


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


# The host-wide sweeps, in a thread of their own in the child (same shape as GROUPS; the first delays as in the
# workers: the reaper at once, the category sweep after 60 s).
HOST_SWEEPS = (
    ('run_reaper', _run_reaper_seconds, 0, (_run_reaper,),
     'Sweep for abandoned financial ingestion runs failed'),
    ('payment_categories', _payment_categories_seconds, 60, (_payment_categories,),
     'Category sweep failed'),
)


class Schedule:
    """When each group runs next (monotonic seconds). ``groups``: GROUPS unless given."""

    def __init__(self, now=None, groups=None):
        now = time.monotonic() if now is None else now
        self.groups = GROUPS if groups is None else groups
        self.next = {name: now + first for name, _, first, _, _ in self.groups}

    def due(self):
        """The groups due now, each moved to its next time as it is handed out (as the worker loop did)."""
        for name, every, _, steps, failure in self.groups:
            now = time.monotonic()
            if now >= self.next[name]:
                try:
                    interval = every()
                except Exception:  # noqa: BLE001 - one bad interval never ends the thread running the others
                    log.exception('Interval for %s could not be read; trying again in %s s', name, RETRY_SECONDS)
                    interval = RETRY_SECONDS
                self.next[name] = now + interval
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


def decide_child_mode():
    """Once per worker, before its loops start: True when the rounds run in the host's child (there is a lock
    location). The ledger graph follow-ups then run there too: this worker hands its requests to the child
    (graph_followup.hand_off_to) and its batch turn no longer runs them. If the hand-off cannot be set up, the
    worker keeps running its follow-ups (as the child does): the same projection twice, never none."""
    from services.financial import graph_followup, vision_rounds
    if not vision_rounds._lock_usable(LOCK_NAME):
        return False
    try:
        graph_followup.hand_off_to(graph_followup.hand_off_directory(vision_rounds._lock_directory()))
    except Exception:  # noqa: BLE001
        log.exception('Graph follow-up requests could not be handed to the batch rounds; this worker runs them')
    return True


async def rounds_forever(factory_source, resolve_path, finish_atomic, child=None):
    """The rounds: in the host's child process when there is a lock location (this worker starts it whenever it
    holds the lock), otherwise in this worker every ``PAUSE_SECONDS``. ``child``: decide_child_mode's answer, if
    already taken."""
    from services.financial import vision_rounds
    if child is None:
        child = await asyncio.to_thread(vision_rounds._lock_usable, LOCK_NAME)
    if child:
        await run_in_child_forever()
        return
    schedule = Schedule(groups=GROUPS + HOST_SWEEPS)
    while True:
        try:
            await run_in_worker(factory_source(), resolve_path, finish_atomic, schedule)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('Financial batch processing interrupted; will resume')
        await asyncio.sleep(PAUSE_SECONDS)


# The child's first statement blocks the stop and dump signals, before any package import: threads started while
# the package imports (before main()) otherwise keep an empty mask and take a signal's default action, an immediate
# end (live 2026-10-30 16:02 and 16:13, status -10). Blocking it in the launcher is not enough: the workers' event
# loop (uvloop/libuv) clears the mask of a process it starts (measured: SigBlk 0 under uvloop, 0x200 under asyncio).
BOOTSTRAP = ("import signal, runpy; signal.pthread_sigmask(signal.SIG_BLOCK, (signal.SIGTERM, signal.SIGINT, "
             "signal.SIGUSR1)); runpy.run_module({module!r}, run_name='__main__', alter_sys=True)")


def _bootstrap_command(module, *arguments):
    import sys
    return [sys.executable, '-c', BOOTSTRAP.format(module=module), *arguments]


def _child_command():
    return _bootstrap_command('services.financial.batch_rounds', CHILD_FLAG)


async def run_in_child_forever():
    """Never returns: this worker runs the child whenever it holds the host lock, and tries again after a pause."""
    from services import process_shutdown
    from services.financial import vision_rounds
    while True:
        lock = await asyncio.to_thread(vision_rounds._take_lock, LOCK_NAME)
        if lock is not None:
            with lock:
                try:
                    await vision_rounds._run_child(_child_command(), 'Batch rounds',
                                                   process_shutdown.BACKGROUND_STOP_SECONDS)
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001 - e.g. the fork failed: tried again after the pause
                    log.exception('Batch rounds process could not be started; trying again after a pause')
        await asyncio.sleep(RETRY_SECONDS)


def rounds(stop, factory=None, resolve_path=None, groups=None):
    """The child's loop: the due groups (GROUPS unless given), a pause, again, until ``stop`` (a threading.Event) is
    set. A step that has started runs to its end; the stop is looked at between steps."""
    if factory is None:
        from postgres.session import _get_session_local
        factory = _get_session_local()
    if resolve_path is None:
        from routers.evidence import _resolve_stored_path
        resolve_path = _resolve_stored_path
    schedule = Schedule() if groups is None else Schedule(groups=groups)
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


GRAPH_FOLLOW_UP_SECONDS = 5


def graph_follow_up_forever(stop, factory=None, graph_session_factory=None, hand_offs=None):
    """The ledger graph follow-ups (graph_followup.serve_round: handed-off requests, the drift scan, due
    projections) every ``GRAPH_FOLLOW_UP_SECONDS`` until ``stop``. In its own thread of the child, beside
    ``rounds``: a whole-case projection (d5b330d1: about 49 CPU-s) does not hold back the batch rounds, and a long
    batch round does not hold back the graph. ``stop`` is looked at between cases and between statements (a
    stopped projection rolls back). A failed round is logged and retried. ``hand_offs``: the directory the workers
    hand their requests to; taken up here (not before the rounds start), so a failure to set it up is retried
    every round and never stops the batch rounds."""
    from services.financial import graph_followup
    while not stop.is_set():
        if hand_offs is not None:
            try:
                graph_followup.serve_hand_offs(hand_offs)
                hand_offs = None
            except Exception:  # noqa: BLE001 - retried next round; the rounds go on meanwhile
                log.exception('Graph follow-up hand-offs could not be taken up; trying again next round')
        try:
            graph_followup.serve_round(factory, graph_session_factory, stop=stop)
        except Exception:  # noqa: BLE001 - retried next round
            log.exception('Financial graph follow-up round failed; it will retry')
        stop.wait(GRAPH_FOLLOW_UP_SECONDS)


def host_sweeps_forever(stop, factory=None, resolve_path=None):
    """HOST_SWEEPS until ``stop``, in a thread of the child beside ``rounds``."""
    rounds(stop, factory, resolve_path, groups=HOST_SWEEPS)


def child_work(stop, factory, resolve_path, hand_offs=None):
    """Everything the child runs: the graph follow-ups and the host sweeps in threads of their own, the rounds in
    this one."""
    graph = threading.Thread(target=graph_follow_up_forever, args=(stop, factory), kwargs=dict(hand_offs=hand_offs),
                             name='graph-follow-up', daemon=True)
    sweeps = threading.Thread(target=host_sweeps_forever, args=(stop, factory, resolve_path), name='host-sweeps',
                              daemon=True)
    graph.start()
    sweeps.start()
    try:
        rounds(stop, factory, resolve_path)
    finally:
        stop.set()
        graph.join()
        sweeps.join()


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
    from services.financial import graph_followup, vision_rounds
    factory = _get_session_local()
    hand_offs = graph_followup.hand_off_directory(vision_rounds._lock_directory())
    # kill -USR1 <child> writes its threads' stacks to the same file as for the workers (services/thread_dump.py).
    _serve_until_signalled(threading.Event(), process_shutdown.BACKGROUND_STOP_SECONDS, os._exit,
                           lambda stop: child_work(stop, factory, _resolve_stored_path, hand_offs), dump=thread_dump.write_dump)


if __name__ == '__main__':
    import sys
    # WARNING and up, as in the workers (uvicorn gives this logger no handler); modules with journal() loggers
    # print their INFO lines themselves.
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(name)s: %(message)s')
    if CHILD_FLAG in sys.argv[1:]:
        main()
