"""The release's warm-up before the restart: started with the service's own settings, never holding a release up."""
import json
import subprocess
from pathlib import Path

from services.financial import view_cache, view_prepare

# `systemctl show owl-backend-v2.service` on the live host 2026-10-30, drop-in settings included.
SHOWN = '\n'.join((
    'User=conorbowles51',
    'Group=conorbowles51',
    'WorkingDirectory=/home/conorbowles51/app-v3/owl-n4j/backend',
    'Environment=PATH=/home/conorbowles51/app-v3/owl-n4j/.venv/bin:/usr/local/bin:/usr/bin:/bin PYTHONMALLOC=mimalloc '
    'UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN=20 UVICORN_TIMEOUT_WORKER_HEALTHCHECK=120 "SPACED=a b" PERCENT=50%h',
    'EnvironmentFiles=/home/conorbowles51/app-v3/owl-n4j/.env (ignore_errors=no)',
))


class FakeSystem:
    def __init__(self, active_polls=0, shown=SHOWN, journal='', commit='a' * 40):
        self.calls, self.active_polls, self.shown, self.journal, self.commit = [], active_polls, shown, journal, commit

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
        elif argv[0] == 'git':
            out = self.commit + '\n'
        return subprocess.CompletedProcess(argv, code, out, '')


def test_the_prepare_unit_carries_every_service_setting_the_identity_reads():
    argv = view_prepare.prepare_command(view_prepare.service_settings(FakeSystem()))
    properties = [arg.split('=', 1)[1] for arg in argv if arg.startswith('--property=')]
    for assignment in ('PATH=/home/conorbowles51/app-v3/owl-n4j/.venv/bin:/usr/local/bin:/usr/bin:/bin',
                       'PYTHONMALLOC=mimalloc', 'UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN=20',
                       'UVICORN_TIMEOUT_WORKER_HEALTHCHECK=120', 'SPACED=a b'):
        assert 'Environment=' + assignment in properties or 'Environment="%s"' % assignment in properties
    # systemd splits an unquoted value on its spaces.
    assert 'Environment="SPACED=a b"' in properties
    # systemd-run passes % as written (measured: Environment=P=50%h gives 50%h; 50%%h gives 50%%h).
    assert 'Environment=PERCENT=50%h' in properties
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


def test_a_state_file_left_by_an_earlier_release_is_not_reported(tmp_path):
    state = tmp_path / 'state.json'
    state.write_text(json.dumps(dict(started=1000.0)))
    system = FakeSystem(active_polls=10 ** 6, journal='prepare: 63 views warmed in 312 s\n')
    assert view_prepare.wait(log=str(tmp_path / 'log'), run=system, state=str(state), clock=lambda: 1000.0 + 86400,
                             sleep=lambda s: None) == 0
    assert system.calls == [] and not (tmp_path / 'log').exists() and not state.exists()


def test_the_release_waits_before_the_frontend_switches_and_after_dependencies_are_installed():
    # The frontend is built aside and never stopped (48035271); the wait comes before the build switch and restart.
    script = (Path(__file__).resolve().parents[2] / 'deploy' / 'deploy.sh').read_text()
    wait = script.index('"${PREPARE_VIEWS}" wait')
    assert script.index('step "Installing backend dependencies"') < wait
    assert wait < script.index('frontend_switch "${FRONTEND_ID}"')
    assert wait < script.index('restart_backend_bounded; then')
    assert 'services/financial/view_prepare.py' in script


def test_the_release_warm_up_unit_has_the_service_identity(monkeypatch):
    # systemd names each unit's own cgroup here (measured 2026-10-30: the only difference between the service and
    # a warm-up run with the service's user, environment file and settings in a unit of its own).
    monkeypatch.setenv('MEMORY_PRESSURE_WATCH', '/sys/fs/cgroup/system.slice/owl-backend-v2.service/memory.pressure')
    monkeypatch.setenv('MEMORY_PRESSURE_WRITE', 'c29tZSAyMDAwMDAgMjAwMDAwMAA=')
    service = view_cache._identity_now()
    assert service is not None
    monkeypatch.setenv('MEMORY_PRESSURE_WATCH', '/sys/fs/cgroup/system.slice/loupe-financial-prepare.service/memory.pressure')
    assert view_cache._identity_now() == service
    monkeypatch.setenv('PYTHONMALLOC', 'not the service setting')
    assert view_cache._identity_now() != service


