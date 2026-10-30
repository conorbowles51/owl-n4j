"""Warm the Financial views for a release before the service restarts, and never hold the release up for long.

After every release with new code the first visits to the large cases waited minutes (measured 2026-10-30 after
release ec0e927d: d5b330d1 account history 61 s, parties 42 s, statement file list 38 s) while the after-start
warm-up computed them. The saved copies are keyed on the code identity (every backend file, the libraries and the
process environment, view_cache._identity_now), so they can be computed before the restart, from the code on disk,
by a process with the service's own environment.

    python3 services/financial/view_prepare.py start   (deploy-now.sh, right after it pulls the release)
    python3 services/financial/view_prepare.py follow  (deploy/deploy.sh, right after its own fetch: other code -> again)
    python3 services/financial/view_prepare.py wait    (deploy/deploy.sh, before the frontend stops)

``start`` runs ``python -m services.financial.view_warmup --prepare`` as a unit of its own with the backend unit's
user, group, working directory, environment file and environment settings (drop-ins included, read from systemd)
and the same login shell as its ExecStart, so it computes the identity the started service looks up. ``wait``
waits for it at most PREPARE_CAP_SECONDS from its start; on the cap it stops it and the release goes on. A missing
or failed prepare never stops a release: the after-start warm-up still runs.

Standard library only: it runs as root with the system python3, outside the backend's own environment.
"""
import json
import os
import shlex
import subprocess
import sys
import time

SERVICE = 'owl-backend-v2.service'
UNIT = 'loupe-financial-prepare'
PREPARE_CAP_SECONDS = 600
STATE = '/run/loupe-financial-prepare.json'
SUMMARY_PREFIX = 'prepare: '


def _run(argv):
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def service_settings(run=_run):
    """The backend unit's settings a process needs to compute the service's code identity."""
    names = ('User', 'Group', 'WorkingDirectory', 'Environment', 'EnvironmentFiles')
    shown = run(['systemctl', 'show', SERVICE] + ['--property=' + name for name in names]).stdout
    settings = dict(environment=[], environment_files=[])
    for line in shown.splitlines():
        name, _, value = line.partition('=')
        if name == 'Environment':
            settings['environment'] = shlex.split(value)
        elif name == 'EnvironmentFiles':
            # "/path (ignore_errors=no)", one line per file.
            path, _, flags = value.rpartition(' (')
            settings['environment_files'].append(('-' if 'ignore_errors=yes' in flags else '') + (path or value))
        elif name in names:
            settings[name.lower()] = value
    missing = [name for name in ('user', 'group', 'workingdirectory') if not settings.get(name)]
    if missing or not settings['environment']:
        raise RuntimeError('%s settings unreadable (%s)' % (SERVICE, ', '.join(missing) or 'Environment'))
    return settings


def prepare_command(settings):
    """systemd-run for the prepare unit: the service's settings, at a lower CPU and I/O priority."""
    argv = ['systemd-run', '--unit=' + UNIT, '--collect', '--quiet',
            '--property=User=' + settings['user'], '--property=Group=' + settings['group'],
            '--property=WorkingDirectory=' + settings['workingdirectory'],
            '--property=RuntimeMaxSec=%d' % PREPARE_CAP_SECONDS,
            '--property=Nice=10', '--property=IOSchedulingClass=best-effort', '--property=IOSchedulingPriority=7',
            # Under memory pressure the kernel ends the prepare before a serving worker.
            '--property=OOMScoreAdjust=500']
    argv += ['--property=EnvironmentFile=' + path for path in settings['environment_files']]
    # systemd splits an Environment= value on spaces: each assignment is passed quoted, as systemctl shows it.
    argv += ['--property=Environment=' + _quoted(assignment) for assignment in settings['environment']]
    # The backend's ExecStart is a login shell (bash -lc), which can set more of the environment.
    argv += ['/bin/bash', '-lc', 'exec python -m services.financial.view_warmup --prepare']
    return argv


def _quoted(assignment):
    if not any(character in assignment for character in ' \t"\'\\'):
        return assignment
    return '"%s"' % assignment.replace('\\', '\\\\').replace('"', '\\"')


