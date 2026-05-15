"""
Postgres-backed last graph storage.

Stores the Cypher needed to recreate the most recently cleared graph so the UI
can offer a restore path without relying on a JSON file.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from threading import RLock
from typing import Callable, Dict, Iterator, Optional

from sqlalchemy.orm import Session

from postgres.models.runtime_state import LastGraphState
from postgres.session import get_background_session


SessionFactory = Callable[[], Session]
LAST_GRAPH_KEY = "global"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _format_datetime(value: datetime | str | None) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()


class LastGraphStorage:
    """Stores the last-cleared graph's Cypher and metadata in Postgres."""

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory = session_factory
        self._lock = RLock()

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

    def get(self, *, db: Session | None = None) -> Optional[Dict]:
        """Get the last stored graph metadata, or None if not present."""
        with self._lock:
            with self._session_scope(db) as session:
                record = session.get(LastGraphState, LAST_GRAPH_KEY)
                if record is None:
                    return None
                return {
                    "cypher": record.cypher,
                    "saved_at": _format_datetime(record.saved_at),
                }

    def set(self, cypher: str, *, db: Session | None = None) -> Dict:
        """
        Store a new last graph snapshot.

        Args:
            cypher: Cypher string that can recreate the graph.
            db: Optional request-scoped SQLAlchemy session.
        """
        timestamp = _now()
        with self._lock:
            with self._session_scope(db) as session:
                record = session.get(LastGraphState, LAST_GRAPH_KEY)
                if record is None:
                    record = LastGraphState(
                        key=LAST_GRAPH_KEY,
                        cypher=cypher,
                        saved_at=timestamp,
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                    session.add(record)
                else:
                    record.cypher = cypher
                    record.saved_at = timestamp
                    record.updated_at = timestamp

                session.flush()
                return {
                    "cypher": record.cypher,
                    "saved_at": _format_datetime(record.saved_at),
                }


last_graph_storage = LastGraphStorage()
