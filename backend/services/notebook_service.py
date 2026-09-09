"""Compatibility service for the case Notebook backed by canonical entries."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import desc, or_
from sqlalchemy.orm import Session, selectinload

from postgres.models.user import User
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
from services.system_log_service import LogOrigin, LogType, system_log_service
from services.workspace_entry_service import create_entry, soft_delete_entry, update_entry


NOTEBOOK_TARGET_TYPES = {
    "entity",
    "evidence",
    "document",
    "timeline_event",
    "agent_artifact",
}


class NotebookNoteNotFound(Exception):
    """Raised when a canonical Notebook note is absent from the requested case."""


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _clean_title(value: str | None) -> str | None:
    value = _clean_text(value)
    if value and len(value) > 255:
        raise ValueError("Title must be 255 characters or fewer")
    return value


def _clean_body(value: str | None) -> str:
    body = _clean_text(value)
    if not body:
        raise ValueError("Note body is required")
    return body


def _clean_tags(tags: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    for tag in tags or []:
        value = _clean_text(tag)
        if value and value not in cleaned:
            cleaned.append(value[:64])
    return cleaned[:20]


def _sanitize_links(links: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Validate the legacy Notebook link shape without writing legacy rows."""

    sanitized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for link in links or []:
        target_type = _clean_text(str(link.get("target_type") or "")) or ""
        target_id = _clean_text(str(link.get("target_id") or "")) or ""
        if target_type not in NOTEBOOK_TARGET_TYPES:
            raise ValueError(f"Unsupported note link type: {target_type}")
        if not target_id:
            raise ValueError("Note link target_id is required")
        key = (target_type, target_id)
        if key in seen:
            continue
        seen.add(key)
        raw_label = link.get("target_label")
        target_label = _clean_text(str(raw_label)) if raw_label is not None else None
        metadata = link.get("metadata")
        sanitized.append(
            {
                "target_type": target_type,
                "target_id": target_id[:512],
                "target_label": target_label[:512] if target_label else None,
                "metadata": dict(metadata) if isinstance(metadata, dict) else {},
            }
        )
    return sanitized


