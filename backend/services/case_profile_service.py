from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from postgres.models.case_profile import (
    CASE_PROFILE_ATTRIBUTE_KINDS,
    CASE_PROFILE_TYPES,
    CaseProfile,
    CaseProfileAttribute,
    CaseProfileEvidenceLink,
    CaseProfileFindingLink,
    CaseProfileGraphNodeLink,
    CaseProfileNoteLink,
)
from postgres.models.evidence import EvidenceFile
from postgres.models.user import User
from postgres.models.workspace import WorkspaceFinding, WorkspaceNote
from services.case_service import check_case_access, get_case_if_allowed


class CaseProfileNotFound(Exception):
    pass


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _normalize_value(value: str) -> str:
    return " ".join(value.lower().split())


def _dedupe_strings(values: Iterable[Any] | None) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values or []:
        text = _clean_text(value)
        if not text:
            continue
        key = _normalize_value(text)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _coerce_profile_type(value: str) -> str:
    profile_type = _normalize_value(value).replace("organization", "organisation")
    if profile_type not in CASE_PROFILE_TYPES:
        raise ValueError(f"Invalid profile_type: {value}")
    return profile_type


def _coerce_attribute_kind(value: str) -> str:
    kind = _normalize_value(value).replace("organization", "organisation")
    if kind not in CASE_PROFILE_ATTRIBUTE_KINDS:
        raise ValueError(f"Invalid attribute kind: {value}")
    return kind


def _profile_options():
    return (
        selectinload(CaseProfile.attributes),
        selectinload(CaseProfile.graph_node_links),
        selectinload(CaseProfile.evidence_links).selectinload(CaseProfileEvidenceLink.evidence_file),
        selectinload(CaseProfile.note_links),
        selectinload(CaseProfile.finding_links),
    )


def _load_profile(db: Session, profile_id: uuid.UUID) -> CaseProfile:
    profile = db.execute(
        select(CaseProfile).options(*_profile_options()).where(CaseProfile.id == profile_id)
    ).scalar_one_or_none()
    if not profile:
        raise CaseProfileNotFound(f"Case profile {profile_id} not found")
    return profile


def _require_profile_read(db: Session, profile_id: uuid.UUID, user: User) -> CaseProfile:
    profile = _load_profile(db, profile_id)
    get_case_if_allowed(db=db, case_id=profile.case_id, user=user)
    return profile


def _require_profile_write(db: Session, profile_id: uuid.UUID, user: User) -> CaseProfile:
    profile = _load_profile(db, profile_id)
    check_case_access(db, profile.case_id, user, required_permission=("case", "edit"))
    return profile


def _serialize_dt(value: Any) -> str | None:
    return value.isoformat() if value else None


def serialize_attribute(attribute: CaseProfileAttribute) -> dict[str, Any]:
    return {
        "id": str(attribute.id),
        "kind": attribute.kind,
        "name": attribute.name,
        "value": attribute.value,
        "ordinal": attribute.ordinal,
    }


def serialize_graph_link(link: CaseProfileGraphNodeLink) -> dict[str, Any]:
    return {
        "id": str(link.id),
        "node_key": link.node_key,
        "node_name": link.node_name,
        "node_type": link.node_type,
        "relationship_type": link.relationship_type,
        "created_at": _serialize_dt(link.created_at),
    }


def serialize_evidence_link(link: CaseProfileEvidenceLink) -> dict[str, Any]:
    evidence = link.evidence_file
    return {
        "id": str(link.id),
        "evidence_file_id": str(link.evidence_file_id),
        "relationship_type": link.relationship_type,
        "excerpt": link.excerpt,
        "page": link.page,
        "created_at": _serialize_dt(link.created_at),
        "evidence": _serialize_evidence_file(evidence) if evidence else None,
    }


def serialize_note_link(link: CaseProfileNoteLink) -> dict[str, Any]:
    return {
        "id": str(link.id),
        "note_id": link.note_id,
        "relationship_type": link.relationship_type,
        "created_at": _serialize_dt(link.created_at),
    }


def serialize_finding_link(link: CaseProfileFindingLink) -> dict[str, Any]:
    return {
        "id": str(link.id),
        "finding_id": link.finding_id,
        "relationship_type": link.relationship_type,
        "created_at": _serialize_dt(link.created_at),
    }


