"""Exercise the real release scripts with local, inert service/Git commands.

The real read-only SQL gate still runs. Synthetic jobs arrive between release
stages to check that neither deployment nor rollback replaces their services.
"""
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
                 'nginx-loupe-frontend.conf', 'record_release.py'):
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
    event = 'gate'
with (root / 'events').open('a') as stream:
    stream.write(json.dumps(event) + '\\n')
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
    print('1')
elif name == 'npm' and 'build' in args and '--outDir' in args:
    # A build writes its output where it is told (deploy/frontend-release.sh builds beside the served one).
    out = pathlib.Path(args[args.index('--outDir') + 1])
    (out / 'assets').mkdir(parents=True, exist_ok=True)
    (out / 'index.html').write_text('<script src="/assets/app.js"></script>')
    (out / 'assets/app.js').write_text('app')
elif name == 'systemctl' and args[:1] == ['show']:
    print('inactive')  # the bounded stop sees the backend stopped at once
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
           'FRONTEND_NGINX_AVAILABLE': str(project / 'nginx/sites-available/loupe-frontend')}
    if arrives_after:
        env['WORK_ARRIVES_AFTER'] = arrives_after
    if health_failure:
        env['FORCE_HEALTH_FAILURE'] = '1'
    env.update(extra_env or {})
    result = subprocess.run(['bash', str(project / 'deploy' / script), 'previous-safe-revision'],
                            input='y\n', text=True, capture_output=True, env=env, timeout=180)
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
