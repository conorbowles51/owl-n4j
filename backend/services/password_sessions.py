"""A sign-in issued before its user's password last changed is refused.

Changing a password (the person's own change, or an administrator setting one) stamps
users.password_changed_at; every token carries when it was issued (``iat``; a token from before
``iat`` was added is dated from its expiry minus the token lifetime, which is exact because only
sign-in issues tokens). The check reads the stamp at most once every CACHE_SECONDS per user and
worker: the worker where the change happened forgets it at once, another worker within
CACHE_SECONDS.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

CACHE_SECONDS = 30.0

_cache: dict[str, tuple[float, float | None]] = {}
_lock = threading.Lock()


def _read_changed_at(email: str) -> float | None:
    from sqlalchemy import select
    from postgres.models.user import User
    from postgres.session import _get_session_local
    with _get_session_local()() as db:
        changed = db.execute(select(User.password_changed_at).where(User.email == email)).scalar()
    if changed is None:
        return None
    if changed.tzinfo is None:
        changed = changed.replace(tzinfo=timezone.utc)
    return changed.timestamp()


def cached_changed_at(email: str):
    """(True, seconds or None) when a fresh cached value exists, else (False, None)."""
    with _lock:
        hit = _cache.get(email)
    if hit is not None and time.monotonic() - hit[0] < CACHE_SECONDS:
        return True, hit[1]
    return False, None


def changed_at(email: str) -> float | None:
    fresh, value = cached_changed_at(email)
    if fresh:
        return value
    value = _read_changed_at(email)
    with _lock:
        _cache[email] = (time.monotonic(), value)
    return value


def forget(email: str) -> None:
    with _lock:
        _cache.pop(email, None)


def issued_before_change(issued_at: int | None, changed: float | None) -> bool:
    # Whole seconds, as iat is: a token issued in the same second as the change is kept.
    return changed is not None and issued_at is not None and issued_at < int(changed)


def stamp(user) -> None:
    """Record that ``user``'s password changed now (the caller commits)."""
    user.password_changed_at = datetime.now(timezone.utc)
    forget(user.email)


async def refused(data: dict) -> bool:
    """Whether a verified token's sign-in predates its user's last password change."""
    email, issued = data.get("username"), data.get("issued_at")
    if not email or issued is None:
        return False
    fresh, changed = cached_changed_at(email)
    if not fresh:
        from starlette.concurrency import run_in_threadpool
        changed = await run_in_threadpool(changed_at, email)
    return issued_before_change(issued, changed)
