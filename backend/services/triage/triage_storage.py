"""
Postgres-backed triage orchestration storage.

File inventory and processor artifacts remain in Neo4j; this service owns only
case/stage orchestration metadata and structured state snapshots.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import RLock
from typing import Callable, Dict, Iterator, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload

from postgres.models.triage import TriageCase, TriageStage
from postgres.session import get_background_session


SessionFactory = Callable[[], Session]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_datetime(value: datetime | str | None) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()


def _default_scan_stats() -> Dict:
    return {
        "total_files": 0,
        "total_size": 0,
        "os_detected": None,
    }


class TriageStorage:
    """Thread-safe Postgres storage for triage case and stage state."""

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
        """Compatibility no-op: state is read from Postgres on every call."""

    def _persist(self) -> None:
        """Compatibility no-op: writes are committed by the active DB session."""

    @staticmethod
    def _stage_to_dict(stage: TriageStage) -> Dict:
        return {
            "id": stage.id,
            "order": stage.stage_order,
            "name": stage.name,
            "type": stage.type,
            "status": stage.status,
            "config": dict(stage.config or {}),
            "created_at": _format_datetime(stage.created_at),
            "started_at": _format_datetime(stage.started_at),
            "completed_at": _format_datetime(stage.completed_at),
            "files_total": stage.files_total or 0,
            "files_processed": stage.files_processed or 0,
            "files_failed": stage.files_failed or 0,
            "error": stage.error,
        }

    @classmethod
    def _case_to_dict(cls, case: TriageCase) -> Dict:
        scan_stats = dict(case.scan_stats or {})
        for key, value in _default_scan_stats().items():
            scan_stats.setdefault(key, value)
        data = {
            "id": case.id,
            "name": case.name,
            "description": case.description or "",
            "source_path": case.source_path,
            "status": case.status,
            "created_at": _format_datetime(case.created_at) or _now().isoformat(),
            "updated_at": _format_datetime(case.updated_at) or _now().isoformat(),
            "created_by": case.created_by,
            "stages": [cls._stage_to_dict(stage) for stage in sorted(case.stages, key=lambda s: s.stage_order)],
            "scan_cursor": case.scan_cursor,
            "scan_stats": scan_stats,
        }
        if case.profile is not None:
            data["profile"] = case.profile
        return data

    # -- Case CRUD -----------------------------------------------------

    def create_case(
        self,
        *,
        name: str,
        description: str = "",
        source_path: str,
        created_by: str,
        db: Session | None = None,
    ) -> Dict:
        with self._lock:
            with self._session_scope(db) as session:
                case_id = str(uuid.uuid4())
                timestamp = _now()
                case = TriageCase(
                    id=case_id,
                    name=name,
                    description=description or "",
                    source_path=source_path,
                    status="created",
                    created_by=created_by,
                    scan_cursor=None,
                    scan_stats=_default_scan_stats(),
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                session.add(case)
                session.flush()

                for order, stage_name, stage_type in (
                    (0, "Scan", "scan"),
                    (1, "Classify", "classify"),
                    (2, "Profile", "profile"),
                ):
                    session.add(_make_stage(case_id, order, stage_name, stage_type, timestamp=timestamp))

                session.flush()
                session.refresh(case)
                return self._case_to_dict(case)

    def get_case(self, case_id: str, *, db: Session | None = None) -> Optional[Dict]:
        with self._lock:
            with self._session_scope(db) as session:
                case = session.scalars(
                    select(TriageCase)
                    .options(joinedload(TriageCase.stages))
                    .where(TriageCase.id == case_id)
                ).unique().first()
                return self._case_to_dict(case) if case else None

    def update_case(self, case_id: str, *, db: Session | None = None, **updates) -> Optional[Dict]:
        with self._lock:
            with self._session_scope(db) as session:
                case = session.scalars(
                    select(TriageCase)
                    .options(joinedload(TriageCase.stages))
                    .where(TriageCase.id == case_id)
                ).unique().first()
                if not case:
                    return None

                for key, value in updates.items():
                    if key == "scan_stats" and isinstance(value, dict):
                        merged = dict(case.scan_stats or {})
                        merged.update(value)
                        case.scan_stats = merged
                    elif key == "profile":
                        case.profile = value
                    elif key == "scan_cursor":
                        case.scan_cursor = value
                    elif hasattr(case, key):
                        setattr(case, key, value)

                case.updated_at = _now()
                session.flush()
                return self._case_to_dict(case)

    def list_cases(self, owner: Optional[str] = None, *, db: Session | None = None) -> List[Dict]:
        with self._lock:
            with self._session_scope(db) as session:
                statement = select(TriageCase).options(joinedload(TriageCase.stages))
                if owner:
                    statement = statement.where(TriageCase.created_by == owner)
                statement = statement.order_by(desc(TriageCase.created_at), desc(TriageCase.id))
                cases = session.scalars(statement).unique().all()
                return [self._case_to_dict(case) for case in cases]

    def delete_case(self, case_id: str, *, db: Session | None = None) -> bool:
        with self._lock:
            with self._session_scope(db) as session:
                case = session.get(TriageCase, case_id)
                if not case:
                    return False
                session.delete(case)
                session.flush()
                return True

    # -- Stage helpers -------------------------------------------------

    def get_stage(self, case_id: str, stage_id: str, *, db: Session | None = None) -> Optional[Dict]:
        with self._lock:
            with self._session_scope(db) as session:
                stage = session.scalars(
                    select(TriageStage).where(
                        TriageStage.triage_case_id == case_id,
                        TriageStage.id == stage_id,
                    )
                ).first()
                return self._stage_to_dict(stage) if stage else None

    def update_stage(
        self,
        case_id: str,
        stage_id: str,
        *,
        db: Session | None = None,
        **updates,
    ) -> Optional[Dict]:
        with self._lock:
            with self._session_scope(db) as session:
                stage = session.scalars(
                    select(TriageStage).where(
                        TriageStage.triage_case_id == case_id,
                        TriageStage.id == stage_id,
                    )
                ).first()
                if not stage:
                    return None

                for key, value in updates.items():
                    if key in {"started_at", "completed_at"}:
                        setattr(stage, key, _parse_datetime(value))
                    elif key == "order":
                        stage.stage_order = int(value)
                    elif hasattr(stage, key):
                        setattr(stage, key, value)

                case = session.get(TriageCase, case_id)
                if case:
                    case.updated_at = _now()
                stage.updated_at = _now()
                session.flush()
                return self._stage_to_dict(stage)

    def add_stage(
        self,
        case_id: str,
        *,
        name: str,
        stage_type: str = "custom",
        config: Optional[Dict] = None,
        db: Session | None = None,
    ) -> Optional[Dict]:
        with self._lock:
            with self._session_scope(db) as session:
                case = session.get(TriageCase, case_id)
                if not case:
                    return None

                order = session.scalar(
                    select(TriageStage.stage_order)
                    .where(TriageStage.triage_case_id == case_id)
                    .order_by(desc(TriageStage.stage_order))
                    .limit(1)
                )
                next_order = 0 if order is None else int(order) + 1
                timestamp = _now()
                stage = _make_stage(
                    case_id,
                    next_order,
                    name,
                    stage_type,
                    config=config,
                    timestamp=timestamp,
                )
                session.add(stage)
                case.updated_at = timestamp
                session.flush()
                return self._stage_to_dict(stage)

    def remove_stage(self, case_id: str, stage_id: str, *, db: Session | None = None) -> bool:
        with self._lock:
            with self._session_scope(db) as session:
                stage = session.scalars(
                    select(TriageStage).where(
                        TriageStage.triage_case_id == case_id,
                        TriageStage.id == stage_id,
                    )
                ).first()
                if not stage:
                    return False

                session.delete(stage)
                session.flush()

                stages = session.scalars(
                    select(TriageStage)
                    .where(TriageStage.triage_case_id == case_id)
                    .order_by(TriageStage.stage_order)
                ).all()
                for order, item in enumerate(stages):
                    item.stage_order = order

                case = session.get(TriageCase, case_id)
                if case:
                    case.updated_at = _now()
                session.flush()
                return True


def _make_stage(
    case_id: str,
    order: int,
    name: str,
    stage_type: str,
    config: Optional[Dict] = None,
    *,
    timestamp: datetime | None = None,
) -> TriageStage:
    now = timestamp or _now()
    return TriageStage(
        id=str(uuid.uuid4()),
        triage_case_id=case_id,
        stage_order=order,
        name=name,
        type=stage_type,
        status="pending",
        config=config or {},
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
        files_total=0,
        files_processed=0,
        files_failed=0,
        error=None,
    )


triage_storage = TriageStorage()
