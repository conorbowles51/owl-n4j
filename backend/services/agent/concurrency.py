from __future__ import annotations

from threading import Lock


class AgentConcurrencyLimitExceeded(RuntimeError):
    """Raised when the in-memory agent run cap is already exhausted."""


_lock = Lock()
_active_runs_by_user: dict[str, int] = {}
_active_runs_global = 0


def acquire_run_slot(user_id: str, *, max_per_user: int, max_global: int) -> None:
    user_key = str(user_id)
    per_user_limit = max(1, int(max_per_user or 1))
    global_limit = max(1, int(max_global or 1))

    global _active_runs_global
    with _lock:
        user_count = _active_runs_by_user.get(user_key, 0)
        if user_count >= per_user_limit:
            raise AgentConcurrencyLimitExceeded(
                f"Agent run limit reached for this user ({per_user_limit} concurrent run(s))."
            )
        if _active_runs_global >= global_limit:
            raise AgentConcurrencyLimitExceeded(
                f"Agent run limit reached for the workspace ({global_limit} concurrent run(s))."
            )

        _active_runs_by_user[user_key] = user_count + 1
        _active_runs_global += 1


def release_run_slot(user_id: str) -> None:
    user_key = str(user_id)

    global _active_runs_global
    with _lock:
        user_count = _active_runs_by_user.get(user_key, 0)
        if user_count <= 1:
            _active_runs_by_user.pop(user_key, None)
        else:
            _active_runs_by_user[user_key] = user_count - 1
        if _active_runs_global > 0:
            _active_runs_global -= 1


def _reset_for_tests() -> None:
    global _active_runs_global
    with _lock:
        _active_runs_by_user.clear()
        _active_runs_global = 0
