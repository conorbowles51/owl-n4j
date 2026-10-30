"""Background children of the web workers (page-image rounds, batch rounds, view warm-up) run below the request
threads: they share the workers' cgroup, so only their own nice and IO class rank them lower."""
import functools
import os
import subprocess
import sys

from services.financial import view_warmup


def test_child_is_set_to_nice_15_and_idle_io(monkeypatch):
    calls = []
    monkeypatch.setattr(view_warmup, '_PRCTL', lambda *a: calls.append(('prctl',) + a))
    monkeypatch.setattr(view_warmup, '_SYSCALL', lambda *a: calls.append(('syscall',) + a))
    monkeypatch.setattr(os, 'getpriority', lambda which, who: 0)
    monkeypatch.setattr(os, 'setpriority', lambda which, who, value: calls.append(('setpriority', which, who, value)))
    view_warmup._end_with_parent(None)
    assert ('setpriority', os.PRIO_PROCESS, 0, 15) in calls
    assert ('syscall', 251, 1, 0, 3 << 13) in calls  # ioprio_set(IOPRIO_WHO_PROCESS, self, IOPRIO_CLASS_IDLE)


def test_a_nicer_child_is_not_raised(monkeypatch):
    calls = []
    monkeypatch.setattr(view_warmup, '_PRCTL', None)
    monkeypatch.setattr(view_warmup, '_SYSCALL', None)
    monkeypatch.setattr(os, 'getpriority', lambda which, who: 19)
    monkeypatch.setattr(os, 'setpriority', lambda *a: calls.append(a))
    view_warmup._end_with_parent(None)
    assert calls == []


def test_a_started_child_runs_at_nice_15_or_nicer():
    out = subprocess.run([sys.executable, '-c', 'import os; print(os.getpriority(os.PRIO_PROCESS, 0))'],
                         preexec_fn=functools.partial(view_warmup._end_with_parent, os.getpid()),
                         capture_output=True, text=True, check=True)
    assert int(out.stdout) >= view_warmup.BACKGROUND_NICE