def serialize_profile(profile: CaseProfile) -> dict[str, Any]:
    attributes = [serialize_attribute(attr) for attr in profile.attributes]
    aliases = [attr["value"] for attr in attributes if attr["kind"] == "alias"]
    tags = [attr["value"] for attr in attributes if attr["kind"] == "tag"]
    return {
        "id": str(profile.id),
        "case_id": str(profile.case_id),
        "profile_type": profile.profile_type,
        "display_name": profile.display_name,
        "summary": profile.summary,
        "importance": profile.importance,
        "aliases": aliases,
        "tags": tags,
        "attributes": attributes,
        "graph_node_links": [serialize_graph_link(link) for link in profile.graph_node_links],
        "evidence_links": [serialize_evidence_link(link) for link in profile.evidence_links],
        "note_links": [serialize_note_link(link) for link in profile.note_links],
        "finding_links": [serialize_finding_link(link) for link in profile.finding_links],
        "archived_at": _serialize_dt(profile.archived_at),
        "created_by_user_id": str(profile.created_by_user_id) if profile.created_by_user_id else None,
        "updated_by_user_id": str(profile.updated_by_user_id) if profile.updated_by_user_id else None,
        "created_at": _serialize_dt(profile.created_at),
        "updated_at": _serialize_dt(profile.updated_at),
    }


def _serialize_evidence_file(file: EvidenceFile) -> dict[str, Any]:
    return {
        "id": str(file.id),
        "case_id": str(file.case_id),
        "original_filename": file.original_filename,
        "status": file.status,
        "summary": file.summary,
        "source_type": file.source_type,
        "created_at": _serialize_dt(file.created_at),
        "processed_at": _serialize_dt(file.processed_at),
    }


def _replace_attributes(
    db: Session,
    profile: CaseProfile,
    *,
    aliases: Sequence[str] | None = None,
    tags: Sequence[str] | None = None,
    attributes: Sequence[dict[str, Any]] | None = None,
) -> None:
    db.execute(delete(CaseProfileAttribute).where(CaseProfileAttribute.profile_id == profile.id))
    ordinal = 0
    seen: set[tuple[str, str]] = set()

    def add_attr(kind: str, value: str, name: str | None = None) -> None:
        nonlocal ordinal
        text = _clean_text(value)
        if not text:
            return
        normalized_kind = _coerce_attribute_kind(kind)
        key = (normalized_kind, _normalize_value(text))
        if key in seen:
            return
        seen.add(key)
        db.add(
            CaseProfileAttribute(
                profile_id=profile.id,
                case_id=profile.case_id,
                kind=normalized_kind,
                name=_clean_text(name),
                value=text,
                normalized_value=_normalize_value(text),
                ordinal=ordinal,
            )
        )
        ordinal += 1

    for alias in _dedupe_strings(aliases):
        add_attr("alias", alias)
    for tag in _dedupe_strings(tags):
        add_attr("tag", tag)

    for item in attributes or []:
        kind = _coerce_attribute_kind(str(item.get("kind") or "custom"))
        value = _clean_text(item.get("value"))
        if not value:
            continue
        add_attr(kind, value, item.get("name"))


def _replace_graph_links(
    db: Session,
    profile: CaseProfile,
    links: Sequence[dict[str, Any]] | None,
    user: User,
) -> None:
    if links is None:
        return
    db.execute(delete(CaseProfileGraphNodeLink).where(CaseProfileGraphNodeLink.profile_id == profile.id))
    seen: set[str] = set()
    for item in links:
        node_key = _clean_text(item.get("node_key") or item.get("key"))
        if not node_key or node_key in seen:
            continue
        seen.add(node_key)
        db.add(
            CaseProfileGraphNodeLink(
                profile_id=profile.id,
                case_id=profile.case_id,
                node_key=node_key,
                node_name=_clean_text(item.get("node_name") or item.get("name")),
                node_type=_clean_text(item.get("node_type") or item.get("type")),
                relationship_type=_clean_text(item.get("relationship_type")),
                created_by_user_id=user.id,
            )
        )


