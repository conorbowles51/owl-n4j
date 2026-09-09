"""Canonical service for investigator-authored Notes, Findings, and Theories."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import String, asc, cast, desc, or_, select
from sqlalchemy.orm import Session, selectinload

from postgres.models.case_deadline import CaseDeadline
from postgres.models.case_profile import CaseProfile
from postgres.models.agent import AgentArtifactRecord, AgentThread
from postgres.models.evidence import EvidenceFile
from postgres.models.timeline_view import TimelineViewEvent
from postgres.models.user import User
from postgres.models.work import CaseTask
from postgres.models.workspace_entry import (
    ENTRY_LINK_RELATIONSHIPS,
    ENTRY_LINK_TARGET_TYPES,
    FINDING_SIGNIFICANCE,
    FINDING_STATES,
    THEORY_STATES,
    WORKSPACE_ENTRY_TYPES,
    WorkspaceEntry,
    WorkspaceEntryEvent,
    WorkspaceEntryLink,
    WorkspaceEntryRevision,
    WorkspaceLegacyMapping,
)


_UNSET = object()
_RAW_HTML = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")


class WorkspaceEntryNotFound(Exception):
    pass


class WorkspaceEntryConflict(Exception):
    pass


class WorkspaceEntryValidationError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_optional_text(value: Any, *, max_length: int | None = None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if max_length is not None and len(text) > max_length:
        raise WorkspaceEntryValidationError(
            f"Value must be {max_length} characters or fewer"
        )
    return text


def _clean_body(value: Any) -> str:
    body = _clean_optional_text(value)
    if not body:
        raise WorkspaceEntryValidationError("Entry body is required")
    if _RAW_HTML.search(body):
        raise WorkspaceEntryValidationError(
            "Raw HTML is not supported; use Markdown-compatible formatting"
        )
    return body


def _clean_tags(values: list[str] | None) -> list[str]:
    tags: list[str] = []
    for value in values or []:
        tag = _clean_optional_text(value, max_length=64)
        if tag and tag not in tags:
            tags.append(tag)
    return tags[:20]


def _entry_defaults(
    entry_type: str,
    *,
    lifecycle_state: str | None,
    significance: str | None,
    confidence: int | None,
    allow_migration_review: bool = False,
) -> tuple[str | None, str | None, int | None]:
    if entry_type not in WORKSPACE_ENTRY_TYPES:
        raise WorkspaceEntryValidationError(f"Unsupported entry type: {entry_type}")

    if entry_type == "note":
        if lifecycle_state is not None or significance is not None or confidence is not None:
            raise WorkspaceEntryValidationError(
                "Notes do not have lifecycle, significance, or confidence fields"
            )
        return None, None, None

    if entry_type == "finding":
        state = lifecycle_state or "draft"
        normalized_significance = significance.lower() if significance else None
        if state not in FINDING_STATES:
            raise WorkspaceEntryValidationError(f"Invalid Finding state: {state}")
        if normalized_significance not in FINDING_SIGNIFICANCE and not allow_migration_review:
            raise WorkspaceEntryValidationError(
                "Finding significance must be High, Medium, or Low"
            )
        if confidence is not None:
            raise WorkspaceEntryValidationError("Findings do not have confidence")
        return state, normalized_significance, None

    state = lifecycle_state or "proposed"
    if state not in THEORY_STATES:
        raise WorkspaceEntryValidationError(f"Invalid Theory state: {state}")
    if significance is not None:
        raise WorkspaceEntryValidationError("Theories do not have significance")
    if confidence is not None:
        if isinstance(confidence, bool) or not isinstance(confidence, int):
            raise WorkspaceEntryValidationError("Theory confidence must be a whole number")
        if confidence < 0 or confidence > 100 or confidence % 5 != 0:
            raise WorkspaceEntryValidationError(
                "Theory confidence must be between 0 and 100 in increments of five"
            )
    return state, None, confidence


def _validate_title(entry_type: str, value: Any) -> str | None:
    title = _clean_optional_text(value, max_length=255)
    if entry_type != "note" and not title:
        raise WorkspaceEntryValidationError(
            f"{entry_type.capitalize()} title is required"
        )
    return title


def _actor_fields(user: User) -> dict[str, Any]:
    return {
        "user_id": user.id,
        "email": user.email,
        "name": user.name,
    }


def _state_snapshot(entry: WorkspaceEntry) -> dict[str, Any]:
    return {
        "version": entry.version,
        "entry_type": entry.entry_type,
        "title": entry.title,
        "body": entry.body,
        "tags": list(entry.tags or []),
        "lifecycle_state": entry.lifecycle_state,
        "significance": entry.significance,
        "confidence": entry.confidence,
        "confidence_rationale": entry.confidence_rationale,
        "review_state": entry.review_state,
        "deleted_at": entry.deleted_at.isoformat() if entry.deleted_at else None,
    }


def _record_revision(
    db: Session,
    entry: WorkspaceEntry,
    user: User | None,
    *,
    created_at: datetime | None = None,
) -> None:
    actor = _actor_fields(user) if user else {"user_id": None, "email": None, "name": None}
    db.add(
        WorkspaceEntryRevision(
            entry_id=entry.id,
            case_id=entry.case_id,
            revision_number=entry.version,
            entry_type=entry.entry_type,
            title=entry.title,
            body=entry.body,
            tags=list(entry.tags or []),
            lifecycle_state=entry.lifecycle_state,
            significance=entry.significance,
            confidence=entry.confidence,
            confidence_rationale=entry.confidence_rationale,
            review_state=entry.review_state,
            editor_user_id=actor["user_id"],
            editor_email=actor["email"],
            editor_name=actor["name"],
            created_at=created_at or _now(),
        )
    )


def _record_event(
    db: Session,
    entry: WorkspaceEntry,
    event_type: str,
    user: User | None,
    *,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    rationale: str | None = None,
    created_at: datetime | None = None,
) -> None:
    actor = _actor_fields(user) if user else {"user_id": None, "email": None, "name": None}
    db.add(
        WorkspaceEntryEvent(
            entry_id=entry.id,
            case_id=entry.case_id,
            event_type=event_type,
            before_state=before_state or {},
            after_state=after_state or {},
            rationale=_clean_optional_text(rationale),
            actor_user_id=actor["user_id"],
            actor_email=actor["email"],
            actor_name=actor["name"],
            created_at=created_at or _now(),
        )
    )


def _validate_link_target(
    db: Session,
    *,
    case_id: UUID,
    target_type: str,
    target_id: str,
) -> None:
    if target_type == "evidence":
        try:
            record = db.get(EvidenceFile, UUID(target_id))
        except (TypeError, ValueError):
            record = None
        if not record or record.case_id != case_id:
            raise WorkspaceEntryValidationError(
                f"Evidence file {target_id} was not found in this case"
            )
    elif target_type == "dossier":
        try:
            record = db.get(CaseProfile, UUID(target_id))
        except (TypeError, ValueError):
            record = None
        if not record or record.case_id != case_id or record.archived_at is not None:
            raise WorkspaceEntryValidationError(
                f"Dossier {target_id} was not found in this case"
            )
    elif target_type == "entry":
        try:
            record = db.get(WorkspaceEntry, UUID(target_id))
        except (TypeError, ValueError):
            record = None
        if not record or record.case_id != case_id:
            raise WorkspaceEntryValidationError(
                f"Workspace entry {target_id} was not found in this case"
            )
    elif target_type == "deadline":
        try:
            record = db.get(CaseDeadline, UUID(target_id))
        except (TypeError, ValueError):
            record = None
        if not record or record.case_id != case_id:
            raise WorkspaceEntryValidationError(
                f"Case deadline {target_id} was not found in this case"
            )
    elif target_type == "task":
        try:
            task_id = UUID(target_id)
        except (TypeError, ValueError):
            task_id = None
        record = db.scalar(
            select(CaseTask).where(
                CaseTask.id == task_id,
                CaseTask.case_id == case_id,
                CaseTask.deleted_at.is_(None),
            )
        )
        if record is None:
            raise WorkspaceEntryValidationError(
                f"Case task {target_id} was not found in this case"
            )
    elif target_type == "timeline_event":
        record = db.query(TimelineViewEvent).filter(
            TimelineViewEvent.case_id == case_id,
            TimelineViewEvent.event_key == target_id,
        ).first()
        if not record:
            raise WorkspaceEntryValidationError(
                f"Timeline event {target_id} was not found in this case"
            )
    elif target_type == "agent_artifact":
        try:
            artifact_id = UUID(target_id)
        except (TypeError, ValueError):
            artifact_id = None
        record = (
            db.query(AgentArtifactRecord)
            .join(AgentThread, AgentThread.id == AgentArtifactRecord.thread_id)
            .filter(
                AgentArtifactRecord.id == artifact_id,
                AgentThread.case_id == case_id,
            )
            .first()
            if artifact_id
            else None
        )
        if not record:
            raise WorkspaceEntryValidationError(
                f"Agent artifact {target_id} was not found in this case"
            )


def search_attachment_options(
    db: Session,
    *,
    case_id: UUID,
    target_type: str,
    query_text: str | None = None,
    target_ids: list[str] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return bounded, case-scoped link targets with human-readable labels."""

    limit = max(1, min(limit, 50))
    search = _clean_optional_text(query_text)
    pattern = f"%{search}%" if search else None
    bounded_ids = [str(value).strip() for value in (target_ids or []) if str(value).strip()][
        :50
    ]
    if target_type == "evidence":
        query = db.query(EvidenceFile).filter(EvidenceFile.case_id == case_id)
        if bounded_ids:
            valid_ids: list[UUID] = []
            for value in bounded_ids:
                try:
                    valid_ids.append(UUID(value))
                except ValueError:
                    continue
            if not valid_ids:
                return []
            query = query.filter(EvidenceFile.id.in_(valid_ids))
        if pattern:
            query = query.filter(
                or_(
                    EvidenceFile.original_filename.ilike(pattern),
                    EvidenceFile.summary.ilike(pattern),
                )
            )
        rows = query.order_by(desc(EvidenceFile.updated_at)).limit(limit).all()
        return [
            {
                "target_type": "evidence",
                "target_id": str(row.id),
                "label": row.original_filename,
                "description": row.summary,
                "metadata": {"status": row.status, "source_type": row.source_type},
            }
            for row in rows
        ]
    if target_type == "entry":
        query = db.query(WorkspaceEntry).filter(
            WorkspaceEntry.case_id == case_id,
            WorkspaceEntry.deleted_at.is_(None),
        )
        if bounded_ids:
            valid_ids = []
            for value in bounded_ids:
                try:
                    valid_ids.append(UUID(value))
                except ValueError:
                    continue
            if not valid_ids:
                return []
            query = query.filter(WorkspaceEntry.id.in_(valid_ids))
        if pattern:
            query = query.filter(
                or_(WorkspaceEntry.title.ilike(pattern), WorkspaceEntry.body.ilike(pattern))
            )
        rows = query.order_by(desc(WorkspaceEntry.updated_at)).limit(limit).all()
        return [
            {
                "target_type": "entry",
                "target_id": str(row.id),
                "label": row.title or row.body.splitlines()[0][:100],
                "description": row.body[:240],
                "metadata": {"entry_type": row.entry_type},
            }
            for row in rows
        ]
    if target_type == "deadline":
        query = db.query(CaseDeadline).filter(CaseDeadline.case_id == case_id)
        if pattern:
            query = query.filter(CaseDeadline.name.ilike(pattern))
        rows = query.order_by(CaseDeadline.due_date.asc()).limit(limit).all()
        return [
            {
                "target_type": "deadline",
                "target_id": str(row.id),
                "label": row.name,
                "description": row.due_date.isoformat(),
                "metadata": {"due_date": row.due_date.isoformat()},
            }
            for row in rows
        ]
    if target_type == "task":
        query = db.query(CaseTask).filter(
            CaseTask.case_id == case_id,
            CaseTask.deleted_at.is_(None),
        )
        if pattern:
            query = query.filter(
                or_(CaseTask.title.ilike(pattern), CaseTask.description.ilike(pattern))
            )
        rows = query.order_by(desc(CaseTask.updated_at)).limit(limit).all()
        return [
            {
                "target_type": "task",
                "target_id": str(row.id),
                "label": row.title,
                "description": row.description,
                "metadata": {"status": row.status},
            }
            for row in rows
        ]
    if target_type == "timeline_event":
        query = db.query(TimelineViewEvent).filter(TimelineViewEvent.case_id == case_id)
        if pattern:
            query = query.filter(cast(TimelineViewEvent.event_snapshot, String).ilike(pattern))
        rows = query.order_by(desc(TimelineViewEvent.updated_at)).limit(limit).all()
        return [
            {
                "target_type": "timeline_event",
                "target_id": row.event_key,
                "label": str((row.event_snapshot or {}).get("name") or row.event_key),
                "description": (row.event_snapshot or {}).get("summary"),
                "metadata": {
                    "date": row.sort_date,
                    "time": row.sort_time,
                },
            }
            for row in rows
        ]
    if target_type == "agent_artifact":
        query = (
            db.query(AgentArtifactRecord)
            .join(AgentThread, AgentThread.id == AgentArtifactRecord.thread_id)
            .filter(AgentThread.case_id == case_id)
        )
        if pattern:
            query = query.filter(AgentArtifactRecord.title.ilike(pattern))
        rows = query.order_by(desc(AgentArtifactRecord.created_at)).limit(limit).all()
        return [
            {
                "target_type": "agent_artifact",
                "target_id": str(row.id),
                "label": row.title,
                "description": row.type,
                "metadata": {"artifact_type": row.type},
            }
            for row in rows
        ]
    if target_type == "dossier":
        query = db.query(CaseProfile).filter(
            CaseProfile.case_id == case_id,
            CaseProfile.archived_at.is_(None),
        )
        if bounded_ids:
            valid_ids = []
            for value in bounded_ids:
                try:
                    valid_ids.append(UUID(value))
                except ValueError:
                    continue
            if not valid_ids:
                return []
            query = query.filter(CaseProfile.id.in_(valid_ids))
        if pattern:
            query = query.filter(or_(CaseProfile.display_name.ilike(pattern), CaseProfile.summary.ilike(pattern)))
        rows = query.order_by(desc(CaseProfile.updated_at)).limit(limit).all()
        return [
            {
                "target_type": "dossier",
                "target_id": str(row.id),
                "label": row.display_name,
                "description": row.summary,
                "metadata": {"dossier_type": row.profile_type},
            }
            for row in rows
        ]
    if target_type == "graph_entity":
        return []
    raise WorkspaceEntryValidationError(f"Unsupported attachment search: {target_type}")


