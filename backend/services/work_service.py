from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from postgres.models.case import Case
from postgres.models.case_deadline import CaseDeadline
from postgres.models.case_membership import CaseMembership
from postgres.models.case_profile import CaseProfile
from postgres.models.evidence import EvidenceFile
from postgres.models.user import User
from postgres.models.work import CaseTask, CaseTaskLink, SharedEvidencePin
from postgres.models.workspace_entry import WorkspaceEntry
from services.case_service import check_case_access


TASK_STATUSES = {"todo", "in_progress", "done"}
TASK_PRIORITIES = {"low", "standard", "high", "urgent"}
TASK_LINK_TYPES = {"dossier", "entry", "evidence"}


class WorkValidationError(ValueError):
    pass


class TaskNotFound(LookupError):
    pass


class PinNotFound(LookupError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _assert_view(db: Session, case_id: UUID, user: User) -> None:
    check_case_access(db, case_id, user, required_permission=("case", "view"))


def _assert_edit(db: Session, case_id: UUID, user: User) -> None:
    check_case_access(db, case_id, user, required_permission=("case", "edit"))


def _validate_assignee(db: Session, case_id: UUID, assignee_user_id: UUID | None) -> User | None:
    if assignee_user_id is None:
        return None
    case = db.get(Case, case_id)
    if not case:
        raise WorkValidationError("Case not found")
    user = db.get(User, assignee_user_id)
    if not user or not user.is_active:
        raise WorkValidationError("Assignee must be an active case member")
    if case.owner_user_id == assignee_user_id:
        return user
    membership = db.get(CaseMembership, (case_id, assignee_user_id))
    if not membership:
        raise WorkValidationError("Assignee must be a current member of this case")
    return user


def _validate_deadline(db: Session, case_id: UUID, deadline_id: UUID | None) -> CaseDeadline | None:
    if deadline_id is None:
        return None
    deadline = db.scalar(
        select(CaseDeadline).where(
            CaseDeadline.id == deadline_id,
            CaseDeadline.case_id == case_id,
        )
    )
    if not deadline:
        raise WorkValidationError("Linked deadline was not found in this case")
    return deadline


def _validate_parent(
    db: Session,
    case_id: UUID,
    parent_task_id: UUID | None,
    task_id: UUID | None = None,
) -> CaseTask | None:
    if parent_task_id is None:
        return None
    if task_id and parent_task_id == task_id:
        raise WorkValidationError("A task cannot be its own parent")
    parent = db.scalar(
        select(CaseTask).where(
            CaseTask.id == parent_task_id,
            CaseTask.case_id == case_id,
            CaseTask.deleted_at.is_(None),
        )
    )
    if not parent:
        raise WorkValidationError("Parent task was not found in this case")
    if parent.parent_task_id is not None:
        raise WorkValidationError("Tasks support one subtask level only")
    if task_id:
        has_parent_as_child = db.scalar(
            select(func.count())
            .select_from(CaseTask)
            .where(
                CaseTask.id == parent_task_id,
                CaseTask.parent_task_id == task_id,
                CaseTask.case_id == case_id,
            )
        )
        if has_parent_as_child:
            raise WorkValidationError("Cyclic task relationships are not allowed")
        has_children = db.scalar(
            select(func.count())
            .select_from(CaseTask)
            .where(
                CaseTask.parent_task_id == task_id,
                CaseTask.case_id == case_id,
                CaseTask.deleted_at.is_(None),
            )
        )
        if has_children:
            raise WorkValidationError("A task with subtasks cannot itself become a subtask")
    return parent


def _validate_link(db: Session, case_id: UUID, link: dict[str, Any]) -> None:
    target_type = str(link.get("target_type") or "").strip().lower()
    target_id = str(link.get("target_id") or "").strip()
    if target_type not in TASK_LINK_TYPES or not target_id:
        raise WorkValidationError("Task links require a supported target type and identifier")
    try:
        target_uuid = UUID(target_id)
    except (TypeError, ValueError) as exc:
        raise WorkValidationError("Task link target identifier must be a UUID") from exc
    if target_type == "dossier":
        exists = db.scalar(
            select(func.count()).select_from(CaseProfile).where(
                CaseProfile.id == target_uuid,
                CaseProfile.case_id == case_id,
            )
        )
    elif target_type == "entry":
        exists = db.scalar(
            select(func.count()).select_from(WorkspaceEntry).where(
                WorkspaceEntry.id == target_uuid,
                WorkspaceEntry.case_id == case_id,
                WorkspaceEntry.deleted_at.is_(None),
            )
        )
    else:
        exists = db.scalar(
            select(func.count()).select_from(EvidenceFile).where(
                EvidenceFile.id == target_uuid,
                EvidenceFile.case_id == case_id,
            )
        )
    if not exists:
        raise WorkValidationError(f"Linked {target_type} was not found in this case")


def _task_links(task: CaseTask, db: Session) -> list[dict[str, Any]]:
    links = db.scalars(
        select(CaseTaskLink)
        .where(CaseTaskLink.task_id == task.id)
        .order_by(CaseTaskLink.created_at, CaseTaskLink.id)
    ).all()
    return [
        {
            "id": str(link.id),
            "target_type": link.target_type,
            "target_id": link.target_id,
            "label": link.label,
            "source_anchor": link.source_anchor or {},
        }
        for link in links
    ]


def task_to_dict(task: CaseTask, db: Session, *, include_links: bool = True) -> dict[str, Any]:
    child_total, child_done = db.execute(
        select(
            func.count(CaseTask.id),
            func.count(CaseTask.id).filter(CaseTask.status == "done"),
        ).where(
            CaseTask.parent_task_id == task.id,
            CaseTask.deleted_at.is_(None),
        )
    ).one()
    payload: dict[str, Any] = {
        "id": str(task.id),
        "task_id": str(task.id),
        "case_id": str(task.case_id),
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "assignee_user_id": str(task.assignee_user_id) if task.assignee_user_id else None,
        "assignee_name": task.assignee.name if task.assignee else None,
        "assignee_email": task.assignee.email if task.assignee else None,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "parent_task_id": str(task.parent_task_id) if task.parent_task_id else None,
        "deadline_id": str(task.deadline_id) if task.deadline_id else None,
        "deadline_name": task.deadline.name if task.deadline else None,
        "deadline_date": task.deadline.due_date.isoformat() if task.deadline else None,
        "created_by_user_id": str(task.created_by_user_id) if task.created_by_user_id else None,
        "created_by_name": task.creator.name if task.creator else None,
        "updated_by_user_id": str(task.updated_by_user_id) if task.updated_by_user_id else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "deleted_at": task.deleted_at.isoformat() if task.deleted_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "legacy_id": task.legacy_id,
        "migration_metadata": task.migration_metadata or {},
        "needs_migration_review": task.needs_migration_review,
        "subtask_progress": {"done": int(child_done or 0), "total": int(child_total or 0)},
    }
    payload["links"] = _task_links(task, db) if include_links else []
    return payload


def list_tasks(
    db: Session,
    *,
    case_id: UUID,
    user: User,
    status: str | None = None,
    assignee_user_id: UUID | None = None,
    due_before: datetime | None = None,
    include_deleted: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    _assert_view(db, case_id, user)
    conditions = [CaseTask.case_id == case_id]
    if not include_deleted:
        conditions.append(CaseTask.deleted_at.is_(None))
    if status:
        if status not in TASK_STATUSES:
            raise WorkValidationError("Unsupported task status")
        conditions.append(CaseTask.status == status)
    if assignee_user_id:
        conditions.append(CaseTask.assignee_user_id == assignee_user_id)
    if due_before:
        conditions.append(CaseTask.due_at <= due_before)
    total = int(db.scalar(select(func.count()).select_from(CaseTask).where(*conditions)) or 0)
    rows = db.scalars(
        select(CaseTask)
        .where(*conditions)
        .order_by(
            CaseTask.due_at.is_(None),
            CaseTask.due_at,
            CaseTask.created_at.desc(),
            CaseTask.id,
        )
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 250))
    ).all()
    return [task_to_dict(row, db) for row in rows], total