def _replace_evidence_links(
    db: Session,
    profile: CaseProfile,
    links: Sequence[dict[str, Any]] | None,
    user: User,
) -> None:
    if links is None:
        return
    db.execute(delete(CaseProfileEvidenceLink).where(CaseProfileEvidenceLink.profile_id == profile.id))
    seen: set[uuid.UUID] = set()
    for item in links:
        try:
            evidence_file_id = uuid.UUID(str(item.get("evidence_file_id") or item.get("id")))
        except (TypeError, ValueError):
            raise ValueError("Invalid evidence_file_id")
        if evidence_file_id in seen:
            continue
        file = db.get(EvidenceFile, evidence_file_id)
        if not file or file.case_id != profile.case_id:
            raise ValueError(f"Evidence file {evidence_file_id} not found in this case")
        seen.add(evidence_file_id)
        db.add(
            CaseProfileEvidenceLink(
                profile_id=profile.id,
                case_id=profile.case_id,
                evidence_file_id=evidence_file_id,
                relationship_type=_clean_text(item.get("relationship_type")),
                excerpt=_clean_text(item.get("excerpt")),
                page=item.get("page"),
                created_by_user_id=user.id,
            )
        )


def _replace_note_links(
    db: Session,
    profile: CaseProfile,
    links: Sequence[dict[str, Any]] | None,
    user: User,
) -> None:
    if links is None:
        return
    db.execute(delete(CaseProfileNoteLink).where(CaseProfileNoteLink.profile_id == profile.id))
    seen: set[str] = set()
    for item in links:
        note_id = _clean_text(item.get("note_id") or item.get("id"))
        if not note_id or note_id in seen:
            continue
        note = db.scalars(
            select(WorkspaceNote).where(
                WorkspaceNote.case_id == profile.case_id,
                WorkspaceNote.note_id == note_id,
            )
        ).first()
        if note is None:
            raise ValueError(f"Workspace note {note_id} not found in this case")
        seen.add(note_id)
        db.add(
            CaseProfileNoteLink(
                profile_id=profile.id,
                case_id=profile.case_id,
                note_id=note_id,
                relationship_type=_clean_text(item.get("relationship_type")),
                created_by_user_id=user.id,
            )
        )


def _replace_finding_links(
    db: Session,
    profile: CaseProfile,
    links: Sequence[dict[str, Any]] | None,
    user: User,
) -> None:
    if links is None:
        return
    db.execute(delete(CaseProfileFindingLink).where(CaseProfileFindingLink.profile_id == profile.id))
    seen: set[str] = set()
    for item in links:
        finding_id = _clean_text(item.get("finding_id") or item.get("id"))
        if not finding_id or finding_id in seen:
            continue
        finding = db.scalars(
            select(WorkspaceFinding).where(
                WorkspaceFinding.case_id == profile.case_id,
                WorkspaceFinding.finding_id == finding_id,
                WorkspaceFinding.deleted_at.is_(None),
            )
        ).first()
        if finding is None:
            raise ValueError(f"Workspace finding {finding_id} not found in this case")
        seen.add(finding_id)
        db.add(
            CaseProfileFindingLink(
                profile_id=profile.id,
                case_id=profile.case_id,
                finding_id=finding_id,
                relationship_type=_clean_text(item.get("relationship_type")),
                created_by_user_id=user.id,
            )
        )


