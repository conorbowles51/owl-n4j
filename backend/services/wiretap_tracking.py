"""
Postgres-backed wiretap processing status tracking.

Tracks which folders have already been processed as wiretaps. Module-level
functions are kept for compatibility with existing routers.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import RLock
from typing import Callable, Dict, Iterator, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from postgres.models.runtime_state import WiretapProcessedFolder
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


class WiretapTrackingService:
    """Postgres-backed tracking for processed wiretap folders."""

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
    def _to_dict(record: WiretapProcessedFolder) -> Dict[str, str | None]:
        return {
            "case_id": record.case_id,
            "folder_path": record.folder_path,
            "processed_at": _format_datetime(record.processed_at),
        }

    def mark_wiretap_processed(
        self,
        case_id: str,
        folder_path: str,
        *,
        db: Session | None = None,
    ) -> None:
        """
        Mark a folder as processed as a wiretap.

        Args:
            case_id: Case ID
            folder_path: Relative folder path from case data directory
            db: Optional request-scoped SQLAlchemy session
        """
        with self._lock:
            with self._session_scope(db) as session:
                statement = select(WiretapProcessedFolder).where(
                    WiretapProcessedFolder.case_id == case_id,
                    WiretapProcessedFolder.folder_path == folder_path,
                )
                record = session.scalars(statement).one_or_none()
                timestamp = _now()

                if record is None:
                    record = WiretapProcessedFolder(
                        id=str(uuid.uuid4()),
                        case_id=case_id,
                        folder_path=folder_path,
                        processed_at=timestamp,
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                    session.add(record)
                else:
                    record.processed_at = timestamp
                    record.updated_at = timestamp

                session.flush()

    def is_wiretap_processed(
        self,
        case_id: str,
        folder_path: str,
        *,
        db: Session | None = None,
    ) -> bool:
        """
        Check if a folder has been processed as a wiretap.

        Args:
            case_id: Case ID
            folder_path: Relative folder path from case data directory
            db: Optional request-scoped SQLAlchemy session

        Returns:
            True if folder has been processed, False otherwise
        """
        with self._lock:
            with self._session_scope(db) as session:
                statement = select(WiretapProcessedFolder.id).where(
                    WiretapProcessedFolder.case_id == case_id,
                    WiretapProcessedFolder.folder_path == folder_path,
                )
                return session.scalar(statement) is not None

    def get_wiretap_status(
        self,
        case_id: str,
        folder_path: str,
        *,
        db: Session | None = None,
    ) -> Optional[Dict[str, str | None]]:
        """
        Get wiretap processing status for a folder.

        Args:
            case_id: Case ID
            folder_path: Relative folder path from case data directory
            db: Optional request-scoped SQLAlchemy session

        Returns:
            Dict with processing info or None if not processed
        """
        with self._lock:
            with self._session_scope(db) as session:
                statement = select(WiretapProcessedFolder).where(
                    WiretapProcessedFolder.case_id == case_id,
                    WiretapProcessedFolder.folder_path == folder_path,
                )
                record = session.scalars(statement).one_or_none()
                return self._to_dict(record) if record else None

    def list_processed_wiretaps(
        self,
        case_id: Optional[str] = None,
        *,
        db: Session | None = None,
    ) -> List[Dict[str, str | None]]:
        """
        List all processed wiretap folders.

        Args:
            case_id: Optional case ID to filter by. If None, returns all processed wiretaps.
            db: Optional request-scoped SQLAlchemy session

        Returns:
            List of dicts with processing info, sorted by processed_at (newest first)
        """
        with self._lock:
            with self._session_scope(db) as session:
                statement = select(WiretapProcessedFolder)
                if case_id is not None:
                    statement = statement.where(WiretapProcessedFolder.case_id == case_id)
                statement = statement.order_by(desc(WiretapProcessedFolder.processed_at))
                records = session.scalars(statement).all()
                return [self._to_dict(record) for record in records]


wiretap_tracking_service = WiretapTrackingService()


def mark_wiretap_processed(case_id: str, folder_path: str, *, db: Session | None = None) -> None:
    return wiretap_tracking_service.mark_wiretap_processed(case_id, folder_path, db=db)


def is_wiretap_processed(case_id: str, folder_path: str, *, db: Session | None = None) -> bool:
    return wiretap_tracking_service.is_wiretap_processed(case_id, folder_path, db=db)


def get_wiretap_status(
    case_id: str,
    folder_path: str,
    *,
    db: Session | None = None,
) -> Optional[Dict[str, str | None]]:
    return wiretap_tracking_service.get_wiretap_status(case_id, folder_path, db=db)


def list_processed_wiretaps(
    case_id: Optional[str] = None,
    *,
    db: Session | None = None,
) -> List[Dict[str, str | None]]:
    return wiretap_tracking_service.list_processed_wiretaps(case_id=case_id, db=db)
