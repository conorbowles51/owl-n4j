"""Persistence and lifecycle operations for the case Significant manifest."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from postgres.models.significant import SignificantEntity
from postgres.models.user import User
from services.system_log_service import LogOrigin, LogType, system_log_service


MAX_SIGNIFICANT_BATCH = 10_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_entity_keys(entity_keys: Iterable[str]) -> list[str]:
    """Trim, deduplicate, and bound a caller-provided entity-key collection."""
    normalized: list[str] = []
    seen: set[str] = set()
    for value in entity_keys:
        key = str(value or "").strip()
        if not key or key in seen:
            continue
        if len(key) > 512:
            raise ValueError("Entity keys cannot exceed 512 characters")
        seen.add(key)
        normalized.append(key)
        if len(normalized) > MAX_SIGNIFICANT_BATCH:
            raise ValueError(
                f"A single Significant operation is limited to {MAX_SIGNIFICANT_BATCH:,} entities"
            )
    return normalized


def _serialize(item: SignificantEntity) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "case_id": str(item.case_id),
        "entity_key": item.entity_key,
        "addition_source": item.addition_source,
        "context": dict(item.context or {}),
        "added_by_user_id": str(item.added_by_user_id) if item.added_by_user_id else None,
        "added_by_name": item.added_by.name if item.added_by else None,
        "added_by_email": item.added_by.email if item.added_by else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def list_significant_entities(db: Session, *, case_id: UUID) -> dict[str, Any]:
    rows = db.scalars(
        select(SignificantEntity)
        .options(selectinload(SignificantEntity.added_by))
        .where(
            SignificantEntity.case_id == case_id,
            SignificantEntity.removed_at.is_(None),
        )
        .order_by(SignificantEntity.created_at, SignificantEntity.entity_key)
    ).all()
    return {
        "case_id": str(case_id),
        "entity_keys": [row.entity_key for row in rows],
        "items": [_serialize(row) for row in rows],
        "count": len(rows),
    }


def get_significant_entity_keys(db: Session, *, case_id: UUID) -> list[str]:
    return list(
        db.scalars(
            select(SignificantEntity.entity_key)
            .where(
                SignificantEntity.case_id == case_id,
                SignificantEntity.removed_at.is_(None),
            )
            .order_by(SignificantEntity.entity_key)
        ).all()
    )


def add_significant_entities(
    db: Session,
    *,
    case_id: UUID,
    current_user: User,
    entity_keys: Iterable[str],
    addition_source: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    keys = normalize_entity_keys(entity_keys)
    if not keys:
        manifest = list_significant_entities(db, case_id=case_id)
        return {
            **manifest,
            "added_count": 0,
            "already_significant_count": 0,
            "added_entity_keys": [],
        }

    existing_rows = db.scalars(
        select(SignificantEntity).where(
            SignificantEntity.case_id == case_id,
            SignificantEntity.entity_key.in_(keys),
        )
    ).all()
    existing_by_key = {row.entity_key: row for row in existing_rows}
    timestamp = _now()
    added_keys: list[str] = []
    already_count = 0

    for key in keys:
        row = existing_by_key.get(key)
        if row is not None and row.removed_at is None:
            already_count += 1
            continue
        if row is None:
            row = SignificantEntity(
                case_id=case_id,
                entity_key=key,
                added_by_user_id=current_user.id,
                addition_source=addition_source,
                context=dict(context or {}),
            )
            db.add(row)
        else:
            row.added_by_user_id = current_user.id
            row.addition_source = addition_source
            row.context = dict(context or {})
            row.removed_at = None
            row.removed_by_user_id = None
            row.removal_reason = None
            row.updated_at = timestamp
        added_keys.append(key)

    system_log_service.log(
        log_type=LogType.CASE_OPERATION,
        origin=LogOrigin.BACKEND,
        action="Add Entities to Significant",
        details={
            "case_id": str(case_id),
            "entity_keys": added_keys,
            "addition_source": addition_source,
            "already_significant_count": already_count,
            "context": dict(context or {}),
        },
        user=current_user.email,
        db=db,
    )
    db.commit()

    manifest = list_significant_entities(db, case_id=case_id)
    return {
        **manifest,
        "added_count": len(added_keys),
        "already_significant_count": already_count,
        "added_entity_keys": added_keys,
    }


def remove_significant_entities(
    db: Session,
    *,
    case_id: UUID,
    current_user: User,
    entity_keys: Iterable[str],
    removal_reason: str = "manual",
) -> dict[str, Any]:
    keys = normalize_entity_keys(entity_keys)
    rows = db.scalars(
        select(SignificantEntity).where(
            SignificantEntity.case_id == case_id,
            SignificantEntity.entity_key.in_(keys),
            SignificantEntity.removed_at.is_(None),
        )
    ).all()
    timestamp = _now()
    removed_keys: list[str] = []
    for row in rows:
        row.removed_at = timestamp
        row.removed_by_user_id = current_user.id
        row.removal_reason = removal_reason
        row.updated_at = timestamp
        removed_keys.append(row.entity_key)

    system_log_service.log(
        log_type=LogType.CASE_OPERATION,
        origin=LogOrigin.BACKEND,
        action="Remove Entities from Significant",
        details={
            "case_id": str(case_id),
            "entity_keys": removed_keys,
            "removal_reason": removal_reason,
        },
        user=current_user.email,
        db=db,
    )
    db.commit()

    manifest = list_significant_entities(db, case_id=case_id)
    return {
        **manifest,
        "removed_count": len(removed_keys),
        "not_significant_count": len(keys) - len(removed_keys),
        "removed_entity_keys": removed_keys,
    }


def clear_significant_entities(
    db: Session,
    *,
    case_id: UUID,
    current_user: User,
) -> dict[str, Any]:
    active_keys = get_significant_entity_keys(db, case_id=case_id)
    return remove_significant_entities(
        db,
        case_id=case_id,
        current_user=current_user,
        entity_keys=active_keys,
        removal_reason="clear",
    )


def suspend_significant_entity_for_delete(
    db: Session,
    *,
    case_id: UUID,
    entity_key: str,
    current_user: User | None,
) -> bool:
    row = db.scalar(
        select(SignificantEntity).where(
            SignificantEntity.case_id == case_id,
            SignificantEntity.entity_key == entity_key,
            SignificantEntity.removed_at.is_(None),
        )
    )
    if row is None:
        return False
    timestamp = _now()
    row.removed_at = timestamp
    row.removed_by_user_id = current_user.id if current_user else None
    row.removal_reason = "entity_deleted"
    row.updated_at = timestamp
    db.commit()
    return True


def restore_significant_entity_after_restore(
    db: Session,
    *,
    case_id: UUID,
    entity_key: str,
) -> bool:
    row = db.scalar(
        select(SignificantEntity).where(
            SignificantEntity.case_id == case_id,
            SignificantEntity.entity_key == entity_key,
            SignificantEntity.removal_reason == "entity_deleted",
        )
    )
    if row is None:
        return False
    row.removed_at = None
    row.removed_by_user_id = None
    row.removal_reason = None
    row.updated_at = _now()
    db.commit()
    return True


def transfer_significant_membership_after_merge(
    db: Session,
    *,
    case_id: UUID,
    source_entity_keys: Iterable[str],
    merged_entity_key: str,
) -> bool:
    """Transfer active membership when any source entity was significant."""
    source_keys = normalize_entity_keys(source_entity_keys)
    if not source_keys or not merged_entity_key:
        return False

    rows = db.scalars(
        select(SignificantEntity).where(
            SignificantEntity.case_id == case_id,
            SignificantEntity.entity_key.in_(source_keys),
        )
    ).all()
    if not any(row.removed_at is None for row in rows):
        return False

    timestamp = _now()
    target = db.scalar(
        select(SignificantEntity).where(
            SignificantEntity.case_id == case_id,
            SignificantEntity.entity_key == merged_entity_key,
        )
    )
    if target is None:
        target = SignificantEntity(
            case_id=case_id,
            entity_key=merged_entity_key,
            added_by_user_id=None,
            addition_source="merge",
            context={"source_entity_keys": source_keys},
        )
        db.add(target)
    else:
        target.addition_source = "merge"
        target.context = {"source_entity_keys": source_keys}
        target.removed_at = None
        target.removed_by_user_id = None
        target.removal_reason = None
        target.updated_at = timestamp

    for row in rows:
        if row.entity_key == merged_entity_key:
            continue
        if row.removed_at is None:
            row.removed_at = timestamp
            row.removed_by_user_id = None
            row.removal_reason = "entity_merged"
            row.updated_at = timestamp

    db.commit()
    return True
