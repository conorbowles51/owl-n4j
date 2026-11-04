from __future__ import annotations

import mimetypes
import uuid
from datetime import date, datetime, timezone
import re
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
from postgres import link_types
from postgres.models.workspace_entry import WorkspaceEntry
from services.case_service import check_case_access, get_case_if_allowed
from services.significant_service import add_significant_entities


BUILTIN_ROLES = {
    "subject", "witness", "source", "complainant", "affected party",
    "expert", "client", "key contact", "custodian",
}
LITIGATION_ROLES = {"friendly", "neutral", "adverse"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".avif"}
LINK_TARGET_TYPES = link_types.DOSSIER_TYPES


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
    db.execute(select(CaseProfile.id).where(CaseProfile.id == dossier_id).with_for_update())
    return dossier


def _graph_identity(case_id: uuid.UUID, key: str) -> dict[str, Any] | None:
    try:
        from services.neo4j import neo4j_service
        return neo4j_service.get_node_details(key, case_id=str(case_id))
    except Exception:
        return None


def _graph_list_identities(case_id: uuid.UUID, keys: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Name and type of every listed dossier's graph entity, in one read.

    The list shows only the name; the full identity with its connections stays on the detail route.
    The node filter is the one get_node_details applies. Should two active nodes share a key, the first
    record returned is kept; Neo4j defines no order there, as it defines none for get_node_details
    (0 of the 20 linked dossier keys had a duplicate on 30 Oct). A failed read leaves every identity
    out, as _graph_identity does.
    """
    wanted = sorted({key for key in keys if key})
    if not wanted:
        return {}
    try:
        from services.neo4j.driver import active_node_predicate, driver
        with driver.session() as session:
            records = session.run(
                f"""
                MATCH (n)
                WHERE n.case_id = $case_id AND n.key IN $keys AND {active_node_predicate("n")}
                RETURN n.key AS key, n.name AS name, labels(n)[0] AS type
                """,
                case_id=str(case_id), keys=wanted,
            )
            found: dict[str, dict[str, Any]] = {}
            for record in records:
                found.setdefault(record["key"], {"key": record["key"], "name": record["name"], "type": record["type"]})
            return found
    except Exception:
        return {}


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


def _read_by(db: Session, item: DossierAssessment) -> str | None:
    """CO-18: "Read by <model>, accepted by <name>" for an assessment accepted from machine text or an agent
    answer."""
    if getattr(item, "agent_message_id", None):
        from postgres.models.agent import AgentMessage
        from postgres.models.user import User as _User
        m = db.get(AgentMessage, item.agent_message_id)
        who = db.get(_User, item.author_user_id) if item.author_user_id else None
        model = (m.model_id if m else None) or (m.model_provider if m else None) or "the agent"
        return "Read by %s, accepted by %s" % (model, (getattr(who, "name", None) or getattr(who, "email", None)
                                                       or "a person"))
    if not getattr(item, "derived_text_id", None):
        return None
    from postgres.models.phone_derived import PhoneDerivedText
    from postgres.models.user import User as _User
    d = db.get(PhoneDerivedText, item.derived_text_id)
    who = db.get(_User, item.author_user_id) if item.author_user_id else None
    model = " ".join(x for x in ((d.model if d else None), (d.model_version if d else None)) if x) or "a model"
    return "Read by %s, accepted by %s" % (model, (getattr(who, "name", None) or getattr(who, "email", None)
                                                  or "a person"))


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
        "derived_text_id": str(item.derived_text_id) if getattr(item, "derived_text_id", None) else None,
        "agent_message_id": str(item.agent_message_id) if getattr(item, "agent_message_id", None) else None,
        "read_by": _read_by(db, item),
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
        "date_value": item.date_value or _dt(item.interview_date),
        "participants": list(item.participants or []), "interviewer_user_ids": list(item.interviewer_user_ids or []),
        "status": item.status, "working_notes": item.working_notes,
        "created_by_user_id": str(item.created_by_user_id) if item.created_by_user_id else None,
        "updated_by_user_id": str(item.updated_by_user_id) if item.updated_by_user_id else None,
        "created_at": _dt(item.created_at), "updated_at": _dt(item.updated_at),
        "evidence_links": [
            {"id": str(link.id),
             "evidence_file_id": str(link.evidence_file_id) if link.evidence_file_id else None,
             "target_type": link.target_type or "evidence",
             "target_id": link.target_id or str(link.evidence_file_id),
             "source_anchor": dict(link.source_anchor or {}),
             "evidence": _evidence_summary(link.evidence_file) if link.evidence_file_id else None}
            for link in evidence_links
        ],
    }


def _graph_linked(dossier: CaseProfile) -> bool:
    return bool(dossier.canonical_entity_key) and not dossier.graph_entity_deleted


def serialize_dossier(db: Session, dossier: CaseProfile, *, detail: bool = True,
                      identity: dict[str, Any] | None = None,
                      roles: list[DossierRole] | None = None) -> dict[str, Any]:
    """identity and roles are passed by list_dossiers, which reads them for the whole page at once."""
    if detail:
        identity = _graph_identity(dossier.case_id, dossier.canonical_entity_key) if _graph_linked(dossier) else None
    if roles is None:
        roles = db.scalars(select(DossierRole).where(DossierRole.dossier_id == dossier.id).order_by(DossierRole.name)).all()
    result = {
        "id": str(dossier.id), "case_id": str(dossier.case_id),
        "dossier_type": dossier.profile_type,
        "display_name": (identity or {}).get("name") or dossier.display_name,
        "display_name_snapshot": dossier.display_name,
        "summary": dossier.summary, "importance": dossier.importance,
        "contacts": list(dossier.contacts or []),
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
                  linked_evidence_file_id: uuid.UUID | None = None, canonical_entity_key: str | None = None,
                  include_archived: bool = False, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    get_case_if_allowed(db, case_id, user)
    conditions = [CaseProfile.case_id == case_id]
    if not include_archived:
        conditions.append(CaseProfile.archived_at.is_(None))
    if dossier_type:
        conditions.append(CaseProfile.profile_type == dossier_type)
    if linkage_state:
        conditions.append(CaseProfile.linkage_state == linkage_state)
    if canonical_entity_key:
        conditions.append(CaseProfile.canonical_entity_key == canonical_entity_key)
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
    identities = _graph_list_identities(case_id, (row.canonical_entity_key for row in rows if _graph_linked(row)))
    roles_by_dossier: dict[uuid.UUID, list[DossierRole]] = {row.id: [] for row in rows}
    if rows:
        for role in db.scalars(select(DossierRole).where(DossierRole.dossier_id.in_(list(roles_by_dossier))).order_by(DossierRole.name)).all():
            roles_by_dossier[role.dossier_id].append(role)
    return {
        "dossiers": [
            serialize_dossier(
                db, row, detail=False,
                identity=identities.get(row.canonical_entity_key) if _graph_linked(row) else None,
                roles=roles_by_dossier[row.id],
            )
            for row in rows
        ],
        "total": total, "limit": limit, "offset": offset,
    }


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


def _contacts(db: Session, case_id: uuid.UUID, user: User, raw_contacts: list[dict], existing: list[dict]) -> list[dict]:
    if len(raw_contacts) > 100:
        raise ValueError("A dossier can hold up to 100 contact details")
    by_id = {str(item.get("id")): item for item in existing}
    result = []
    seen = set()
    for raw in raw_contacts:
        kind, value = raw.get("kind"), _text(raw.get("value"))
        if kind not in {"phone", "email", "address"} or not value:
            raise ValueError("Each contact needs a phone, email or address value")
        contact_id = str(raw.get("id") or uuid.uuid4())
        if contact_id in seen:
            raise ValueError("Contact identifiers must be unique")
        seen.add(contact_id)
        evidence_id = raw.get("evidence_file_id")
        if evidence_id:
            evidence_id = uuid.UUID(str(evidence_id))
            _get_evidence(db, case_id, evidence_id)
        previous = by_id.get(contact_id, {})
        evidence_id = str(evidence_id) if evidence_id else None
        source = _contact_source(db, case_id, raw.get("record_source"), evidence_id, previous)
        unchanged = (previous.get("value") == value and previous.get("kind") == kind
                     and previous.get("evidence_file_id") == evidence_id
                     and _source_key(_stored_source(previous)) == _source_key(source))
        result.append({"id": contact_id, "kind": kind, "label": _text(raw.get("label")), "value": value,
                       "evidence_file_id": evidence_id, "record_source": source,
                       "recorded_by_user_id": previous.get("recorded_by_user_id") if unchanged else str(user.id)})
    return result


CONTACT_SOURCE_TYPES = ("manual", "evidence", "phone_record")


def _stored_source(contact: dict) -> dict:
    """A stored contact's source; contacts saved before sources were recorded derive it from their evidence file."""
    if isinstance(contact.get("record_source"), dict):
        return contact["record_source"]
    if contact.get("evidence_file_id"):
        return {"type": "evidence", "target_id": contact["evidence_file_id"]}
    return {"type": "manual"}


def _source_key(source: Any) -> tuple[str, str | None]:
    source = source if isinstance(source, dict) else {}
    return (source.get("type") or "manual", source.get("target_id"))


def _contact_source(db: Session, case_id: uuid.UUID, raw: Any, evidence_id: str | None, previous: dict) -> dict:
    """Where a contact detail came from (07 section 6.4 item 6): typed by a person, read from an evidence file,
    or copied from a phone record, which is checked against the case and keeps its mapping version set."""
    raw = raw if isinstance(raw, dict) else {}
    kind = raw.get("type")
    if kind not in (None, *CONTACT_SOURCE_TYPES):
        raise ValueError(f"A contact's source must be one of {', '.join(CONTACT_SOURCE_TYPES)}")
    if kind != "phone_record":
        # Typed or read from evidence: always worked out from the evidence file the request carries, never from
        # the copy of the stored source the editor sends back, so adding or removing a file updates it.
        kind = "evidence" if evidence_id else "manual"
    if kind == "phone_record":
        target_id = _text(raw.get("target_id"))
        if not target_id:
            raise ValueError("A contact copied from a phone needs the phone record it came from")
        old = _stored_source(previous)
        if _source_key(old) == ("phone_record", target_id) and "mapping_versions" in old:
            return dict(old)  # unchanged: the mapping version set at copy time is kept
        phone = link_types.resolve_phone_target(db, case_id, "phone_record", target_id)
        return {"type": "phone_record", "target_id": target_id, "mapping_versions": dict(phone.mapping_versions)}
    if kind == "evidence":
        if not evidence_id:
            raise ValueError("A contact read from evidence needs its evidence file")
        return {"type": "evidence", "target_id": evidence_id}
    return {"type": "manual"}


def contacts_for_suggestions(db: Session, case_id: uuid.UUID) -> list[dict[str, Any]]:
    """The dossier contact details that identity suggestions may match against (07 sections 6.4 item 6 and 7.1).

    Contacts copied from phones are excluded: matching a phone's identifier against a copy of itself would only
    confirm the copy. Archived dossiers are excluded. Each item names its dossier.
    """
    rows = db.scalars(select(CaseProfile).where(CaseProfile.case_id == case_id, CaseProfile.archived_at.is_(None))).all()
    result = []
    for dossier in rows:
        for contact in dossier.contacts or []:
            if _stored_source(contact).get("type") == "phone_record":
                continue
            result.append({"dossier_id": str(dossier.id), **contact})
    return result


def _interview_date(data: dict[str, Any]) -> tuple[datetime | None, str | None]:
    value = _text(data.get("date_value"))
    if value is None:
        old = data.get("interview_date")
        return old, _dt(old)
    try:
        if re.fullmatch(r"\d{4}", value):
            date(int(value), 1, 1)
            return None, value
        if re.fullmatch(r"\d{4}-\d{2}", value):
            date.fromisoformat(value + "-01")
            return None, value
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            parsed = date.fromisoformat(value)
            return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc), value
        parsed_time = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if "T" not in value or parsed_time.tzinfo is None:
            raise ValueError()
        return parsed_time, parsed_time.isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError("Enter a year, year-month, full date or timestamp with timezone") from exc


