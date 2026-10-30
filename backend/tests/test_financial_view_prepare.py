"""The release's warm-up before the restart: started with the service's own settings, never holding a release up."""
import json
import subprocess

from services.financial import view_prepare

# `systemctl show owl-backend-v2.service` on the live host 2026-10-30, drop-in settings included.
SHOWN = '\n'.join((
    'User=conorbowles51',
    'Group=conorbowles51',
    'WorkingDirectory=/home/conorbowles51/app-v3/owl-n4j/backend',
    'Environment=PATH=/home/conorbowles51/app-v3/owl-n4j/.venv/bin:/usr/local/bin:/usr/bin:/bin PYTHONMALLOC=mimalloc '
    'UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN=20 UVICORN_TIMEOUT_WORKER_HEALTHCHECK=120 "SPACED=a b"',
    'EnvironmentFiles=/home/conorbowles51/app-v3/owl-n4j/.env (ignore_errors=no)',
))


class FakeSystem:
    def __init__(self, active_polls=0, shown=SHOWN, journal=''):
        self.calls, self.active_polls, self.shown, self.journal = [], active_polls, shown, journal

    def __call__(self, argv):
        self.calls.append(argv)
        out, code = '', 0
        if argv[:2] == ['systemctl', 'show']:
            out = self.shown
        elif argv[:2] == ['systemctl', 'is-active']:
            code = 0 if self.active_polls > 0 else 3
            self.active_polls -= 1
        elif argv[0] == 'journalctl':
            out = self.journal
        return subprocess.CompletedProcess(argv, code, out, '')


def test_the_prepare_unit_carries_every_service_setting_the_identity_reads():
    argv = view_prepare.prepare_command(view_prepare.service_settings(FakeSystem()))
    properties = [arg.split('=', 1)[1] for arg in argv if arg.startswith('--property=')]
    for assignment in ('PATH=/home/conorbowles51/app-v3/owl-n4j/.venv/bin:/usr/local/bin:/usr/bin:/bin',
                       'PYTHONMALLOC=mimalloc', 'UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN=20',
                       'UVICORN_TIMEOUT_WORKER_HEALTHCHECK=120', 'SPACED=a b'):
        assert 'Environment=' + assignment in properties
    assert 'EnvironmentFile=/home/conorbowles51/app-v3/owl-n4j/.env' in properties
    assert 'User=conorbowles51' in properties and 'Group=conorbowles51' in properties
    assert 'WorkingDirectory=/home/conorbowles51/app-v3/owl-n4j/backend' in properties
    assert 'RuntimeMaxSec=%d' % view_prepare.PREPARE_CAP_SECONDS in properties
    assert argv[-3:] == ['/bin/bash', '-lc', 'exec python -m services.financial.view_warmup --prepare']


def test_unreadable_service_settings_start_nothing(tmp_path):
    system = FakeSystem(shown='User=\n')
    state = tmp_path / 'state.json'
    assert view_prepare.start(log=str(tmp_path / 'log'), run=system, state=str(state)) == 0
    assert not state.exists()
    assert not any(call[0] == 'systemd-run' for call in system.calls)
    assert 'prepare: not started' in (tmp_path / 'log').read_text()


def test_a_finished_prepare_reports_its_summary(tmp_path):
    state = tmp_path / 'state.json'
    state.write_text(json.dumps(dict(started=1000.0)))
    system = FakeSystem(active_polls=2, journal='INFO x\nprepare: 63 views warmed in 312 s (0 failed, code 0123)\n')
    now = iter(range(1100, 1200))
    view_prepare.wait(log=str(tmp_path / 'log'), run=system, state=str(state), clock=lambda: next(now),
                      sleep=lambda s: None)
    logged = (tmp_path / 'log').read_text()
    assert 'prepare: 63 views warmed in 312 s' in logged and 'prepare: release waited' in logged
    assert not any(call[:2] == ['systemctl', 'stop'] for call in system.calls)
    assert not state.exists()


def test_a_capped_prepare_is_stopped_and_the_release_goes_on(tmp_path):
    state = tmp_path / 'state.json'
    state.write_text(json.dumps(dict(started=1000.0)))
    system = FakeSystem(active_polls=10 ** 6)
    now = iter(range(1000, 10 ** 6, 50))
    assert view_prepare.wait(log=str(tmp_path / 'log'), run=system, state=str(state), cap=600,
                             clock=lambda: next(now), sleep=lambda s: None) == 0
    assert ['systemctl', 'stop', view_prepare.UNIT] in system.calls
    assert 'prepare: capped after 6' in (tmp_path / 'log').read_text()


def test_no_prepare_for_this_release_waits_for_nothing(tmp_path):
    system = FakeSystem(active_polls=10 ** 6)
    assert view_prepare.wait(run=system, state=str(tmp_path / 'absent.json')) == 0
    assert system.calls == []