def get_task(db: Session, *, case_id: UUID, task_id: UUID, user: User) -> dict[str, Any]:
    _assert_view(db, case_id, user)
    task = db.scalar(
        select(CaseTask).where(CaseTask.id == task_id, CaseTask.case_id == case_id)
    )
    if not task:
        raise TaskNotFound("Task not found")
    return task_to_dict(task, db)


def _replace_links(
    db: Session,
    *,
    task: CaseTask,
    links: list[dict[str, Any]],
    user: User,
) -> None:
    for link in links:
        _validate_link(db, task.case_id, link)
    db.query(CaseTaskLink).filter(CaseTaskLink.task_id == task.id).delete(synchronize_session=False)
    for link in links:
        db.add(
            CaseTaskLink(
                task_id=task.id,
                case_id=task.case_id,
                target_type=str(link["target_type"]).lower(),
                target_id=str(link["target_id"]),
                label=link.get("label"),
                source_anchor=link.get("source_anchor") or {},
                created_by_user_id=user.id,
            )
        )


def create_task(
    db: Session,
    *,
    case_id: UUID,
    user: User,
    data: dict[str, Any],
) -> dict[str, Any]:
    _assert_edit(db, case_id, user)
    title = str(data.get("title") or "").strip()
    if not title:
        raise WorkValidationError("Task title is required")
    status = str(data.get("status") or "todo").lower()
    priority = str(data.get("priority") or "standard").lower()
    if status not in TASK_STATUSES:
        raise WorkValidationError("Unsupported task status")
    if priority not in TASK_PRIORITIES:
        raise WorkValidationError("Unsupported task priority")
    _validate_assignee(db, case_id, data.get("assignee_user_id"))
    _validate_deadline(db, case_id, data.get("deadline_id"))
    _validate_parent(db, case_id, data.get("parent_task_id"))
    now = _now()
    task = CaseTask(
        case_id=case_id,
        title=title,
        description=(str(data.get("description") or "").strip() or None),
        status=status,
        priority=priority,
        assignee_user_id=data.get("assignee_user_id"),
        due_at=data.get("due_at"),
        parent_task_id=data.get("parent_task_id"),
        deadline_id=data.get("deadline_id"),
        created_by_user_id=user.id,
        updated_by_user_id=user.id,
        completed_at=now if status == "done" else None,
    )
    db.add(task)
    db.flush()
    _replace_links(db, task=task, links=data.get("links") or [], user=user)
    db.commit()
    db.refresh(task)
    return task_to_dict(task, db)


