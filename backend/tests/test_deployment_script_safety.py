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


@pytest.fixture
def release_sandbox(tmp_path):
    project = tmp_path / 'release'
    for directory in ('deploy/logs', 'backend/postgres', 'frontend_v2', '.venv/bin', 'commands'):
        (project / directory).mkdir(parents=True)
    for name in ('deploy.sh', 'rollback.sh', 'ingestion-safety.sh', 'check_ingestion_idle.py'):
        shutil.copy(DEPLOY / name, project / 'deploy' / name)
    # Exercise real install/mv commands, but target a synthetic unit directory.
    helper = project / 'deploy/ingestion-safety.sh'
    helper.write_text(helper.read_text().replace('/etc/systemd/system/owl-backend-v2.service.d',
        str(project / 'units/owl-backend-v2.service.d')))
    # The desktop sandbox disallows bash's /dev/fd process-substitution log
    # sink. Capture stdout directly; leave all release control flow intact.
    deploy_script = project / 'deploy/deploy.sh'
    deploy_script.write_text(deploy_script.read_text().replace(
        'exec > >(tee -a "${LOG_FILE}") 2>&1', '# Output captured by subprocess.run in this isolated test.'))
    # This service installer is not under test, and must never touch the host.
    (project / 'deploy/install-frontend-service.sh').write_text('#!/bin/bash\nexit 0\n')
    (project / '.env').write_text('API_PORT=8002\nFRONTEND_PORT=5174\n')
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
        print('main' if '--abbrev-ref' in args else 'current-revision')
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
    else:
        print('{"status":"ok"}')
elif name == 'seq':
    print('1')
''')
    stub.chmod(0o755)
    for name in ('git', 'id', 'whoami', 'sudo', 'docker', 'npm', 'systemctl', 'curl', 'sleep', 'seq', 'flock'):
        (project / 'commands' / name).symlink_to(stub)
    for name in ('python', 'pip', 'alembic'):
        (project / '.venv/bin' / name).symlink_to(stub)
    return project


def run_release(project, script, *, arrives_after=None, initially_active=False, health_failure=False):
    if initially_active:
        with sqlite3.connect(project / 'jobs.sqlite') as db:
            db.execute("INSERT INTO jobs VALUES ('processing',false)")
    env = {**os.environ, 'PATH': str(project / 'commands') + ':/usr/bin:/bin',
           'RELEASE_SANDBOX': str(project), 'GATE_DATABASE': str(project / 'jobs.sqlite')}
    if arrives_after:
        env['WORK_ARRIVES_AFTER'] = arrives_after
    if health_failure:
        env['FORCE_HEALTH_FAILURE'] = '1'
    result = subprocess.run(['bash', str(project / 'deploy' / script), 'previous-safe-revision'],
                            input='y\n', text=True, capture_output=True, env=env, timeout=30)
    events = [json.loads(line) for line in (project / 'events').read_text().splitlines()]
    return result, events


@pytest.mark.parametrize('script', ['deploy.sh', 'rollback.sh'])
def test_existing_work_blocks_checkout_dependency_and_service_changes(release_sandbox, script):
    result, events = run_release(release_sandbox, script, initially_active=True)
    assert result.returncode == 75, result.stdout + result.stderr
    assert 'Release deferred' in result.stdout + result.stderr
    assert not any(event.startswith(('git pull', 'git checkout', 'git reset', 'pip ', 'npm ', 'docker compose ', 'systemctl restart')) for event in events)


@pytest.mark.parametrize('script,checkout', [('deploy.sh', 'git pull'), ('rollback.sh', 'git checkout')])
def test_current_gate_survives_checkout_to_revision_with_no_checks(release_sandbox, script, checkout):
    result, events = run_release(release_sandbox, script, arrives_after=checkout)
    assert result.returncode == 75, result.stdout + result.stderr
    assert (release_sandbox / 'deploy/check_ingestion_idle.py').read_text() == 'raise SystemExit(0)\n'
    assert not any(event.startswith(('pip ', 'docker compose ', 'systemctl restart')) for event in events)


@pytest.mark.parametrize('script', ['deploy.sh', 'rollback.sh'])
def test_work_arriving_during_image_build_blocks_container_replacement(release_sandbox, script):
    result, events = run_release(release_sandbox, script, arrives_after='docker compose build')
    assert result.returncode == 75, result.stdout + result.stderr
    assert 'docker compose build' in events
    assert not any(event.startswith(('docker compose up', 'systemctl restart owl-backend')) for event in events)
    if script == 'deploy.sh':
        assert 'serving the bundle currently on disk; the release is not confirmed complete' in result.stdout
        assert 'serving the previous build' not in result.stdout


@pytest.mark.parametrize('script', ['deploy.sh', 'rollback.sh'])
def test_work_arriving_during_container_change_blocks_backend_restart(release_sandbox, script):
    result, events = run_release(release_sandbox, script, arrives_after='docker compose up')
    assert result.returncode == 75, result.stdout + result.stderr
    assert any(event.startswith('docker compose up -d --no-build') for event in events)
    assert 'systemctl restart owl-backend-v2' not in events
    assert (release_sandbox / 'units/owl-backend-v2.service.d/ingestion-shutdown.conf').read_text() == '[Service]\nTimeoutStopSec=14500\n'
    assert 'systemctl daemon-reload' in events


def test_automatic_rollback_retains_checks_after_reset(release_sandbox):
    result, events = run_release(release_sandbox, 'deploy.sh', arrives_after='git reset', health_failure=True)
    assert result.returncode == 75, result.stdout + result.stderr
    reset = next(index for index, event in enumerate(events) if event.startswith('git reset'))
    assert events[reset + 1] == 'gate'
    assert not any(event.startswith(('pip ', 'npm ', 'docker compose ', 'systemctl restart')) for event in events[reset + 1:])


@pytest.mark.parametrize('script', ['deploy.sh', 'rollback.sh'])
def test_idle_release_still_completes_with_bounded_graceful_shutdown(release_sandbox, script):
    result, events = run_release(release_sandbox, script)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'systemctl restart owl-backend-v2' in events
    unit = release_sandbox / 'units/owl-backend-v2.service.d/ingestion-shutdown.conf'
    assert unit.read_text() == '[Service]\nTimeoutStopSec=14500\n'
    assert unit.stat().st_mode & 0o777 == 0o644


def test_shutdown_dropin_installer_uses_real_files_and_fails_before_reload():
    result = subprocess.run(['bash', str(DEPLOY / 'tests/test-ingestion-shutdown.sh')],
        capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'real install checks passed' in result.stdout
