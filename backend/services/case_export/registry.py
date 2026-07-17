"""Small section registry for server-side case exports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

from sqlalchemy.orm import Session

from postgres.models.user import User


@dataclass(frozen=True)
class ExportContext:
    case_id: UUID
    case_name: str
    current_user: User
    db: Session | None = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class ExportSection:
    key: str
    title: str
    order: int
    render: Callable[[ExportContext], str]


_SECTIONS: dict[str, ExportSection] = {}


def register_section(section: ExportSection) -> ExportSection:
    if not section.key:
        raise ValueError("Export section key is required")
    _SECTIONS[section.key] = section
    return section


def get_registered_sections() -> list[ExportSection]:
    return sorted(_SECTIONS.values(), key=lambda item: (item.order, item.key))


def section_metadata() -> list[dict[str, Any]]:
    return [
        {"key": section.key, "title": section.title, "order": section.order}
        for section in get_registered_sections()
    ]