def update_task(
    db: Session,
    *,
    case_id: UUID,
    task_id: UUID,
    user: User,
    updates: dict[str, Any],
) -> dict[str, Any]:
    _assert_edit(db, case_id, user)
    task = db.scalar(
        select(CaseTask).where(
            CaseTask.id == task_id,
            CaseTask.case_id == case_id,
            CaseTask.deleted_at.is_(None),
        )
    )
    if not task:
        raise TaskNotFound("Task not found")
    if "title" in updates:
        title = str(updates.get("title") or "").strip()
        if not title:
            raise WorkValidationError("Task title is required")
        task.title = title
    if "description" in updates:
        task.description = str(updates.get("description") or "").strip() or None
    if "status" in updates:
        status = str(updates["status"]).lower()
        if status not in TASK_STATUSES:
            raise WorkValidationError("Unsupported task status")
        task.status = status
        task.completed_at = (task.completed_at or _now()) if status == "done" else None
    if "priority" in updates:
        priority = str(updates["priority"]).lower()
        if priority not in TASK_PRIORITIES:
            raise WorkValidationError("Unsupported task priority")
        task.priority = priority
    if "assignee_user_id" in updates:
        _validate_assignee(db, case_id, updates["assignee_user_id"])
        task.assignee_user_id = updates["assignee_user_id"]
    if "due_at" in updates:
        task.due_at = updates["due_at"]
    if "deadline_id" in updates:
        _validate_deadline(db, case_id, updates["deadline_id"])
        task.deadline_id = updates["deadline_id"]
    if "parent_task_id" in updates:
        _validate_parent(db, case_id, updates["parent_task_id"], task.id)
        task.parent_task_id = updates["parent_task_id"]
    task.updated_by_user_id = user.id
    if "links" in updates:
        _replace_links(db, task=task, links=updates.get("links") or [], user=user)
    db.commit()
    db.refresh(task)
    return task_to_dict(task, db)


