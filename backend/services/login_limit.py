"""Failed sign-ins are limited, from the ``login_failure`` rows of the activity trail.

The trail is Postgres, so the count holds across workers and restarts, and ``ix_activity_events_action_at`` keeps the
read to the last few minutes of failures. Only failures count: a correct sign-in, however frequent, adds nothing, so
the shared jobs login (851 sign-ins in 7 days, 3 failures ever on 5 Nov) is untouched.

Three limits over the same window:
- one account from one address stops a guesser quickly;
- one address across accounts stops a sweep;
- one account from every address together is far higher, so a single outsider, who stops at the first two, cannot lock
  a real person out, while a guess spread over many addresses is still bounded.

Measured on live 5 Nov: the worst 15 minutes held 1 failure for an account and 2 for an address.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from postgres.models.activity_event import ActivityEvent
from services import activity_trail

log = logging.getLogger(__name__)

WINDOW = timedelta(minutes=15)
ACCOUNT_AT_ADDRESS_LIMIT = 10
ADDRESS_LIMIT = 30
ACCOUNT_LIMIT = 100
READ_LIMIT = 1000
# A refused attempt is audited once a minute for one account and address: the trail is append-only for good.
REFUSAL_RECORD_GAP = timedelta(seconds=60)


@dataclass(frozen=True)
class Limited:
    scope: str
    wait_seconds: int

    @property
    def message(self) -> str:
        minutes = (self.wait_seconds + 59) // 60
        unit = "minute" if minutes == 1 else "minutes"
        return f"Too many failed sign-ins. Wait {minutes} {unit} and try again."


def _account(value: str | None) -> str:
    return (value or "").strip().lower()


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _wait(moments: list[datetime], limit: int, now: datetime) -> int | None:
    """Seconds until fewer than ``limit`` of ``moments`` (newest first) remain in the window; None when under it."""
    if len(moments) < limit:
        return None
    return max(1, int((moments[limit - 1] + WINDOW - now).total_seconds()) + 1)


def _failures(db: Session, account: str, address: str | None, since: datetime):
    who = func.lower(ActivityEvent.user_email) == account
    return (db.query(ActivityEvent.at, ActivityEvent.user_email, ActivityEvent.source_address)
            .filter(ActivityEvent.action == "login_failure", ActivityEvent.at >= since,
                    or_(who, ActivityEvent.source_address == address) if address else who)
            .order_by(ActivityEvent.at.desc()).limit(READ_LIMIT).all())


def refusal(db: Session, email: str | None, address: str | None, now: datetime | None = None) -> Limited | None:
    """Whether this attempt is refused. A trail that cannot be read refuses nobody: the password still decides."""
    now = now or datetime.now(timezone.utc)
    account = _account(email)
    try:
        rows = _failures(db, account, address, now - WINDOW)
    except Exception:
        log.exception("Sign-in limit: could not read the failures; this attempt goes on to the password check")
        db.rollback()
        return None
    of_account = [_aware(row.at) for row in rows if _account(row.user_email) == account]
    of_address = [_aware(row.at) for row in rows if address and row.source_address == address]
    of_both = [_aware(row.at) for row in rows if _account(row.user_email) == account
               and address and row.source_address == address]
    waits = {scope: wait for scope, wait in (
        ("account_at_address", _wait(of_both, ACCOUNT_AT_ADDRESS_LIMIT, now)),
        ("address", _wait(of_address, ADDRESS_LIMIT, now)),
        ("account", _wait(of_account, ACCOUNT_LIMIT, now)),
    ) if wait is not None}
    if not waits:
        return None
    scope = max(waits, key=waits.get)
    return Limited(scope=scope, wait_seconds=waits[scope])


def record_refusal(db: Session, email: str | None, address: str | None, limited: Limited,
                   now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    typed = (email or "")[:255]
    try:
        recent = (db.query(ActivityEvent.id)
                  .filter(ActivityEvent.action == "login_rate_limited", ActivityEvent.at >= now - REFUSAL_RECORD_GAP,
                          ActivityEvent.user_email == typed, ActivityEvent.source_address == address)
                  .first())
    except Exception:
        log.exception("Sign-in limit: could not read the refusals; the attempt is still refused")
        db.rollback()
        return
    if recent is None:
        activity_trail.record("login_rate_limited", db=db, commit=True, user_email=typed,
                              details=dict(limit=limited.scope, wait_seconds=limited.wait_seconds))
