from __future__ import annotations

from threading import Lock


_lock = Lock()
_cancelled_run_ids: set[str] = set()


def request_cancel(run_id: str) -> None:
    with _lock:
        _cancelled_run_ids.add(run_id)


def clear_cancel(run_id: str) -> None:
    with _lock:
        _cancelled_run_ids.discard(run_id)


def is_cancelled(run_id: str) -> bool:
    with _lock:
        return run_id in _cancelled_run_ids
