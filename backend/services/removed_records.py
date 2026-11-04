"""Kept copies of removed analyst work, and putting a removal back (followups m11032229063349).

A removal that used to be a bare hard delete (a dossier assessment and its supporting links, an interview with its
working notes and evidence links, a media item, a dossier link, a saved snapshot) first calls ``keep`` with the rows
it is about to delete, in the same transaction. ``restore`` puts exactly those rows back, column for column, and
stamps the copy restored. Nothing here changes what the removal removes or what a read shows.
"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import inspect as sa_inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from postgres.models.removed_record import RemovedRecord


class RemovedRecordError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _plain(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, enum.Enum):
        return value.value
    return value


def row_values(obj) -> dict[str, Any]:
    """Every column of a mapped row, as JSON values, keyed by column name."""
    mapper = sa_inspect(obj).mapper
    return {attr.columns[0].name: _plain(getattr(obj, attr.key)) for attr in mapper.column_attrs}


def _mapper_for(table: str):
    from postgres.base import Base
    for mapper in Base.registry.mappers:
        if getattr(mapper.local_table, "name", None) == table:
            return mapper
    raise RemovedRecordError(f"Removed rows of {table} cannot be put back here.", 409)


def _typed(column, value: Any) -> Any:
    if value is None:
        return None
    try:
        python_type = column.type.python_type
    except NotImplementedError:
        return value
    if python_type is uuid.UUID:
        return uuid.UUID(str(value))
    if python_type is datetime:
        return datetime.fromisoformat(value)
    if python_type is date:
        return date.fromisoformat(value)
    if python_type is Decimal:
        return Decimal(str(value))
    if isinstance(python_type, type) and issubclass(python_type, enum.Enum):
        return python_type(value)
    return value


def _revive(table: str, values: dict[str, Any]):
    mapper = _mapper_for(table)
    kwargs = {}
    for attr in mapper.column_attrs:
        column = attr.columns[0]
        if column.name in values:
            kwargs[attr.key] = _typed(column, values[column.name])
    return mapper.class_(**kwargs)


def _actor(user) -> tuple[uuid.UUID | None, str | None]:
    if user is None:
        return None, None
    if isinstance(user, dict):
        return None, user.get("email") or user.get("username")
    user_id = getattr(user, "id", None)
    return (user_id if isinstance(user_id, uuid.UUID) else None,
            getattr(user, "email", None) or getattr(user, "username", None))


def keep(db: Session, *, kind: str, case_id, subject_id, label: str | None, rows: Iterable[Any], user) -> RemovedRecord:
    """Keep a copy of ``rows`` (parents first) before they are deleted. Call in the delete's own transaction."""
    rows = [row for row in rows if row is not None]
    user_id, by = _actor(user)
    record = RemovedRecord(
        id=uuid.uuid4(), kind=kind, subject_id=str(subject_id), label=(label or None) and str(label)[:500],
        case_id=uuid.UUID(str(case_id)) if case_id else None,
        data={"rows": [{"table": sa_inspect(row).mapper.local_table.name, "values": row_values(row)} for row in rows]},
        removed_by_user_id=user_id, removed_by=by, removed_at=datetime.now(timezone.utc),
    )
    db.add(record)
    db.flush()
    return record


def as_dict(record: RemovedRecord) -> dict[str, Any]:
    return dict(id=str(record.id), case_id=str(record.case_id) if record.case_id else None, kind=record.kind,
                subject_id=record.subject_id, label=record.label, removed_by=record.removed_by,
                removed_at=record.removed_at.isoformat() if record.removed_at else None,
                restored_at=record.restored_at.isoformat() if record.restored_at else None,
                restored_by=record.restored_by, rows=len((record.data or {}).get("rows") or []),
                dossier_id=_first_values(record).get("dossier_id"))


def _first_values(record: RemovedRecord) -> dict[str, Any]:
    rows = (record.data or {}).get("rows") or []
    return (rows[0].get("values") or {}) if rows else {}


def list_removed(db: Session, *, case_id, kinds: Iterable[str] | None = None, include_restored: bool = False,
                 dossier_id=None, limit: int = 200) -> dict[str, Any]:
    query = select(RemovedRecord).where(RemovedRecord.case_id == uuid.UUID(str(case_id)))
    if kinds:
        query = query.where(RemovedRecord.kind.in_(list(kinds)))
    if not include_restored:
        query = query.where(RemovedRecord.restored_at.is_(None))
    query = query.order_by(RemovedRecord.removed_at.desc())
    if dossier_id is not None:
        rows = [r for r in db.scalars(query) if str(_first_values(r).get("dossier_id")) == str(dossier_id)][:limit + 1]
    else:
        rows = list(db.scalars(query.limit(limit + 1)))
    out = dict(items=[as_dict(r) for r in rows[:limit]], returned=min(len(rows), limit))
    if len(rows) > limit:
        out["clipped"] = f"Showing the latest {limit} removals."
    return out


def load(db: Session, record_id) -> RemovedRecord:
    try:
        record = db.get(RemovedRecord, uuid.UUID(str(record_id)))
    except (TypeError, ValueError):
        record = None
    if record is None:
        raise RemovedRecordError("That removal was not found.", 404)
    return record


def restore(db: Session, record: RemovedRecord, *, user) -> dict[str, Any]:
    """Put the removed rows back as they were. Refused when already restored or when a row cannot go back (its
    dossier was removed since, or a row with the same id exists)."""
    if record.restored_at is not None:
        raise RemovedRecordError("This removal was already undone.", 409)
    try:
        with db.begin_nested():
            for row in (record.data or {}).get("rows") or []:
                db.add(_revive(row["table"], row["values"]))
                db.flush()
    except IntegrityError as exc:
        raise RemovedRecordError("This cannot be put back: what it belonged to was removed or changed since. "
                                 "The kept copy is unchanged.", 409) from exc
    _, by = _actor(user)
    record.restored_at, record.restored_by = datetime.now(timezone.utc), by
    db.flush()
    return as_dict(record)
