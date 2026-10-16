"""The commit this backend process was started from, reported by /health.

deploy/deploy.sh records a release as last known-good only after its own
health check. A backend restarted directly (systemctl, or a pull and restart
by hand) never passed that check, so a later failed deploy rolled back past
it. The process reads its checkout's commit once at startup (later pulls do
not change what is running) and whether tracked files differed from it; the
deploy script records a clean, healthy running commit as last known-good.
"""
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
_started = dict(commit=None, commit_clean=False)


def _git(*args):
    result = subprocess.run(['git', '-C', str(PROJECT_DIR), *args], capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        raise RuntimeError('git unavailable')
    return result.stdout.strip()


def record_started_commit():
    """Read HEAD and whether tracked files match it. Never raises; unknown stays None."""
    try:
        commit = _git('rev-parse', 'HEAD')
        clean = _git('status', '--porcelain', '--untracked-files=no') == ''
    except Exception:
        commit, clean = None, False
    if commit is not None and (len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit)):
        commit, clean = None, False
    _started.update(commit=commit, commit_clean=bool(commit and clean))
    return dict(_started)


def started_commit():
    return dict(_started)
