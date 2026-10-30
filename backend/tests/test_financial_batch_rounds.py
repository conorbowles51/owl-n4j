"""Batch upkeep rounds run in one child process per host, not in the workers serving requests."""
import asyncio
import fcntl
import os
import pathlib
import signal
import subprocess
import sys
import threading
import time

import pytest

from services.financial import batch_rounds, import_batches, vision_rounds

BACKEND = str(pathlib.Path(batch_rounds.__file__).resolve().parents[2])


@pytest.fixture
def lock_dir(tmp_path, monkeypatch):
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path))
    monkeypatch.setattr(batch_rounds, 'RETRY_SECONDS', 0.05)
    return tmp_path


def _stub_steps(monkeypatch, calls, fail=()):
    """Every group's steps replaced by recorders (``fail``: step names that raise)."""
    groups = []
    for name, every, first, steps, failure in batch_rounds.GROUPS:
        def make(step_name):
            def step(factory, resolve_path):
                calls.append(step_name)
                if step_name in fail:
                    raise RuntimeError('synthetic failure')
            return step
        groups.append((name, every, first, tuple(make(step.__name__) for step in steps), failure))
    monkeypatch.setattr(batch_rounds, 'GROUPS', tuple(groups))


def test_every_round_the_worker_loop_ran_is_in_a_group():
    names = [step.__name__ for _, _, _, steps, _ in batch_rounds.GROUPS for step in steps]
    assert names == ['_auto_read', '_reader_release', '_held_reprepare', '_reader_gaps', '_refresh_readiness',
                     '_sweep_save', '_autofill_reapply', '_sweep_backlog']
    first = {name: delay for name, _, delay, _, _ in batch_rounds.GROUPS}
    assert first == dict(auto_read=0, reader_release=60, held_reprepare=60, reader_gaps=60, readiness=60)
    every = {name: interval() for name, interval, _, _, _ in batch_rounds.GROUPS}
    from services.financial import reader_gaps
    assert every == dict(auto_read=10, reader_release=120, held_reprepare=120, reader_gaps=reader_gaps.SWEEP_SECONDS,
                         readiness=60)


def test_the_worker_loop_no_longer_runs_the_rounds(monkeypatch):
    """The worker's own loop turns batches and precomputes its review queue; the sweeps are not called from it."""
    import inspect
    source = inspect.getsource(import_batches._turns_forever)
    for name in ('auto_read', 'reader_release', 'held_reprepare', 'reader_gaps', 'refresh_stale_readiness',
                 'sweep_save', 'autofill_reapply', 'sweep_backlog'):
        assert name not in source
    assert 'prewarm' in source  # fills this worker's in-memory queue cache


def test_with_a_lock_location_the_worker_runs_the_child_not_the_steps(lock_dir, monkeypatch):
    calls, started = [], []
    _stub_steps(monkeypatch, calls)

    async def child_forever():
        started.append(1)
        await asyncio.sleep(3600)
    monkeypatch.setattr(batch_rounds, 'run_in_child_forever', child_forever)

    async def run():
        task = asyncio.create_task(batch_rounds.rounds_forever(lambda: 'factory', lambda p: p,
                                                               import_batches._finish_atomic))
        await asyncio.sleep(0.3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    assert started == [1] and calls == []


def test_without_a_lock_location_the_worker_runs_the_steps_itself(monkeypatch):
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', '')
    calls = []
    _stub_steps(monkeypatch, calls)
    monkeypatch.setattr(batch_rounds, 'PAUSE_SECONDS', 0.01)

    async def run():
        task = asyncio.create_task(batch_rounds.rounds_forever(lambda: 'factory', lambda p: p,
                                                               import_batches._finish_atomic))
        await asyncio.sleep(0.3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    assert calls and set(calls) == {'_auto_read'}  # the others first run 60 s after start


def test_child_loop_runs_due_groups_and_a_failed_step_ends_only_its_group(monkeypatch):
    calls = []
    _stub_steps(monkeypatch, calls, fail={'_sweep_save'})
    monkeypatch.setattr(batch_rounds, 'PAUSE_SECONDS', 0.01)
    real = batch_rounds.Schedule.__init__
    monkeypatch.setattr(batch_rounds.Schedule, '__init__', lambda self, now=None: real(self, time.monotonic() - 61))
    stop = threading.Event()
    threading.Timer(0.3, stop.set).start()
    batch_rounds.rounds(stop, factory='factory', resolve_path=lambda p: p)
    # The readiness group stopped at the failure; nothing else is due again within 0.3 s.
    assert calls == ['_auto_read', '_reader_release', '_held_reprepare', '_reader_gaps', '_refresh_readiness',
                     '_sweep_save']


def test_a_stop_lets_the_running_step_finish_and_starts_no_other(monkeypatch):
    calls = []
    stop = threading.Event()

    def slow(factory, resolve_path):
        calls.append('slow-start')
        stop.set()  # the stop arrives while this step runs
        time.sleep(0.1)
        calls.append('slow-end')

    def after(factory, resolve_path):
        calls.append('after')
    monkeypatch.setattr(batch_rounds, 'GROUPS', (('g', lambda: 60, 0, (slow, after), 'failed'),))
    batch_rounds.rounds(stop, factory='factory', resolve_path=lambda p: p)
    assert calls == ['slow-start', 'slow-end']


def test_a_signal_stops_the_rounds_thread_and_ends_the_process_after_the_deadline():
    """A step that outlives the deadline does not keep the process: it ends anyway (its transaction rolls back)."""
    ended, entered = [], threading.Event()

    def run(stop):
        entered.set()
        time.sleep(5)  # a step that does not finish in time
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, [])

    main = threading.main_thread().ident

    def send():
        entered.wait(5)
        signal.pthread_kill(main, signal.SIGTERM)
    threading.Thread(target=send, daemon=True).start()
    started = time.monotonic()
    try:
        batch_rounds._serve_until_signalled(threading.Event(), 0.2, ended.append, run)
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)
    assert ended == [0] and time.monotonic() - started < 3