def create_dossier(db: Session, *, case_id: uuid.UUID, user: User, data: dict[str, Any], commit: bool = True) -> dict[str, Any]:
    """``commit=False`` flushes and leaves the commit to the caller, so a phone identity link (02 section 8.8) creates
    the person and records the link in one transaction."""
    check_case_access(db, case_id, user, required_permission=("case", "edit"))
    key = _text(data.get("canonical_entity_key"))
    if key and not commit:
        raise ValueError("A Dossier on a graph entity is created with its own commit (its significant entities follow it)")
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
        display_name=str(name), summary=_text(data.get("summary")), contacts=_contacts(db, case_id, user, data.get("contacts") or [], []), importance=_text(data.get("importance")),
        canonical_entity_key=key, linkage_state="linked" if key else "unlinked",
        status=_text(data.get("status")) or "active", needs_link_review=False,
        graph_entity_deleted=False, created_by_user_id=user.id, updated_by_user_id=user.id,
    )
    db.add(dossier)
    try:
        db.flush()
        _replace_roles(db, dossier, data.get("roles") or [], user)
        if commit:
            db.commit()
        else:
            db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise DossierConflict("This graph entity already has an active Dossier in this case") from exc
    if not commit:
        return {"id": str(dossier.id), "display_name": dossier.display_name}
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
    if "contacts" in data:
        dossier.contacts = _contacts(db, dossier.case_id, user, data.get("contacts") or [], dossier.contacts or [])
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