def _to_canonical_links(links: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    canonical: list[dict[str, Any]] = []
    for link in _sanitize_links(links):
        metadata = dict(link["metadata"])
        canonical.append(
            {
                "target_type": {
                    "entity": "graph_entity",
                    "document": "evidence",
                }.get(link["target_type"], link["target_type"]),
                "target_id": link["target_id"],
                "target_label": link["target_label"],
                "relationship": metadata.get("relationship", "unclassified"),
                "source_anchor": metadata.get("source_anchor", {}),
                "metadata": metadata,
            }
        )
    return canonical


def _link_to_dict(link: WorkspaceEntryLink) -> dict[str, Any]:
    metadata = dict(link.link_metadata or {})
    if link.relationship_type != "unclassified":
        metadata["relationship"] = link.relationship_type
    if link.source_anchor:
        metadata["source_anchor"] = dict(link.source_anchor)
    return {
        "id": str(link.id),
        "note_id": str(link.entry_id),
        "case_id": str(link.case_id),
        "target_type": "entity" if link.target_type == "graph_entity" else link.target_type,
        "target_id": link.target_id,
        "target_label": link.target_label,
        "metadata": metadata,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


def note_to_dict(note: WorkspaceEntry) -> dict[str, Any]:
    return {
        "id": str(note.id),
        "case_id": str(note.case_id),
        "title": note.title,
        "body": note.body,
        "tags": list(note.tags or []),
        "visibility": "case",
        "author_user_id": str(note.author_user_id) if note.author_user_id else None,
        "author_email": note.author_email,
        "author_name": note.author_name,
        "created_at": note.created_at.isoformat() if note.created_at else None,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
        "links": [_link_to_dict(link) for link in note.links],
    }


def _base_query(db: Session, case_id: UUID):
    return (
        db.query(WorkspaceEntry)
        .options(selectinload(WorkspaceEntry.links))
        .filter(
            WorkspaceEntry.case_id == case_id,
            WorkspaceEntry.entry_type == "note",
            WorkspaceEntry.legacy_source == "notebook_note",
        )
    )


def _get_note(db: Session, case_id: UUID, note_id: UUID) -> WorkspaceEntry:
    note = (
        _base_query(db, case_id)
        .filter(WorkspaceEntry.id == note_id, WorkspaceEntry.deleted_at.is_(None))
        .first()
    )
    if not note:
        raise NotebookNoteNotFound(f"Notebook note {note_id} not found")
    return note


def list_notes(
    db: Session,
    *,
    case_id: UUID,
    current_user: User,
    mine: bool = False,
    query_text: str | None = None,
    linked_type: str | None = None,
    linked_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    query = _base_query(db, case_id).filter(WorkspaceEntry.deleted_at.is_(None))
    if mine:
        query = query.filter(WorkspaceEntry.author_user_id == current_user.id)
    if linked_type or linked_id:
        if linked_type not in NOTEBOOK_TARGET_TYPES or not linked_id:
            raise ValueError("Both linked_type and linked_id are required for link filtering")
        canonical_type = {
            "entity": "graph_entity",
            "document": "evidence",
        }.get(linked_type, linked_type)
        query = query.join(WorkspaceEntryLink).filter(
            WorkspaceEntryLink.target_type == canonical_type,
            WorkspaceEntryLink.target_id == linked_id,
        )
    search = _clean_text(query_text)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                WorkspaceEntry.title.ilike(pattern),
                WorkspaceEntry.body.ilike(pattern),
                WorkspaceEntry.links.any(WorkspaceEntryLink.target_label.ilike(pattern)),
            )
        )
    total = query.count()
    notes = (
        query.order_by(
            desc(WorkspaceEntry.updated_at),
            desc(WorkspaceEntry.created_at),
            desc(WorkspaceEntry.id),
        )
        .offset(max(offset, 0))
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return {"notes": [note_to_dict(note) for note in notes], "total": total}


def create_note(
    db: Session,
    *,
    case_id: UUID,
    current_user: User,
    title: str | None,
    body: str,
    tags: list[str] | None = None,
    links: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    note_id = uuid4()
    created = create_entry(
        db,
        case_id=case_id,
        current_user=current_user,
        entry_id=note_id,
        entry_type="note",
        title=_clean_title(title),
        body=_clean_body(body),
        tags=_clean_tags(tags),
        links=_to_canonical_links(links),
        legacy_source="notebook_note",
        legacy_id=str(note_id),
    )
    system_log_service.log(
        log_type=LogType.CASE_OPERATION,
        origin=LogOrigin.FRONTEND,
        action="Create Notebook Note",
        details={"case_id": str(case_id), "note_id": str(note_id), "links": len(created["links"])},
        user=current_user.email,
        success=True,
        db=db,
    )
    db.commit()
    return note_to_dict(_get_note(db, case_id, note_id))


def update_note(
    db: Session,
    *,
    case_id: UUID,
    note_id: UUID,
    current_user: User,
    title: str | None = None,
    body: str | None = None,
    tags: list[str] | None = None,
    links: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    note = _get_note(db, case_id, note_id)
    before = note_to_dict(note)
    changes: dict[str, Any] = {}
    if title is not None:
        changes["title"] = _clean_title(title)
    if body is not None:
        changes["body"] = _clean_body(body)
    if tags is not None:
        changes["tags"] = _clean_tags(tags)
    if links is not None:
        changes["links"] = _to_canonical_links(links)
    updated = update_entry(
        db,
        case_id=case_id,
        entry_id=note_id,
        current_user=current_user,
        expected_version=note.version,
        **changes,
    )
    system_log_service.log(
        log_type=LogType.CASE_OPERATION,
        origin=LogOrigin.FRONTEND,
        action="Update Notebook Note",
        details={
            "case_id": str(case_id),
            "note_id": str(note_id),
            "before": {"title": before["title"], "body": before["body"], "links": before["links"]},
            "after": {"title": updated["title"], "body": updated["body"], "links": updated["links"]},
        },
        user=current_user.email,
        success=True,
        db=db,
    )
    db.commit()
    return note_to_dict(_get_note(db, case_id, note_id))


def delete_note(
    db: Session,
    *,
    case_id: UUID,
    note_id: UUID,
    current_user: User,
) -> None:
    note = _get_note(db, case_id, note_id)
    soft_delete_entry(
        db,
        case_id=case_id,
        entry_id=note_id,
        current_user=current_user,
        expected_version=note.version,
    )
    system_log_service.log(
        log_type=LogType.CASE_OPERATION,
        origin=LogOrigin.FRONTEND,
        action="Delete Notebook Note",
        details={"case_id": str(case_id), "note_id": str(note_id)},
        user=current_user.email,
        success=True,
        db=db,
    )
    db.commit()
