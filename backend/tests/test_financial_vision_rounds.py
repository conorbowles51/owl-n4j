"""Page-image rounds run in one child process per host, not in the workers serving requests."""
import asyncio
import fcntl
import os
import subprocess
import sys

import pytest

from services.financial import vision_reader, vision_rounds


@pytest.fixture
def lock_dir(tmp_path, monkeypatch):
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path))
    monkeypatch.setattr(vision_reader, 'ENABLED', True)
    monkeypatch.setattr(vision_rounds, 'PAUSE_SECONDS', 0.05)
    return tmp_path


def test_the_rounds_run_in_a_child_holding_the_host_lock(lock_dir, monkeypatch):
    seen = lock_dir / 'seen'
    script = ("import fcntl, os, sys; lock = open(sys.argv[1] + '/vision-rounds.lock', 'a')\n"
              "try:\n    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); held = 'free'\n"
              "except OSError:\n    held = 'held'\n"
              "open(sys.argv[1] + '/seen', 'a').write(f'{os.getpid()} {held}\\n')")
    monkeypatch.setattr(vision_rounds, '_child_command', lambda: [sys.executable, '-c', script, str(lock_dir)])

    async def run():
        task = asyncio.create_task(vision_rounds.run_in_child_forever())
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
    assert vision_rounds._take_lock() is not None  # released when the worker stops


def test_no_child_while_another_worker_holds_the_lock(lock_dir, monkeypatch):
    started = []
    monkeypatch.setattr(vision_rounds, '_child_command', lambda: started.append(1) or [sys.executable, '-c', ''])

    async def run():
        task = asyncio.create_task(vision_rounds.run_in_child_forever())
        await asyncio.sleep(0.4)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    with open(lock_dir / 'vision-rounds.lock', 'a') as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        asyncio.run(run())
    assert started == []


def test_without_a_lock_location_the_worker_runs_the_rounds_itself(monkeypatch):
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', '')
    monkeypatch.setattr(vision_reader, 'ENABLED', True)
    assert asyncio.run(vision_rounds.run_in_child_forever()) is False


def test_a_worker_whose_rounds_run_in_the_child_never_sweeps_itself(lock_dir, monkeypatch):
    from services.financial import import_batches
    swept = []
    monkeypatch.setattr(vision_reader, 'sweep', lambda *a, **k: swept.append(1))

    async def child_runs():
        return True
    monkeypatch.setattr(vision_rounds, 'run_in_child_forever', child_runs)
    asyncio.run(import_batches._vision_forever(lambda path: path))
    assert swept == []


def test_the_child_loop_sweeps_and_logs_a_failed_round(monkeypatch):
    calls = []

    def sweep(factory, resolve_path):
        calls.append(resolve_path)
        if len(calls) == 1:
            raise RuntimeError('synthetic failure')
    monkeypatch.setattr(vision_reader, 'ENABLED', True)
    monkeypatch.setattr(vision_reader, 'sweep', sweep)
    monkeypatch.setattr(vision_rounds, 'PAUSE_SECONDS', 0)
    import postgres.session
    monkeypatch.setattr(postgres.session, '_get_session_local', lambda: 'factory')
    vision_rounds.rounds(stop=lambda: len(calls) >= 2)
    assert len(calls) == 2 and all(callable(path) for path in calls)


def test_the_child_command_starts_the_rounds_module():
    command = vision_rounds._child_command()
    assert command[1:] == ['-m', 'services.financial.vision_rounds', vision_rounds.CHILD_FLAG]
    import pathlib
    backend = pathlib.Path(vision_rounds.__file__).resolve().parents[2]
    # Without the flag the module only imports: proves it starts in a fresh process.
    done = subprocess.run([sys.executable, '-m', 'services.financial.vision_rounds'], cwd=backend,
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]


def test_an_unwritable_lock_location_leaves_the_rounds_to_the_worker(tmp_path, monkeypatch):
    blocked = tmp_path / 'file'
    blocked.write_text('')
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(blocked / 'memo'))  # under a file: cannot be created
    monkeypatch.setattr(vision_reader, 'ENABLED', True)
    assert asyncio.run(vision_rounds.run_in_child_forever()) is False


def test_a_child_that_cannot_be_started_is_tried_again(lock_dir, monkeypatch):
    tries = []

    async def failing():
        tries.append(1)
        raise OSError('fork failed')
    monkeypatch.setattr(vision_rounds, '_run_child', failing)

    async def run():
        task = asyncio.create_task(vision_rounds.run_in_child_forever())
        for _ in range(100):
            await asyncio.sleep(0.05)
            if len(tries) >= 2:
                break
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    assert len(tries) >= 2


def test_the_real_child_runs_its_rounds_and_ends_with_its_worker(tmp_path):
    """The child command itself (python -m ... --lock-held), with the sweep stubbed, and PR_SET_PDEATHSIG."""
    import pathlib
    import signal
    import time
    backend = str(pathlib.Path(vision_rounds.__file__).resolve().parents[2])
    marker = tmp_path / 'swept'
    worker = ("import asyncio, os, sys, runpy; sys.path.insert(0, sys.argv[1])\n"
              "from services.financial import vision_rounds as r\n"
              "stub = (\"import runpy, sys; sys.path.insert(0, '.');\"\n"
              "        \"from services.financial import vision_reader as v; v.ENABLED = True;\"\n"
              "        \"v.sweep = lambda *a, **k: open(sys.argv[1], 'a').write(str(__import__('os').getpid()) + chr(10));\"\n"
              "        \"import services.financial.vision_rounds as r; r.PAUSE_SECONDS = 0.05;\"\n"
              "        \"import postgres.session as s; s._get_session_local = lambda: None;\"\n"
              "        \"import routers.evidence; r.rounds()\")\n"
              "r._child_command = lambda: [sys.executable, '-c', stub, sys.argv[2]]\n"
              "asyncio.run(r._run_child())")
    process = subprocess.Popen([sys.executable, '-c', worker, backend, str(marker)], cwd=backend)
    for _ in range(1200):
        if marker.exists() and len(marker.read_text().split()) >= 2:
            break
        time.sleep(0.1)
    pids = set(marker.read_text().split())
    assert len(pids) == 1  # rounds repeat in one child
    child = int(pids.pop())
    process.send_signal(signal.SIGKILL); process.wait()
    for _ in range(50):
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        os.kill(child, 9)
        raise AssertionError('the rounds child outlived its killed worker')