def test_the_rounds_run_in_a_child_holding_the_batch_lock(lock_dir, monkeypatch):
    seen = lock_dir / 'seen'
    script = ("import fcntl, os, sys; lock = open(sys.argv[1] + '/batch-rounds.lock', 'a')\n"
              "try:\n    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); held = 'free'\n"
              "except OSError:\n    held = 'held'\n"
              "open(sys.argv[1] + '/seen', 'a').write(f'{os.getpid()} {held}\\n')")
    monkeypatch.setattr(batch_rounds, '_child_command', lambda: [sys.executable, '-c', script, str(lock_dir)])

    async def run():
        task = asyncio.create_task(batch_rounds.run_in_child_forever())
        for _ in range(200):
            await asyncio.sleep(0.05)
            if seen.exists() and len(seen.read_text().splitlines()) >= 2:
                break
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    lines = [line.split() for line in seen.read_text().splitlines()]
    assert len(lines) >= 2  # an ended child is started again
    assert all(int(pid) != os.getpid() and held == 'held' for pid, held in lines)
    assert vision_rounds._take_lock(batch_rounds.LOCK_NAME) is not None  # released when the worker stops
    assert vision_rounds._take_lock() is not None  # a different lock from the page-image rounds


def test_no_child_while_another_worker_holds_the_lock(lock_dir, monkeypatch):
    started = []
    monkeypatch.setattr(batch_rounds, '_child_command', lambda: started.append(1) or [sys.executable, '-c', ''])

    async def run():
        task = asyncio.create_task(batch_rounds.run_in_child_forever())
        await asyncio.sleep(0.4)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    with open(lock_dir / 'batch-rounds.lock', 'a') as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        asyncio.run(run())
    assert started == []


def test_stopping_the_worker_loop_stops_the_rounds_task(monkeypatch):
    stopped = []

    async def rounds_forever(*args):
        try:
            await asyncio.sleep(3600)
        finally:
            stopped.append(1)

    async def turns_forever(*args):
        await asyncio.sleep(3600)

    async def vision_forever(resolve_path):
        await asyncio.sleep(3600)
    monkeypatch.setattr(batch_rounds, 'rounds_forever', rounds_forever)
    monkeypatch.setattr(import_batches, '_turns_forever', turns_forever)
    monkeypatch.setattr(import_batches, '_vision_forever', vision_forever)

    async def run():
        task = asyncio.create_task(import_batches.run_batches_forever())
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    assert stopped == [1]


