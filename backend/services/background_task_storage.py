"""
Postgres-backed background task storage.

The public service API intentionally mirrors the previous storage class so
routers and background workers can keep creating, updating, listing, and
deleting tasks without knowing whether they are inside a request session.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from threading import RLock
from typing import Callable, Dict, Iterator, List, Optional

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from postgres.models.runtime_state import BackgroundTask
from postgres.session import get_background_session


# Maximum number of task entries to retain (oldest are dropped)
MAX_TASK_ENTRIES = 500


class TaskStatus(str, Enum):
    """Task status enumeration."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


SessionFactory = Callable[[], Session]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _format_datetime(value: datetime | str | None) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()


def _default_progress() -> Dict[str, int]:
    return {"total": 0, "completed": 0, "failed": 0}


class BackgroundTaskStorage:
    """Postgres-backed storage for background tasks. Thread-safe."""

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

    def reload(self) -> None:
        """Compatibility no-op: Postgres is queried directly for every call."""

    def _persist(self) -> None:
        """Compatibility no-op: writes are committed by the active DB session."""

    def _trim_old_tasks(self, db: Session) -> None:
        old_task_ids = db.scalars(
            select(BackgroundTask.id)
            .order_by(desc(BackgroundTask.created_at), desc(BackgroundTask.id))
            .offset(MAX_TASK_ENTRIES)
        ).all()
        if old_task_ids:
            db.execute(delete(BackgroundTask).where(BackgroundTask.id.in_(old_task_ids)))

    @staticmethod
    def _to_dict(task: BackgroundTask) -> Dict:
        progress = dict(task.progress or {})
        for key, value in _default_progress().items():
            progress.setdefault(key, value)

        return {
            "id": task.id,
            "task_type": task.task_type,
            "task_name": task.task_name,
            "owner": task.owner,
            "case_id": task.case_id,
            "status": task.status,
            "created_at": _format_datetime(task.created_at) or _now().isoformat(),
            "updated_at": _format_datetime(task.updated_at) or _now().isoformat(),
            "started_at": _format_datetime(task.started_at),
            "completed_at": _format_datetime(task.completed_at),
            "progress": progress,
            "files": list(task.files or []),
            "error": task.error,
            "metadata": dict(task.metadata_ or {}),
        }

    def create_task(
        self,
        *,
        task_type: str,
        task_name: str,
        owner: Optional[str] = None,
        case_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        db: Session | None = None,
    ) -> Dict:
        """
        Create a new background task.

        Args:
            task_type: Type of task (e.g., "evidence_processing")
            task_name: Human-readable task name
            owner: Optional owner username
            case_id: Optional associated case ID
            metadata: Optional additional metadata
            db: Optional request-scoped SQLAlchemy session

        Returns:
            Task dict with id, status, progress, files, and metadata.
        """
        with self._lock:
            with self._session_scope(db) as session:
                timestamp = _now()
                task = BackgroundTask(
                    id=str(uuid.uuid4()),
                    task_type=task_type,
                    task_name=task_name,
                    owner=owner,
                    case_id=case_id,
                    status=TaskStatus.PENDING.value,
                    created_at=timestamp,
                    updated_at=timestamp,
                    progress=_default_progress(),
                    files=[],
                    error=None,
                    metadata_=metadata or {},
                )
                session.add(task)
                session.flush()
                self._trim_old_tasks(session)
                session.flush()
                return self._to_dict(task)

    def get_task(self, task_id: str, *, db: Session | None = None) -> Optional[Dict]:
        """Get a task by ID."""
        with self._lock:
            with self._session_scope(db) as session:
                task = session.get(BackgroundTask, task_id)
                return self._to_dict(task) if task else None

    def update_task(
        self,
        task_id: str,
        *,
        status: Optional[str] = None,
        progress_total: Optional[int] = None,
        progress_completed: Optional[int] = None,
        progress_failed: Optional[int] = None,
        file_status: Optional[Dict] = None,
        error: Optional[str] = None,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
        metadata: Optional[Dict] = None,
        db: Session | None = None,
    ) -> Optional[Dict]:
        """
        Update a task's status, progress, files, error, timestamps, or metadata.

        Args:
            task_id: Task ID
            status: New status
            progress_total: Total items to process
            progress_completed: Number completed
            progress_failed: Number failed
            file_status: Dict with file_id, filename, status, error for file-by-file updates
            error: Error message if task failed
            started_at: When task started (ISO timestamp)
            completed_at: When task completed (ISO timestamp)
            metadata: Additional metadata to merge into the existing metadata dict
            db: Optional request-scoped SQLAlchemy session

        Returns:
            Updated task dict or None if not found
        """
        with self._lock:
            with self._session_scope(db) as session:
                task = session.get(BackgroundTask, task_id)
                if not task:
                    return None

                updated = False

                if status is not None:
                    task.status = status
                    updated = True

                if any(
                    value is not None
                    for value in (progress_total, progress_completed, progress_failed)
                ):
                    progress = dict(task.progress or _default_progress())
                    if progress_total is not None:
                        progress["total"] = progress_total
                    if progress_completed is not None:
                        progress["completed"] = progress_completed
                    if progress_failed is not None:
                        progress["failed"] = progress_failed
                    task.progress = progress
                    updated = True

                if file_status is not None:
                    file_id = file_status.get("file_id")
                    if file_id:
                        files = [dict(file_info) for file_info in (task.files or [])]
                        existing_file = next(
                            (file_info for file_info in files if file_info.get("file_id") == file_id),
                            None,
                        )
                        if existing_file:
                            existing_file.update(file_status)
                        else:
                            files.append(dict(file_status))
                        task.files = files
                        updated = True

                if error is not None:
                    task.error = error
                    updated = True

                parsed_started_at = _parse_datetime(started_at)
                if parsed_started_at is not None:
                    task.started_at = parsed_started_at
                    updated = True

                parsed_completed_at = _parse_datetime(completed_at)
                if parsed_completed_at is not None:
                    task.completed_at = parsed_completed_at
                    updated = True

                if metadata is not None:
                    merged_metadata = dict(task.metadata_ or {})
                    merged_metadata.update(metadata)
                    task.metadata_ = merged_metadata
                    updated = True

                if updated:
                    task.updated_at = _now()
                    session.flush()

                return self._to_dict(task)

    def list_tasks(
        self,
        *,
        owner: Optional[str] = None,
        case_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        db: Session | None = None,
    ) -> List[Dict]:
        """
        List tasks, optionally filtered.

        Args:
            owner: Filter by owner
            case_id: Filter by case_id
            status: Filter by status
            limit: Max number of tasks to return (most recent first)
            db: Optional request-scoped SQLAlchemy session

        Returns:
            List of task dicts
        """
        with self._lock:
            with self._session_scope(db) as session:
                statement = select(BackgroundTask)
                if owner:
                    statement = statement.where(BackgroundTask.owner == owner)
                if case_id:
                    statement = statement.where(BackgroundTask.case_id == case_id)
                if status:
                    statement = statement.where(BackgroundTask.status == status)

                statement = statement.order_by(desc(BackgroundTask.created_at), desc(BackgroundTask.id)).limit(limit)
                tasks = session.scalars(statement).all()
                return [self._to_dict(task) for task in tasks]

    def delete_task(self, task_id: str, *, db: Session | None = None) -> bool:
        """
        Delete a task.

        Args:
            task_id: Task ID
            db: Optional request-scoped SQLAlchemy session

        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            with self._session_scope(db) as session:
                task = session.get(BackgroundTask, task_id)
                if not task:
                    return False
                session.delete(task)
                session.flush()
                return True


# Singleton instance
background_task_storage = BackgroundTaskStorage()
