"""
Postgres-backed presence service.

Tracks active workspace sessions and user presence for real-time collaboration.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Callable, Dict, Iterator, List, Optional

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from postgres.models.runtime_state import PresenceSession
from postgres.session import get_background_session


SessionFactory = Callable[[], Session]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _format_datetime(value: datetime | str | None) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()


class PresenceService:
    """Service for tracking user presence in workspace sessions."""

    def __init__(
        self,
        session_factory: SessionFactory | None = None,
        stale_timeout_minutes: int = 30,
    ) -> None:
        self._session_factory = session_factory
        self._lock = RLock()
        self._stale_timeout = timedelta(minutes=stale_timeout_minutes)

    @contextmanager
    def _session_scope(self, db: Session | None = None) -> Iterator[Session]:
        if db is not None:
            yield db
            return

        if self._session_factory is not None:
            session = self._session_factory()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
            return

        with get_background_session() as session:
            yield session

    @staticmethod
    def _to_dict(session: PresenceSession) -> Dict:
        return {
            "session_id": session.session_id,
            "case_id": session.case_id,
            "user_id": session.user_id,
            "username": session.username,
            "ip_address": session.ip_address,
            "device_info": session.device_info,
            "started_at": _format_datetime(session.started_at),
            "last_active": _format_datetime(session.last_active),
        }

    def create_session(
        self,
        case_id: str,
        user_id: str,
        username: str,
        ip_address: Optional[str] = None,
        device_info: Optional[str] = None,
        *,
        db: Session | None = None,
    ) -> str:
        """Create a new workspace session."""
        session_id = f"ws_{uuid.uuid4().hex[:16]}"
        timestamp = _now()

        with self._lock:
            with self._session_scope(db) as session:
                session.add(
                    PresenceSession(
                        session_id=session_id,
                        case_id=case_id,
                        user_id=user_id,
                        username=username,
                        ip_address=ip_address,
                        device_info=device_info,
                        started_at=timestamp,
                        last_active=timestamp,
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )
                session.flush()

        return session_id

    def update_session_activity(self, session_id: str, *, db: Session | None = None) -> None:
        """Update last active timestamp for a session."""
        with self._lock:
            with self._session_scope(db) as session:
                record = session.get(PresenceSession, session_id)
                if record is not None:
                    timestamp = _now()
                    record.last_active = timestamp
                    record.updated_at = timestamp
                    session.flush()

    def remove_session(self, session_id: str, *, db: Session | None = None) -> None:
        """Remove a session (user left workspace)."""
        with self._lock:
            with self._session_scope(db) as session:
                record = session.get(PresenceSession, session_id)
                if record is not None:
                    session.delete(record)
                    session.flush()

    def get_online_users(self, case_id: str, *, db: Session | None = None) -> List[Dict]:
        """Get list of users currently online in a workspace."""
        cutoff = _now() - self._stale_timeout

        with self._lock:
            with self._session_scope(db) as session:
                statement = (
                    select(PresenceSession)
                    .where(
                        PresenceSession.case_id == case_id,
                        PresenceSession.last_active >= cutoff,
                    )
                    .order_by(desc(PresenceSession.last_active))
                )
                records = session.scalars(statement).all()

                online_users = []
                seen_users = set()
                for record in records:
                    if record.user_id not in seen_users:
                        online_users.append(
                            {
                                "user_id": record.user_id,
                                "username": record.username,
                            }
                        )
                        seen_users.add(record.user_id)

                return online_users

    def cleanup_stale_sessions(
        self,
        timeout_minutes: int = 30,
        *,
        db: Session | None = None,
    ) -> int:
        """Remove sessions that haven't been active for timeout_minutes."""
        cutoff = _now() - timedelta(minutes=timeout_minutes)

        with self._lock:
            with self._session_scope(db) as session:
                result = session.execute(
                    delete(PresenceSession).where(PresenceSession.last_active < cutoff)
                )
                session.flush()
                return result.rowcount or 0

    def get_session(self, session_id: str, *, db: Session | None = None) -> Optional[Dict]:
        """Get session data by session_id."""
        with self._lock:
            with self._session_scope(db) as session:
                record = session.get(PresenceSession, session_id)
                return self._to_dict(record) if record else None


# Singleton instance
presence_service = PresenceService()
