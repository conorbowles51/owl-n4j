"""
Deadline service - CRUD operations for case deadlines.

Provides deadline management with permission checks via case_service.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from postgres.models.case_deadline import CaseDeadline
from postgres.models.user import User
from services.case_service import check_case_access, CaseNotFound


class DeadlineNotFound(Exception):
    """Raised when a deadline is not found."""
    pass


def list_deadlines(db: Session, case_id: UUID, user: User) -> list[CaseDeadline]:
    """List all deadlines for a case, ordered by due_date asc. Requires case.view."""
    check_case_access(db, case_id, user, required_permission=("case", "view"))

    return (
        db.query(CaseDeadline)
        .filter(CaseDeadline.case_id == case_id)
        .order_by(CaseDeadline.due_date.asc())
        .all()
    )


def create_deadline(
    db: Session,
    case_id: UUID,
    user: User,
    name: str,
    due_date: date,
) -> CaseDeadline:
    """Create a new deadline. Requires case.edit."""
    check_case_access(db, case_id, user, required_permission=("case", "edit"))

    deadline = CaseDeadline(
        case_id=case_id,
        name=name,
        due_date=due_date,
        created_by_user_id=user.id,
    )
    db.add(deadline)
    db.commit()
    db.refresh(deadline)
    return deadline


def update_deadline(
    db: Session,
    deadline_id: UUID,
    case_id: UUID,
    user: User,
    name: str | None = None,
    due_date: date | None = None,
    completed: bool | None = None,
) -> CaseDeadline:
    """Edit, complete or reopen a deadline. Requires case.edit."""
    check_case_access(db, case_id, user, required_permission=("case", "edit"))

    deadline = (
        db.query(CaseDeadline)
        .filter(CaseDeadline.id == deadline_id, CaseDeadline.case_id == case_id)
        .first()
    )
    if not deadline:
        raise DeadlineNotFound(f"Deadline {deadline_id} not found in case {case_id}")

    if name is not None:
        deadline.name = name
    if due_date is not None:
        deadline.due_date = due_date
    if completed is True and deadline.completed_at is None:
        deadline.completed_at = datetime.now(timezone.utc)
    elif completed is False:
        deadline.completed_at = None

    db.commit()
    db.refresh(deadline)
    return deadline


def delete_deadline(db: Session, deadline_id: UUID, case_id: UUID, user: User) -> None:
    """Delete a deadline. Requires case.edit."""
    check_case_access(db, case_id, user, required_permission=("case", "edit"))

    deadline = (
        db.query(CaseDeadline)
        .filter(CaseDeadline.id == deadline_id, CaseDeadline.case_id == case_id)
        .first()
    )
    if not deadline:
        raise DeadlineNotFound(f"Deadline {deadline_id} not found in case {case_id}")

    from postgres.models.work import CaseTask
    from services import removed_records  # Deleted items (lx-deletebin): a kept copy, restorable
    kept = removed_records.keep(db, kind="case_deadline", case_id=case_id, subject_id=deadline.id,
                                label=getattr(deadline, "name", None) or "Deadline", rows=[deadline], user=user)
    # Tasks lose their deadline link with it (ON DELETE SET NULL); a restore links them again.
    kept.data = dict(kept.data, linked_task_ids=[str(t) for (t,) in db.query(CaseTask.id).filter(
        CaseTask.deadline_id == deadline.id)])
    db.delete(deadline)
    db.commit()


def get_next_deadline_for_cases(
    db: Session, case_ids: list[UUID]
) -> dict[UUID, tuple[date, str]]:
    """
    Get the nearest future deadline for each case in a single batched query.

    Returns a dict mapping case_id -> (due_date, name) for cases that have
    a future (or today) deadline. Cases with no upcoming deadlines are omitted.
    """
    if not case_ids:
        return {}

    today = date.today()

    # Subquery: for each case_id, find the minimum due_date >= today
    subq = (
        db.query(
            CaseDeadline.case_id,
            func.min(CaseDeadline.due_date).label("min_date"),
        )
        .filter(
            CaseDeadline.case_id.in_(case_ids),
            CaseDeadline.due_date >= today,
            CaseDeadline.completed_at.is_(None),
        )
        .group_by(CaseDeadline.case_id)
        .subquery()
    )

    # Join back to get the name of the deadline with that min date
    rows = (
        db.query(CaseDeadline.case_id, CaseDeadline.due_date, CaseDeadline.name)
        .join(
            subq,
            (CaseDeadline.case_id == subq.c.case_id)
            & (CaseDeadline.due_date == subq.c.min_date),
        )
        .filter(CaseDeadline.completed_at.is_(None))
        .all()
    )

    # If multiple deadlines share the same min date, take the first one per case
    result: dict[UUID, tuple[date, str]] = {}
    for case_id, due, name in rows:
        if case_id not in result:
            result[case_id] = (due, name)

    return result