LINKS_ADD_LIMIT = 5000


def _clean_link(raw: dict[str, Any]) -> tuple[str, str]:
    target_type = _text(raw.get("target_type")) or ""
    target_id = _text(raw.get("target_id")) or ""
    if target_type not in LINK_TARGET_TYPES or not target_id:
        raise ValueError("Invalid Dossier link target")
    return target_type, target_id


def _record_link_event(db: Session, action: str, dossier: CaseProfile, user: User, details: dict[str, Any]) -> None:
    from services import activity_trail

    activity_trail.record(action, db=db, user=user, case_id=dossier.case_id,
                          details={"dossier_id": str(dossier.id), **details})


def replace_links(db: Session, *, dossier_id: uuid.UUID, user: User, links: list[dict[str, Any]]) -> dict[str, Any]:
    """Make the Dossier's links exactly `links`.

    A link that stays keeps who added it and when; only its relationship, label and anchor follow the request.
    Links that go are removed; new links are added by `user`. One event row records the counts.
    """
    dossier = _write(db, dossier_id, user)
    wanted: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in links:
        key = _clean_link(raw)
        wanted.setdefault(key, raw)
    existing = {(link.target_type, link.target_id): link for link in db.scalars(
        select(DossierLink).where(DossierLink.dossier_id == dossier.id)
    ).all()}
    removed = [link for key, link in existing.items() if key not in wanted]
    from services import collection_index

    for link in removed:
        if link.target_type == "phone_selection":
            collection_index.remove_members(db, link_id=link.id)
        db.delete(link)
    added = kept = 0
    for (target_type, target_id), raw in wanted.items():
        current = existing.get((target_type, target_id))
        if current is not None:
            kept += 1
            current.relationship_type = _text(raw.get("relationship_type"))
            current.label = _text(raw.get("label"))
            anchor = dict(raw.get("source_anchor") or {})
            if "mapping_versions" in (current.source_anchor or {}):
                # The mapping version set is what the record was at collect time; it is never rewritten.
                anchor["mapping_versions"] = current.source_anchor["mapping_versions"]
            current.source_anchor = anchor
            continue
        phone = _validate_target(db, dossier.case_id, target_type, target_id)
        row = DossierLink(
            id=uuid.uuid4(), dossier_id=dossier.id, case_id=dossier.case_id, target_type=target_type,
            target_id=target_id, relationship_type=_text(raw.get("relationship_type")),
            label=_text(raw.get("label")) or (phone.label if phone else None), source_anchor=_link_anchor(phone, raw),
            created_by_user_id=user.id,
        )
        db.add(row)
        if phone is not None and target_type == "phone_selection":
            collection_index.write_members(
                db, case_id=dossier.case_id, container_type="dossier", container_id=str(dossier.id),
                link_id=row.id, members=phone.members,
            )
        added += 1
    dossier.updated_by_user_id = user.id
    db.flush()
    _record_link_event(db, "dossier_links_replaced", dossier, user,
                       {"added": added, "kept": kept, "removed": len(removed)})
    db.commit()
    return serialize_dossier(db, _load(db, dossier.id))


