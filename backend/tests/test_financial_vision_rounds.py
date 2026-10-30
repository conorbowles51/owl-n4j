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
