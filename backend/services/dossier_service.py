from __future__ import annotations

import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from postgres.models.agent import AgentArtifactRecord, AgentThread
from postgres.models.case_deadline import CaseDeadline
from postgres.models.case_profile import CaseProfile, CaseProfileGraphNodeLink
from postgres.models.dossier import (
    DossierAssessment,
    DossierAssessmentLink,
    DossierInterview,
    DossierInterviewEvidenceLink,
    DossierLink,
    DossierMedia,
    DossierRole,
)
from postgres.models.evidence import EvidenceFile
from postgres.models.timeline_view import TimelineViewEvent
from postgres.models.user import User
from postgres.models.work import CaseTask
from postgres.models.workspace_entry import WorkspaceEntry
from services.case_service import check_case_access, get_case_if_allowed
from services.significant_service import add_significant_entities


BUILTIN_ROLES = {
    "subject", "witness", "source", "complainant", "affected party",
    "expert", "client", "key contact", "custodian",
}
LITIGATION_ROLES = {"friendly", "neutral", "adverse"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".avif"}
LINK_TARGET_TYPES = {"entry", "task", "evidence", "deadline", "timeline_event", "agent_artifact", "graph_entity", "dossier"}


class DossierNotFound(Exception):
    pass


class DossierConflict(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _dt(value: Any) -> str | None:
    return value.isoformat() if value else None


def _normalize(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _dossier_type(value: Any) -> str:
    normalized = _normalize(str(value or "other")).replace("organization", "organisation")
    return normalized if normalized in {"person", "address", "event", "device", "organisation", "vehicle", "other"} else "other"


def _load(db: Session, dossier_id: uuid.UUID) -> CaseProfile:
    dossier = db.get(CaseProfile, dossier_id)
    if dossier is None:
        raise DossierNotFound(f"Dossier {dossier_id} not found")
    return dossier


def _read(db: Session, dossier_id: uuid.UUID, user: User) -> CaseProfile:
    dossier = _load(db, dossier_id)
    get_case_if_allowed(db, dossier.case_id, user)
    return dossier


def _write(db: Session, dossier_id: uuid.UUID, user: User) -> CaseProfile:
    dossier = _load(db, dossier_id)
    check_case_access(db, dossier.case_id, user, required_permission=("case", "edit"))
    return dossier


def _graph_identity(case_id: uuid.UUID, key: str) -> dict[str, Any] | None:
    try:
        from services.neo4j import neo4j_service
        return neo4j_service.get_node_details(key, case_id=str(case_id))
    except Exception:
        return None


def _require_graph_identity(case_id: uuid.UUID, key: str) -> dict[str, Any]:
    identity = _graph_identity(case_id, key)
    if not identity:
        raise ValueError("The selected graph entity does not exist in this case")
    return identity


def _serialize_role(item: DossierRole) -> dict[str, Any]:
    return {"id": str(item.id), "name": item.name, "is_builtin": item.is_builtin, "template_key": item.template_key}


def _serialize_link(item: DossierLink) -> dict[str, Any]:
    return {
        "id": str(item.id), "target_type": item.target_type, "target_id": item.target_id,
        "relationship_type": item.relationship_type, "label": item.label,
        "source_anchor": dict(item.source_anchor or {}), "created_at": _dt(item.created_at),
    }


def _serialize_assessment(db: Session, item: DossierAssessment) -> dict[str, Any]:
    links = db.scalars(select(DossierAssessmentLink).where(DossierAssessmentLink.assessment_id == item.id).order_by(DossierAssessmentLink.created_at)).all()
    return {
        "id": str(item.id), "category": item.category, "content": item.content,
        "assessment_date": item.assessment_date.isoformat() if item.assessment_date else None,
        "author_user_id": str(item.author_user_id) if item.author_user_id else None,
        "updated_by_user_id": str(item.updated_by_user_id) if item.updated_by_user_id else None,
        "legacy_label": item.legacy_label,
        "provenance_type": item.provenance_type,
        "generated_output_id": str(item.generated_output_id) if item.generated_output_id else None,
        "created_at": _dt(item.created_at), "updated_at": _dt(item.updated_at),
        "supporting_links": [
            {"id": str(link.id), "target_type": link.target_type, "target_id": link.target_id,
             "label": link.label, "source_anchor": dict(link.source_anchor or {})}
            for link in links
        ],
    }


def _evidence_summary(file: EvidenceFile) -> dict[str, Any]:
    return {
        "id": str(file.id), "original_filename": file.original_filename,
        "status": file.status, "size": file.size, "sha256": file.sha256,
        "source_type": file.source_type, "metadata": dict(file.metadata_ or {}),
        "file_url": f"/api/evidence/{file.id}/file",
    }


def _serialize_media(item: DossierMedia) -> dict[str, Any]:
    return {
        "id": str(item.id), "evidence_file_id": str(item.evidence_file_id),
        "is_cover": item.is_cover, "ordinal": item.ordinal, "caption": item.caption,
        "focal_x": item.focal_x, "focal_y": item.focal_y,
        "crop_metadata": dict(item.crop_metadata or {}), "source_anchor": dict(item.source_anchor or {}),
        "evidence": _evidence_summary(item.evidence_file), "created_at": _dt(item.created_at),
    }


def _serialize_interview(db: Session, item: DossierInterview) -> dict[str, Any]:
    evidence_links = db.scalars(select(DossierInterviewEvidenceLink).where(DossierInterviewEvidenceLink.interview_id == item.id).order_by(DossierInterviewEvidenceLink.created_at)).all()
    return {
        "id": str(item.id), "interview_date": _dt(item.interview_date),
        "participants": list(item.participants or []), "interviewer_user_ids": list(item.interviewer_user_ids or []),
        "status": item.status, "working_notes": item.working_notes,
        "created_by_user_id": str(item.created_by_user_id) if item.created_by_user_id else None,
        "updated_by_user_id": str(item.updated_by_user_id) if item.updated_by_user_id else None,
        "created_at": _dt(item.created_at), "updated_at": _dt(item.updated_at),
        "evidence_links": [
            {"id": str(link.id), "evidence_file_id": str(link.evidence_file_id),
             "source_anchor": dict(link.source_anchor or {}), "evidence": _evidence_summary(link.evidence_file)}
            for link in evidence_links
        ],
    }


def serialize_dossier(db: Session, dossier: CaseProfile, *, detail: bool = True) -> dict[str, Any]:
    identity = _graph_identity(dossier.case_id, dossier.canonical_entity_key) if dossier.canonical_entity_key and not dossier.graph_entity_deleted else None
    roles = db.scalars(select(DossierRole).where(DossierRole.dossier_id == dossier.id).order_by(DossierRole.name)).all()
    result = {
        "id": str(dossier.id), "case_id": str(dossier.case_id),
        "dossier_type": dossier.profile_type,
        "display_name": (identity or {}).get("name") or dossier.display_name,
        "display_name_snapshot": dossier.display_name,
        "summary": dossier.summary, "importance": dossier.importance,
        "canonical_entity_key": dossier.canonical_entity_key,
        "linkage_state": dossier.linkage_state, "status": dossier.status,
        "needs_link_review": dossier.needs_link_review,
        "graph_entity_deleted": dossier.graph_entity_deleted,
        "canonical_identity": identity,
        "roles": [_serialize_role(role) for role in roles],
        "archived_at": _dt(dossier.archived_at),
        "created_by_user_id": str(dossier.created_by_user_id) if dossier.created_by_user_id else None,
        "updated_by_user_id": str(dossier.updated_by_user_id) if dossier.updated_by_user_id else None,
        "created_at": _dt(dossier.created_at), "updated_at": _dt(dossier.updated_at),
    }
    if detail:
        links = db.scalars(select(DossierLink).where(DossierLink.dossier_id == dossier.id).order_by(DossierLink.created_at)).all()
        assessments = db.scalars(select(DossierAssessment).where(DossierAssessment.dossier_id == dossier.id).order_by(DossierAssessment.created_at.desc())).all()
        media = db.scalars(select(DossierMedia).where(DossierMedia.dossier_id == dossier.id).order_by(DossierMedia.ordinal, DossierMedia.created_at)).all()
        interviews = db.scalars(select(DossierInterview).where(DossierInterview.dossier_id == dossier.id).order_by(DossierInterview.interview_date.desc().nullslast(), DossierInterview.created_at.desc())).all()
        result.update({
            "links": [_serialize_link(link) for link in links],
            "assessments": [_serialize_assessment(db, item) for item in assessments],
            "media": [_serialize_media(item) for item in media],
            "interviews": [_serialize_interview(db, item) for item in interviews],
        })
    return result


def list_dossiers(db: Session, *, case_id: uuid.UUID, user: User, query: str | None = None,
                  dossier_type: str | None = None, linkage_state: str | None = None,
                  linked_evidence_file_id: uuid.UUID | None = None,
                  include_archived: bool = False, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    get_case_if_allowed(db, case_id, user)
    conditions = [CaseProfile.case_id == case_id]
    if not include_archived:
        conditions.append(CaseProfile.archived_at.is_(None))
    if dossier_type:
        conditions.append(CaseProfile.profile_type == dossier_type)
    if linkage_state:
        conditions.append(CaseProfile.linkage_state == linkage_state)
    if linked_evidence_file_id:
        conditions.append(
            CaseProfile.id.in_(
                select(DossierLink.dossier_id).where(
                    DossierLink.case_id == case_id,
                    DossierLink.target_type == "evidence",
                    DossierLink.target_id == str(linked_evidence_file_id),
                )
            )
        )
    if query:
        pattern = f"%{query.strip()}%"
        conditions.append(or_(CaseProfile.display_name.ilike(pattern), CaseProfile.summary.ilike(pattern)))
    total = db.scalar(select(func.count()).select_from(CaseProfile).where(*conditions)) or 0
    rows = db.scalars(select(CaseProfile).where(*conditions).order_by(CaseProfile.updated_at.desc()).limit(limit).offset(offset)).all()
    return {"dossiers": [serialize_dossier(db, row, detail=False) for row in rows], "total": total, "limit": limit, "offset": offset}


def _replace_roles(db: Session, dossier: CaseProfile, roles: Iterable[dict[str, Any] | str], user: User) -> None:
    db.execute(delete(DossierRole).where(DossierRole.dossier_id == dossier.id))
    seen: set[str] = set()
    for raw in roles:
        item = raw if isinstance(raw, dict) else {"name": raw}
        name = _text(item.get("name"))
        if not name:
            continue
        normalized = _normalize(name)
        if normalized in seen:
            continue
        template_key = _text(item.get("template_key"))
        if normalized in LITIGATION_ROLES and template_key != "litigation":
            raise ValueError("Friendly, Neutral, and Adverse roles require the litigation template")
        seen.add(normalized)
        db.add(DossierRole(
            dossier_id=dossier.id, case_id=dossier.case_id, name=name,
            normalized_name=normalized, is_builtin=normalized in BUILTIN_ROLES,
            template_key=template_key, created_by_user_id=user.id,
        ))


def create_dossier(db: Session, *, case_id: uuid.UUID, user: User, data: dict[str, Any]) -> dict[str, Any]:
    check_case_access(db, case_id, user, required_permission=("case", "edit"))
    key = _text(data.get("canonical_entity_key"))
    identity = _require_graph_identity(case_id, key) if key else None
    if key and db.scalar(select(CaseProfile.id).where(
        CaseProfile.case_id == case_id, CaseProfile.canonical_entity_key == key,
        CaseProfile.archived_at.is_(None),
    )):
        raise DossierConflict("This graph entity already has an active Dossier in this case")
    name = (identity or {}).get("name") or _text(data.get("display_name"))
    if not name:
        raise ValueError("display_name is required for an unlinked Dossier")
    dossier = CaseProfile(
        case_id=case_id, profile_type=_dossier_type(data.get("dossier_type") or (identity or {}).get("type")),
        display_name=str(name), summary=_text(data.get("summary")), importance=_text(data.get("importance")),
        canonical_entity_key=key, linkage_state="linked" if key else "unlinked",
        status=_text(data.get("status")) or "active", needs_link_review=False,
        graph_entity_deleted=False, created_by_user_id=user.id, updated_by_user_id=user.id,
    )
    db.add(dossier)
    try:
        db.flush()
        _replace_roles(db, dossier, data.get("roles") or [], user)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DossierConflict("This graph entity already has an active Dossier in this case") from exc
    if key:
        add_significant_entities(db, case_id=case_id, current_user=user, entity_keys=[key], addition_source="dossier", context={"dossier_id": str(dossier.id)})
    return serialize_dossier(db, _load(db, dossier.id))


def get_dossier(db: Session, *, dossier_id: uuid.UUID, user: User) -> dict[str, Any]:
    return serialize_dossier(db, _read(db, dossier_id, user))


def update_dossier(db: Session, *, dossier_id: uuid.UUID, user: User, data: dict[str, Any]) -> dict[str, Any]:
    dossier = _write(db, dossier_id, user)
    if "display_name" in data:
        if dossier.canonical_entity_key:
            raise ValueError("Linked Dossier identity names are controlled by the graph")
        name = _text(data.get("display_name"))
        if not name:
            raise ValueError("display_name cannot be blank")
        dossier.display_name = name
    for field in ("summary", "importance", "status"):
        if field in data:
            setattr(dossier, field, _text(data.get(field)))
    if "dossier_type" in data and data.get("dossier_type"):
        dossier.profile_type = _dossier_type(data["dossier_type"])
    if "roles" in data:
        _replace_roles(db, dossier, data.get("roles") or [], user)
    dossier.updated_by_user_id = user.id
    db.commit()
    return serialize_dossier(db, _load(db, dossier.id))


def link_dossier(db: Session, *, dossier_id: uuid.UUID, entity_key: str, user: User) -> dict[str, Any]:
    dossier = _write(db, dossier_id, user)
    key = _text(entity_key)
    if not key:
        raise ValueError("entity_key is required")
    identity = _require_graph_identity(dossier.case_id, key)
    existing = db.scalar(select(CaseProfile.id).where(
        CaseProfile.case_id == dossier.case_id, CaseProfile.canonical_entity_key == key,
        CaseProfile.archived_at.is_(None), CaseProfile.id != dossier.id,
    ))
    if existing:
        raise DossierConflict("This graph entity already has an active Dossier in this case")
    dossier.canonical_entity_key = key
    dossier.linkage_state = "linked"
    dossier.graph_entity_deleted = False
    dossier.needs_link_review = False
    dossier.display_name = str(identity.get("name") or dossier.display_name)
    dossier.updated_by_user_id = user.id
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DossierConflict("This graph entity already has an active Dossier in this case") from exc
    add_significant_entities(db, case_id=dossier.case_id, current_user=user, entity_keys=[key], addition_source="dossier", context={"dossier_id": str(dossier.id)})
    return serialize_dossier(db, _load(db, dossier.id))


def archive_dossier(db: Session, *, dossier_id: uuid.UUID, user: User, archived: bool) -> dict[str, Any]:
    dossier = _write(db, dossier_id, user)
    if not archived and dossier.canonical_entity_key and db.scalar(select(CaseProfile.id).where(
        CaseProfile.case_id == dossier.case_id,
        CaseProfile.canonical_entity_key == dossier.canonical_entity_key,
        CaseProfile.archived_at.is_(None), CaseProfile.id != dossier.id,
    )):
        raise DossierConflict("An active Dossier already exists for this graph entity")
    dossier.archived_at = _now() if archived else None
    dossier.archived_by_user_id = user.id if archived else None
    dossier.updated_by_user_id = user.id
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DossierConflict("An active Dossier already exists for this graph entity") from exc
    return serialize_dossier(db, _load(db, dossier.id))


def replace_links(db: Session, *, dossier_id: uuid.UUID, user: User, links: list[dict[str, Any]]) -> dict[str, Any]:
    dossier = _write(db, dossier_id, user)
    db.execute(delete(DossierLink).where(DossierLink.dossier_id == dossier.id))
    seen: set[tuple[str, str]] = set()
    for raw in links:
        target_type = _text(raw.get("target_type")) or ""
        target_id = _text(raw.get("target_id")) or ""
        if target_type not in LINK_TARGET_TYPES or not target_id:
            raise ValueError("Invalid Dossier link target")
        if (target_type, target_id) in seen:
            continue
        _validate_target(db, dossier.case_id, target_type, target_id)
        seen.add((target_type, target_id))
        db.add(DossierLink(
            dossier_id=dossier.id, case_id=dossier.case_id, target_type=target_type,
            target_id=target_id, relationship_type=_text(raw.get("relationship_type")),
            label=_text(raw.get("label")), source_anchor=dict(raw.get("source_anchor") or {}),
            created_by_user_id=user.id,
        ))
    dossier.updated_by_user_id = user.id
    db.commit()
    return serialize_dossier(db, _load(db, dossier.id))


def add_evidence_links(
    db: Session,
    *,
    dossier_id: uuid.UUID,
    evidence_file_ids: list[uuid.UUID],
    user: User,
) -> dict[str, Any]:
    dossier = _write(db, dossier_id, user)
    unique_ids = list(dict.fromkeys(evidence_file_ids))
    if not unique_ids:
        raise ValueError("At least one evidence file is required")
    evidence_rows = db.scalars(
        select(EvidenceFile).where(
            EvidenceFile.id.in_(unique_ids), EvidenceFile.case_id == dossier.case_id
        )
    ).all()
    by_id = {row.id: row for row in evidence_rows}
    missing = [value for value in unique_ids if value not in by_id]
    if missing:
        raise ValueError("Every evidence file must belong to the Dossier case")
    existing = set(
        db.scalars(
            select(DossierLink.target_id).where(
                DossierLink.dossier_id == dossier.id,
                DossierLink.target_type == "evidence",
                DossierLink.target_id.in_([str(value) for value in unique_ids]),
            )
        ).all()
    )
    for evidence_id in unique_ids:
        target_id = str(evidence_id)
        if target_id in existing:
            continue
        db.add(
            DossierLink(
                dossier_id=dossier.id,
                case_id=dossier.case_id,
                target_type="evidence",
                target_id=target_id,
                relationship_type="linked evidence",
                label=by_id[evidence_id].original_filename,
                source_anchor={},
                created_by_user_id=user.id,
            )
        )
    dossier.updated_by_user_id = user.id
    db.commit()
    return serialize_dossier(db, _load(db, dossier.id))


def remove_evidence_link(
    db: Session,
    *,
    dossier_id: uuid.UUID,
    evidence_file_id: uuid.UUID,
    user: User,
) -> dict[str, Any]:
    dossier = _write(db, dossier_id, user)
    db.execute(
        delete(DossierLink).where(
            DossierLink.dossier_id == dossier.id,
            DossierLink.target_type == "evidence",
            DossierLink.target_id == str(evidence_file_id),
        )
    )
    dossier.updated_by_user_id = user.id
    db.commit()
    return serialize_dossier(db, _load(db, dossier.id))


def _validate_target(db: Session, case_id: uuid.UUID, target_type: str, target_id: str) -> None:
    if target_type == "evidence":
        try: target_uuid = uuid.UUID(target_id)
        except ValueError as exc: raise ValueError("Invalid evidence identifier") from exc
        if not db.scalar(select(EvidenceFile.id).where(EvidenceFile.id == target_uuid, EvidenceFile.case_id == case_id)):
            raise ValueError("Evidence is not in this case")
    elif target_type == "entry":
        try: target_uuid = uuid.UUID(target_id)
        except ValueError as exc: raise ValueError("Invalid entry identifier") from exc
        if not db.scalar(select(WorkspaceEntry.id).where(WorkspaceEntry.id == target_uuid, WorkspaceEntry.case_id == case_id, WorkspaceEntry.deleted_at.is_(None))):
            raise ValueError("Casework entry is not in this case")
    elif target_type == "dossier":
        try: target_uuid = uuid.UUID(target_id)
        except ValueError as exc: raise ValueError("Invalid Dossier identifier") from exc
        if not db.scalar(select(CaseProfile.id).where(CaseProfile.id == target_uuid, CaseProfile.case_id == case_id)):
            raise ValueError("Dossier is not in this case")
    elif target_type == "task":
        try: target_uuid = uuid.UUID(target_id)
        except ValueError as exc: raise ValueError("Invalid task identifier") from exc
        if not db.scalar(select(CaseTask.id).where(CaseTask.id == target_uuid, CaseTask.case_id == case_id, CaseTask.deleted_at.is_(None))):
            raise ValueError("Task is not in this case")
    elif target_type == "deadline":
        try: target_uuid = uuid.UUID(target_id)
        except ValueError as exc: raise ValueError("Invalid deadline identifier") from exc
        if not db.scalar(select(CaseDeadline.id).where(CaseDeadline.id == target_uuid, CaseDeadline.case_id == case_id)):
            raise ValueError("Deadline is not in this case")
    elif target_type == "timeline_event":
        if not db.scalar(select(TimelineViewEvent.id).where(TimelineViewEvent.event_key == target_id, TimelineViewEvent.case_id == case_id)):
            raise ValueError("Timeline event is not in this case")
    elif target_type == "agent_artifact":
        try: target_uuid = uuid.UUID(target_id)
        except ValueError as exc: raise ValueError("Invalid agent artifact identifier") from exc
        if not db.scalar(
            select(AgentArtifactRecord.id)
            .join(AgentThread, AgentThread.id == AgentArtifactRecord.thread_id)
            .where(AgentArtifactRecord.id == target_uuid, AgentThread.case_id == case_id)
        ):
            raise ValueError("Agent artifact is not in this case")
    elif target_type == "graph_entity":
        _require_graph_identity(case_id, target_id)


def create_assessment(
    db: Session,
    *,
    dossier_id: uuid.UUID,
    user: User,
    data: dict[str, Any],
    commit: bool = True,
) -> dict[str, Any]:
    dossier = _write(db, dossier_id, user)
    category, content = _text(data.get("category")), _text(data.get("content"))
    if not category or not content:
        raise ValueError("category and content are required")
    assessment = DossierAssessment(
        dossier_id=dossier.id, case_id=dossier.case_id, category=category, content=content,
        assessment_date=data.get("assessment_date"), author_user_id=user.id, updated_by_user_id=user.id,
        provenance_type=_text(data.get("provenance_type")) or "investigator",
        generated_output_id=data.get("generated_output_id"),
    )
    db.add(assessment); db.flush()
    for raw in data.get("supporting_links") or []:
        target_type, target_id = _text(raw.get("target_type")) or "", _text(raw.get("target_id")) or ""
        if target_type not in LINK_TARGET_TYPES or not target_id:
            raise ValueError("Invalid assessment supporting link")
        _validate_target(db, dossier.case_id, target_type, target_id)
        db.add(DossierAssessmentLink(
            assessment_id=assessment.id, case_id=dossier.case_id, target_type=target_type,
            target_id=target_id, label=_text(raw.get("label")), source_anchor=dict(raw.get("source_anchor") or {}),
        ))
    if commit:
        db.commit()
    else:
        db.flush()
    return _serialize_assessment(db, assessment)


def delete_assessment(db: Session, *, dossier_id: uuid.UUID, assessment_id: uuid.UUID, user: User) -> None:
    dossier = _write(db, dossier_id, user)
    assessment = db.scalar(select(DossierAssessment).where(DossierAssessment.id == assessment_id, DossierAssessment.dossier_id == dossier.id))
    if assessment is None: raise DossierNotFound("Assessment not found")
    db.delete(assessment); db.commit()


def _get_evidence(db: Session, case_id: uuid.UUID, evidence_file_id: uuid.UUID) -> EvidenceFile:
    file = db.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_file_id, EvidenceFile.case_id == case_id))
    if file is None: raise ValueError("Evidence is not in this case")
    return file


def add_media(db: Session, *, dossier_id: uuid.UUID, user: User, data: dict[str, Any]) -> dict[str, Any]:
    dossier = _write(db, dossier_id, user)
    try: evidence_id = uuid.UUID(str(data.get("evidence_file_id")))
    except (TypeError, ValueError) as exc: raise ValueError("Invalid evidence_file_id") from exc
    file = _get_evidence(db, dossier.case_id, evidence_id)
    mime = mimetypes.guess_type(file.original_filename)[0] or ""
    if not mime.startswith("image/") and Path(file.original_filename).suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError("The initial Dossier gallery supports image evidence only")
    is_cover = bool(data.get("is_cover"))
    if is_cover:
        db.query(DossierMedia).filter(DossierMedia.dossier_id == dossier.id, DossierMedia.is_cover.is_(True)).update({"is_cover": False})
    ordinal = data.get("ordinal")
    if ordinal is None:
        ordinal = (db.scalar(select(func.max(DossierMedia.ordinal)).where(DossierMedia.dossier_id == dossier.id)) or -1) + 1
    item = DossierMedia(
        dossier_id=dossier.id, case_id=dossier.case_id, evidence_file_id=file.id,
        is_cover=is_cover, ordinal=int(ordinal), caption=_text(data.get("caption")),
        focal_x=data.get("focal_x"), focal_y=data.get("focal_y"),
        crop_metadata=dict(data.get("crop_metadata") or {}), source_anchor=dict(data.get("source_anchor") or {}),
        created_by_user_id=user.id,
    )
    db.add(item)
    try: db.commit()
    except IntegrityError as exc:
        db.rollback(); raise DossierConflict("This evidence image is already in the Dossier gallery") from exc
    db.refresh(item)
    return _serialize_media(item)


def update_media(db: Session, *, dossier_id: uuid.UUID, media_id: uuid.UUID, user: User, data: dict[str, Any]) -> dict[str, Any]:
    dossier = _write(db, dossier_id, user)
    item = db.scalar(select(DossierMedia).where(DossierMedia.id == media_id, DossierMedia.dossier_id == dossier.id))
    if item is None: raise DossierNotFound("Dossier media not found")
    if data.get("is_cover") is True:
        db.query(DossierMedia).filter(DossierMedia.dossier_id == dossier.id, DossierMedia.id != item.id).update({"is_cover": False})
    for field in ("is_cover", "ordinal", "caption", "focal_x", "focal_y", "crop_metadata", "source_anchor"):
        if field in data:
            setattr(item, field, data[field] if field not in {"caption"} else _text(data[field]))
    db.commit(); db.refresh(item)
    return _serialize_media(item)


def reorder_media(
    db: Session,
    *,
    dossier_id: uuid.UUID,
    user: User,
    media_ids: Iterable[uuid.UUID],
) -> list[dict[str, Any]]:
    dossier = _write(db, dossier_id, user)
    requested = list(media_ids)
    if len(requested) != len(set(requested)):
        raise ValueError("Dossier media order contains duplicate identifiers")
    items = db.scalars(
        select(DossierMedia).where(DossierMedia.dossier_id == dossier.id)
    ).all()
    by_id = {item.id: item for item in items}
    if set(requested) != set(by_id):
        raise ValueError("Dossier media order must include every gallery item exactly once")
    for ordinal, media_id in enumerate(requested):
        by_id[media_id].ordinal = ordinal
    db.commit()
    return [_serialize_media(by_id[media_id]) for media_id in requested]


def delete_media(db: Session, *, dossier_id: uuid.UUID, media_id: uuid.UUID, user: User) -> None:
    dossier = _write(db, dossier_id, user)
    item = db.scalar(select(DossierMedia).where(DossierMedia.id == media_id, DossierMedia.dossier_id == dossier.id))
    if item is None: raise DossierNotFound("Dossier media not found")
    db.delete(item); db.commit()


def create_interview(db: Session, *, dossier_id: uuid.UUID, user: User, data: dict[str, Any]) -> dict[str, Any]:
    dossier = _write(db, dossier_id, user)
    interviewer_ids = [str(value) for value in dict.fromkeys(data.get("interviewer_user_ids") or [])]
    # Interviewers are represented by stable user IDs; Phase 5's member helper is reused through permission checks here.
    valid_members = _case_member_ids(db, dossier.case_id)
    if any(value not in valid_members for value in interviewer_ids):
        raise ValueError("Interviewers must be current case members")
    item = DossierInterview(
        dossier_id=dossier.id, case_id=dossier.case_id, interview_date=data.get("interview_date"),
        participants=list(data.get("participants") or []), interviewer_user_ids=interviewer_ids,
        status=_text(data.get("status")) or "planned", working_notes=_text(data.get("working_notes")),
        created_by_user_id=user.id, updated_by_user_id=user.id,
    )
    db.add(item); db.flush()
    for raw in data.get("evidence_links") or []:
        try: evidence_id = uuid.UUID(str(raw.get("evidence_file_id")))
        except (TypeError, ValueError) as exc: raise ValueError("Invalid evidence_file_id") from exc
        _get_evidence(db, dossier.case_id, evidence_id)
        db.add(DossierInterviewEvidenceLink(
            interview_id=item.id, case_id=dossier.case_id, evidence_file_id=evidence_id,
            source_anchor=dict(raw.get("source_anchor") or {}),
        ))
    db.commit(); db.refresh(item)
    return _serialize_interview(db, item)


def _case_member_ids(db: Session, case_id: uuid.UUID) -> set[str]:
    from postgres.models.case_membership import CaseMembership
    return {str(value) for value in db.scalars(select(CaseMembership.user_id).where(CaseMembership.case_id == case_id)).all()}


def update_interview(db: Session, *, dossier_id: uuid.UUID, interview_id: uuid.UUID, user: User, data: dict[str, Any]) -> dict[str, Any]:
    dossier = _write(db, dossier_id, user)
    item = db.scalar(select(DossierInterview).where(DossierInterview.id == interview_id, DossierInterview.dossier_id == dossier.id))
    if item is None: raise DossierNotFound("Interview not found")
    if "interviewer_user_ids" in data:
        interviewer_ids = [str(value) for value in dict.fromkeys(data.get("interviewer_user_ids") or [])]
        if any(value not in _case_member_ids(db, dossier.case_id) for value in interviewer_ids):
            raise ValueError("Interviewers must be current case members")
        data = {**data, "interviewer_user_ids": interviewer_ids}
    for field in ("interview_date", "participants", "interviewer_user_ids", "status", "working_notes"):
        if field in data:
            setattr(item, field, data[field])
    if "evidence_links" in data:
        db.execute(delete(DossierInterviewEvidenceLink).where(DossierInterviewEvidenceLink.interview_id == item.id))
        for raw in data.get("evidence_links") or []:
            evidence_id = uuid.UUID(str(raw.get("evidence_file_id")))
            _get_evidence(db, dossier.case_id, evidence_id)
            db.add(DossierInterviewEvidenceLink(interview_id=item.id, case_id=dossier.case_id, evidence_file_id=evidence_id, source_anchor=dict(raw.get("source_anchor") or {})))
    item.updated_by_user_id = user.id
    db.commit(); db.refresh(item)
    return _serialize_interview(db, item)


def delete_interview(db: Session, *, dossier_id: uuid.UUID, interview_id: uuid.UUID, user: User) -> None:
    dossier = _write(db, dossier_id, user)
    item = db.scalar(select(DossierInterview).where(DossierInterview.id == interview_id, DossierInterview.dossier_id == dossier.id))
    if item is None: raise DossierNotFound("Interview not found")
    db.delete(item); db.commit()


def suspend_dossier_for_entity_delete(db: Session, *, case_id: uuid.UUID, entity_key: str) -> int:
    rows = db.scalars(select(CaseProfile).where(CaseProfile.case_id == case_id, CaseProfile.canonical_entity_key == entity_key, CaseProfile.archived_at.is_(None))).all()
    for row in rows:
        row.graph_entity_deleted = True; row.linkage_state = "deleted"
    if rows: db.commit()
    return len(rows)


def restore_dossier_after_entity_restore(db: Session, *, case_id: uuid.UUID, entity_key: str) -> int:
    rows = db.scalars(select(CaseProfile).where(CaseProfile.case_id == case_id, CaseProfile.canonical_entity_key == entity_key, CaseProfile.graph_entity_deleted.is_(True))).all()
    for row in rows:
        row.graph_entity_deleted = False; row.linkage_state = "linked"
    if rows: db.commit()
    return len(rows)


def transfer_dossiers_after_merge(db: Session, *, case_id: uuid.UUID, source_entity_keys: Iterable[str], merged_entity_key: str) -> int:
    keys = list(dict.fromkeys(filter(None, source_entity_keys)))
    rows = db.scalars(select(CaseProfile).where(CaseProfile.case_id == case_id, CaseProfile.canonical_entity_key.in_(keys), CaseProfile.archived_at.is_(None)).order_by(CaseProfile.created_at)).all()
    if not rows: return 0
    existing = db.scalar(select(CaseProfile).where(CaseProfile.case_id == case_id, CaseProfile.canonical_entity_key == merged_entity_key, CaseProfile.archived_at.is_(None)))
    if len(rows) == 1 and (existing is None or existing.id == rows[0].id):
        rows[0].canonical_entity_key = merged_entity_key; rows[0].graph_entity_deleted = False; rows[0].linkage_state = "linked"
    else:
        # Preserve all authored material and force a visible human resolution instead of silently merging Dossiers.
        for row in rows:
            row.canonical_entity_key = None; row.graph_entity_deleted = False
            row.linkage_state = "unlinked"; row.needs_link_review = True
            if not db.scalar(select(DossierLink.id).where(DossierLink.dossier_id == row.id, DossierLink.target_type == "graph_entity", DossierLink.target_id == merged_entity_key)):
                db.add(DossierLink(dossier_id=row.id, case_id=case_id, target_type="graph_entity", target_id=merged_entity_key, relationship_type="merge_candidate", label="Merged graph identity", source_anchor={"source_entity_keys": keys}))
    db.commit()
    return len(rows)