def test_a_prepare_records_the_code_it_computes_and_follows_a_later_fetch(tmp_path):
    state = tmp_path / 'state.json'
    system = FakeSystem(commit='5f7e69f3' + '0' * 32)
    view_prepare.start(log=str(tmp_path / 'log'), run=system, state=str(state))
    assert json.loads(state.read_text())['commit'] == '5f7e69f3' + '0' * 32
    started = sum(call[0] == 'systemd-run' for call in system.calls)
    view_prepare.follow(log=str(tmp_path / 'log'), run=system, state=str(state))
    assert sum(call[0] == 'systemd-run' for call in system.calls) == started  # same code: nothing
    system.commit = '9ff80b1f' + '0' * 32  # deploy.sh fetched other code
    view_prepare.follow(log=str(tmp_path / 'log'), run=system, state=str(state))
    assert sum(call[0] == 'systemd-run' for call in system.calls) == started + 1
    assert json.loads(state.read_text())['commit'].startswith('9ff80b1f')
    assert 'code changed to 9ff80b1f' in (tmp_path / 'log').read_text()


def test_follow_without_a_prepare_starts_nothing(tmp_path):
    system = FakeSystem()
    assert view_prepare.follow(run=system, state=str(tmp_path / 'absent.json')) == 0
    assert system.calls == []


def test_deploy_follows_its_own_fetch_before_the_party_gate():
    script = (Path(__file__).resolve().parents[2] / 'deploy' / 'deploy.sh').read_text()
    follow = script.index('view_prepare.py" follow')
    assert script.index('NEW_COMMIT="$(git rev-parse HEAD)"') < follow < script.index('PARTY_GATE=')


def test_a_prepare_skipped_for_migrations_runs_again_after_them(tmp_path):
    # Release 3745be94 (2026-10-31 02:36): 'prepare: skipped, database migrations pending', then a cold start.
    state, marker = tmp_path / 'state.json', tmp_path / 'after-migrations'
    state.write_text(json.dumps(dict(started=1000.0)))
    skipped = FakeSystem(journal='prepare: skipped, database migrations pending (20261031_batches_compact)\n')
    now = iter(range(1000, 2000))
    view_prepare.wait(log=str(tmp_path / 'log'), run=skipped, state=str(state), clock=lambda: next(now),
                      sleep=lambda s: None, after_migrations_marker=str(marker))
    assert marker.exists()

    prepared = FakeSystem(active_polls=1, journal='prepare: 119 views warmed in 240 s (0 failed, 3 processes, code 0)\n')
    view_prepare.after_migrations(log=str(tmp_path / 'log'), run=prepared, state=str(state), marker=str(marker),
                                  clock=lambda: next(now), sleep=lambda s: None)
    logged = (tmp_path / 'log').read_text()
    assert 'prepare: migrations applied; preparing the views now' in logged
    assert 'prepare: 119 views warmed in 240 s' in logged
    assert any(call[:1] == ['systemd-run'] for call in prepared.calls)
    assert not marker.exists() and not state.exists()


def test_after_migrations_does_nothing_when_the_prepare_ran(tmp_path):
    state, marker = tmp_path / 'state.json', tmp_path / 'after-migrations'
    state.write_text(json.dumps(dict(started=1000.0)))
    view_prepare.wait(run=FakeSystem(journal='prepare: 119 views warmed in 240 s\n'), state=str(state),
                      clock=lambda: 1100.0, sleep=lambda s: None, after_migrations_marker=str(marker))
    assert not marker.exists()
    system = FakeSystem()
    assert view_prepare.after_migrations(run=system, state=str(state), marker=str(marker)) == 0
    assert system.calls == []


def test_the_release_prepares_again_after_its_migrations_and_before_the_restart():
    script = (Path(__file__).resolve().parents[2] / 'deploy' / 'deploy.sh').read_text()
    migrate = script.index('alembic" upgrade head')
    again = script.index('"${PREPARE_VIEWS}" after-migrations')
    assert migrate < again < script.index('restart_backend_bounded; then')
    assert script.index('PREPARE_VIEWS="') < migrate


def test_a_marker_left_by_an_earlier_release_is_cleared_by_the_next_wait(tmp_path):
    marker = tmp_path / 'after-migrations'
    marker.write_text('prepare: skipped, database migrations pending (old)\n')
    view_prepare.wait(run=FakeSystem(), state=str(tmp_path / 'absent.json'), after_migrations_marker=str(marker))
    assert not marker.exists()