def soft_delete_task(db: Session, *, case_id: UUID, task_id: UUID, user: User) -> None:
    _assert_edit(db, case_id, user)
    task = db.scalar(
        select(CaseTask).where(
            CaseTask.id == task_id,
            CaseTask.case_id == case_id,
            CaseTask.deleted_at.is_(None),
        )
    )
    if not task:
        raise TaskNotFound("Task not found")
    task.deleted_at = _now()
    task.updated_by_user_id = user.id
    db.commit()


def restore_task(db: Session, *, case_id: UUID, task_id: UUID, user: User) -> dict[str, Any]:
    _assert_edit(db, case_id, user)
    task = db.scalar(
        select(CaseTask).where(CaseTask.id == task_id, CaseTask.case_id == case_id)
    )
    if not task:
        raise TaskNotFound("Task not found")
    task.deleted_at = None
    task.updated_by_user_id = user.id
    db.commit()
    db.refresh(task)
    return task_to_dict(task, db)


def pin_to_dict(pin: SharedEvidencePin) -> dict[str, Any]:
    evidence = pin.evidence_file
    return {
        "id": str(pin.id),
        "pin_id": str(pin.id),
        "case_id": str(pin.case_id),
        "item_type": "evidence",
        "item_id": str(pin.evidence_file_id),
        "evidence_file_id": str(pin.evidence_file_id),
        "filename": evidence.original_filename,
        "display_name": evidence.original_filename,
        "size": evidence.size,
        "status": evidence.status,
        "source_type": evidence.source_type,
        "summary": evidence.summary,
        "sha256": evidence.sha256,
        "pinned_by_user_id": str(pin.pinned_by_user_id) if pin.pinned_by_user_id else None,
        "pinned_by_name": pin.pinned_by.name if pin.pinned_by else None,
        "created_at": pin.created_at.isoformat() if pin.created_at else None,
    }


def list_pins(
    db: Session,
    *,
    case_id: UUID,
    user: User,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    _assert_view(db, case_id, user)
    total = int(
        db.scalar(
            select(func.count()).select_from(SharedEvidencePin).where(
                SharedEvidencePin.case_id == case_id
            )
        )
        or 0
    )
    pins = db.scalars(
        select(SharedEvidencePin)
        .where(SharedEvidencePin.case_id == case_id)
        .order_by(SharedEvidencePin.created_at.desc(), SharedEvidencePin.id)
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 100))
    ).all()
    return [pin_to_dict(pin) for pin in pins], total


def get_pin_status(
    db: Session,
    *,
    case_id: UUID,
    evidence_file_ids: list[UUID],
    user: User,
) -> dict[str, str]:
    _assert_view(db, case_id, user)
    unique_ids = list(dict.fromkeys(evidence_file_ids))
    if len(unique_ids) > 250:
        raise WorkValidationError("At most 250 evidence items can be checked at once")
    if not unique_ids:
        return {}
    rows = db.execute(
        select(SharedEvidencePin.evidence_file_id, SharedEvidencePin.id).where(
            SharedEvidencePin.case_id == case_id,
            SharedEvidencePin.evidence_file_id.in_(unique_ids),
        )
    ).all()
    return {str(evidence_id): str(pin_id) for evidence_id, pin_id in rows}


def pin_evidence(
    db: Session,
    *,
    case_id: UUID,
    evidence_file_id: UUID,
    user: User,
) -> tuple[dict[str, Any], bool]:
    _assert_edit(db, case_id, user)
    evidence = db.scalar(
        select(EvidenceFile).where(
            EvidenceFile.id == evidence_file_id,
            EvidenceFile.case_id == case_id,
        )
    )
    if not evidence:
        raise WorkValidationError("Evidence was not found in this case")
    existing = db.scalar(
        select(SharedEvidencePin).where(
            SharedEvidencePin.case_id == case_id,
            SharedEvidencePin.evidence_file_id == evidence_file_id,
        )
    )
    if existing:
        return pin_to_dict(existing), False
    pin = SharedEvidencePin(
        case_id=case_id,
        evidence_file_id=evidence_file_id,
        pinned_by_user_id=user.id,
        legacy_metadata={},
    )
    db.add(pin)
    db.commit()
    db.refresh(pin)
    return pin_to_dict(pin), True


