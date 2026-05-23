"""Shared helpers for crash-safe, multi-worker JSON file writes.

Centralises the fcntl-locked atomic-write pattern so every JSON-singleton
storage serialises writes across uvicorn workers and never hits the
`.tmp` rename race: two workers open the SAME `<file>.tmp` path, worker
B's `os.replace` consumes the file, worker A's `replace` then fails with
ENOENT (observed killing a Cellebrite ingest on 2026-05-23). Two defences
stacked here:

  1. an fcntl LOCK_EX on a sidecar `<file>.lock` serialises writers, and
  2. a per-writer unique temp filename means even an un-serialised write
     never collides on the same temp path.

This is the lighter helper for storages whose mutation methods don't yet
reload-before-save. The heavier per-class reload-under-lock variant lives
in evidence_storage / evidence_log_storage / background_task_storage and
additionally prevents lost-updates from stale in-memory caches.
"""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional


@contextmanager
def file_lock(lock_path: Path):
    """Hold an exclusive fcntl lock on `lock_path` for the with-block.

    The lock file is kept world-writable (0o666) so a root-owned re-create
    by a sudo'd maintenance script can't lock out the backend user — same
    rationale as evidence_storage._file_locked.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a") as lf:
        try:
            os.chmod(lock_path, 0o666)
        except OSError:
            pass
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def save_json_atomic(
    path: Path,
    data: Any,
    *,
    indent: int = 2,
    ensure_ascii: bool = False,
    default: Optional[Any] = None,
) -> None:
    """Serialise `data` to `path` atomically and under an exclusive lock.

    Writes to a per-writer unique temp file then `os.replace`s it into
    place (atomic on the same filesystem). Serialised against other
    workers via `<path>.lock`.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with file_lock(lock_path):
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii, default=default)
            os.replace(tmp, path)
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