def add_links(
    db: Session, *, dossier_id: uuid.UUID, user: User, links: list[dict[str, Any]], origin: str | None = None,
) -> dict[str, Any]:
    """Append links. Idempotent: a target already on the Dossier is skipped and keeps its adder and time.

    Returns the added and skipped counts. More than LINKS_ADD_LIMIT links in one request is refused, never cut;
    the caller sends the rest in further parts.
    """
    dossier = _write(db, dossier_id, user)
    if not links:
        raise ValueError("At least one link is required")
    if len(links) > LINKS_ADD_LIMIT:
        raise ValueError(
            f"{len(links):,} links were sent; one request takes at most {LINKS_ADD_LIMIT:,}. "
            "Send them in parts; nothing was added."
        )
    requested: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in links:
        requested.setdefault(_clean_link(raw), raw)
    present: set[tuple[str, str]] = set()
    by_type: dict[str, list[str]] = {}
    for target_type, target_id in requested:
        by_type.setdefault(target_type, []).append(target_id)
    for target_type, ids in by_type.items():
        for start in range(0, len(ids), 500):
            present.update((target_type, value) for value in db.scalars(select(DossierLink.target_id).where(
                DossierLink.dossier_id == dossier.id, DossierLink.target_type == target_type,
                DossierLink.target_id.in_(ids[start:start + 500]),
            )).all())
    new_rows: list[DossierLink] = []
    for (target_type, target_id), raw in requested.items():
        if (target_type, target_id) in present:
            continue
        phone = _validate_target(db, dossier.case_id, target_type, target_id)
        row = DossierLink(
            id=uuid.uuid4(), dossier_id=dossier.id, case_id=dossier.case_id, target_type=target_type,
            target_id=target_id, relationship_type=_text(raw.get("relationship_type")),
            label=_text(raw.get("label")) or (phone.label if phone else None), source_anchor=_link_anchor(phone, raw),
            created_by_user_id=user.id,
        )
        db.add(row)
        new_rows.append(row)
        if phone is not None and target_type == "phone_selection":
            from services import collection_index

            collection_index.write_members(
                db, case_id=dossier.case_id, container_type="dossier", container_id=str(dossier.id),
                link_id=row.id, members=phone.members,
            )
    skipped = len(links) - len(new_rows)
    if new_rows:
        dossier.updated_by_user_id = user.id
    db.flush()
    _record_link_event(db, "dossier_links_added", dossier, user, {
        "added": len(new_rows), "skipped": skipped, "origin": _text(origin),
        "types": sorted({row.target_type for row in new_rows}),
    })
    db.commit()
    return {
        "dossier_id": str(dossier.id),
        "added": len(new_rows),
        "skipped": skipped,
        "added_link_ids": [str(row.id) for row in new_rows],
        "total_links": db.scalar(select(func.count()).select_from(DossierLink).where(DossierLink.dossier_id == dossier.id)),
    }