def _sanitize_link(
    db: Session,
    *,
    case_id: UUID,
    link: dict[str, Any],
    validate_target: bool = True,
) -> dict[str, Any]:
    target_type = _clean_optional_text(link.get("target_type"), max_length=32)
    target_id = _clean_optional_text(link.get("target_id"), max_length=512)
    if target_type == "entity":
        target_type = "graph_entity"
    elif target_type == "document":
        target_type = "evidence"
    if target_type not in ENTRY_LINK_TARGET_TYPES:
        raise WorkspaceEntryValidationError(f"Unsupported link type: {target_type}")
    if not target_id:
        raise WorkspaceEntryValidationError("Link target_id is required")

    relationship = str(link.get("relationship") or "unclassified").strip().lower()
    if relationship not in ENTRY_LINK_RELATIONSHIPS:
        raise WorkspaceEntryValidationError(
            f"Unsupported link relationship: {relationship}"
        )
    source_anchor = link.get("source_anchor")
    metadata = link.get("metadata")
    if source_anchor is not None and not isinstance(source_anchor, dict):
        raise WorkspaceEntryValidationError("source_anchor must be an object")
    if metadata is not None and not isinstance(metadata, dict):
        raise WorkspaceEntryValidationError("metadata must be an object")
    if validate_target:
        _validate_link_target(
            db, case_id=case_id, target_type=target_type, target_id=target_id
        )
    return {
        "target_type": target_type,
        "target_id": target_id,
        "target_label": _clean_optional_text(link.get("target_label"), max_length=512),
        "relationship": relationship,
        "source_anchor": source_anchor or {},
        "metadata": metadata or {},
    }


