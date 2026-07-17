"""Types for case file export rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session

from postgres.models.case import Case
from postgres.models.user import User


@dataclass(frozen=True)
class ExportSection:
    key: str
    label: str
    description: str
    default_enabled: bool
    order: int
    render: Callable[["SectionContext"], str]


@dataclass
class SectionContext:
    db: Session
    case: Case
    current_user: User
    generated_at: datetime
    included_sections: tuple[ExportSection, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CaseExportResult:
    content: bytes
    filename: str
    media_type: str