def remove_link(db: Session, *, dossier_id: uuid.UUID, link_id: uuid.UUID, user: User) -> dict[str, Any]:
    dossier = _write(db, dossier_id, user)
    link = db.scalar(select(DossierLink).where(DossierLink.id == link_id, DossierLink.dossier_id == dossier.id))
    if link is None:
        raise DossierNotFound("Link not found")
    details = {"link_id": str(link.id), "target_type": link.target_type, "target_id": link.target_id}
    from postgres.models.collection_membership import CollectionMembership
    from services import removed_records
    members = db.scalars(select(CollectionMembership).where(CollectionMembership.link_id == link.id)).all()
    kept = removed_records.keep(db, kind="dossier_link", case_id=dossier.case_id, subject_id=link.id,
                                label=link.label or f"{link.target_type} {link.target_id}", rows=[link, *members],
                                user=user)
    details["removed_record_id"] = str(kept.id)
    if link.target_type == "phone_selection":
        from services import collection_index

        collection_index.remove_members(db, link_id=link.id)
    db.delete(link)
    dossier.updated_by_user_id = user.id
    db.flush()
    _record_link_event(db, "dossier_link_removed", dossier, user, details)
    db.commit()
    return {"dossier_id": str(dossier.id), "removed": 1}


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
    from services import removed_records
    rows = db.scalars(select(DossierLink).where(
        DossierLink.dossier_id == dossier.id, DossierLink.target_type == "evidence",
        DossierLink.target_id == str(evidence_file_id))).all()
    if rows:
        removed_records.keep(db, kind="dossier_evidence_link", case_id=dossier.case_id, subject_id=evidence_file_id,
                             label=rows[0].label or "Evidence link", rows=rows, user=user)
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


