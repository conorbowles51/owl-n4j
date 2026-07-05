"""Service layer for the case notebook."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import desc, or_
from sqlalchemy.orm import Session, selectinload

from postgres.models.notebook import NotebookNote, NotebookNoteLink
from postgres.models.user import User
from services.system_log_service import LogOrigin, LogType, system_log_service


NOTEBOOK_TARGET_TYPES = {
    "entity",
    "evidence",
    "document",
    "timeline_event",
    "agent_artifact",
}


class NotebookNoteNotFound(Exception):
    """Raised when a notebook note does not exist in the requested case."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
                "metadata": metadata if isinstance(metadata, dict) else {},
            }
        )

    return sanitized


def _link_to_dict(link: NotebookNoteLink) -> dict[str, Any]:
    return {
        "id": str(link.id),
        "note_id": str(link.note_id),
        "case_id": str(link.case_id),
        "target_type": link.target_type,
        "target_id": link.target_id,
        "target_label": link.target_label,
        "metadata": dict(link.link_metadata or {}),
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


def note_to_dict(note: NotebookNote) -> dict[str, Any]:
    return {
        "id": str(note.id),
        "case_id": str(note.case_id),
        "title": note.title,
        "body": note.body,
        "tags": list(note.tags or []),
        "visibility": note.visibility,
        "author_user_id": str(note.author_user_id) if note.author_user_id else None,
        "author_email": note.author_email,
        "author_name": note.author_name,
        "created_at": note.created_at.isoformat() if note.created_at else None,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
        "links": [_link_to_dict(link) for link in note.links],
    }


def _get_note(db: Session, case_id: UUID, note_id: UUID) -> NotebookNote:
    note = (
        db.query(NotebookNote)
        .options(selectinload(NotebookNote.links))
        .filter(
            NotebookNote.id == note_id,
            NotebookNote.case_id == case_id,
            NotebookNote.deleted_at.is_(None),
        )
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
    query = (
        db.query(NotebookNote)
        .options(selectinload(NotebookNote.links))
        .filter(NotebookNote.case_id == case_id, NotebookNote.deleted_at.is_(None))
    )

    if mine:
        query = query.filter(NotebookNote.author_user_id == current_user.id)

    if linked_type or linked_id:
        if linked_type not in NOTEBOOK_TARGET_TYPES or not linked_id:
            raise ValueError("Both linked_type and linked_id are required for link filtering")
        query = query.join(NotebookNoteLink).filter(
            NotebookNoteLink.target_type == linked_type,
            NotebookNoteLink.target_id == linked_id,
        )

    search = _clean_text(query_text)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                NotebookNote.title.ilike(pattern),
                NotebookNote.body.ilike(pattern),
                NotebookNote.links.any(NotebookNoteLink.target_label.ilike(pattern)),
            )
        )

    total = query.count()
    notes = (
        query.order_by(desc(NotebookNote.updated_at), desc(NotebookNote.created_at), desc(NotebookNote.id))
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
    note = NotebookNote(
        case_id=case_id,
        author_user_id=current_user.id,
        author_email=current_user.email,
        author_name=current_user.name,
        title=_clean_title(title),
        body=_clean_body(body),
        tags=_clean_tags(tags),
        visibility="case",
    )
    db.add(note)
    db.flush()

    sanitized_links = _sanitize_links(links)
    for link in sanitized_links:
        db.add(
            NotebookNoteLink(
                note_id=note.id,
                case_id=case_id,
                target_type=link["target_type"],
                target_id=link["target_id"],
                target_label=link["target_label"],
                link_metadata=link["metadata"],
            )
        )

    db.flush()
    system_log_service.log(
        log_type=LogType.CASE_OPERATION,
        origin=LogOrigin.FRONTEND,
        action="Create Notebook Note",
        details={"case_id": str(case_id), "note_id": str(note.id), "links": len(sanitized_links)},
        user=current_user.email,
        success=True,
        db=db,
    )
    db.commit()
    return note_to_dict(_get_note(db, case_id, note.id))


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

    if title is not None:
        note.title = _clean_title(title)
    if body is not None:
        note.body = _clean_body(body)
    if tags is not None:
        note.tags = _clean_tags(tags)

    if links is not None:
        note.links.clear()
        db.flush()
        for link in _sanitize_links(links):
            note.links.append(
                NotebookNoteLink(
                    note_id=note.id,
                    case_id=case_id,
                    target_type=link["target_type"],
                    target_id=link["target_id"],
                    target_label=link["target_label"],
                    link_metadata=link["metadata"],
                )
            )

    db.flush()
    after = note_to_dict(note)
    system_log_service.log(
        log_type=LogType.CASE_OPERATION,
        origin=LogOrigin.FRONTEND,
        action="Update Notebook Note",
        details={
            "case_id": str(case_id),
            "note_id": str(note.id),
            "before": {
                "title": before["title"],
                "body": before["body"],
                "links": before["links"],
            },
            "after": {
                "title": after["title"],
                "body": after["body"],
                "links": after["links"],
            },
        },
        user=current_user.email,
        success=True,
        db=db,
    )
    db.commit()
    return note_to_dict(_get_note(db, case_id, note.id))


def delete_note(
    db: Session,
    *,
    case_id: UUID,
    note_id: UUID,
    current_user: User,
) -> None:
    note = _get_note(db, case_id, note_id)
    note.deleted_at = _now()
    db.flush()
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