def _append_link(
    db: Session,
    entry: WorkspaceEntry,
    user: User | None,
    link: dict[str, Any],
    *,
    validate_target: bool = True,
) -> WorkspaceEntryLink:
    data = _sanitize_link(
        db, case_id=entry.case_id, link=link, validate_target=validate_target
    )
    record = WorkspaceEntryLink(
        entry_id=entry.id,
        case_id=entry.case_id,
        target_type=data["target_type"],
        target_id=data["target_id"],
        target_label=data["target_label"],
        relationship_type=data["relationship"],
        source_anchor=data["source_anchor"],
        link_metadata=data["metadata"],
        created_by_user_id=user.id if user else None,
    )
    db.add(record)
    return record


def _replace_links(
    db: Session,
    entry: WorkspaceEntry,
    user: User | None,
    links: list[dict[str, Any]],
) -> None:
    sanitized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for link in links:
        data = _sanitize_link(db, case_id=entry.case_id, link=link)
        key = (data["target_type"], data["target_id"])
        if key in seen:
            continue
        seen.add(key)
        sanitized.append(data)
    entry.links.clear()
    db.flush()
    for data in sanitized:
        _append_link(db, entry, user, data)


def _load_entry(
    db: Session,
    *,
    case_id: UUID,
    entry_id: UUID,
    include_deleted: bool = False,
) -> WorkspaceEntry:
    query = (
        db.query(WorkspaceEntry)
        .options(
            selectinload(WorkspaceEntry.links),
            selectinload(WorkspaceEntry.revisions),
            selectinload(WorkspaceEntry.events),
        )
        .filter(WorkspaceEntry.id == entry_id, WorkspaceEntry.case_id == case_id)
    )
    if not include_deleted:
        query = query.filter(WorkspaceEntry.deleted_at.is_(None))
    entry = query.first()
    if not entry:
        raise WorkspaceEntryNotFound(f"Workspace entry {entry_id} not found")
    return entry