def _validate_target(
    db: Session, case_id: uuid.UUID, target_type: str, target_id: str
) -> link_types.PhoneTarget | None:
    """Check a link target is in the case. A phone target returns what its resolver confirmed."""
    if link_types.is_phone_type(target_type):
        return link_types.resolve_phone_target(db, case_id, target_type, target_id)
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
    return None


def _link_anchor(phone: link_types.PhoneTarget | None, raw: dict[str, Any]) -> dict[str, Any]:
    anchor = dict(raw.get("source_anchor") or {})
    return link_types.phone_anchor(phone, anchor) if phone is not None else anchor


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
        derived_text_id=data.get("derived_text_id"),
        agent_message_id=data.get("agent_message_id"),
    )
    db.add(assessment); db.flush()
    for raw in data.get("supporting_links") or []:
        target_type, target_id = _text(raw.get("target_type")) or "", _text(raw.get("target_id")) or ""
        if target_type not in LINK_TARGET_TYPES or not target_id:
            raise ValueError("Invalid assessment supporting link")
        phone = _validate_target(db, dossier.case_id, target_type, target_id)
        db.add(DossierAssessmentLink(
            assessment_id=assessment.id, case_id=dossier.case_id, target_type=target_type,
            target_id=target_id, label=_text(raw.get("label")) or (phone.label if phone else None),
            source_anchor=_link_anchor(phone, raw),
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
    from services import removed_records
    links = db.scalars(select(DossierAssessmentLink).where(DossierAssessmentLink.assessment_id == assessment.id)).all()
    removed_records.keep(db, kind="dossier_assessment", case_id=dossier.case_id, subject_id=assessment.id,
                         label=f"{assessment.category}: {(assessment.content or '')[:200]}", rows=[assessment, *links],
                         user=user)
    for link in links:  # what the foreign key cascade removes, removed explicitly (the copy holds exactly these)
        db.delete(link)
    db.delete(assessment); db.commit()


def _get_evidence(db: Session, case_id: uuid.UUID, evidence_file_id: uuid.UUID) -> EvidenceFile:
    file = db.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_file_id, EvidenceFile.case_id == case_id))
    if file is None: raise ValueError("Evidence is not in this case")
    return file


