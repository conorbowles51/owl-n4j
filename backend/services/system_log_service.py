"""
Postgres-backed system log service.

Centralizes audit-style runtime events from routers and services while keeping
the public API from the old JSONL implementation.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from threading import RLock
from typing import Any, Callable, Dict, Iterator, List, Optional

from sqlalchemy import delete, desc, func, or_, select
from sqlalchemy.orm import Session

from postgres.models.runtime_state import SystemLog
from postgres.session import get_background_session


class LogType(str, Enum):
    AI_ASSISTANT = "ai_assistant"
    GRAPH_OPERATION = "graph_operation"
    CASE_MANAGEMENT = "case_management"
    CASE_OPERATION = "case_operation"
    DOCUMENT_INGESTION = "document_ingestion"
    USER_ACTION = "user_action"
    SYSTEM = "system"
    ERROR = "error"


class LogOrigin(str, Enum):
    FRONTEND = "frontend"
    BACKEND = "backend"
    INGESTION = "ingestion"
    SYSTEM = "system"


SessionFactory = Callable[[], Session]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _format_datetime(value: datetime | str | None) -> str:
    if value is None:
        return _now().isoformat()
    if isinstance(value, str):
        return value
    return value.isoformat()


def _enum_value(value: Enum | str) -> str:
    return value.value if isinstance(value, Enum) else str(value)


def _case_id_from_details(details: Optional[Dict[str, Any]]) -> str | None:
    if not isinstance(details, dict):
        return None
    value = details.get("case_id")
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned[:64] or None


class SystemLogService:
    """Service for managing system logs in Postgres."""

    def __init__(
        self,
        log_file: Optional[str] = None,
        session_factory: SessionFactory | None = None,
        max_logs: int = 10000,
    ) -> None:
        self.log_file = log_file
        self._session_factory = session_factory
        self._max_logs = max_logs
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
    def _to_dict(log: SystemLog) -> Dict[str, Any]:
        return {
            "timestamp": _format_datetime(log.timestamp),
            "type": log.log_type,
            "origin": log.origin,
            "action": log.action,
            "user": log.user,
            "success": bool(log.success),
            "error": log.error,
            "details": dict(log.details or {}),
        }

    def _trim_old_logs(self, db: Session) -> None:
        old_log_ids = db.scalars(
            select(SystemLog.id)
            .order_by(desc(SystemLog.timestamp), desc(SystemLog.id))
            .offset(self._max_logs)
        ).all()
        if old_log_ids:
            db.execute(delete(SystemLog).where(SystemLog.id.in_(old_log_ids)))

    def log(
        self,
        log_type: LogType,
        origin: LogOrigin,
        action: str,
        details: Optional[Dict[str, Any]] = None,
        user: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None,
        *,
        db: Session | None = None,
    ) -> None:
        """Log a system event."""
        timestamp = _now()
        entry = SystemLog(
            id=str(uuid.uuid4()),
            timestamp=timestamp,
            log_type=_enum_value(log_type),
            origin=_enum_value(origin),
            action=action,
            user=user,
            case_id=_case_id_from_details(details),
            success=success,
            error=error,
            details=details or {},
            created_at=timestamp,
            updated_at=timestamp,
        )

        with self._lock:
            try:
                with self._session_scope(db) as session:
                    session.add(entry)
                    session.flush()
                    self._trim_old_logs(session)
                    session.flush()
            except Exception as exc:
                print(f"[SystemLog] Error writing log: {exc}")

    def get_logs(
        self,
        log_type: Optional[LogType] = None,
        log_types: Optional[List[LogType]] = None,
        origin: Optional[LogOrigin] = None,
        origins: Optional[List[LogOrigin]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
        user: Optional[str] = None,
        success_only: Optional[bool] = None,
        *,
        db: Session | None = None,
    ) -> Dict[str, Any]:
        """Retrieve logs with filtering and pagination."""
        limit = max(1, min(limit, 1000))
        offset = max(0, offset)

        try:
            with self._session_scope(db) as session:
                statement = select(SystemLog)
                count_statement = select(func.count()).select_from(SystemLog)

                filters = []
                if log_types:
                    filters.append(SystemLog.log_type.in_([_enum_value(item) for item in log_types]))
                elif log_type:
                    filters.append(SystemLog.log_type == _enum_value(log_type))

                if origins:
                    filters.append(SystemLog.origin.in_([_enum_value(item) for item in origins]))
                elif origin:
                    filters.append(SystemLog.origin == _enum_value(origin))

                if start_time:
                    filters.append(SystemLog.timestamp >= start_time)
                if end_time:
                    filters.append(SystemLog.timestamp <= end_time)
                if user:
                    filters.append(SystemLog.user == user)
                if success_only is not None:
                    filters.append(SystemLog.success == success_only)

                for item in filters:
                    statement = statement.where(item)
                    count_statement = count_statement.where(item)

                total = session.scalar(count_statement) or 0
                records = session.scalars(
                    statement.order_by(desc(SystemLog.timestamp), desc(SystemLog.id))
                    .offset(offset)
                    .limit(limit)
                ).all()

                return {
                    "logs": [self._to_dict(record) for record in records],
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }
        except Exception as exc:
            print(f"[SystemLog] Error reading logs: {exc}")
            return {"logs": [], "total": 0, "limit": limit, "offset": offset}

    def get_case_logs(
        self,
        case_id: str,
        *,
        limit: int = 500,
        offset: int = 0,
        db: Session | None = None,
    ) -> Dict[str, Any]:
        """Retrieve audit log entries scoped to one case.

        The JSON details fallback keeps pre-migration records visible until all
        writers have populated the indexed column.
        """
        case_id = str(case_id or "").strip()
        limit = max(1, min(limit, self._max_logs))
        offset = max(0, offset)
        if not case_id:
            return {"logs": [], "total": 0, "limit": limit, "offset": offset}

        try:
            with self._session_scope(db) as session:
                case_filter = or_(
                    SystemLog.case_id == case_id,
                    SystemLog.details["case_id"].as_string() == case_id,
                )
                statement = select(SystemLog).where(case_filter)
                count_statement = select(func.count()).select_from(SystemLog).where(case_filter)

                total = session.scalar(count_statement) or 0
                records = session.scalars(
                    statement.order_by(desc(SystemLog.timestamp), desc(SystemLog.id))
                    .offset(offset)
                    .limit(limit)
                ).all()

                return {
                    "logs": [self._to_dict(record) for record in records],
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }
        except Exception as exc:
            print(f"[SystemLog] Error reading case logs: {exc}")
            return {"logs": [], "total": 0, "limit": limit, "offset": offset}

    def get_log_statistics(self, *, db: Session | None = None) -> Dict[str, Any]:
        """Get aggregate statistics about logs."""
        try:
            with self._session_scope(db) as session:
                total = session.scalar(select(func.count()).select_from(SystemLog)) or 0
                successful = (
                    session.scalar(
                        select(func.count()).select_from(SystemLog).where(SystemLog.success.is_(True))
                    )
                    or 0
                )
                failed = total - successful

                by_type = dict(
                    session.execute(
                        select(SystemLog.log_type, func.count())
                        .group_by(SystemLog.log_type)
                    ).all()
                )
                by_origin = dict(
                    session.execute(
                        select(SystemLog.origin, func.count())
                        .group_by(SystemLog.origin)
                    ).all()
                )

                return {
                    "total_logs": total,
                    "by_type": by_type,
                    "by_origin": by_origin,
                    "successful": successful,
                    "failed": failed,
                    "success_rate": successful / total if total else 0.0,
                }
        except Exception as exc:
            print(f"[SystemLog] Error calculating statistics: {exc}")
            return {
                "total_logs": 0,
                "by_type": {},
                "by_origin": {},
                "successful": 0,
                "failed": 0,
                "success_rate": 0.0,
            }

    def clear_logs(self, *, db: Session | None = None) -> None:
        """Clear all logs."""
        with self._lock:
            try:
                with self._session_scope(db) as session:
                    session.execute(delete(SystemLog))
                    session.flush()
            except Exception as exc:
                print(f"[SystemLog] Error clearing logs: {exc}")


system_log_service = SystemLogService()