def _link_to_dict(link: WorkspaceEntryLink) -> dict[str, Any]:
    return {
        "id": str(link.id),
        "entry_id": str(link.entry_id),
        "case_id": str(link.case_id),
        "target_type": link.target_type,
        "target_id": link.target_id,
        "target_label": link.target_label,
        "relationship": link.relationship_type,
        "source_anchor": dict(link.source_anchor or {}),
        "metadata": dict(link.link_metadata or {}),
        "created_by_user_id": str(link.created_by_user_id)
        if link.created_by_user_id
        else None,
        "created_at": link.created_at.isoformat() if link.created_at else None,
        "updated_at": link.updated_at.isoformat() if link.updated_at else None,
    }


def _revision_to_dict(revision: WorkspaceEntryRevision) -> dict[str, Any]:
    return {
        "id": str(revision.id),
        "entry_id": str(revision.entry_id),
        "revision_number": revision.revision_number,
        "entry_type": revision.entry_type,
        "title": revision.title,
        "body": revision.body,
        "tags": list(revision.tags or []),
        "lifecycle_state": revision.lifecycle_state,
        "significance": revision.significance,
        "confidence": revision.confidence,
        "confidence_rationale": revision.confidence_rationale,
        "review_state": revision.review_state,
        "editor_user_id": str(revision.editor_user_id)
        if revision.editor_user_id
        else None,
        "editor_email": revision.editor_email,
        "editor_name": revision.editor_name,
        "created_at": revision.created_at.isoformat(),
    }


def _event_to_dict(event: WorkspaceEntryEvent) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "entry_id": str(event.entry_id),
        "event_type": event.event_type,
        "before_state": dict(event.before_state or {}),
        "after_state": dict(event.after_state or {}),
        "rationale": event.rationale,
        "actor_user_id": str(event.actor_user_id) if event.actor_user_id else None,
        "actor_email": event.actor_email,
        "actor_name": event.actor_name,
        "created_at": event.created_at.isoformat(),
    }


def entry_to_dict(
    entry: WorkspaceEntry,
    *,
    include_history: bool = False,
) -> dict[str, Any]:
    data = {
        "id": str(entry.id),
        "case_id": str(entry.case_id),
        "entry_type": entry.entry_type,
        "title": entry.title,
        "body": entry.body,
        "tags": list(entry.tags or []),
        "lifecycle_state": entry.lifecycle_state,
        "significance": entry.significance,
        "confidence": entry.confidence,
        "confidence_rationale": entry.confidence_rationale,
        "review_state": entry.review_state,
        "author_user_id": str(entry.author_user_id) if entry.author_user_id else None,
        "author_email": entry.author_email,
        "author_name": entry.author_name,
        "updated_by_user_id": str(entry.updated_by_user_id)
        if entry.updated_by_user_id
        else None,
        "updated_by_email": entry.updated_by_email,
        "updated_by_name": entry.updated_by_name,
        "version": entry.version,
        "source_theory_entry_id": str(entry.source_theory_entry_id)
        if entry.source_theory_entry_id
        else None,
        "legacy_source": entry.legacy_source,
        "legacy_id": entry.legacy_id,
        "migration_metadata": dict(entry.migration_metadata or {}),
        "needs_migration_review": entry.needs_migration_review,
        "deleted_at": entry.deleted_at.isoformat() if entry.deleted_at else None,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
        "links": [_link_to_dict(link) for link in entry.links],
    }
    if include_history:
        data["revisions"] = [_revision_to_dict(item) for item in entry.revisions]
        data["events"] = [_event_to_dict(item) for item in entry.events]
    return data