def add_media(db: Session, *, dossier_id: uuid.UUID, user: User, data: dict[str, Any]) -> dict[str, Any]:
    dossier = _write(db, dossier_id, user)
    if data.get("phone_file_id") and data.get("evidence_file_id"):
        raise ValueError("Give either an evidence file or a phone file, not both")
    if data.get("phone_file_id"):
        # A phone file becomes an evidence row only now, when it is added as dossier media (07 section 6.4 item 4).
        from services import phone_files

        file, _ = phone_files.ensure_phone_file_evidence(
            db, case_id=dossier.case_id, phone_file_id=str(data["phone_file_id"]), user=user)
        evidence_id = file.id
    else:
        try: evidence_id = uuid.UUID(str(data.get("evidence_file_id")))
        except (TypeError, ValueError) as exc: raise ValueError("Invalid evidence_file_id") from exc
        file = _get_evidence(db, dossier.case_id, evidence_id)
    mime = mimetypes.guess_type(file.original_filename)[0] or ""
    if not mime.startswith("image/") and Path(file.original_filename).suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError("The initial Dossier gallery supports image evidence only")
    existing = db.scalar(select(DossierMedia).where(DossierMedia.dossier_id == dossier.id, DossierMedia.evidence_file_id == evidence_id))
    if existing is not None:
        db.commit()
        return _serialize_media(existing)
    is_cover = bool(data.get("is_cover"))
    if is_cover:
        db.query(DossierMedia).filter(DossierMedia.dossier_id == dossier.id, DossierMedia.is_cover.is_(True)).update({"is_cover": False})
    ordinal = data.get("ordinal")
    if ordinal is None:
        last_ordinal = db.scalar(select(func.max(DossierMedia.ordinal)).where(DossierMedia.dossier_id == dossier.id))
        ordinal = (last_ordinal if last_ordinal is not None else -1) + 1
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
    from services import removed_records
    removed_records.keep(db, kind="dossier_media", case_id=dossier.case_id, subject_id=item.id,
                         label=getattr(item, "caption", None) or "Media item", rows=[item], user=user)
    db.delete(item); db.commit()


def create_interview(db: Session, *, dossier_id: uuid.UUID, user: User, data: dict[str, Any]) -> dict[str, Any]:
    dossier = _write(db, dossier_id, user)
    interviewer_ids = [str(value) for value in dict.fromkeys(data.get("interviewer_user_ids") or [])]
    # Interviewers are represented by stable user IDs; Phase 5's member helper is reused through permission checks here.
    valid_members = _case_member_ids(db, dossier.case_id)
    if any(value not in valid_members for value in interviewer_ids):
        raise ValueError("Interviewers must be current case members")
    interview_date, date_value = _interview_date(data)
    item = DossierInterview(
        dossier_id=dossier.id, case_id=dossier.case_id, interview_date=interview_date, date_value=date_value,
        participants=list(data.get("participants") or []), interviewer_user_ids=interviewer_ids,
        status=_text(data.get("status")) or "planned", working_notes=_text(data.get("working_notes")),
        created_by_user_id=user.id, updated_by_user_id=user.id,
    )
    db.add(item); db.flush()
    _add_interview_evidence(db, dossier, item, data.get("evidence_links") or [], user)
    db.commit(); db.refresh(item)
    return _serialize_interview(db, item)


def _add_interview_evidence(
    db: Session, dossier: CaseProfile, interview: DossierInterview, items: list[dict[str, Any]], user: User,
) -> None:
    """Add an interview's evidence items: evidence files, phone files and registry targets (07 section 6.4 item 5).

    A phone file is registered as one evidence row on first use (item 4) and linked as evidence. A phone record,
    analysis or statement check is linked by its registry type and id, checked against the case, and keeps the
    mapping version set behind it. A repeated item is kept once.
    """
    seen: set[tuple[str, str]] = set()
    for raw in items:
        target_type = _text(raw.get("target_type")) or "evidence"
        if target_type not in link_types.INTERVIEW_EVIDENCE_TYPES:
            raise ValueError(f"Interview evidence cannot be a {target_type}")
        anchor = dict(raw.get("source_anchor") or {})
        if target_type == "phone_file":
            from services import phone_files

            phone_file_id = _text(raw.get("target_id")) or ""
            file, _ = phone_files.ensure_phone_file_evidence(
                db, case_id=dossier.case_id, phone_file_id=phone_file_id, user=user)
            evidence_id = file.id
            anchor = {**anchor, "phone_file_id": phone_file_id}
            target_type = "evidence"
        elif target_type == "evidence":
            try: evidence_id = uuid.UUID(str(raw.get("evidence_file_id") or raw.get("target_id")))
            except (TypeError, ValueError) as exc: raise ValueError("Invalid evidence_file_id") from exc
            _get_evidence(db, dossier.case_id, evidence_id)
        if target_type == "evidence":
            if ("evidence", str(evidence_id)) in seen:
                continue
            seen.add(("evidence", str(evidence_id)))
            db.add(DossierInterviewEvidenceLink(
                interview_id=interview.id, case_id=dossier.case_id, evidence_file_id=evidence_id, source_anchor=anchor))
            continue
        target_id = _text(raw.get("target_id")) or ""
        if not target_id:
            raise ValueError("Interview evidence needs a target id")
        if (target_type, target_id) in seen:
            continue
        seen.add((target_type, target_id))
        phone = link_types.resolve_phone_target(db, dossier.case_id, target_type, target_id)
        db.add(DossierInterviewEvidenceLink(
            interview_id=interview.id, case_id=dossier.case_id, target_type=target_type, target_id=target_id,
            source_anchor=link_types.phone_anchor(phone, anchor)))