def list_case_profiles(
    db: Session,
    *,
    case_id: uuid.UUID,
    user: User,
    query: str | None = None,
    profile_type: str | None = None,
    include_archived: bool = False,
    linked_graph_node_key: str | None = None,
    linked_evidence_file_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    get_case_if_allowed(db=db, case_id=case_id, user=user)

    stmt = select(CaseProfile).options(*_profile_options()).where(CaseProfile.case_id == case_id)
    count_stmt = select(func.count()).select_from(CaseProfile).where(CaseProfile.case_id == case_id)
    filters = []
    if not include_archived:
        filters.append(CaseProfile.archived_at.is_(None))
    if profile_type:
        filters.append(CaseProfile.profile_type == _coerce_profile_type(profile_type))
    if query:
        pattern = f"%{query.strip()}%"
        filters.append(
            or_(
                CaseProfile.display_name.ilike(pattern),
                CaseProfile.summary.ilike(pattern),
                CaseProfile.attributes.any(CaseProfileAttribute.value.ilike(pattern)),
            )
        )
    if linked_graph_node_key:
        filters.append(CaseProfile.graph_node_links.any(CaseProfileGraphNodeLink.node_key == linked_graph_node_key))
    if linked_evidence_file_id:
        filters.append(
            CaseProfile.evidence_links.any(CaseProfileEvidenceLink.evidence_file_id == linked_evidence_file_id)
        )
    for condition in filters:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = db.scalar(count_stmt) or 0
    profiles = db.scalars(
        stmt.order_by(CaseProfile.updated_at.desc()).limit(limit).offset(offset)
    ).all()
    return {
        "profiles": [serialize_profile(profile) for profile in profiles],
        "total": total,
    }


def create_case_profile(db: Session, *, case_id: uuid.UUID, user: User, data: dict[str, Any]) -> dict[str, Any]:
    check_case_access(db, case_id, user, required_permission=("case", "edit"))
    display_name = _clean_text(data.get("display_name"))
    if not display_name:
        raise ValueError("display_name is required")

    profile = CaseProfile(
        case_id=case_id,
        profile_type=_coerce_profile_type(str(data.get("profile_type") or "other")),
        display_name=display_name,
        summary=_clean_text(data.get("summary")),
        importance=_clean_text(data.get("importance")),
        created_by_user_id=user.id,
        updated_by_user_id=user.id,
    )
    db.add(profile)
    db.flush()
    _replace_attributes(
        db,
        profile,
        aliases=data.get("aliases"),
        tags=data.get("tags"),
        attributes=data.get("attributes"),
    )
    _replace_graph_links(db, profile, data.get("graph_node_links"), user)
    _replace_evidence_links(db, profile, data.get("evidence_links"), user)
    _replace_note_links(db, profile, data.get("note_links"), user)
    _replace_finding_links(db, profile, data.get("finding_links"), user)
    db.commit()
    return serialize_profile(_load_profile(db, profile.id))


def get_case_profile(db: Session, *, profile_id: uuid.UUID, user: User) -> dict[str, Any]:
    return serialize_profile(_require_profile_read(db, profile_id, user))


def update_case_profile(db: Session, *, profile_id: uuid.UUID, user: User, data: dict[str, Any]) -> dict[str, Any]:
    profile = _require_profile_write(db, profile_id, user)
    if "profile_type" in data and data["profile_type"] is not None:
        profile.profile_type = _coerce_profile_type(str(data["profile_type"]))
    if "display_name" in data:
        display_name = _clean_text(data.get("display_name"))
        if not display_name:
            raise ValueError("display_name cannot be blank")
        profile.display_name = display_name
    if "summary" in data:
        profile.summary = _clean_text(data.get("summary"))
    if "importance" in data:
        profile.importance = _clean_text(data.get("importance"))
    profile.updated_by_user_id = user.id

    if any(key in data for key in ("aliases", "tags", "attributes")):
        current_aliases = [attr.value for attr in profile.attributes if attr.kind == "alias"]
        current_tags = [attr.value for attr in profile.attributes if attr.kind == "tag"]
        current_attributes = [
            {"kind": attr.kind, "name": attr.name, "value": attr.value}
            for attr in profile.attributes
            if attr.kind not in {"alias", "tag"}
        ]
        _replace_attributes(
            db,
            profile,
            aliases=data.get("aliases") if "aliases" in data else current_aliases,
            tags=data.get("tags") if "tags" in data else current_tags,
            attributes=data.get("attributes") if "attributes" in data else current_attributes,
        )
    _replace_graph_links(db, profile, data.get("graph_node_links"), user)
    _replace_evidence_links(db, profile, data.get("evidence_links"), user)
    _replace_note_links(db, profile, data.get("note_links"), user)
    _replace_finding_links(db, profile, data.get("finding_links"), user)
    db.commit()
    return serialize_profile(_load_profile(db, profile.id))


def archive_case_profile(db: Session, *, profile_id: uuid.UUID, user: User, archived: bool = True) -> dict[str, Any]:
    profile = _require_profile_write(db, profile_id, user)
    if archived:
        profile.archived_at = datetime.now(timezone.utc)
        profile.archived_by_user_id = user.id
    else:
        profile.archived_at = None
        profile.archived_by_user_id = None
    profile.updated_by_user_id = user.id
    db.commit()
    return serialize_profile(_load_profile(db, profile.id))


def delete_case_profile(db: Session, *, profile_id: uuid.UUID, user: User) -> None:
    profile = _require_profile_write(db, profile_id, user)
    db.delete(profile)
    db.commit()


def _neo4j_node_details(node_key: str, case_id: uuid.UUID) -> dict[str, Any] | None:
    try:
        from services.neo4j_service import neo4j_service

        return neo4j_service.get_node_details(node_key, case_id=str(case_id))
    except Exception as exc:
        return {"key": node_key, "error": str(exc)}


def _linked_timeline_nodes(node_keys: Sequence[str], case_id: uuid.UUID) -> list[dict[str, Any]]:
    if not node_keys:
        return []
    try:
        from services.neo4j.driver import driver

        with driver.session() as session:
            result = session.run(
                """
                MATCH (source {case_id: $case_id})
                WHERE source.key IN $node_keys
                MATCH path = (source)-[*0..2]-(event {case_id: $case_id})
                WHERE event.date IS NOT NULL
                  AND NONE(label IN labels(event) WHERE label IN ['Document', 'Case', 'RecycleBin', 'RecycleBinItem'])
                  AND coalesce(properties(event)['system_node'], false) <> true
                RETURN DISTINCT event.key AS key, event.name AS name, labels(event)[0] AS type,
                       event.date AS date, event.time AS time, event.summary AS summary,
                       source.key AS source_key
                ORDER BY event.date ASC, event.time ASC
                LIMIT 100
                """,
                case_id=str(case_id),
                node_keys=list(node_keys),
            )
            return [dict(record) for record in result]
    except Exception:
        return []


def get_case_profile_context(db: Session, *, profile_id: uuid.UUID, user: User) -> dict[str, Any]:
    profile = _require_profile_read(db, profile_id, user)
    graph_links = [serialize_graph_link(link) for link in profile.graph_node_links]
    graph_nodes = []
    for link in profile.graph_node_links:
        details = _neo4j_node_details(link.node_key, profile.case_id)
        graph_nodes.append({"link": serialize_graph_link(link), "node": details})

    evidence = [serialize_evidence_link(link) for link in profile.evidence_links]
    notes = _linked_workspace_rows(
        db,
        WorkspaceNote,
        "note_id",
        [link.note_id for link in profile.note_links],
        profile.case_id,
    )
    findings = _linked_workspace_rows(
        db,
        WorkspaceFinding,
        "finding_id",
        [link.finding_id for link in profile.finding_links],
        profile.case_id,
    )
    return {
        "profile": serialize_profile(profile),
        "graph_node_links": graph_links,
        "graph_nodes": graph_nodes,
        "evidence_links": evidence,
        "notes": notes,
        "findings": findings,
        "timeline_nodes": _linked_timeline_nodes([link.node_key for link in profile.graph_node_links], profile.case_id),
    }


def _linked_workspace_rows(
    db: Session,
    model: Any,
    id_attr: str,
    ids: Sequence[str],
    case_id: uuid.UUID,
) -> list[dict[str, Any]]:
    if not ids:
        return []
    column = getattr(model, id_attr)
    statement = select(model).where(model.case_id == case_id, column.in_(list(ids)))
    if hasattr(model, "deleted_at"):
        statement = statement.where(model.deleted_at.is_(None))
    rows = db.scalars(statement).all()
    serialized = []
    for row in rows:
        data = dict(row.data or {})
        serialized.append(
            {
                "id": data.get(id_attr) or getattr(row, id_attr),
                "title": data.get("title") or data.get("name"),
                "content": data.get("content") or data.get("summary") or data.get("description"),
                "created_at": data.get("created_at") or _serialize_dt(row.created_at),
                "updated_at": data.get("updated_at") or _serialize_dt(row.updated_at),
            }
        )
    return serialized