def create_entry(
    db: Session,
    *,
    case_id: UUID,
    current_user: User,
    entry_id: UUID | None = None,
    entry_type: str,
    body: str,
    title: str | None = None,
    tags: list[str] | None = None,
    lifecycle_state: str | None = None,
    significance: str | None = None,
    confidence: int | None = None,
    confidence_rationale: str | None = None,
    review_state: str = "accepted",
    links: list[dict[str, Any]] | None = None,
    legacy_source: str | None = None,
    legacy_id: str | None = None,
    compatibility_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_type = str(entry_type).strip().lower()
    normalized_title = _validate_title(normalized_type, title)
    state, normalized_significance, normalized_confidence = _entry_defaults(
        normalized_type,
        lifecycle_state=lifecycle_state.lower() if lifecycle_state else None,
        significance=significance,
        confidence=confidence,
    )
    if review_state not in {"accepted", "pending", "rejected"}:
        raise WorkspaceEntryValidationError("Invalid review state")
    actor = _actor_fields(current_user)
    entry = WorkspaceEntry(
        id=entry_id or None,
        case_id=case_id,
        entry_type=normalized_type,
        title=normalized_title,
        body=_clean_body(body),
        tags=_clean_tags(tags),
        lifecycle_state=state,
        significance=normalized_significance,
        confidence=normalized_confidence,
        confidence_rationale=_clean_optional_text(confidence_rationale),
        review_state=review_state,
        author_user_id=actor["user_id"],
        author_email=actor["email"],
        author_name=actor["name"],
        updated_by_user_id=actor["user_id"],
        updated_by_email=actor["email"],
        updated_by_name=actor["name"],
        legacy_source=_clean_optional_text(legacy_source, max_length=64),
        legacy_id=_clean_optional_text(legacy_id, max_length=255),
        migration_metadata=dict(compatibility_metadata or {}),
    )
    db.add(entry)
    db.flush()
    for link in links or []:
        _append_link(db, entry, current_user, link)
    _record_revision(db, entry, current_user)
    _record_event(
        db,
        entry,
        "created",
        current_user,
        after_state=_state_snapshot(entry),
    )
    if entry.legacy_source and entry.legacy_id:
        db.add(
            WorkspaceLegacyMapping(
                case_id=entry.case_id,
                source_type=entry.legacy_source,
                source_id=entry.legacy_id,
                target_type="entry",
                target_id=str(entry.id),
            )
        )
    db.commit()
    return entry_to_dict(
        _load_entry(db, case_id=case_id, entry_id=entry.id), include_history=True
    )


def list_entries(
    db: Session,
    *,
    case_id: UUID,
    entry_type: str | None = None,
    lifecycle_state: str | None = None,
    significance: str | None = None,
    confidence_min: int | None = None,
    confidence_max: int | None = None,
    author_user_id: UUID | None = None,
    query_text: str | None = None,
    updated_since: datetime | None = None,
    include_deleted: bool = False,
    sort_by: str = "updated_at",
    sort_direction: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    query = (
        db.query(WorkspaceEntry)
        .options(selectinload(WorkspaceEntry.links))
        .filter(WorkspaceEntry.case_id == case_id)
    )
    if not include_deleted:
        query = query.filter(WorkspaceEntry.deleted_at.is_(None))
    if entry_type:
        query = query.filter(WorkspaceEntry.entry_type == entry_type.lower())
    if lifecycle_state:
        query = query.filter(WorkspaceEntry.lifecycle_state == lifecycle_state.lower())
    if significance:
        query = query.filter(WorkspaceEntry.significance == significance.lower())
    if confidence_min is not None:
        query = query.filter(WorkspaceEntry.confidence >= confidence_min)
    if confidence_max is not None:
        query = query.filter(WorkspaceEntry.confidence <= confidence_max)
    if author_user_id:
        query = query.filter(WorkspaceEntry.author_user_id == author_user_id)
    if updated_since:
        query = query.filter(WorkspaceEntry.updated_at >= updated_since)
    search = _clean_optional_text(query_text)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(WorkspaceEntry.title.ilike(pattern), WorkspaceEntry.body.ilike(pattern))
        )
    total = query.count()
    sort_columns = {
        "updated_at": WorkspaceEntry.updated_at,
        "created_at": WorkspaceEntry.created_at,
        "title": WorkspaceEntry.title,
        "confidence": WorkspaceEntry.confidence,
        "significance": WorkspaceEntry.significance,
    }
    if sort_by not in sort_columns:
        raise WorkspaceEntryValidationError(f"Unsupported entry sort: {sort_by}")
    if sort_direction not in {"asc", "desc"}:
        raise WorkspaceEntryValidationError(
            f"Unsupported entry sort direction: {sort_direction}"
        )
    order = asc if sort_direction == "asc" else desc
    entries = (
        query.order_by(order(sort_columns[sort_by]), order(WorkspaceEntry.id))
        .offset(max(offset, 0))
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return {"entries": [entry_to_dict(entry) for entry in entries], "total": total}


def get_entry(
    db: Session,
    *,
    case_id: UUID,
    entry_id: UUID,
    include_deleted: bool = False,
) -> dict[str, Any]:
    return entry_to_dict(
        _load_entry(
            db, case_id=case_id, entry_id=entry_id, include_deleted=include_deleted
        ),
        include_history=True,
    )


def list_entry_authors(db: Session, *, case_id: UUID) -> list[dict[str, Any]]:
    """Return the bounded set of authors represented in a case's authored work."""

    rows = (
        db.query(
            WorkspaceEntry.author_user_id,
            WorkspaceEntry.author_name,
            WorkspaceEntry.author_email,
        )
        .filter(
            WorkspaceEntry.case_id == case_id,
            WorkspaceEntry.author_user_id.is_not(None),
        )
        .distinct()
        .order_by(WorkspaceEntry.author_name, WorkspaceEntry.author_email)
        .limit(200)
        .all()
    )
    return [
        {
            "user_id": str(user_id),
            "name": name,
            "email": email,
            "label": name or email or "Unknown investigator",
        }
        for user_id, name, email in rows
    ]


def update_entry(
    db: Session,
    *,
    case_id: UUID,
    entry_id: UUID,
    current_user: User,
    expected_version: int,
    title: Any = _UNSET,
    body: Any = _UNSET,
    tags: Any = _UNSET,
    links: Any = _UNSET,
) -> dict[str, Any]:
    entry = _load_entry(db, case_id=case_id, entry_id=entry_id)
    if entry.version != expected_version:
        raise WorkspaceEntryConflict(
            f"Entry changed from version {expected_version} to {entry.version}"
        )
    before = _state_snapshot(entry)
    if title is not _UNSET:
        entry.title = _validate_title(entry.entry_type, title)
    if body is not _UNSET:
        entry.body = _clean_body(body)
    if tags is not _UNSET:
        entry.tags = _clean_tags(tags)
    if links is not _UNSET:
        _replace_links(db, entry, current_user, links)

    actor = _actor_fields(current_user)
    entry.updated_by_user_id = actor["user_id"]
    entry.updated_by_email = actor["email"]
    entry.updated_by_name = actor["name"]
    entry.version += 1
    db.flush()
    _record_revision(db, entry, current_user)
    _record_event(
        db,
        entry,
        "updated",
        current_user,
        before_state=before,
        after_state=_state_snapshot(entry),
    )
    db.commit()
    return get_entry(db, case_id=case_id, entry_id=entry_id)


def change_lifecycle(
    db: Session,
    *,
    case_id: UUID,
    entry_id: UUID,
    current_user: User,
    expected_version: int,
    lifecycle_state: str,
    rationale: str | None = None,
) -> dict[str, Any]:
    entry = _load_entry(db, case_id=case_id, entry_id=entry_id)
    if entry.version != expected_version:
        raise WorkspaceEntryConflict(
            f"Entry changed from version {expected_version} to {entry.version}"
        )
    if entry.entry_type == "note":
        raise WorkspaceEntryValidationError("Notes do not have a lifecycle")
    allowed = FINDING_STATES if entry.entry_type == "finding" else THEORY_STATES
    normalized_state = lifecycle_state.strip().lower()
    if normalized_state not in allowed:
        raise WorkspaceEntryValidationError(
            f"Invalid {entry.entry_type.capitalize()} state: {normalized_state}"
        )
    if normalized_state == entry.lifecycle_state:
        raise WorkspaceEntryValidationError("Entry is already in that state")
    before = _state_snapshot(entry)
    entry.lifecycle_state = normalized_state
    actor = _actor_fields(current_user)
    entry.updated_by_user_id = actor["user_id"]
    entry.updated_by_email = actor["email"]
    entry.updated_by_name = actor["name"]
    entry.version += 1
    db.flush()
    _record_revision(db, entry, current_user)
    _record_event(
        db,
        entry,
        "lifecycle_changed",
        current_user,
        before_state=before,
        after_state=_state_snapshot(entry),
        rationale=rationale,
    )
    db.commit()
    return get_entry(db, case_id=case_id, entry_id=entry_id)


def change_confidence(
    db: Session,
    *,
    case_id: UUID,
    entry_id: UUID,
    current_user: User,
    expected_version: int,
    confidence: int | None,
    rationale: str | None = None,
) -> dict[str, Any]:
    entry = _load_entry(db, case_id=case_id, entry_id=entry_id)
    if entry.version != expected_version:
        raise WorkspaceEntryConflict(
            f"Entry changed from version {expected_version} to {entry.version}"
        )
    if entry.entry_type != "theory":
        raise WorkspaceEntryValidationError("Only Theories have confidence")
    if confidence is not None:
        _entry_defaults(
            "theory",
            lifecycle_state=entry.lifecycle_state,
            significance=None,
            confidence=confidence,
        )
    cleaned_rationale = _clean_optional_text(rationale)
    if entry.confidence is not None and confidence != entry.confidence and not cleaned_rationale:
        raise WorkspaceEntryValidationError(
            "A rationale is required when changing an existing confidence assessment"
        )
    if confidence == entry.confidence:
        raise WorkspaceEntryValidationError("Confidence has not changed")
    before = _state_snapshot(entry)
    entry.confidence = confidence
    entry.confidence_rationale = cleaned_rationale
    actor = _actor_fields(current_user)
    entry.updated_by_user_id = actor["user_id"]
    entry.updated_by_email = actor["email"]
    entry.updated_by_name = actor["name"]
    entry.version += 1
    db.flush()
    _record_revision(db, entry, current_user)
    _record_event(
        db,
        entry,
        "confidence_changed",
        current_user,
        before_state=before,
        after_state=_state_snapshot(entry),
        rationale=cleaned_rationale,
    )
    db.commit()
    return get_entry(db, case_id=case_id, entry_id=entry_id)


def change_significance(
    db: Session,
    *,
    case_id: UUID,
    entry_id: UUID,
    current_user: User,
    expected_version: int,
    significance: str,
) -> dict[str, Any]:
    """Change a Finding's required significance with revision history."""

    entry = _load_entry(db, case_id=case_id, entry_id=entry_id)
    if entry.version != expected_version:
        raise WorkspaceEntryConflict(
            f"Entry changed from version {expected_version} to {entry.version}"
        )
    if entry.entry_type != "finding":
        raise WorkspaceEntryValidationError("Only Findings have significance")
    normalized = str(significance).strip().lower()
    if normalized not in FINDING_SIGNIFICANCE:
        raise WorkspaceEntryValidationError(
            "Finding significance must be High, Medium, or Low"
        )
    if normalized == entry.significance:
        raise WorkspaceEntryValidationError("Significance has not changed")
    before = _state_snapshot(entry)
    entry.significance = normalized
    actor = _actor_fields(current_user)
    entry.updated_by_user_id = actor["user_id"]
    entry.updated_by_email = actor["email"]
    entry.updated_by_name = actor["name"]
    entry.version += 1
    db.flush()
    _record_revision(db, entry, current_user)
    _record_event(
        db,
        entry,
        "updated",
        current_user,
        before_state=before,
        after_state=_state_snapshot(entry),
        rationale="Significance changed",
    )
    db.commit()
    return get_entry(db, case_id=case_id, entry_id=entry_id)


def soft_delete_entry(
    db: Session,
    *,
    case_id: UUID,
    entry_id: UUID,
    current_user: User,
    expected_version: int,
) -> None:
    entry = _load_entry(db, case_id=case_id, entry_id=entry_id)
    if entry.version != expected_version:
        raise WorkspaceEntryConflict(
            f"Entry changed from version {expected_version} to {entry.version}"
        )
    before = _state_snapshot(entry)
    entry.deleted_at = _now()
    entry.deleted_by_user_id = current_user.id
    entry.updated_by_user_id = current_user.id
    entry.updated_by_email = current_user.email
    entry.updated_by_name = current_user.name
    entry.version += 1
    db.flush()
    _record_revision(db, entry, current_user)
    _record_event(
        db,
        entry,
        "deleted",
        current_user,
        before_state=before,
        after_state=_state_snapshot(entry),
    )
    db.commit()


def restore_entry(
    db: Session,
    *,
    case_id: UUID,
    entry_id: UUID,
    current_user: User,
    expected_version: int,
) -> dict[str, Any]:
    entry = _load_entry(
        db, case_id=case_id, entry_id=entry_id, include_deleted=True
    )
    if entry.deleted_at is None:
        raise WorkspaceEntryValidationError("Entry is not deleted")
    if entry.version != expected_version:
        raise WorkspaceEntryConflict(
            f"Entry changed from version {expected_version} to {entry.version}"
        )
    before = _state_snapshot(entry)
    entry.deleted_at = None
    entry.deleted_by_user_id = None
    entry.updated_by_user_id = current_user.id
    entry.updated_by_email = current_user.email
    entry.updated_by_name = current_user.name
    entry.version += 1
    db.flush()
    _record_revision(db, entry, current_user)
    _record_event(
        db,
        entry,
        "restored",
        current_user,
        before_state=before,
        after_state=_state_snapshot(entry),
    )
    db.commit()
    return get_entry(db, case_id=case_id, entry_id=entry_id)


def convert_theory_to_finding(
    db: Session,
    *,
    case_id: UUID,
    theory_id: UUID,
    current_user: User,
    expected_version: int,
    significance: str,
    title: str | None = None,
    body: str | None = None,
) -> dict[str, Any]:
    theory = _load_entry(db, case_id=case_id, entry_id=theory_id)
    if theory.entry_type != "theory":
        raise WorkspaceEntryValidationError("Only a Theory can be converted")
    if theory.version != expected_version:
        raise WorkspaceEntryConflict(
            f"Entry changed from version {expected_version} to {theory.version}"
        )
    if theory.lifecycle_state == "converted":
        raise WorkspaceEntryValidationError("Theory has already been converted")
    finding_title = _validate_title("finding", title if title is not None else theory.title)
    _, finding_significance, _ = _entry_defaults(
        "finding",
        lifecycle_state="draft",
        significance=significance,
        confidence=None,
    )
    actor = _actor_fields(current_user)
    finding = WorkspaceEntry(
        case_id=case_id,
        entry_type="finding",
        title=finding_title,
        body=_clean_body(body if body is not None else theory.body),
        tags=list(theory.tags or []),
        lifecycle_state="draft",
        significance=finding_significance,
        review_state="accepted",
        author_user_id=actor["user_id"],
        author_email=actor["email"],
        author_name=actor["name"],
        updated_by_user_id=actor["user_id"],
        updated_by_email=actor["email"],
        updated_by_name=actor["name"],
        source_theory_entry_id=theory.id,
    )
    db.add(finding)
    db.flush()
    for link in theory.links:
        _append_link(
            db,
            finding,
            current_user,
            {
                "target_type": link.target_type,
                "target_id": link.target_id,
                "target_label": link.target_label,
                "relationship": link.relationship_type,
                "source_anchor": dict(link.source_anchor or {}),
                "metadata": dict(link.link_metadata or {}),
            },
        )
    _record_revision(db, finding, current_user)
    _record_event(
        db,
        finding,
        "created",
        current_user,
        after_state=_state_snapshot(finding),
        rationale="Converted from Theory",
    )

    before = _state_snapshot(theory)
    theory.lifecycle_state = "converted"
    theory.updated_by_user_id = actor["user_id"]
    theory.updated_by_email = actor["email"]
    theory.updated_by_name = actor["name"]
    theory.version += 1
    db.flush()
    _record_revision(db, theory, current_user)
    _record_event(
        db,
        theory,
        "converted",
        current_user,
        before_state=before,
        after_state={**_state_snapshot(theory), "finding_entry_id": str(finding.id)},
    )
    db.commit()
    return {
        "theory": get_entry(db, case_id=case_id, entry_id=theory.id),
        "finding": get_entry(db, case_id=case_id, entry_id=finding.id),
    }


def add_entry_link(
    db: Session,
    *,
    case_id: UUID,
    entry_id: UUID,
    current_user: User,
    expected_version: int,
    link: dict[str, Any],
) -> dict[str, Any]:
    entry = _load_entry(db, case_id=case_id, entry_id=entry_id)
    if entry.version != expected_version:
        raise WorkspaceEntryConflict(
            f"Entry changed from version {expected_version} to {entry.version}"
        )
    sanitized = _sanitize_link(db, case_id=case_id, link=link)
    if any(
        item.target_type == sanitized["target_type"]
        and item.target_id == sanitized["target_id"]
        for item in entry.links
    ):
        raise WorkspaceEntryConflict("That item is already linked to this entry")
    record = _append_link(db, entry, current_user, sanitized)
    entry.version += 1
    entry.updated_by_user_id = current_user.id
    entry.updated_by_email = current_user.email
    entry.updated_by_name = current_user.name
    db.flush()
    _record_revision(db, entry, current_user)
    _record_event(
        db,
        entry,
        "link_added",
        current_user,
        after_state=_link_to_dict(record),
    )
    db.commit()
    return get_entry(db, case_id=case_id, entry_id=entry_id)


def add_entry_links(
    db: Session,
    *,
    case_id: UUID,
    entry_id: UUID,
    current_user: User,
    expected_version: int,
    links: list[dict[str, Any]],
    ignore_existing: bool = False,
    commit: bool = True,
) -> dict[str, Any]:
    """Atomically add a reviewed set of links through the canonical service."""

    entry = _load_entry(db, case_id=case_id, entry_id=entry_id)
    if entry.version != expected_version:
        raise WorkspaceEntryConflict(
            f"Entry changed from version {expected_version} to {entry.version}"
        )
    existing = {(item.target_type, item.target_id) for item in entry.links}
    prepared: list[dict[str, Any]] = []
    seen = set(existing)
    for raw in links:
        sanitized = _sanitize_link(db, case_id=case_id, link=raw)
        identity = (sanitized["target_type"], sanitized["target_id"])
        if identity in seen:
            if ignore_existing:
                continue
            raise WorkspaceEntryConflict("That item is already linked to this entry")
        seen.add(identity)
        prepared.append(sanitized)
    added = [_append_link(db, entry, current_user, item) for item in prepared]
    if added:
        entry.version += 1
        entry.updated_by_user_id = current_user.id
        entry.updated_by_email = current_user.email
        entry.updated_by_name = current_user.name
        db.flush()
        _record_revision(db, entry, current_user)
        for record in added:
            _record_event(
                db,
                entry,
                "link_added",
                current_user,
                after_state=_link_to_dict(record),
                rationale="Accepted Workspace AI proposal",
            )
    if commit:
        db.commit()
    else:
        db.flush()
    return {
        "entry_id": str(entry.id),
        "version": entry.version,
        "added_link_ids": [str(item.id) for item in added],
    }


def update_entry_link(
    db: Session,
    *,
    case_id: UUID,
    entry_id: UUID,
    link_id: UUID,
    current_user: User,
    expected_version: int,
    relationship: str,
    source_anchor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry = _load_entry(db, case_id=case_id, entry_id=entry_id)
    if entry.version != expected_version:
        raise WorkspaceEntryConflict(
            f"Entry changed from version {expected_version} to {entry.version}"
        )
    link = next((item for item in entry.links if item.id == link_id), None)
    if not link:
        raise WorkspaceEntryNotFound(f"Workspace entry link {link_id} not found")
    normalized_relationship = relationship.strip().lower()
    if normalized_relationship not in ENTRY_LINK_RELATIONSHIPS:
        raise WorkspaceEntryValidationError(
            f"Unsupported link relationship: {normalized_relationship}"
        )
    if source_anchor is not None and not isinstance(source_anchor, dict):
        raise WorkspaceEntryValidationError("source_anchor must be an object")
    before = _link_to_dict(link)
    link.relationship_type = normalized_relationship
    if source_anchor is not None:
        link.source_anchor = source_anchor
    entry.version += 1
    entry.updated_by_user_id = current_user.id
    entry.updated_by_email = current_user.email
    entry.updated_by_name = current_user.name
    db.flush()
    _record_revision(db, entry, current_user)
    _record_event(
        db,
        entry,
        "link_updated",
        current_user,
        before_state=before,
        after_state=_link_to_dict(link),
    )
    db.commit()
    return get_entry(db, case_id=case_id, entry_id=entry_id)


def remove_entry_link(
    db: Session,
    *,
    case_id: UUID,
    entry_id: UUID,
    link_id: UUID,
    current_user: User,
    expected_version: int,
) -> dict[str, Any]:
    entry = _load_entry(db, case_id=case_id, entry_id=entry_id)
    if entry.version != expected_version:
        raise WorkspaceEntryConflict(
            f"Entry changed from version {expected_version} to {entry.version}"
        )
    link = next((item for item in entry.links if item.id == link_id), None)
    if not link:
        raise WorkspaceEntryNotFound(f"Workspace entry link {link_id} not found")
    before = _link_to_dict(link)
    db.delete(link)
    entry.version += 1
    entry.updated_by_user_id = current_user.id
    entry.updated_by_email = current_user.email
    entry.updated_by_name = current_user.name
    db.flush()
    _record_revision(db, entry, current_user)
    _record_event(
        db,
        entry,
        "link_removed",
        current_user,
        before_state=before,
    )
    db.commit()
    return get_entry(db, case_id=case_id, entry_id=entry_id)