def bulk_pin_evidence(
    db: Session,
    *,
    case_id: UUID,
    evidence_file_ids: list[UUID],
    user: User,
) -> dict[str, Any]:
    _assert_edit(db, case_id, user)
    unique_ids = list(dict.fromkeys(evidence_file_ids))
    if not unique_ids:
        return {"pins": [], "created": 0, "already_pinned": 0}
    if len(unique_ids) > 250:
        raise WorkValidationError("At most 250 evidence items can be pinned at once")
    evidence_rows = db.scalars(
        select(EvidenceFile).where(
            EvidenceFile.case_id == case_id,
            EvidenceFile.id.in_(unique_ids),
        )
    ).all()
    if len(evidence_rows) != len(unique_ids):
        raise WorkValidationError("One or more evidence items were not found in this case")
    existing = {
        pin.evidence_file_id: pin
        for pin in db.scalars(
            select(SharedEvidencePin).where(
                SharedEvidencePin.case_id == case_id,
                SharedEvidencePin.evidence_file_id.in_(unique_ids),
            )
        ).all()
    }
    created = 0
    for evidence_id in unique_ids:
        if evidence_id in existing:
            continue
        pin = SharedEvidencePin(
            case_id=case_id,
            evidence_file_id=evidence_id,
            pinned_by_user_id=user.id,
            legacy_metadata={},
        )
        db.add(pin)
        existing[evidence_id] = pin
        created += 1
    db.commit()
    for pin in existing.values():
        if pin.id is None:
            db.refresh(pin)
    ordered = [existing[evidence_id] for evidence_id in unique_ids]
    return {
        "pins": [pin_to_dict(pin) for pin in ordered],
        "created": created,
        "already_pinned": len(unique_ids) - created,
    }


def unpin_evidence(db: Session, *, case_id: UUID, pin_id: UUID, user: User) -> None:
    _assert_edit(db, case_id, user)
    pin = db.scalar(
        select(SharedEvidencePin).where(
            SharedEvidencePin.id == pin_id,
            SharedEvidencePin.case_id == case_id,
        )
    )
    if not pin:
        raise PinNotFound("Pinned evidence not found")
    db.delete(pin)
    db.commit()


def get_work_view(
    db: Session,
    *,
    case_id: UUID,
    user: User,
    include_tasks: bool = True,
    include_deadlines: bool = True,
    task_status: str | None = None,
    assignee_user_id: UUID | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    _assert_view(db, case_id, user)
    tasks: list[dict[str, Any]] = []
    task_total = 0
    if include_tasks:
        tasks, task_total = list_tasks(
            db,
            case_id=case_id,
            user=user,
            status=task_status,
            assignee_user_id=assignee_user_id,
            limit=limit,
        )
    deadlines: list[dict[str, Any]] = []
    deadline_total = 0
    if include_deadlines:
        deadline_total = int(
            db.scalar(
                select(func.count()).select_from(CaseDeadline).where(
                    CaseDeadline.case_id == case_id
                )
            )
            or 0
        )
        rows = db.scalars(
            select(CaseDeadline)
            .where(CaseDeadline.case_id == case_id)
            .order_by(CaseDeadline.due_date, CaseDeadline.name, CaseDeadline.id)
            .limit(min(max(limit, 1), 250))
        ).all()
        deadlines = [
            {
                "id": str(row.id),
                "case_id": str(row.case_id),
                "name": row.name,
                "due_date": row.due_date.isoformat(),
                "created_by_user_id": str(row.created_by_user_id) if row.created_by_user_id else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]
    return {
        "tasks": tasks,
        "task_total": task_total,
        "deadlines": deadlines,
        "deadline_total": deadline_total,
        "bounded": True,
        "limit": min(max(limit, 1), 250),
    }
