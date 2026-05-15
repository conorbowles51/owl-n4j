"""
Postgres-backed triage workflow templates.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import RLock
from typing import Callable, Dict, Iterator, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from postgres.models.triage import TriageTemplate
from postgres.session import get_background_session

logger = __import__("logging").getLogger(__name__)

SessionFactory = Callable[[], Session]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _format_datetime(value: datetime | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.isoformat()


class TemplateService:
    """Manages reusable triage workflow templates."""

    def __init__(self, session_factory: SessionFactory | None = None):
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
    def _to_summary(template: TriageTemplate) -> Dict:
        stages = list(template.stages or [])
        return {
            "id": template.id,
            "name": template.name,
            "description": template.description or "",
            "created_by": template.created_by or "",
            "created_at": _format_datetime(template.created_at),
            "stage_count": len(stages),
            "stages": [
                {"name": s.get("name"), "processor_name": s.get("processor_name")}
                for s in stages
            ],
        }

    @staticmethod
    def _to_detail(template: TriageTemplate) -> Dict:
        data = TemplateService._to_summary(template)
        data["stages"] = list(template.stages or [])
        return data

    def save_template(
        self,
        case_id: str,
        name: str,
        description: str = "",
        created_by: str = "",
        *,
        db: Session | None = None,
    ) -> Dict:
        from services.triage.triage_storage import triage_storage

        case = triage_storage.get_case(case_id, db=db)
        if not case:
            raise ValueError(f"Triage case not found: {case_id}")

        custom_stages = []
        for stage in case.get("stages", []):
            if stage.get("type") == "custom":
                custom_stages.append({
                    "name": stage.get("name"),
                    "processor_name": stage.get("config", {}).get("processor_name"),
                    "config": stage.get("config", {}).get("config", {}),
                    "file_filter": stage.get("config", {}).get("file_filter", {}),
                })

        if not custom_stages:
            raise ValueError("No custom stages to save as template")

        with self._lock:
            with self._session_scope(db) as session:
                timestamp = _now()
                template = TriageTemplate(
                    id=str(uuid.uuid4()),
                    name=name,
                    description=description or "",
                    created_by=created_by or "",
                    stages=custom_stages,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                session.add(template)
                session.flush()
                return self._to_detail(template)

    def list_templates(self, *, db: Session | None = None) -> List[Dict]:
        with self._lock:
            with self._session_scope(db) as session:
                templates = session.scalars(
                    select(TriageTemplate).order_by(desc(TriageTemplate.created_at), desc(TriageTemplate.id))
                ).all()
                return [self._to_summary(template) for template in templates]

    def get_template(self, template_id: str, *, db: Session | None = None) -> Optional[Dict]:
        with self._lock:
            with self._session_scope(db) as session:
                template = session.get(TriageTemplate, template_id)
                return self._to_detail(template) if template else None

    def apply_template(
        self,
        template_id: str,
        case_id: str,
        *,
        db: Session | None = None,
    ) -> List[Dict]:
        from services.triage.triage_storage import triage_storage

        template = self.get_template(template_id, db=db)
        if not template:
            raise ValueError(f"Template not found: {template_id}")

        case = triage_storage.get_case(case_id, db=db)
        if not case:
            raise ValueError(f"Triage case not found: {case_id}")

        created_stages = []
        for stage_def in template.get("stages", []):
            stage = triage_storage.add_stage(
                case_id,
                name=stage_def["name"],
                stage_type="custom",
                config={
                    "processor_name": stage_def["processor_name"],
                    "config": stage_def.get("config", {}),
                    "file_filter": stage_def.get("file_filter", {}),
                },
                db=db,
            )
            if stage:
                created_stages.append(stage)

        return created_stages

    def delete_template(self, template_id: str, *, db: Session | None = None) -> bool:
        with self._lock:
            with self._session_scope(db) as session:
                template = session.get(TriageTemplate, template_id)
                if not template:
                    return False
                session.delete(template)
                session.flush()
                return True


template_service = TemplateService()
