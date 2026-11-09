"""Persistence and lifecycle operations for the case Significant manifest."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from postgres.models.significant import SignificantEntity, SignificantRelationship
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
        "relationships": list_significant_relationships(db, case_id=case_id),
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


def get_significant_layer_keys(db: Session, *, case_id: UUID) -> list[str]:
    """The entities the Significant layer shows: those marked, then both ends of each relationship marked (GR-01),
    so a marked relationship is drawn in the layer even when neither end is marked itself."""
    keys = get_significant_entity_keys(db, case_id=case_id)
    seen = set(keys)
    for source_key, target_key in db.execute(
        select(SignificantRelationship.source_key, SignificantRelationship.target_key).where(
            SignificantRelationship.case_id == case_id, SignificantRelationship.removed_at.is_(None),
        ).order_by(SignificantRelationship.created_at, SignificantRelationship.id)
    ):
        for key in (source_key, target_key):
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return keys


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


# ---- relationships (GR-01) --------------------------------------------------------------------------------------------
# A relationship is marked by its (source key, type, target key) within the case: graph reads give no stable id.


def normalize_relationships(relationships: Iterable[Any]) -> list[tuple[str, str, str]]:
    """Trim and deduplicate caller-given relationships ({source_key, type, target_key}) into triples."""
    out: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for rel in relationships:
        get = rel.get if isinstance(rel, dict) else (lambda k, _r=rel: getattr(_r, k, None))
        triple = (str(get("source_key") or "").strip(), str(get("type") or "").strip(),
                  str(get("target_key") or "").strip())
        if not all(triple):
            raise ValueError("A relationship needs its source entity, its type and its target entity")
        if len(triple[0]) > 512 or len(triple[2]) > 512 or len(triple[1]) > 255:
            raise ValueError("A relationship key is too long")
        if triple in seen:
            continue
        seen.add(triple)
        out.append(triple)
        if len(out) > MAX_SIGNIFICANT_BATCH:
            raise ValueError(
                f"A single Significant operation is limited to {MAX_SIGNIFICANT_BATCH:,} relationships")
    return out


def _serialize_relationship(item: SignificantRelationship) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "source_key": item.source_key,
        "type": item.rel_type,
        "target_key": item.target_key,
        "addition_source": item.addition_source,
        "context": dict(item.context or {}),
        "added_by_user_id": str(item.added_by_user_id) if item.added_by_user_id else None,
        "added_by_name": item.added_by.name if item.added_by else None,
        "added_by_email": item.added_by.email if item.added_by else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def list_significant_relationships(db: Session, *, case_id: UUID) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(SignificantRelationship)
        .options(selectinload(SignificantRelationship.added_by))
        .where(SignificantRelationship.case_id == case_id, SignificantRelationship.removed_at.is_(None))
        .order_by(SignificantRelationship.created_at, SignificantRelationship.source_key,
                  SignificantRelationship.rel_type, SignificantRelationship.target_key)
    ).all()
    return [_serialize_relationship(row) for row in rows]


def _relationship_rows(db: Session, case_id: UUID, triples: list[tuple[str, str, str]]):
    if not triples:
        return {}
    sources = {t[0] for t in triples}
    rows = db.scalars(
        select(SignificantRelationship).where(
            SignificantRelationship.case_id == case_id,
            SignificantRelationship.source_key.in_(sources),
        )
    ).all()
    wanted = set(triples)
    return {(r.source_key, r.rel_type, r.target_key): r for r in rows
            if (r.source_key, r.rel_type, r.target_key) in wanted}


def add_significant_relationships(
    db: Session,
    *,
    case_id: UUID,
    current_user: User,
    relationships: Iterable[Any],
    addition_source: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    triples = normalize_relationships(relationships)
    existing = _relationship_rows(db, case_id, triples)
    timestamp = _now()
    added: list[tuple[str, str, str]] = []
    already = 0
    for triple in triples:
        row = existing.get(triple)
        if row is not None and row.removed_at is None:
            already += 1
            continue
        if row is None:
            db.add(SignificantRelationship(
                case_id=case_id, source_key=triple[0], rel_type=triple[1], target_key=triple[2],
                added_by_user_id=current_user.id, addition_source=addition_source, context=dict(context or {}),
            ))
        else:
            row.added_by_user_id = current_user.id
            row.addition_source = addition_source
            row.context = dict(context or {})
            row.removed_at = None
            row.removed_by_user_id = None
            row.removal_reason = None
            row.updated_at = timestamp
        added.append(triple)
    system_log_service.log(
        log_type=LogType.CASE_OPERATION,
        origin=LogOrigin.BACKEND,
        action="Add Relationships to Significant",
        details={"case_id": str(case_id), "relationships": [list(t) for t in added],
                 "addition_source": addition_source, "already_significant_count": already,
                 "context": dict(context or {})},
        user=current_user.email,
        db=db,
    )
    db.commit()
    manifest = list_significant_entities(db, case_id=case_id)
    return {**manifest, "added_relationship_count": len(added), "already_significant_relationship_count": already}


def remove_significant_relationships(
    db: Session,
    *,
    case_id: UUID,
    current_user: User,
    relationships: Iterable[Any],
    removal_reason: str = "manual",
) -> dict[str, Any]:
    triples = normalize_relationships(relationships)
    existing = _relationship_rows(db, case_id, triples)
    timestamp = _now()
    removed: list[tuple[str, str, str]] = []
    for triple, row in existing.items():
        if row.removed_at is not None:
            continue
        row.removed_at = timestamp
        row.removed_by_user_id = current_user.id
        row.removal_reason = removal_reason
        row.updated_at = timestamp
        removed.append(triple)
    system_log_service.log(
        log_type=LogType.CASE_OPERATION,
        origin=LogOrigin.BACKEND,
        action="Remove Relationships from Significant",
        details={"case_id": str(case_id), "relationships": [list(t) for t in removed],
                 "removal_reason": removal_reason},
        user=current_user.email,
        db=db,
    )
    db.commit()
    manifest = list_significant_entities(db, case_id=case_id)
    return {**manifest, "removed_relationship_count": len(removed),
            "not_significant_relationship_count": len(triples) - len(removed)}


def transfer_significant_relationships_after_merge(
    db: Session,
    *,
    case_id: UUID,
    source_entity_keys: Iterable[str],
    merged_entity_key: str,
) -> int:
    """A merge rewires relationships onto the merged entity; carry each active mark with it.

    The old row is kept, marked removed with reason "entity_merged", and a mark on the rewired triple takes its
    place with the old triple in its context. A relationship between two of the merged entities becomes a loop on
    the merged entity and keeps its mark there. Returns how many marks moved.
    """
    sources = set(normalize_entity_keys(source_entity_keys))
    if not sources or not merged_entity_key:
        return 0
    from sqlalchemy import or_
    rows = db.scalars(
        select(SignificantRelationship).where(
            SignificantRelationship.case_id == case_id,
            SignificantRelationship.removed_at.is_(None),
            or_(SignificantRelationship.source_key.in_(sources), SignificantRelationship.target_key.in_(sources)),
        )
    ).all()
    if not rows:
        return 0
    timestamp = _now()
    moved = 0
    for row in rows:
        new = (merged_entity_key if row.source_key in sources else row.source_key, row.rel_type,
               merged_entity_key if row.target_key in sources else row.target_key)
        target = _relationship_rows(db, case_id, [new]).get(new)
        if target is None:
            db.add(SignificantRelationship(
                case_id=case_id, source_key=new[0], rel_type=new[1], target_key=new[2],
                added_by_user_id=row.added_by_user_id, addition_source="merge",
                context={**dict(row.context or {}), "merged_from": [row.source_key, row.rel_type, row.target_key]},
            ))
            db.flush()
        elif target.removed_at is not None:
            target.removed_at = None
            target.removed_by_user_id = None
            target.removal_reason = None
            target.addition_source = "merge"
            target.context = {**dict(row.context or {}), "merged_from": [row.source_key, row.rel_type, row.target_key]}
            target.updated_at = timestamp
        row.removed_at = timestamp
        row.removed_by_user_id = None
        row.removal_reason = "entity_merged"
        row.updated_at = timestamp
        moved += 1
    db.commit()
    return moved
