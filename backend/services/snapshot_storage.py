"""
Postgres-backed snapshot storage service.

Snapshots are runtime investigation state, so they are stored in Postgres rather
than JSON files. The service keeps the old public method names used by the
snapshot router.
"""

from __future__ import annotations

import copy
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import RLock
from typing import Callable, Dict, Iterator, Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from postgres.models.runtime_state import SnapshotRecord
from postgres.session import get_background_session


SessionFactory = Callable[[], Session]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_safe_copy(data: Dict) -> Dict:
    return json.loads(json.dumps(data, ensure_ascii=False, default=str))


def _truncate(value: object, max_length: int) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    return text[:max_length]


def _int_or_none(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class SnapshotStorage:
    """Service for managing snapshot storage in Postgres."""

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

    @staticmethod
    def _to_dict(record: SnapshotRecord) -> Dict:
        snapshot = copy.deepcopy(record.data or {})
        snapshot.setdefault("id", record.id)
        if record.owner is not None:
            snapshot.setdefault("owner", record.owner)
        if record.case_id is not None:
            snapshot.setdefault("case_id", record.case_id)
        if record.case_version is not None:
            snapshot.setdefault("case_version", record.case_version)
        if record.case_name is not None:
            snapshot.setdefault("case_name", record.case_name)
        if record.name is not None:
            snapshot.setdefault("name", record.name)
        if record.snapshot_timestamp is not None:
            snapshot.setdefault("timestamp", record.snapshot_timestamp)
        snapshot.setdefault("created_at", snapshot.get("timestamp") or record.created_at.isoformat())
        return snapshot

    def get_all(self, *, db: Session | None = None) -> Dict[str, Dict]:
        """Get all snapshots keyed by snapshot ID."""
        with self._lock:
            with self._session_scope(db) as session:
                records = session.scalars(
                    select(SnapshotRecord).order_by(
                        desc(SnapshotRecord.created_at),
                        desc(SnapshotRecord.id),
                    )
                ).all()
                return {record.id: self._to_dict(record) for record in records}

    def get(self, snapshot_id: str, *, db: Session | None = None) -> Optional[Dict]:
        """Get a specific snapshot by ID."""
        with self._lock:
            with self._session_scope(db) as session:
                record = session.get(SnapshotRecord, snapshot_id)
                return self._to_dict(record) if record else None

    def save(self, snapshot_id: str, snapshot_data: Dict, *, db: Session | None = None) -> None:
        """Create or replace a snapshot."""
        snapshot_copy = _json_safe_copy(snapshot_data)
        snapshot_copy["id"] = snapshot_copy.get("id") or snapshot_id
        timestamp = _now()

        with self._lock:
            with self._session_scope(db) as session:
                record = session.get(SnapshotRecord, snapshot_id)
                if record is None:
                    record = SnapshotRecord(
                        id=snapshot_id,
                        created_at=timestamp,
                        updated_at=timestamp,
                        data=snapshot_copy,
                    )
                    session.add(record)
                else:
                    record.updated_at = timestamp
                    record.data = snapshot_copy

                record.owner = _truncate(snapshot_copy.get("owner"), 255)
                record.case_id = _truncate(snapshot_copy.get("case_id"), 64)
                record.case_version = _int_or_none(snapshot_copy.get("case_version"))
                record.case_name = _truncate(snapshot_copy.get("case_name"), 255)
                record.name = _truncate(snapshot_copy.get("name"), 255)
                record.snapshot_timestamp = _truncate(snapshot_copy.get("timestamp"), 64)
                session.flush()

    def delete(self, snapshot_id: str, *, db: Session | None = None) -> bool:
        """Delete a snapshot. Returns True if deleted, False if not found."""
        with self._lock:
            with self._session_scope(db) as session:
                record = session.get(SnapshotRecord, snapshot_id)
                if record is None:
                    return False
                session.delete(record)
                session.flush()
                return True

    def reload(self) -> None:
        """Compatibility no-op: Postgres is queried directly for every call."""


snapshot_storage = SnapshotStorage()
