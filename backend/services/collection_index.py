"""The per-record membership index for `phone_selection` links (07 section 6.4 item 7)."""
from __future__ import annotations

import uuid
from typing import Iterable

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from postgres.models.collection_membership import CONTAINER_TYPES, CollectionMembership

_WRITE_PART = 1000


def write_members(
    db: Session, *, case_id: uuid.UUID, container_type: str, container_id: str, link_id: uuid.UUID,
    members: Iterable[str],
) -> int:
    """Index every record of a selection link. Returns the number of rows written (one per distinct record)."""
    if container_type not in CONTAINER_TYPES:
        raise ValueError(f"Unknown collection container {container_type}")
    records = list(dict.fromkeys(str(value) for value in members if str(value)))
    rows = [
        {"id": uuid.uuid4(), "case_id": case_id, "container_type": container_type,
         "container_id": str(container_id), "link_id": link_id, "record_id": record}
        for record in records
    ]
    for start in range(0, len(rows), _WRITE_PART):
        db.execute(insert(CollectionMembership), rows[start:start + _WRITE_PART])
    return len(rows)


def remove_members(db: Session, *, link_id: uuid.UUID) -> None:
    db.execute(delete(CollectionMembership).where(CollectionMembership.link_id == link_id))


def members_of(db: Session, *, link_id: uuid.UUID) -> tuple[str, ...]:
    return tuple(db.scalars(select(CollectionMembership.record_id).where(CollectionMembership.link_id == link_id)).all())
