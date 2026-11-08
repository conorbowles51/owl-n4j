"""Exercise the real release scripts with local, inert service/Git commands.

The real read-only SQL gate still runs. Synthetic jobs arrive between release
stages to check that neither deployment nor rollback replaces their services.
"""
import re
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest


DEPLOY = Path(__file__).resolve().parents[2] / 'deploy'
# The bounded-stop drop-in deploy/ingestion-safety.sh installs.
SHUTDOWN_UNIT = '[Service]\nTimeoutStopSec=90\nEnvironment=UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN=20\n'


@pytest.fixture
def release_sandbox(tmp_path):
    project = tmp_path / 'release'
    for directory in ('deploy/logs', 'backend/postgres', 'frontend_v2', '.venv/bin', 'commands'):
        (project / directory).mkdir(parents=True)
    for name in ('deploy.sh', 'rollback.sh', 'ingestion-safety.sh', 'check_ingestion_idle.py', 'backend-stop.sh', 'git-update.sh',
                 'release-plan.sh', 'frontend-release.sh', 'frontend-server.sh', 'frontend-server.conf',
                 'nginx-loupe-frontend.conf', 'record_release.py', 'backend-socket.sh', 'backend-socket.conf',
                 'backend-handover.sh', 'backend-restart.conf', 'backend_supervisor.py', 'backend-tree.sh',
                 'backend-tree.conf'):
        shutil.copy(DEPLOY / name, project / 'deploy' / name)
    # Exercise real install/mv commands, but target a synthetic unit directory.
    helper = project / 'deploy/ingestion-safety.sh'
    helper.write_text(helper.read_text().replace('/etc/systemd/system/owl-backend-v2.service.d',
        str(project / 'units/owl-backend-v2.service.d')))
    # The desktop sandbox disallows bash's /dev/fd process-substitution log
    # sink. Capture stdout directly; leave all release control flow intact.
    deploy_script = project / 'deploy/deploy.sh'
    deploy_script.write_text(deploy_script.read_text().replace(
        'exec > >(tee -a "${LOG_FILE}") 2>&1', '# Output captured by subprocess.run in this isolated test.').replace(
        'TEE_PID=$!', 'TEE_PID=2147483646  # no tee process in this isolated test'))
    # The fast-forward logic has its own test (deploy/tests/test-git-update.sh);
    # here the update is the inert pull the release stages are ordered around.
    (project / 'deploy/git-update.sh').write_text('update_deploy_checkout() { $RUN_AS git pull --ff-only origin "$1"; }\n')
    # This service installer is not under test, and must never touch the host.
    (project / 'deploy/install-frontend-service.sh').write_text('#!/bin/bash\nexit 0\n')
    # The Chroma settings step (bc6570d3a) is not under test, and the real script writes to the live
    # Chroma on 127.0.0.1 (--apply); the sandbox gets an inert stand-in like the installer above.
    (project / 'deploy/chroma-settings.sh').write_text('#!/bin/bash\nexit 0\n')
    (project / '.env').write_text('API_PORT=8002\nFRONTEND_PORT=5174\n')
    # The checked-in choice of server may be nginx; these tests cover the vite preview path, and nginx paths point
    # into the sandbox so a run as root can never install a site on the host.
    (project / 'deploy/frontend-server.conf').write_text('vite\n')
    (project / 'deploy/logs/.last-good-commit').write_text('previous-safe-revision')
    (project / 'backend/postgres/__init__.py').write_text('')
    (project / 'backend/postgres/session.py').write_text(
        'import os\nfrom sqlalchemy import create_engine\n'
        'def _get_engine():\n    return create_engine("sqlite:///" + os.environ["GATE_DATABASE"])\n'
    )
    database = project / 'jobs.sqlite'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE jobs (status TEXT NOT NULL, paused BOOLEAN NOT NULL)')
    # Service/Git commands are inert. File installs run against the redirected
    # fixture directory. A stub may register a new job or replace the on-disk
    # checker, as a real checkout/build could do mid-release.
    stub = project / 'commands/stub'
    stub.write_text(f'#!{sys.executable}\n' + '''
import json, os, pathlib, sqlite3, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
root = pathlib.Path(os.environ['RELEASE_SANDBOX'])
if name == 'sudo':
    while args and args[0].startswith('-'):
        del args[:2 if args[0] == '-u' else 1]
    os.execvp(args[0], args)
event = ' '.join([name, *args])
if name == 'python':
    event = 'compile' if '-m' in args and 'compileall' in args else 'gate'
with (root / 'events').open('a') as stream:
    stream.write(json.dumps(event) + '\\n')
serving = os.environ.get('SANDBOX_PORT')
if serving and event.split()[0] in ('alembic', 'pip') or serving and event.startswith('docker compose build'):
    # A request reaching the running backend while the release prepares.
    import urllib.error, urllib.request
    try:
        with urllib.request.urlopen('http://127.0.0.1:%s/profile' % serving, timeout=20) as answer:
            seen = [answer.status, answer.read().decode()]
    except urllib.error.HTTPError as error:
        seen = [error.code, error.read().decode()]
    except OSError:
        seen = None  # no backend yet: the first release
    if seen:
        with (root / 'probes').open('a') as stream:
            stream.write(json.dumps(seen) + '\\n')
if os.environ.get('SANDBOX_REAL_GIT') and name == 'git':
    os.execv('/usr/bin/git', ['git', *args])
trigger = os.environ.get('WORK_ARRIVES_AFTER')
if trigger and event.startswith(trigger) and not (root / 'arrived').exists():
    with sqlite3.connect(os.environ['GATE_DATABASE']) as db:
        db.execute("INSERT INTO jobs VALUES ('processing',false)")
    (root / 'arrived').touch()
if name == 'python':
    os.execv(sys.executable, [sys.executable, *args])
elif name == 'git':
    if args[0] == 'rev-parse':
        print('main' if '--abbrev-ref' in args else os.environ.get('REVISION', 'current-revision'))
    if args[0] == 'worktree' and 'add' in args:
        # The build worktree beside the checkout (deploy/frontend-release.sh); its path precedes the revision.
        worktree = pathlib.Path(args[-2])
        (worktree / 'frontend_v2').mkdir(parents=True, exist_ok=True)
        (worktree / '.git').write_text('gitdir: inert')
    if args[0] in ('checkout', 'reset', 'pull'):
        # The captured checker must still run after reverting to older code.
        (root / 'deploy/check_ingestion_idle.py').write_text('raise SystemExit(0)\\n')
elif name == 'id':
    print('1000')
elif name == 'whoami':
    print('release-test')
elif name == 'docker' and args[0] == 'ps':
    print('owl-v2-n4j\\nowl-v2-pg')
elif name == 'curl':
    if os.environ.get('FORCE_HEALTH_FAILURE'):
        print('{}')
    elif ':5174' in args[-1]:
        print('<script src="/assets/app.js"></script>')
    elif os.environ.get('HEALTH_COMMIT'):
        print('{"status":"ok","commit":"%s","commit_clean":%s}' % (os.environ['HEALTH_COMMIT'], os.environ.get('HEALTH_COMMIT_CLEAN', 'true')))
    else:
        print('{"status":"ok"}')
elif name == 'seq':
    if args[-1] != '0':  # one try is enough here; no tries stays no tries
        print('1')
elif name == 'npm' and 'build' in args and '--outDir' in args:
    # A build writes its output where it is told (deploy/frontend-release.sh builds beside the served one).
    out = pathlib.Path(args[args.index('--outDir') + 1])
    (out / 'assets').mkdir(parents=True, exist_ok=True)
    (out / 'index.html').write_text('<script src="/assets/app.js"></script>')
    (out / 'assets/app.js').write_text('app')
elif name == 'systemctl' and serving and 'ControlGroup' in args:
    print('/sandbox')
elif name == 'systemctl' and serving and args[0] == 'start' and 'owl-backend-v2' in args:
    import subprocess
    tree = root / 'units/owl-backend-v2.service.d/70-lx-releaseprep-tree.conf'
    lines = tree.read_text().splitlines() if tree.exists() else []
    folder = next((line.split('=', 1)[1] for line in lines if line.startswith('WorkingDirectory=')), str(root / 'backend'))
    server = subprocess.Popen([sys.executable, 'app.py', serving], cwd=folder, start_new_session=True,
                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (root / 'cgroup/sandbox/cgroup.procs').write_text('%d\\n' % server.pid)
elif name == 'systemctl' and serving and args[0] == 'stop' and 'owl-backend-v2' in args:
    import signal
    for pid in (root / 'cgroup/sandbox/cgroup.procs').read_text().split():
        try:
            os.kill(int(pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
    (root / 'cgroup/sandbox/cgroup.procs').write_text('')
elif name == 'systemctl' and args[:1] == ['show']:
    print('inactive')  # the bounded stop sees the backend stopped at once
elif name == 'systemctl' and args[:1] == ['kill'] and os.environ.get('HANDOVER_ANSWER'):
    state = root / 'deploy/logs/backend-supervisor.json'
    current = json.loads(state.read_text())
    if 'SIGUSR2' in args[1] or 'SIGUSR2' in ' '.join(args):
        current.update(handovers=current['handovers'] + 1,
                       handover=dict(phase=os.environ['HANDOVER_ANSWER'], reason='it did not start'))
    elif 'SIGHUP' in ' '.join(args):
        current['handover']['phase'] = 'done'
    elif 'SIGQUIT' in ' '.join(args):
        current['handover']['phase'] = 'failed'
    state.write_text(json.dumps(current))
''')
    stub.chmod(0o755)
    for name in ('git', 'id', 'whoami', 'sudo', 'docker', 'npm', 'systemctl', 'curl', 'sleep', 'seq', 'flock', 'nginx'):
        (project / 'commands' / name).symlink_to(stub)
    for name in ('python', 'pip', 'alembic'):
        (project / '.venv/bin' / name).symlink_to(stub)
    return project