def _say(log, line):
    line = '%s %s' % (time.strftime('%H:%M:%S', time.gmtime()), line)
    print(line, flush=True)
    if log:
        with open(log, 'a') as out:
            out.write(line + '\n')


def start(log=None, run=_run, state=STATE):
    """Start the prepare unit; returns 0 always (a release never waits on a prepare that could not start)."""
    try:
        if run(['systemctl', 'is-active', '--quiet', UNIT]).returncode == 0:
            run(['systemctl', 'stop', UNIT])  # a prepare left from an earlier release computes old code
        run(['systemctl', 'reset-failed', UNIT])
        started = time.time()
        result = run(prepare_command(service_settings(run)))
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout).strip()[:300])
        commit = _checkout_commit(run)
        with open(state, 'w') as out:
            json.dump(dict(started=started, commit=commit), out)
        _say(log, 'prepare: started for %s' % (commit or 'unknown commit')[:8])
    except Exception as error:  # noqa: BLE001 - the release goes on without it
        _say(log, 'prepare: not started (%s)' % error)
    return 0


def _checkout_commit(run):
    """The commit checked out in the tree this file belongs to (the live checkout), or None."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    result = run(['git', '-C', root, 'rev-parse', 'HEAD'])
    commit = (result.stdout or '').strip()
    return commit if result.returncode == 0 and commit else None


def follow(log=None, run=_run, state=STATE):
    """deploy.sh fetches again after deploy-now.sh started the prepare; when that brought other code (another job
    pushed meanwhile; 2026-10-30 22:19 -> 22:29 the prepare computed 5f7e69f3 and 9ff80b1f was released), the
    prepared views would be keyed on code that never runs. Start the prepare again for the code now checked out.
    Nothing when no prepare was started or the code is the same. Returns 0 always."""
    try:
        with open(state) as saved:
            prepared = json.load(saved).get('commit')
    except (OSError, ValueError):
        return 0
    current = _checkout_commit(run)
    if current is None or current == prepared:
        return 0
    _say(log, 'prepare: code changed to %s since the prepare started; starting it again' % current[:8])
    return start(log, run=run, state=state)


def wait(log=None, run=_run, state=STATE, cap=PREPARE_CAP_SECONDS, poll=2.0, clock=time.time, sleep=time.sleep):
    """Wait for the prepare unit, at most ``cap`` seconds from its start; returns 0 always."""
    try:
        with open(state) as saved:
            started = json.load(saved)['started']
    except (OSError, ValueError, KeyError):
        return 0  # no prepare for this release (deploy.sh run on its own)
    try:
        os.unlink(state)
    except OSError:
        pass
    if clock() - started > cap + 3600:
        return 0  # left by a release that ended before its wait (deferred, or stopped by a gate)
    began = clock()
    while run(['systemctl', 'is-active', '--quiet', UNIT]).returncode == 0:
        if clock() - started >= cap:
            run(['systemctl', 'stop', UNIT])
            _say(log, 'prepare: capped after %d s' % round(clock() - started))
            _say(log, 'prepare: release waited %d s' % round(clock() - began))
            return 0
        sleep(poll)
    lines = run(['journalctl', '--unit=' + UNIT, '--since=@%d' % int(started), '--output=cat', '--no-pager']).stdout
    summary = [line for line in lines.splitlines() if line.startswith(SUMMARY_PREFIX)]
    _say(log, summary[-1] if summary else 'prepare: ended without a summary after %d s (see journalctl -u %s)'
         % (round(clock() - started), UNIT))
    _say(log, 'prepare: release waited %d s' % round(clock() - began))
    return 0


if __name__ == '__main__':
    action = sys.argv[1] if len(sys.argv) > 1 else ''
    log = os.environ.get('LOUPE_PREPARE_LOG') or None
    if action == 'start':
        sys.exit(start(log))
    if action == 'wait':
        sys.exit(wait(log))
    if action == 'follow':
        sys.exit(follow(log))
    print(__doc__)
    sys.exit(2)
