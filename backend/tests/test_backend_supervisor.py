"""deploy/backend_supervisor.py with real uvicorn workers on a throwaway port: the next backend starts beside the old
one on the same listening socket, and nothing about the port changes while they swap."""
import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip('uvicorn', reason='uvicorn is not installed')

DEPLOY = Path(__file__).resolve().parents[2] / 'deploy'
SUPERVISOR = DEPLOY / 'backend_supervisor.py'


def _load():
    spec = importlib.util.spec_from_file_location('backend_supervisor', SUPERVISOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Rig:
    def __init__(self, root, **limits):
        self.root = Path(root)
        self.mode = self.root / 'mode'
        self.mode.write_text('ok')
        self.state = self.root / 'state.json'
        self.listener = socket.socket()
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(512)
        self.port = self.listener.getsockname()[1]
        descriptor = self.listener.fileno()

        def as_fd_three():
            os.dup2(descriptor, 3)
            os.set_inheritable(3, True)

        options = dict(ready=60, commit=60, stop=20, sigint=5)
        options.update(limits)
        env = dict(os.environ, HANDOVER_TEST_MODE=str(self.mode), UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN='20')
        self.process = subprocess.Popen(
            [sys.executable, '-I', str(SUPERVISOR), '--state', str(self.state),
             '--ready-seconds', str(options['ready']), '--commit-seconds', str(options['commit']),
             '--stop-seconds', str(options['stop']), '--sigint-seconds', str(options['sigint']),
             '--leftover-seconds', '1', '--', sys.executable, '-m', 'uvicorn', 'handover_app:app', '--fd', '3',
             '--workers', '2', '--log-level', 'warning'],
            cwd=str(DEPLOY / 'tests'), env=env, preexec_fn=as_fd_three, close_fds=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def ask(self, path='/health', timeout=30):
        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}{path}', timeout=timeout) as response:
            return json.loads(response.read())

    def read(self):
        return json.loads(self.state.read_text())

    def wait_for(self, check, limit=120):
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            try:
                value = check()
                if value:
                    return value
            except (OSError, ValueError):
                pass
            time.sleep(0.05)
        raise AssertionError(f'not reached in {limit} s; state {self.state.read_text() if self.state.exists() else None}')

    def phase(self, *names):
        return self.wait_for(lambda: (self.read().get('handover') or {}).get('phase') in names and self.read()['handover'])

    def serving(self):
        self.wait_for(lambda: self.ask(timeout=5)['status'])
        return self.read()['server_pid']

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(30)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.listener.close()


@pytest.fixture
def rig():
    with tempfile.TemporaryDirectory(dir=os.environ.get('LOUPE_TEST_SCRATCH')) as root:
        made = Rig(root)
        yield made
        made.close()


def hammer(rig, stop, answers, failures):
    while not stop.is_set():
        started = time.monotonic()
        try:
            body = rig.ask(timeout=30)
            answers.append((body['server'], time.monotonic() - started))
        except Exception as error:  # noqa: BLE001 - every failure is the finding
            failures.append(repr(error))
        time.sleep(0.01)


def test_the_new_backend_takes_over_with_no_failed_request_and_no_wait(rig):
    old = rig.serving()
    stop, answers, failures = threading.Event(), [], []
    client = threading.Thread(target=hammer, args=(rig, stop, answers, failures))
    client.start()
    try:
        rig.process.send_signal(signal.SIGUSR2)
        ready = rig.phase('ready')
        assert ready['workers'] == 2
        assert rig.ask()['server'] in (old, ready['new_server_pid'])
        rig.process.send_signal(signal.SIGHUP)
        done = rig.phase('done')
        time.sleep(0.5)
    finally:
        stop.set()
        client.join()
    assert failures == []
    assert done['old_stopped_at'] >= done['stopping_old_at']
    new = done['new_server_pid']
    assert rig.read()['server_pid'] == new
    assert {server for server, _ in answers[-20:]} == {new}
    assert {server for server, _ in answers} == {old, new}
    assert max(seconds for _, seconds in answers) < 2.0
    with pytest.raises(ProcessLookupError):
        os.killpg(old, 0)


def test_a_request_in_flight_on_the_old_backend_finishes(rig):
    old = rig.serving()
    rig.process.send_signal(signal.SIGUSR2)
    rig.phase('ready')
    results = []
    # Several, started just before the commit: a connection may go to either backend during the overlap.
    holders = [threading.Thread(target=lambda: results.append(rig.ask('/slow/3')['server'])) for _ in range(8)]
    for thread in holders:
        thread.start()
    time.sleep(1)
    rig.process.send_signal(signal.SIGHUP)
    rig.phase('done')
    for thread in holders:
        thread.join()
    assert len(results) == 8  # every request answered
    assert old in results  # and at least one of them by the old backend, after its stop began


def test_a_new_backend_that_cannot_start_leaves_the_old_one_serving(rig):
    old = rig.serving()
    # uvicorn respawns a worker that dies at import, so the server stays up and health never comes: the ready limit or
    # the release's abort ends it.
    rig.mode.write_text('broken')
    state = rig.read()
    rig.process.send_signal(signal.SIGQUIT)  # nothing open: ignored
    rig.process.send_signal(signal.SIGUSR2)
    rig.wait_for(lambda: rig.read()['handovers'] == state['handovers'] + 1)
    for _ in range(20):
        assert rig.ask(timeout=10)['server'] == old
        time.sleep(0.05)
    rig.process.send_signal(signal.SIGQUIT)
    failed = rig.phase('failed')
    assert 'aborted' in failed['reason']
    assert rig.read()['server_pid'] == old
    assert rig.ask()['server'] == old
    rig.wait_for(lambda: not _group_alive(failed['new_server_pid']))


def _group_alive(group):
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return False
    return True


def test_an_unhealthy_new_backend_is_stopped_at_the_ready_limit():
    with tempfile.TemporaryDirectory(dir=os.environ.get('LOUPE_TEST_SCRATCH')) as root:
        rig = Rig(root, ready=30)
        try:
            old = rig.serving()
            rig.mode.write_text('unhealthy')
            rig.process.send_signal(signal.SIGUSR2)
            failed = rig.phase('failed')
            assert 'not healthy' in failed['reason']
            assert 'degraded' in failed['reason']
            assert rig.read()['server_pid'] == old
            rig.wait_for(lambda: not _group_alive(failed['new_server_pid']))
            assert {rig.ask()['server'] for _ in range(10)} == {old}
        finally:
            rig.close()


def test_a_release_that_never_commits_leaves_the_old_one_serving():
    with tempfile.TemporaryDirectory(dir=os.environ.get('LOUPE_TEST_SCRATCH')) as root:
        rig = Rig(root, commit=1)
        try:
            old = rig.serving()
            rig.process.send_signal(signal.SIGUSR2)
            failed = rig.phase('failed')
            assert 'no commit' in failed['reason']
            rig.wait_for(lambda: not _group_alive(failed['new_server_pid']))
            assert rig.ask()['server'] == old
        finally:
            rig.close()


def test_a_stop_ends_every_backend(rig):
    rig.serving()
    rig.process.send_signal(signal.SIGUSR2)
    ready = rig.phase('ready')
    old = ready['old_server_pid']
    rig.process.send_signal(signal.SIGTERM)
    assert rig.process.wait(40) == 0
    rig.wait_for(lambda: not _group_alive(old) and not _group_alive(ready['new_server_pid']), limit=20)


def test_the_supervisor_exits_with_the_backend_so_systemd_restarts_it(rig):
    server = rig.serving()
    os.killpg(server, signal.SIGKILL)
    assert rig.process.wait(30) != 0


def test_healthy_means_what_the_release_check_means():
    module = _load()
    good = dict(status='ok', neo4j='connected', evidence_engine='ok', process=dict(one_owner=True))
    assert module.healthy(good)
    assert not module.healthy({**good, 'status': 'degraded'})
    assert not module.healthy({**good, 'neo4j': 'error: unavailable'})
    assert not module.healthy({**good, 'evidence_engine': 'unavailable'})
    assert not module.healthy({**good, 'evidence_engine': 'error: unavailable'})
    # A backend whose rounds would run in every worker (no lock location) must not run beside another.
    assert not module.healthy({**good, 'process': dict(one_owner=False)})