def run_release(project, script, *, arrives_after=None, initially_active=False, health_failure=False, extra_env=None):
    if initially_active:
        with sqlite3.connect(project / 'jobs.sqlite') as db:
            db.execute("INSERT INTO jobs VALUES ('processing',false)")
    env = {**os.environ, 'PATH': str(project / 'commands') + ':/usr/bin:/bin',
           'RELEASE_SANDBOX': str(project), 'GATE_DATABASE': str(project / 'jobs.sqlite'),
           'FRONTEND_NGINX_SITE': str(project / 'nginx/sites-enabled/loupe-frontend'),
           'FRONTEND_NGINX_AVAILABLE': str(project / 'nginx/sites-available/loupe-frontend'),
           # The held API socket's units go to the sandbox, never the host's /etc/systemd/system.
           'BACKEND_SOCKET_UNIT_DIR': str(project / 'units'),
           # This host's own switch and supervisor copy are not under test.
           'BACKEND_RESTART_SWITCH': str(project / 'no-host-switch'),
           'BACKEND_SUPERVISOR_DIR': str(project / 'supervisor')}
    if arrives_after:
        env['WORK_ARRIVES_AFTER'] = arrives_after
    if health_failure:
        env['FORCE_HEALTH_FAILURE'] = '1'
    env.update(extra_env or {})
    # A hang guard. Every stub is a python start: one plain sandbox release took 476 s at load 110, 5 Nov.
    result = subprocess.run(['bash', str(project / 'deploy' / script), 'previous-safe-revision'],
                            input='y\n', text=True, capture_output=True, env=env, timeout=1800)
    events = [json.loads(line) for line in (project / 'events').read_text().splitlines()]
    return result, events