def test_the_real_child_stops_on_sigterm_after_its_running_step(tmp_path):
    """python -m services.financial.batch_rounds --lock-held with stubbed steps: SIGTERM mid-step lets the step
    finish, starts no further step, and the process exits 0."""
    log = tmp_path / 'log'
    stub = ("import sys, time; sys.path.insert(0, '.')\n"
            "import postgres.session as s; s._get_session_local = lambda: None\n"
            "import routers.evidence\n"
            "from services.financial import batch_rounds as b\n"
            "def slow(f, r):\n"
            "    open(sys.argv[1], 'a').write('start\\n'); time.sleep(1.5); open(sys.argv[1], 'a').write('end\\n')\n"
            "def after(f, r):\n"
            "    open(sys.argv[1], 'a').write('after\\n')\n"
            "b.GROUPS = (('g', lambda: 60, 0, (slow, after), 'failed'),)\n"
            "b.main()\n")
    child = subprocess.Popen([sys.executable, '-c', stub, str(log)], cwd=BACKEND)
    for _ in range(1200):
        if log.exists() and 'start' in log.read_text():
            break
        time.sleep(0.1)
    child.send_signal(signal.SIGTERM)
    assert child.wait(timeout=30) == 0
    assert log.read_text().split() == ['start', 'end']


def test_the_child_command_starts_the_rounds_module():
    command = batch_rounds._child_command()
    assert command[1:] == ['-m', 'services.financial.batch_rounds', batch_rounds.CHILD_FLAG]
    # Without the flag the module only imports: proves it starts in a fresh process.
    done = subprocess.run([sys.executable, '-m', 'services.financial.batch_rounds'], cwd=BACKEND,
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]


def test_thread_dump_signals_do_not_stop_the_rounds_process():
    """Repeated SIGUSR1 while the rounds thread is busy: each is a dump, never a stop (review 2026-10-30: a Python
    handler interrupting sigtimedwait made it return garbage that read as a stop)."""
    dumps, ended, sent = [], [], threading.Event()

    def run(stop):
        while not stop.is_set():
            sorted(str(i) for i in range(5000))

    def dump():
        dumps.append(1)
        time.sleep(0.05)
    main = threading.main_thread().ident

    def send():
        for _ in range(40):
            signal.pthread_kill(main, signal.SIGUSR1)
            time.sleep(0.03)
        sent.set()
        time.sleep(1.5)
        signal.pthread_kill(main, signal.SIGTERM)
    # Blocked before the sender starts (as main() does before anything else), so none takes its default action.
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, [signal.SIGUSR1, signal.SIGTERM, signal.SIGINT])
    threading.Thread(target=send, daemon=True).start()
    try:
        batch_rounds._serve_until_signalled(threading.Event(), 2, ended.append, run, dump=dump)
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)
    assert sent.is_set()  # still running after every dump signal; ended only by the SIGTERM
    assert ended == [0] and len(dumps) >= 1


def test_every_thread_of_the_child_starts_with_stop_and_dump_signals_blocked(tmp_path):
    """Threads started while the package imports, before main() runs, took SIGUSR1's default action and ended the
    live process (2026-10-30 16:02, status -10). The launcher blocks the signals before exec."""
    out = tmp_path / 'masks'
    script = ("import sys, threading, time, glob\n"
              "threading.Thread(target=time.sleep, args=(5,), daemon=True).start()  # as an import would\n"
              "time.sleep(0.2)\n"
              "masks = [int(open(t + '/status').read().split('SigBlk:')[1].split()[0], 16)\n"
              "         for t in glob.glob('/proc/self/task/*')]\n"
              "open(sys.argv[1], 'w').write(' '.join(map(str, masks)))\n")
    blocked = batch_rounds.STOP_SIGNALS + (batch_rounds.DUMP_SIGNAL,)
    asyncio.run(vision_rounds._run_child([sys.executable, '-c', script, str(out)], 'test', 5,
                                         blocked_signals=blocked))
    masks = [int(mask) for mask in out.read_text().split()]
    assert len(masks) >= 2
    for mask in masks:
        assert all(mask & (1 << (int(number) - 1)) for number in blocked)


def test_the_batch_child_is_started_with_the_signals_blocked(lock_dir, monkeypatch):
    seen = []

    async def run_child(command, label, stop_seconds, blocked_signals=()):
        seen.append(set(blocked_signals))
        raise asyncio.CancelledError
    monkeypatch.setattr(vision_rounds, '_run_child', run_child)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(batch_rounds.run_in_child_forever())
    assert seen == [{signal.SIGTERM, signal.SIGINT, signal.SIGUSR1}]