def add_interview_evidence(
    db: Session, *, dossier_id: uuid.UUID, interview_id: uuid.UUID, user: User, item: dict[str, Any],
) -> dict[str, Any]:
    """Add one evidence item to an interview, keeping the ones it has (a statement check or a frozen result linked
    from the phone screens, 07 J-9). Updating an interview replaces its whole list; this does not. An item already
    on the interview is reported as already there, not added twice."""
    dossier = _write(db, dossier_id, user)
    interview = db.scalar(select(DossierInterview).where(DossierInterview.id == interview_id,
                                                         DossierInterview.dossier_id == dossier.id))
    if interview is None:
        raise DossierNotFound("Interview not found")
    target_type = _text(item.get("target_type")) or "evidence"
    target_id = _text(item.get("target_id")) or _text(item.get("evidence_file_id")) or ""
    existing = db.scalars(select(DossierInterviewEvidenceLink).where(
        DossierInterviewEvidenceLink.interview_id == interview.id)).all()
    already = any((row.target_type == target_type and row.target_id == target_id)
                  or (target_type == "evidence" and str(row.evidence_file_id) == target_id)
                  or (target_type == "phone_file" and (row.source_anchor or {}).get("phone_file_id") == target_id)
                  for row in existing)
    if not already:
        from sqlalchemy.exc import IntegrityError
        _add_interview_evidence(db, dossier, interview, [item], user)
        interview.updated_by_user_id = user.id
        try:
            db.commit()
        except IntegrityError:
            # the same evidence row reached by another route (a phone file already linked as its evidence file),
            # or a second click racing the first: the item is there, so say so
            db.rollback()
            already = True
    db.refresh(interview)
    return {"added": 0 if already else 1, "already_there": 1 if already else 0,
            "interview": _serialize_interview(db, interview)}


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
    if "date_value" in data or "interview_date" in data:
        item.interview_date, item.date_value = _interview_date(data)
    for field in ("participants", "interviewer_user_ids", "status", "working_notes"):
        if field in data:
            setattr(item, field, data[field])
    if "evidence_links" in data:
        db.execute(delete(DossierInterviewEvidenceLink).where(DossierInterviewEvidenceLink.interview_id == item.id))
        _add_interview_evidence(db, dossier, item, data.get("evidence_links") or [], user)
    item.updated_by_user_id = user.id
    db.commit(); db.refresh(item)
    return _serialize_interview(db, item)


def delete_interview(db: Session, *, dossier_id: uuid.UUID, interview_id: uuid.UUID, user: User) -> None:
    dossier = _write(db, dossier_id, user)
    item = db.scalar(select(DossierInterview).where(DossierInterview.id == interview_id, DossierInterview.dossier_id == dossier.id))
    if item is None: raise DossierNotFound("Interview not found")
    from services import removed_records
    links = db.scalars(select(DossierInterviewEvidenceLink).where(DossierInterviewEvidenceLink.interview_id == item.id)).all()
    removed_records.keep(db, kind="dossier_interview", case_id=dossier.case_id, subject_id=item.id,
                         label=f"Interview {item.date_value or (item.interview_date.date().isoformat() if item.interview_date else '')}".strip(),
                         rows=[item, *links], user=user)
    for link in links:  # what the foreign key cascade removes, removed explicitly (the copy holds exactly these)
        db.delete(link)
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