@pytest.mark.parametrize('script', ['deploy.sh', 'rollback.sh'])
def test_existing_work_blocks_checkout_dependency_and_service_changes(release_sandbox, script):
    result, events = run_release(release_sandbox, script, initially_active=True)
    assert result.returncode == 75, result.stdout + result.stderr
    assert 'Release deferred' in result.stdout + result.stderr
    assert not any(event.startswith(('git pull', 'git checkout', 'git reset', 'pip ', 'npm ', 'docker compose ', 'systemctl restart', 'systemctl start owl-backend', 'systemctl stop --no-block owl-backend')) for event in events)


@pytest.mark.parametrize('script,checkout', [('deploy.sh', 'git pull'), ('rollback.sh', 'git checkout')])
def test_current_gate_survives_checkout_to_revision_with_no_checks(release_sandbox, script, checkout):
    result, events = run_release(release_sandbox, script, arrives_after=checkout)
    assert result.returncode == 75, result.stdout + result.stderr
    assert (release_sandbox / 'deploy/check_ingestion_idle.py').read_text() == 'raise SystemExit(0)\n'
    assert not any(event.startswith(('pip ', 'docker compose ', 'systemctl restart', 'systemctl start owl-backend')) for event in events)


@pytest.mark.parametrize('script', ['deploy.sh', 'rollback.sh'])
def test_work_arriving_during_image_build_blocks_container_replacement(release_sandbox, script):
    result, events = run_release(release_sandbox, script, arrives_after='docker compose build')
    assert result.returncode == 75, result.stdout + result.stderr
    assert 'docker compose build' in events
    assert not any(event.startswith(('docker compose up', 'systemctl restart owl-backend', 'systemctl start owl-backend')) for event in events)
    if script == 'deploy.sh':
        # The frontend is built beside the served one and never stopped before the switch, so a release deferred
        # here leaves the site serving throughout: nothing stopped, nothing to restore.
        assert not any(event.startswith('systemctl stop owl-frontend') for event in events)
        assert 'Deployment exited while the frontend was stopped' not in result.stdout


@pytest.mark.parametrize('script', ['deploy.sh', 'rollback.sh'])
def test_work_arriving_during_container_change_blocks_backend_restart(release_sandbox, script):
    result, events = run_release(release_sandbox, script, arrives_after='docker compose up')
    assert result.returncode == 75, result.stdout + result.stderr
    assert any(event.startswith('docker compose up -d --no-build') for event in events)
    assert 'systemctl start owl-backend-v2' not in events
    assert (release_sandbox / 'units/owl-backend-v2.service.d/ingestion-shutdown.conf').read_text() == SHUTDOWN_UNIT
    assert 'systemctl daemon-reload' in events


def test_automatic_rollback_retains_checks_after_reset(release_sandbox):
    result, events = run_release(release_sandbox, 'deploy.sh', arrives_after='git reset', health_failure=True)
    assert result.returncode == 75, result.stdout + result.stderr
    reset = next(index for index, event in enumerate(events) if event.startswith('git reset'))
    assert events[reset + 1] == 'gate'
    assert not any(event.startswith(('pip ', 'npm ', 'docker compose ', 'systemctl restart', 'systemctl start owl-backend')) for event in events[reset + 1:])


@pytest.mark.parametrize('script', ['deploy.sh', 'rollback.sh'])
def test_release_holds_the_api_port_open_across_the_backend_restart(release_sandbox, script):
    """deploy/backend-socket.conf 'held': the socket unit takes the port after the old backend stopped and before the
    new one starts, so requests wait in its queue instead of being refused (11-14 s per release before)."""
    (release_sandbox / 'units').mkdir(exist_ok=True)
    (release_sandbox / 'units/owl-backend-v2.service').write_text(
        "[Service]\nExecStart=/bin/bash -lc 'exec uvicorn main:app --host 0.0.0.0 --port ${API_PORT:-8002} --workers 2'\n")
    (release_sandbox / 'deploy/backend-socket.conf').write_text('held\n')
    result, events = run_release(release_sandbox, script)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'ListenStream=0.0.0.0:8002' in (release_sandbox / 'units/owl-backend-v2.socket').read_text()
    dropin = (release_sandbox / 'units/owl-backend-v2.service.d/60-lx-release-socket.conf').read_text()
    assert "--fd 3 --workers 2'" in dropin and '--port' not in dropin
    stop = events.index('systemctl stop --no-block owl-backend-v2')
    hold = events.index('systemctl enable --now owl-backend-v2.socket')
    start = events.index('systemctl start owl-backend-v2')
    assert stop < hold < start, events


@pytest.mark.parametrize('script', ['deploy.sh', 'rollback.sh'])
def test_idle_release_still_completes_with_bounded_graceful_shutdown(release_sandbox, script):
    result, events = run_release(release_sandbox, script)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'systemctl start owl-backend-v2' in events
    unit = release_sandbox / 'units/owl-backend-v2.service.d/ingestion-shutdown.conf'
    assert unit.read_text() == SHUTDOWN_UNIT
    assert unit.stat().st_mode & 0o777 == 0o644


def test_shutdown_dropin_installer_uses_real_files_and_fails_before_reload():
    result = subprocess.run(['bash', str(DEPLOY / 'tests/test-ingestion-shutdown.sh')],
        capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'real install checks passed' in result.stdout


RUNNING = 'a' * 40


@pytest.mark.parametrize('clean,health_failure,recorded', [
    ('true', False, True),     # healthy, started from a clean commit: known good
    ('false', False, False),   # local changes to tracked files: not that commit
    ('true', True, False),     # not healthy now: nothing is recorded
])
def test_a_healthy_backend_started_outside_a_deploy_is_recorded_as_last_good(release_sandbox, clean, health_failure, recorded):
    # The gate defers this release before the checkout changes; the record is made before that.
    result, events = run_release(release_sandbox, 'deploy.sh', initially_active=True, health_failure=health_failure,
                                 extra_env={'HEALTH_COMMIT': RUNNING, 'HEALTH_COMMIT_CLEAN': clean})
    assert result.returncode == 75, result.stdout + result.stderr
    last_good = (release_sandbox / 'deploy/logs/.last-good-commit').read_text().strip()
    assert last_good == (RUNNING if recorded else 'previous-safe-revision')
    assert ('recorded as last known-good' in result.stdout) is recorded
    assert not any(event.startswith(('git pull', 'systemctl start owl-backend')) for event in events)


def _party_gate(project, exit_code):
    gate = project / 'backend/benchmarks/statement_automation/party_coverage_gate.py'
    gate.parent.mkdir(parents=True, exist_ok=True)
    for package in (project / 'backend/benchmarks', gate.parent):
        (package / '__init__.py').write_text('')
    gate.write_text(f'import sys\nprint("PARTY COVERAGE GATE: {"FAIL" if exit_code == 1 else "PASS"}")\n'
                    'out = sys.argv[sys.argv.index("--out") + 1]\nopen(out, "w").write("{}")\n'
                    f'raise SystemExit({exit_code})\n')


def test_party_coverage_gate_failure_stops_the_release_before_any_install(release_sandbox):
    _party_gate(release_sandbox, 1)
    result, events = run_release(release_sandbox, 'deploy.sh')
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'Party coverage gate failed' in result.stdout
    assert any(event.startswith('git reset --hard') for event in events)
    assert not any(event.startswith(('pip ', 'npm ', 'docker compose ', 'systemctl restart', 'systemctl stop owl-frontend')) for event in events)
    assert not (release_sandbox / 'deploy/logs/party-coverage-baseline.json').exists()


def test_party_coverage_gate_pass_becomes_the_baseline_after_a_healthy_release(release_sandbox):
    _party_gate(release_sandbox, 0)
    result, events = run_release(release_sandbox, 'deploy.sh')
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'Party coverage gate passed' in result.stdout
    assert (release_sandbox / 'deploy/logs/party-coverage-baseline.json').read_text() == '{}'


RELEASED = 'b' * 40
NO_REPEAT = ('npm ', 'pip ', 'alembic', 'docker compose', 'systemctl restart', 'systemctl stop', 'systemctl start')


def test_a_release_of_the_live_commit_changes_nothing(release_sandbox):
    """Measured 2026-10-30: 37 of 91 releases redeployed the live commit, one of them took the site down 15.5 min."""
    first, _ = run_release(release_sandbox, 'deploy.sh', extra_env={'REVISION': RELEASED})
    assert first.returncode == 0, first.stdout + first.stderr
    assert (release_sandbox / 'deploy/logs/.last-good-commit').read_text().strip() == RELEASED
    (release_sandbox / 'events').write_text('')
    second, events = run_release(release_sandbox, 'deploy.sh', extra_env={'REVISION': RELEASED, 'HEALTH_COMMIT': RELEASED})
    assert second.returncode == 0, second.stdout + second.stderr
    assert 'already live' in second.stdout
    assert not any(event.startswith(NO_REPEAT) for event in events), events


def test_a_frontend_only_release_never_stops_or_restarts_the_backend(release_sandbox):
    first, _ = run_release(release_sandbox, 'deploy.sh', extra_env={'REVISION': RELEASED})
    assert first.returncode == 0, first.stdout + first.stderr
    # Only a setting that reaches the bundle changes (frontend hash); the backend, packages and engine are the same.
    env_file = release_sandbox / '.env'
    env_file.write_text(env_file.read_text() + 'VITE_SOMETHING=2\n')
    (release_sandbox / 'events').write_text('')
    second, events = run_release(release_sandbox, 'deploy.sh', extra_env={'REVISION': RELEASED, 'HEALTH_COMMIT': RELEASED})
    assert second.returncode == 0, second.stdout + second.stderr
    assert 'frontend=run npm=skip pip=skip backend=skip engine=skip' in second.stdout
    assert any(event.startswith('npm run build') for event in events)
    assert not any(event.startswith(('pip ', 'alembic', 'docker compose', 'systemctl stop --no-block owl-backend',
                                     'systemctl start owl-backend', 'systemctl stop owl-backend')) for event in events), events
    current = (release_sandbox.parent / 'loupe-frontend/current').resolve()
    assert (current / 'index.html').exists()


def test_a_manual_rollback_builds_aside_and_switches_like_a_release(release_sandbox):
    """frontend_v2/dist is a link to a read-only build, and nginx may hold the port: rollback.sh must never build in
    the live checkout or restart vite preview by hand."""
    result, events = run_release(release_sandbox, 'rollback.sh')
    assert result.returncode == 0, result.stdout + result.stderr
    builds = [event for event in events if event.startswith('npm run build')]
    assert builds and all('--outDir' in event and '/loupe-frontend/builds/' in event for event in builds), builds
    assert 'systemctl restart owl-frontend-v2' not in events
    dist = release_sandbox / 'frontend_v2/dist'
    assert dist.is_symlink() and dist.resolve() == (release_sandbox.parent / 'loupe-frontend/current').resolve()


def test_nginx_serves_the_site_and_a_frontend_release_then_stops_nothing(release_sandbox):
    (release_sandbox / 'deploy/frontend-server.conf').write_text('nginx\n')
    for directory in ('sites-enabled', 'sites-available'):
        (release_sandbox / 'nginx' / directory).mkdir(parents=True)
    first, events = run_release(release_sandbox, 'deploy.sh', extra_env={'REVISION': RELEASED})
    assert first.returncode == 0, first.stdout + first.stderr
    site = release_sandbox / 'nginx/sites-enabled/loupe-frontend'
    assert site.is_symlink()
    text = site.read_text()
    assert 'listen 5174;' in text and str(release_sandbox.parent / 'loupe-frontend') + '/current' in text
    assert 'proxy_pass http://0.0.0.0:8002;' in text and '@' not in text.split('server {')[1].split('}')[0]
    assert 'systemctl stop owl-frontend-v2' in events and 'systemctl reload nginx' in events
    env_file = release_sandbox / '.env'
    env_file.write_text(env_file.read_text() + 'VITE_SOMETHING=2\n')
    (release_sandbox / 'events').write_text('')
    second, events = run_release(release_sandbox, 'deploy.sh', extra_env={'REVISION': RELEASED, 'HEALTH_COMMIT': RELEASED})
    assert second.returncode == 0, second.stdout + second.stderr
    assert 'the build switch needed no restart' in second.stdout
    assert not any(event.startswith(('systemctl stop owl-frontend', 'systemctl restart owl-frontend',
                                     'systemctl start owl-frontend', 'systemctl reload nginx')) for event in events), events


def _running_under_the_supervisor(project, migrations='none'):
    """The second backend release after the switch: the unit's main process is the supervisor."""
    import hashlib
    (project / 'units').mkdir(exist_ok=True)
    (project / 'units/owl-backend-v2.service').write_text(
        "[Service]\nExecStart=/bin/bash -lc 'exec /venv/bin/uvicorn main:app --host 0.0.0.0 --port ${API_PORT:-8002} --workers 2'\n")
    (project / 'deploy/backend-socket.conf').write_text('held\n')
    (project / 'deploy/backend-restart.conf').write_text('handover\n')
    (project / 'deploy/migration_safety.py').write_text(f'print("{migrations}")\n')
    sha = hashlib.sha256((project / 'deploy/backend_supervisor.py').read_bytes()).hexdigest()
    (project / 'deploy/logs/backend-supervisor.json').write_text(json.dumps(
        dict(pid='inactive', script_sha=sha, handovers=0, handover=dict(phase='done'))))
    (project / 'deploy/logs/.backend-started-unit').write_text(hashlib.sha256((project / '.env').read_bytes()).hexdigest() + '\n')


USR2, HUP, QUIT = ('systemctl kill --kill-whom=main --signal=SIG%s owl-backend-v2' % name for name in ('USR2', 'HUP', 'QUIT'))


def test_a_release_hands_over_without_stopping_the_backend(release_sandbox):
    _running_under_the_supervisor(release_sandbox)
    result, events = run_release(release_sandbox, 'deploy.sh', extra_env={'HANDOVER_ANSWER': 'ready'})
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'systemctl stop --no-block owl-backend-v2' not in events
    assert 'systemctl start owl-backend-v2' not in events
    begin, commit = events.index(USR2), events.index(HUP)
    assert 'gate' in events[begin:commit]  # the ingestion gate again, right before the old backend stops
    assert 'The new backend took over' in result.stdout


def test_a_new_backend_that_fails_leaves_the_old_one_and_undoes_the_release(release_sandbox):
    _running_under_the_supervisor(release_sandbox)
    result, events = run_release(release_sandbox, 'deploy.sh', extra_env={'HANDOVER_ANSWER': 'failed'})
    assert result.returncode == 1, result.stdout + result.stderr
    assert HUP not in events
    assert 'systemctl stop --no-block owl-backend-v2' not in events  # never stopped, not even by the rollback
    assert 'systemctl start owl-backend-v2' not in events
    assert any(e.startswith('git reset --hard') for e in events)
    assert (release_sandbox / 'deploy/logs/.backend-handover-failed').read_text().strip() == 'it did not start'
    assert 'old one is still serving' in result.stdout
    assert 'Health check failed' not in result.stdout


def test_a_failed_handover_keeps_the_record_of_what_runs(release_sandbox):
    _running_under_the_supervisor(release_sandbox)
    components = release_sandbox / 'deploy/logs/.last-good-components'
    components.write_text('backend_commit=the-old-backend\n')
    result, _ = run_release(release_sandbox, 'deploy.sh', extra_env={'HANDOVER_ANSWER': 'failed'})
    assert result.returncode == 1, result.stdout + result.stderr
    assert components.read_text() == 'backend_commit=the-old-backend\n'


def test_after_a_failed_handover_the_next_release_restarts(release_sandbox):
    _running_under_the_supervisor(release_sandbox)
    (release_sandbox / 'deploy/logs/.backend-handover-failed').write_text('earlier\n')
    result, events = run_release(release_sandbox, 'deploy.sh', extra_env={'HANDOVER_ANSWER': 'ready'})
    assert result.returncode == 0, result.stdout + result.stderr
    assert USR2 not in events
    assert 'systemctl stop --no-block owl-backend-v2' in events
    assert not (release_sandbox / 'deploy/logs/.backend-handover-failed').exists()


def test_an_upload_arriving_during_the_start_defers_and_keeps_the_old_backend(release_sandbox):
    _running_under_the_supervisor(release_sandbox)
    result, events = run_release(release_sandbox, 'deploy.sh', arrives_after=USR2,
                                 extra_env={'HANDOVER_ANSWER': 'ready'})
    assert result.returncode == 75, result.stdout + result.stderr
    assert 'Release deferred' in result.stderr + result.stdout
    assert QUIT in events and HUP not in events
    assert 'systemctl stop --no-block owl-backend-v2' not in events
    # The old backend runs from the checkout it started from, whatever is in progress.
    assert any(e.startswith('git reset --hard') for e in events)
    assert not (release_sandbox / 'deploy/logs/.backend-handover-failed').exists()


def test_a_migration_the_old_backend_cannot_live_with_uses_a_restart(release_sandbox):
    _running_under_the_supervisor(release_sandbox, migrations='unsafe r1: op.drop_table')
    result, events = run_release(release_sandbox, 'deploy.sh', extra_env={'HANDOVER_ANSWER': 'ready'})
    assert result.returncode == 0, result.stdout + result.stderr
    assert USR2 not in events
    assert 'systemctl stop --no-block owl-backend-v2' in events
    assert 'op.drop_table' in result.stdout


def test_a_failed_health_check_after_a_handover_rolls_back_with_a_restart(release_sandbox):
    _running_under_the_supervisor(release_sandbox)
    result, events = run_release(release_sandbox, 'deploy.sh', health_failure=True,
                                 extra_env={'HANDOVER_ANSWER': 'ready'})
    assert result.returncode == 1, result.stdout + result.stderr
    assert HUP in events
    assert events.index(HUP) < events.index('systemctl stop --no-block owl-backend-v2')
    # The way back does not depend on the supervisor.
    assert not (release_sandbox / 'units/owl-backend-v2.service.d/65-lx-restartwait-supervisor.conf').exists()


# A backend as the real one is: modules loaded at its start, a module first read by a request, a data file and a child
# process. The commit after this one renames what the lazy module imports, as phone_setup did on 5 Nov.
SERVED_APP = """
import http.server, json, os, subprocess, sys
import helper
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *arguments): pass
    def do_GET(self):
        if self.path == '/up':
            self.send_response(200); self.end_headers(); self.wfile.write(b'{}')
            return
        try:
            import lazy
            with open('zones.json') as stream:
                zones = json.load(stream)['version']
            child = subprocess.run([sys.executable, 'child.py'], capture_output=True, text=True, check=True).stdout.strip()
            code, body = 200, dict(value=lazy.value(), zones=zones, child=child, folder=os.getcwd())
        except Exception as error:
            code, body = 500, dict(error=repr(error))
        self.send_response(code); self.end_headers(); self.wfile.write(json.dumps(body).encode())
http.server.ThreadingHTTPServer(('127.0.0.1', int(sys.argv[1])), Handler).serve_forever()
"""


def _commit_version(project, version, name, branch="main"):
    for file, text in (('helper.py', f'def {name}():\n    return {version}\n'),
                       ('lazy.py', f'from helper import {name}\ndef value():\n    return {name}()\n'),
                       ('child.py', f'print({version})\n'), ('zones.json', json.dumps(dict(version=version)))):
        (project / 'backend' / file).write_text(text)
    subprocess.run(['/usr/bin/git', 'add', '-A'], cwd=project, check=True)
    subprocess.run(['/usr/bin/git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', f'v{version}'], cwd=project, check=True)
    subprocess.run(['/usr/bin/git', 'push', '-q', 'origin', 'main'], cwd=project, check=True)
    return subprocess.run(['/usr/bin/git', 'rev-parse', 'HEAD'], cwd=project, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def real_release(release_sandbox):
    """Real git, a real server process and the real deploy.sh; the host's services stay stubs."""
    import socket
    project = release_sandbox
    (project / 'backend/app.py').write_text(SERVED_APP)
    (project / 'frontend_v2/package.json').write_text('{}')
    (project / 'cgroup/sandbox').mkdir(parents=True)
    (project / 'cgroup/sandbox/cgroup.procs').write_text('')
    (project / '.gitignore').write_text('.env\n.venv\ncommands\ncgroup\nunits\nevents\nprobes\narrived\njobs.sqlite\ndeploy/logs\n'
                                        'nginx\n__pycache__\nfrontend_v2/dist\nfrontend_v2/node_modules\nsupervisor\ndata\n'
                                        'evidence-data\nbackend/logs\n')
    (project / 'events').write_text('')
    origin = project.parent / 'origin.git'
    subprocess.run(['/usr/bin/git', 'init', '-q', '--bare', '-b', 'main', str(origin)], check=True)
    subprocess.run(['/usr/bin/git', 'init', '-q', '-b', 'main'], cwd=project, check=True)
    subprocess.run(['/usr/bin/git', 'remote', 'add', 'origin', str(origin)], cwd=project, check=True)
    (project / 'deploy/logs/.last-good-commit').unlink()
    with socket.socket() as free:
        free.bind(('127.0.0.1', 0))
        port = free.getsockname()[1]
    env = {'SANDBOX_REAL_GIT': '1', 'SANDBOX_PORT': str(port), 'BACKEND_CGROUP_ROOT': str(project / 'cgroup')}
    yield project, env
    for pid in (project / 'cgroup/sandbox/cgroup.procs').read_text().split():
        try:
            os.kill(int(pid), 9)
        except ProcessLookupError:
            pass


def _ask(env, path='/profile'):
    import time
    import urllib.request
    for _ in range(100):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%s%s' % (env['SANDBOX_PORT'], path), timeout=20) as answer:
                return json.loads(answer.read())
        except OSError:
            time.sleep(0.1)
    raise AssertionError('the backend never answered')


def _released_and_waiting_for_the_next(project, env):
    """The first release on trees, then the next commit on origin: the state every later release starts in."""
    first = _commit_version(project, 1, 'old_name')
    result, _ = run_release(project, 'deploy.sh', extra_env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    _ask(env, '/up')  # not the lazy module: it stays unread until a request during the next release
    (project / 'probes').unlink(missing_ok=True)
    (project / 'events').write_text('')
    subprocess.run(['/usr/bin/git', 'checkout', '-q', '-b', 'writer'], cwd=project, check=True)
    second = _commit_version_on(project, 2, 'new_name')
    subprocess.run(['/usr/bin/git', 'checkout', '-q', 'main'], cwd=project, check=True)
    return first, second


def _commit_version_on(project, version, name):
    for file, text in (('helper.py', f'def {name}():\n    return {version}\n'),
                       ('lazy.py', f'from helper import {name}\ndef value():\n    return {name}()\n'),
                       ('child.py', f'print({version})\n'), ('zones.json', json.dumps(dict(version=version)))):
        (project / 'backend' / file).write_text(text)
    subprocess.run(['/usr/bin/git', 'add', '-A'], cwd=project, check=True)
    subprocess.run(['/usr/bin/git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', f'v{version}'], cwd=project, check=True)
    subprocess.run(['/usr/bin/git', 'push', '-q', 'origin', 'writer:main'], cwd=project, check=True)
    return subprocess.run(['/usr/bin/git', 'rev-parse', 'HEAD'], cwd=project, check=True, capture_output=True, text=True).stdout.strip()


def _probes(project):
    return [json.loads(line) for line in (project / 'probes').read_text().splitlines()]


def test_the_old_backend_keeps_its_own_code_while_a_release_prepares(real_release):
    """5 Nov 06:36: /api/phones/<id>/profile answered 500 on every phone between the checkout moving and the restart."""
    project, env = real_release
    _released_and_waiting_for_the_next(project, env)
    result, events = run_release(project, 'deploy.sh', extra_env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    seen = _probes(project)
    assert seen and all(code == 200 for code, _ in seen), seen
    assert all(json.loads(body)['zones'] == 1 and json.loads(body)['child'] == '1' for _, body in seen), seen
    after = _ask(env)
    assert (after['value'], after['zones'], after['child']) == (2, 2, '2')
    assert after['folder'].endswith('loupe-backend/green/backend')
    # The checkout moved first for the tooling; the tree the old backend ran from did not move at all.
    assert subprocess.run(['/usr/bin/git', 'log', '-1', '--format=%s'], cwd=project.parent / 'loupe-backend/blue',
                          capture_output=True, text=True).stdout.strip() == 'v1'


def test_with_the_backend_in_the_checkout_the_same_release_breaks_it(real_release):
    """The test above fails on the old layout: this is that layout, and the failure of 5 Nov."""
    project, env = real_release
    (project / 'deploy/backend-tree.conf').write_text('checkout\n')
    _released_and_waiting_for_the_next(project, env)
    result, _ = run_release(project, 'deploy.sh', extra_env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert any(code == 500 and 'new_name' in body for code, body in _probes(project)), _probes(project)


def test_a_party_gate_refusal_leaves_the_running_tree_and_current_alone(real_release):
    project, env = real_release
    _released_and_waiting_for_the_next(project, env)
    _party_gate(project, 1)
    result, events = run_release(project, 'deploy.sh', extra_env=env)
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'systemctl stop --no-block owl-backend-v2' not in events
    assert (project.parent / 'loupe-backend/current').resolve().name == 'blue'
    assert _ask(env)['value'] == 1


def test_a_failed_health_check_goes_back_to_the_tree_that_ran(real_release):
    project, env = real_release
    first, _ = _released_and_waiting_for_the_next(project, env)
    result, _ = run_release(project, 'deploy.sh', health_failure=True, extra_env=env)
    assert result.returncode == 1, result.stdout + result.stderr
    assert (project.parent / 'loupe-backend/current').resolve().name == 'blue'
    after = _ask(env)
    assert (after['value'], after['zones'], after['child']) == (1, 1, '1')
    assert after['folder'].endswith('loupe-backend/blue/backend')


def test_the_first_release_on_trees_can_go_back_to_the_checkout(real_release):
    project, env = real_release
    # The commit it goes back to has no switch file, as the commit before the trees has none.
    conf = project / 'deploy/backend-tree.conf'
    wanted = conf.read_text()
    conf.unlink()
    _commit_version(project, 1, 'old_name')
    conf.write_text(wanted)
    (project / 'deploy/logs/.last-good-commit').write_text(
        subprocess.run(['/usr/bin/git', 'rev-parse', 'HEAD'], cwd=project, capture_output=True, text=True).stdout)
    subprocess.run(['/usr/bin/git', 'checkout', '-q', '-b', 'writer'], cwd=project, check=True)
    _commit_version_on(project, 2, 'new_name')
    subprocess.run(['/usr/bin/git', 'checkout', '-q', 'main'], cwd=project, check=True)
    result, _ = run_release(project, 'deploy.sh', health_failure=True, extra_env=env)
    assert result.returncode == 1, result.stdout + result.stderr
    assert not (project.parent / 'loupe-backend/current').exists()
    assert not (project / 'units/owl-backend-v2.service.d/70-lx-releaseprep-tree.conf').exists()
    after = _ask(env)
    assert after['folder'] == str(project / 'backend')
    assert (after['value'], after['zones'], after['child']) == (1, 1, '1')


def test_a_tree_that_cannot_switch_leaves_the_old_backend_and_undoes_the_release(real_release):
    project, env = real_release
    _released_and_waiting_for_the_next(project, env)
    (project.parent / 'loupe-backend/.current.tmp').mkdir()  # ln -sfn then links inside it and mv -T cannot replace
    (project.parent / 'loupe-backend/.current.tmp/block').write_text('')
    result, events = run_release(project, 'deploy.sh', extra_env=env)
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'systemctl stop --no-block owl-backend-v2' not in events
    assert (project.parent / 'loupe-backend/current').resolve().name == 'blue'
    assert _ask(env)['value'] == 1


def test_a_backend_in_a_tree_keeps_its_data_paths(tmp_path):
    """Paths are stored and compared against the data folder: from a tree they must stay the checkout's, not the link's."""
    checkout, tree = tmp_path / 'checkout', tmp_path / 'trees/blue'
    (checkout / 'backend').mkdir(parents=True)
    (tree / 'backend').mkdir(parents=True)
    (checkout / '.env').write_text('')
    (tree / '.env').symlink_to(checkout / '.env')
    shutil.copy(Path(__file__).resolve().parents[1] / 'config.py', tree / 'backend/config.py')
    # config.py ends by calling secret_check (a7e1035f5), so the module must sit beside it here too.
    shutil.copy(Path(__file__).resolve().parents[1] / 'secret_check.py', tree / 'backend/secret_check.py')
    env = {key: value for key, value in os.environ.items() if key not in ('EVIDENCE_DATA_ROOT', 'PLATFORM_UPDATE_REPO_DIR')}
    answer = subprocess.run([sys.executable, '-c', 'import config; print(config.EVIDENCE_DATA_ROOT, config.PLATFORM_UPDATE_REPO_DIR, config.BASE_DIR)'],
                            cwd=tree / 'backend', env=env, capture_output=True, text=True, check=True).stdout.split()
    assert answer == [str(checkout / 'evidence-data'), str(checkout), str(tree)]


def _with_work_hook(project, clears_jobs=True, migrations=None):
    """The host's script named in deploy/logs/.release-work-hook, standing in for headless/release-work.sh."""
    hook = project / 'commands/work-hook'
    clear = '''
if [ "$1" = pause-uploads ]; then "%s" -c "import sqlite3, os; c = sqlite3.connect(os.environ['GATE_DATABASE']); c.execute('update jobs set paused=1'); c.commit()"; fi
''' % sys.executable if clears_jobs else ''
    hook.write_text('#!/bin/bash\necho "\\"hook $1\\"" >> "$RELEASE_SANDBOX/events"' + clear + '\n')
    hook.chmod(0o755)
    (project / 'deploy/logs/.release-work-hook').write_text(f'{hook}\n')
    if migrations:
        (project / 'deploy/migration_safety.py').write_text(f'print({migrations!r})\n')


def test_running_work_is_paused_only_for_the_step_that_replaces_services(release_sandbox):
    """5 Nov 07:53-17:12: uploads held 7 of 9 h 19 min, because the pause came before the build."""
    _with_work_hook(release_sandbox, migrations='additive 1')
    result, events = run_release(release_sandbox, 'deploy.sh', initially_active=True)
    assert result.returncode == 0, result.stdout + result.stderr
    imports = events.index('hook pause-imports')
    uploads = events.index('hook pause-uploads')
    resume = events.index('hook resume')
    build = next(i for i, event in enumerate(events) if event.startswith('docker compose build'))
    frontend = next(i for i, event in enumerate(events) if event.startswith('npm '))
    migrate = next(i for i, event in enumerate(events) if event.startswith('alembic'))
    refresh = next(i for i, event in enumerate(events) if event.startswith('docker compose up'))
    restart = next(i for i, event in enumerate(events) if event.startswith('systemctl') and 'owl-backend-v2' in event
                   and any(word in event for word in (' restart ', ' start ')))
    assert frontend < imports and build < imports
    assert imports < migrate < uploads < refresh < restart < resume
    assert events.count('hook resume') == 1


def test_uploads_stop_before_a_migration_the_old_backend_cannot_run_beside(release_sandbox):
    _with_work_hook(release_sandbox, migrations='unsafe 20261105_x: drops a column')
    result, events = run_release(release_sandbox, 'deploy.sh', initially_active=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert events.index('hook pause-uploads') < next(i for i, event in enumerate(events) if event.startswith('alembic'))
    assert sum(event.startswith('alembic') for event in events) == 1


def test_a_failed_gate_after_the_pause_still_resumes(release_sandbox):
    _with_work_hook(release_sandbox, clears_jobs=False, migrations='none')
    result, events = run_release(release_sandbox, 'deploy.sh', initially_active=True)
    assert result.returncode == 75
    assert events.index('hook pause-uploads') < events.index('hook resume')
    assert not any(event.startswith('docker compose up') for event in events)


def test_without_the_hook_every_gate_applies_from_the_start(release_sandbox):
    result, events = run_release(release_sandbox, 'deploy.sh', initially_active=True)
    assert result.returncode == 75
    assert not any(event.startswith(('npm ', 'docker compose build')) for event in events)


def test_every_step_of_a_release_has_its_time(release_sandbox):
    result, _ = run_release(release_sandbox, 'deploy.sh')
    assert result.returncode == 0, result.stdout + result.stderr
    steps = [line for line in result.stdout.splitlines() if '[STEP]' in line]
    assert steps and all(re.search(r'\d\d:\d\d:\d\d', line) for line in steps)


def test_a_release_stopped_by_a_failing_command_names_its_step_and_command():
    result = subprocess.run(['bash', str(DEPLOY / 'tests/test-deploy-failure-named.sh')],
        capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS deploy failure named' in result.stdout
