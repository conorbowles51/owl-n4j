from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from postgres.models.case_context import CaseContext, CaseMandateVersion
from postgres.models.case_deadline import CaseDeadline
from postgres.models.case_profile import CaseProfile
from postgres.models.user import User
from postgres.models.work import CaseTask
from postgres.models.workspace_attention import WorkspaceAttentionState
from postgres.models.workspace_entry import (
    WorkspaceEntry,
    WorkspaceEntryEvent,
    WorkspaceEntryLink,
)
from services.work_service import list_pins


ATTENTION_LIMIT = 12
DUE_SOON_DAYS = 7
MATERIAL_CHANGE_DAYS = 30
MAX_SNOOZE_DAYS = 30

REASON_LABELS = {
    "deadline_overdue": "Deadline overdue",
    "deadline_due_soon": "Deadline due soon",
    "deadline_upcoming": "Upcoming deadline",
    "task_overdue": "Task overdue",
    "task_urgent": "Urgent task",
    "task_due_soon": "Task due soon",
    "task_assigned": "Assigned to you",
    "review_required": "Review required",
    "finding_high_significance": "High-significance finding",
    "theory_material_change": "Material Theory change",
    "contradiction_recorded": "Contradiction recorded",
    "personal_draft": "Your draft",
    "recent_casework_update": "Recent casework update",
}


class WorkspaceAttentionValidationError(ValueError):
    pass


@dataclass(frozen=True)
class AttentionCandidate:
    source_type: str
    source_id: str
    version_token: str
    reason_code: str
    priority_band: int
    sort_value: float
    title: str
    summary: str | None
    occurred_at: datetime | None
    due_at: datetime | None
    href: str
    metadata: dict[str, Any]

    @property
    def attention_key(self) -> str:
        return ":".join(
            (self.source_type, self.source_id, self.reason_code, self.version_token)
        )

    def to_dict(self, *, rank: int) -> dict[str, Any]:
        return {
            "attention_key": self.attention_key,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "reason_code": self.reason_code,
            "reason_label": REASON_LABELS[self.reason_code],
            "rank": rank,
            "priority_band": self.priority_band,
            "title": self.title,
            "summary": self.summary,
            "occurred_at": _iso(self.occurred_at),
            "due_at": _iso(self.due_at),
            "href": self.href,
            "metadata": self.metadata,
        }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    normalized = _aware(value)
    return normalized.isoformat() if normalized else None


def _timestamp(value: datetime | None, *, recent: bool = False) -> float:
    normalized = _aware(value)
    if not normalized:
        return 0 if recent else float("inf")
    stamp = normalized.timestamp()
    return -stamp if recent else stamp


def _version_token(value: datetime | None, fallback: int | str | None = None) -> str:
    if fallback not in (None, ""):
        return str(fallback)
    normalized = _aware(value)
    return str(int(normalized.timestamp() * 1_000_000)) if normalized else "0"


def _short(value: str | None, limit: int = 240) -> str | None:
    if not value:
        return None
    cleaned = " ".join(value.split())
    return cleaned if len(cleaned) <= limit else f"{cleaned[: limit - 1].rstrip()}…"


def _entry_title(entry: WorkspaceEntry) -> str:
    return entry.title or _short(entry.body, 96) or "Untitled casework"


def _timezone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except ZoneInfoNotFoundError as exc:
        raise WorkspaceAttentionValidationError("Unknown IANA timezone") from exc


def _deadline_at(value: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(value, time.min, tzinfo=zone)


def _candidate_sort(candidate: AttentionCandidate) -> tuple[Any, ...]:
    return (
        candidate.priority_band,
        candidate.sort_value,
        candidate.source_type,
        candidate.source_id,
        candidate.reason_code,
    )


def _merge(candidates: list[AttentionCandidate]) -> list[AttentionCandidate]:
    strongest: dict[tuple[str, str], AttentionCandidate] = {}
    for candidate in candidates:
        key = (candidate.source_type, candidate.source_id)
        current = strongest.get(key)
        if current is None or _candidate_sort(candidate) < _candidate_sort(current):
            strongest[key] = candidate
    return sorted(strongest.values(), key=_candidate_sort)


def _task_candidate(
    task: CaseTask,
    *,
    case_id: UUID,
    reason_code: str,
    priority_band: int,
) -> AttentionCandidate:
    due_at = _aware(task.due_at)
    updated_at = _aware(task.updated_at or task.created_at)
    return AttentionCandidate(
        source_type="task",
        source_id=str(task.id),
        version_token=_version_token(updated_at),
        reason_code=reason_code,
        priority_band=priority_band,
        sort_value=_timestamp(due_at or updated_at, recent=priority_band >= 3),
        title=task.title,
        summary=_short(task.description),
        occurred_at=updated_at,
        due_at=due_at,
        href=f"/cases/{case_id}/workspace?view=work&item={task.id}",
        metadata={
            "status": task.status,
            "priority": task.priority,
            "assignee_user_id": (
                str(task.assignee_user_id) if task.assignee_user_id else None
            ),
        },
    )


def _entry_candidate(
    entry: WorkspaceEntry,
    *,
    case_id: UUID,
    reason_code: str,
    priority_band: int,
    occurred_at: datetime | None = None,
    summary: str | None = None,
) -> AttentionCandidate:
    changed_at = _aware(occurred_at or entry.updated_at or entry.created_at)
    return AttentionCandidate(
        source_type=entry.entry_type,
        source_id=str(entry.id),
        version_token=_version_token(changed_at, entry.version),
        reason_code=reason_code,
        priority_band=priority_band,
        sort_value=_timestamp(changed_at, recent=True),
        title=_entry_title(entry),
        summary=_short(summary or entry.body),
        occurred_at=changed_at,
        due_at=None,
        href=(
            f"/cases/{case_id}/workspace?view=casework"
            f"&kind={entry.entry_type}&entry={entry.id}"
        ),
        metadata={
            "entry_type": entry.entry_type,
            "lifecycle_state": entry.lifecycle_state,
            "significance": entry.significance,
            "review_state": entry.review_state,
            "version": entry.version,
        },
    )


def _shared_candidates(
    db: Session,
    *,
    case_id: UUID,
    now: datetime,
    zone: ZoneInfo,
) -> list[AttentionCandidate]:
    candidates: list[AttentionCandidate] = []
    local_today = now.astimezone(zone).date()
    due_soon_date = local_today + timedelta(days=DUE_SOON_DAYS)
    task_due_soon = now + timedelta(days=DUE_SOON_DAYS)

    deadlines = (
        db.query(CaseDeadline)
        .filter(CaseDeadline.case_id == case_id)
        .order_by(CaseDeadline.due_date.asc(), CaseDeadline.id.asc())
        .limit(50)
        .all()
    )
    for deadline in deadlines:
        due_at = _deadline_at(deadline.due_date, zone)
        if deadline.due_date < local_today:
            reason, band = "deadline_overdue", 0
        elif deadline.due_date <= due_soon_date:
            reason, band = "deadline_due_soon", 1
        else:
            reason, band = "deadline_upcoming", 4
        candidates.append(
            AttentionCandidate(
                source_type="deadline",
                source_id=str(deadline.id),
                version_token=_version_token(deadline.updated_at or deadline.created_at),
                reason_code=reason,
                priority_band=band,
                sort_value=_timestamp(due_at),
                title=deadline.name,
                summary=None,
                occurred_at=_aware(deadline.updated_at or deadline.created_at),
                due_at=due_at,
                href=f"/cases/{case_id}/workspace?view=work&item={deadline.id}",
                metadata={"due_date": deadline.due_date.isoformat()},
            )
        )

    active_task = (
        CaseTask.case_id == case_id,
        CaseTask.deleted_at.is_(None),
        CaseTask.status != "done",
    )
    overdue_tasks = (
        db.query(CaseTask)
        .filter(*active_task, CaseTask.due_at < now)
        .order_by(CaseTask.due_at.asc(), CaseTask.id.asc())
        .limit(50)
        .all()
    )
    urgent_tasks = (
        db.query(CaseTask)
        .filter(*active_task, CaseTask.priority == "urgent")
        .order_by(CaseTask.due_at.is_(None), CaseTask.due_at.asc(), CaseTask.id.asc())
        .limit(50)
        .all()
    )
    due_soon_tasks = (
        db.query(CaseTask)
        .filter(
            *active_task,
            CaseTask.due_at >= now,
            CaseTask.due_at <= task_due_soon,
        )
        .order_by(CaseTask.due_at.asc(), CaseTask.id.asc())
        .limit(50)
        .all()
    )
    candidates.extend(
        _task_candidate(task, case_id=case_id, reason_code="task_overdue", priority_band=0)
        for task in overdue_tasks
    )
    candidates.extend(
        _task_candidate(task, case_id=case_id, reason_code="task_urgent", priority_band=0)
        for task in urgent_tasks
    )
    candidates.extend(
        _task_candidate(task, case_id=case_id, reason_code="task_due_soon", priority_band=1)
        for task in due_soon_tasks
    )

    pending_entries = (
        db.query(WorkspaceEntry)
        .filter(
            WorkspaceEntry.case_id == case_id,
            WorkspaceEntry.deleted_at.is_(None),
            or_(
                WorkspaceEntry.review_state == "pending",
                WorkspaceEntry.needs_migration_review.is_(True),
            ),
        )
        .order_by(WorkspaceEntry.updated_at.desc(), WorkspaceEntry.id.asc())
        .limit(25)
        .all()
    )
    candidates.extend(
        _entry_candidate(
            entry,
            case_id=case_id,
            reason_code="review_required",
            priority_band=2,
        )
        for entry in pending_entries
    )

    important_findings = (
        db.query(WorkspaceEntry)
        .filter(
            WorkspaceEntry.case_id == case_id,
            WorkspaceEntry.deleted_at.is_(None),
            WorkspaceEntry.entry_type == "finding",
            WorkspaceEntry.lifecycle_state == "active",
            WorkspaceEntry.significance == "high",
        )
        .order_by(WorkspaceEntry.updated_at.desc(), WorkspaceEntry.id.asc())
        .limit(25)
        .all()
    )
    candidates.extend(
        _entry_candidate(
            entry,
            case_id=case_id,
            reason_code="finding_high_significance",
            priority_band=3,
        )
        for entry in important_findings
    )

    material_cutoff = now - timedelta(days=MATERIAL_CHANGE_DAYS)
    theory_changes = (
        db.query(WorkspaceEntryEvent, WorkspaceEntry)
        .join(WorkspaceEntry, WorkspaceEntry.id == WorkspaceEntryEvent.entry_id)
        .filter(
            WorkspaceEntryEvent.case_id == case_id,
            WorkspaceEntryEvent.created_at >= material_cutoff,
            WorkspaceEntryEvent.event_type.in_(("lifecycle_changed", "confidence_changed", "converted")),
            WorkspaceEntry.entry_type == "theory",
            WorkspaceEntry.deleted_at.is_(None),
        )
        .order_by(WorkspaceEntryEvent.created_at.desc(), WorkspaceEntryEvent.id.asc())
        .limit(50)
        .all()
    )
    candidates.extend(
        _entry_candidate(
            entry,
            case_id=case_id,
            reason_code="theory_material_change",
            priority_band=3,
            occurred_at=event.created_at,
            summary=event.rationale or entry.body,
        )
        for event, entry in theory_changes
    )

    contradictions = (
        db.query(WorkspaceEntryLink, WorkspaceEntry)
        .join(WorkspaceEntry, WorkspaceEntry.id == WorkspaceEntryLink.entry_id)
        .filter(
            WorkspaceEntryLink.case_id == case_id,
            WorkspaceEntryLink.relationship_type == "contradicts",
            WorkspaceEntry.deleted_at.is_(None),
        )
        .order_by(WorkspaceEntryLink.updated_at.desc(), WorkspaceEntryLink.id.asc())
        .limit(25)
        .all()
    )
    candidates.extend(
        _entry_candidate(
            entry,
            case_id=case_id,
            reason_code="contradiction_recorded",
            priority_band=3,
            occurred_at=link.updated_at or link.created_at,
            summary=(
                f"Contradicted by {link.target_label}"
                if link.target_label
                else "Contradicting material is linked to this casework."
            ),
        )
        for link, entry in contradictions
    )

    recent_entries = (
        db.query(WorkspaceEntry)
        .filter(
            WorkspaceEntry.case_id == case_id,
            WorkspaceEntry.deleted_at.is_(None),
            WorkspaceEntry.entry_type.in_(("finding", "theory")),
        )
        .order_by(WorkspaceEntry.updated_at.desc(), WorkspaceEntry.id.asc())
        .limit(12)
        .all()
    )
    candidates.extend(
        _entry_candidate(
            entry,
            case_id=case_id,
            reason_code="recent_casework_update",
            priority_band=4,
        )
        for entry in recent_entries
    )
    return _merge(candidates)


def _personal_candidates(
    db: Session,
    *,
    case_id: UUID,
    user: User,
    now: datetime,
) -> list[AttentionCandidate]:
    candidates: list[AttentionCandidate] = []
    due_soon = now + timedelta(days=DUE_SOON_DAYS)
    assigned = (
        db.query(CaseTask)
        .filter(
            CaseTask.case_id == case_id,
            CaseTask.assignee_user_id == user.id,
            CaseTask.deleted_at.is_(None),
            CaseTask.status != "done",
        )
        .order_by(CaseTask.due_at.is_(None), CaseTask.due_at.asc(), CaseTask.id.asc())
        .limit(100)
        .all()
    )
    for task in assigned:
        due_at = _aware(task.due_at)
        if due_at and due_at < now:
            reason, band = "task_overdue", 0
        elif task.priority == "urgent":
            reason, band = "task_urgent", 0
        elif due_at and due_at <= due_soon:
            reason, band = "task_due_soon", 1
        else:
            reason, band = "task_assigned", 4
        candidates.append(
            _task_candidate(
                task,
                case_id=case_id,
                reason_code=reason,
                priority_band=band,
            )
        )

    drafts = (
        db.query(WorkspaceEntry)
        .filter(
            WorkspaceEntry.case_id == case_id,
            WorkspaceEntry.author_user_id == user.id,
            WorkspaceEntry.deleted_at.is_(None),
            or_(
                (
                    (WorkspaceEntry.entry_type == "finding")
                    & (WorkspaceEntry.lifecycle_state == "draft")
                ),
                (
                    (WorkspaceEntry.entry_type == "theory")
                    & (WorkspaceEntry.lifecycle_state == "proposed")
                ),
                WorkspaceEntry.review_state == "pending",
            ),
        )
        .order_by(WorkspaceEntry.updated_at.desc(), WorkspaceEntry.id.asc())
        .limit(25)
        .all()
    )
    candidates.extend(
        _entry_candidate(
            entry,
            case_id=case_id,
            reason_code="personal_draft",
            priority_band=4,
        )
        for entry in drafts
    )

    awaiting_review = (
        db.query(WorkspaceEntry)
        .filter(
            WorkspaceEntry.case_id == case_id,
            WorkspaceEntry.deleted_at.is_(None),
            WorkspaceEntry.review_state == "pending",
            or_(
                WorkspaceEntry.author_user_id.is_(None),
                WorkspaceEntry.author_user_id != user.id,
            ),
        )
        .order_by(WorkspaceEntry.updated_at.desc(), WorkspaceEntry.id.asc())
        .limit(25)
        .all()
    )
    candidates.extend(
        _entry_candidate(
            entry,
            case_id=case_id,
            reason_code="review_required",
            priority_band=2,
            summary="This casework is awaiting another investigator's review.",
        )
        for entry in awaiting_review
    )
    return _merge(candidates)


def _active_personal_candidates(
    db: Session,
    *,
    case_id: UUID,
    user: User,
    now: datetime,
) -> list[AttentionCandidate]:
    candidates = _personal_candidates(db, case_id=case_id, user=user, now=now)
    if not candidates:
        return []
    keys = [candidate.attention_key for candidate in candidates]
    states = {
        state.attention_key: state
        for state in db.query(WorkspaceAttentionState)
        .filter(
            WorkspaceAttentionState.case_id == case_id,
            WorkspaceAttentionState.user_id == user.id,
            WorkspaceAttentionState.attention_key.in_(keys),
        )
        .all()
    }
    visible: list[AttentionCandidate] = []
    for candidate in candidates:
        state = states.get(candidate.attention_key)
        if not state:
            visible.append(candidate)
            continue
        snoozed_until = _aware(state.snoozed_until)
        if state.dismissed_at is not None or (snoozed_until and snoozed_until > now):
            continue
        visible.append(candidate)
    return visible


def _context_summary(db: Session, case_id: UUID) -> dict[str, Any]:
    context = (
        db.query(CaseContext)
        .options(
            joinedload(CaseContext.active_mandate_version).joinedload(
                CaseMandateVersion.author
            )
        )
        .filter(CaseContext.case_id == case_id)
        .first()
    )
    if not context:
        return {
            "case_summary": None,
            "background": None,
            "investigation_type": None,
            "jurisdiction": None,
            "mandate_complete": False,
            "mandate": None,
            "updated_at": None,
        }
    mandate = context.active_mandate_version
    return {
        "case_summary": context.case_summary,
        "background": _short(context.background, 360),
        "investigation_type": context.investigation_type,
        "jurisdiction": context.jurisdiction,
        "mandate_complete": mandate is not None,
        "mandate": (
            {
                "id": str(mandate.id),
                "version_number": mandate.version_number,
                "objective": _short(mandate.objective, 360),
                "key_questions": (mandate.key_questions or [])[:5],
                "author_name": mandate.author.name if mandate.author else None,
                "created_at": _iso(mandate.created_at),
            }
            if mandate
            else None
        ),
        "updated_at": _iso(context.updated_at),
    }


def _recent_casework(db: Session, case_id: UUID) -> list[dict[str, Any]]:
    rows = (
        db.query(WorkspaceEntry)
        .filter(
            WorkspaceEntry.case_id == case_id,
            WorkspaceEntry.deleted_at.is_(None),
        )
        .order_by(WorkspaceEntry.updated_at.desc(), WorkspaceEntry.id.asc())
        .limit(6)
        .all()
    )
    return [
        {
            "id": str(row.id),
            "entry_type": row.entry_type,
            "title": _entry_title(row),
            "summary": _short(row.body, 180),
            "lifecycle_state": row.lifecycle_state,
            "significance": row.significance,
            "review_state": row.review_state,
            "updated_at": _iso(row.updated_at or row.created_at),
            "href": (
                f"/cases/{case_id}/workspace?view=casework"
                f"&kind={row.entry_type}&entry={row.id}"
            ),
        }
        for row in rows
    ]


def _dossier_highlights(db: Session, case_id: UUID) -> list[dict[str, Any]]:
    rows = (
        db.query(CaseProfile)
        .filter(
            CaseProfile.case_id == case_id,
            CaseProfile.archived_at.is_(None),
            CaseProfile.status != "deleted",
            or_(
                CaseProfile.importance.is_not(None),
                CaseProfile.needs_link_review.is_(True),
            ),
        )
        .order_by(
            CaseProfile.needs_link_review.desc(),
            CaseProfile.updated_at.desc(),
            CaseProfile.id.asc(),
        )
        .limit(4)
        .all()
    )
    return [
        {
            "id": str(row.id),
            "display_name": row.display_name,
            "dossier_type": row.profile_type,
            "summary": _short(row.summary, 180),
            "importance": row.importance,
            "needs_link_review": row.needs_link_review,
            "href": f"/cases/{case_id}/dossiers?dossier={row.id}",
        }
        for row in rows
    ]


def get_workspace_overview(
    db: Session,
    *,
    case_id: UUID,
    user: User,
    timezone_name: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    observed_at = _aware(now) or _now()
    zone = _timezone(timezone_name)
    shared = _shared_candidates(
        db,
        case_id=case_id,
        now=observed_at,
        zone=zone,
    )[:ATTENTION_LIMIT]
    personal = _active_personal_candidates(
        db,
        case_id=case_id,
        user=user,
        now=observed_at,
    )[:ATTENTION_LIMIT]
    pins, _pin_total = list_pins(
        db,
        case_id=case_id,
        user=user,
        limit=6,
        offset=0,
    )
    return {
        "case_id": str(case_id),
        "as_of": observed_at.isoformat(),
        "timezone": zone.key,
        "shared_attention": [
            candidate.to_dict(rank=index + 1)
            for index, candidate in enumerate(shared)
        ],
        "personal_attention": [
            candidate.to_dict(rank=index + 1)
            for index, candidate in enumerate(personal)
        ],
        "context": _context_summary(db, case_id),
        "recent_casework": _recent_casework(db, case_id),
        "dossier_highlights": _dossier_highlights(db, case_id),
        "pinned_evidence": pins,
        "bounded": True,
        "limits": {
            "shared_attention": ATTENTION_LIMIT,
            "personal_attention": ATTENTION_LIMIT,
            "recent_casework": 6,
            "dossier_highlights": 4,
            "pinned_evidence": 6,
        },
    }


def set_personal_attention_state(
    db: Session,
    *,
    case_id: UUID,
    user: User,
    attention_key: str,
    action: str,
    snoozed_until: datetime | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    observed_at = _aware(now) or _now()
    available = {
        candidate.attention_key
        for candidate in _personal_candidates(
            db,
            case_id=case_id,
            user=user,
            now=observed_at,
        )
    }
    if attention_key not in available:
        raise WorkspaceAttentionValidationError(
            "Attention item is not a current personal item for this investigator"
        )
    if action not in {"dismiss", "snooze"}:
        raise WorkspaceAttentionValidationError("Action must be dismiss or snooze")

    state = (
        db.query(WorkspaceAttentionState)
        .filter(
            WorkspaceAttentionState.case_id == case_id,
            WorkspaceAttentionState.user_id == user.id,
            WorkspaceAttentionState.attention_key == attention_key,
        )
        .first()
    )
    if not state:
        state = WorkspaceAttentionState(
            case_id=case_id,
            user_id=user.id,
            attention_key=attention_key,
        )
        db.add(state)
    if action == "dismiss":
        state.dismissed_at = observed_at
        state.snoozed_until = None
    else:
        until = _aware(snoozed_until)
        if not until or until <= observed_at:
            raise WorkspaceAttentionValidationError(
                "snoozed_until must be a future timestamp"
            )
        if until > observed_at + timedelta(days=MAX_SNOOZE_DAYS):
            raise WorkspaceAttentionValidationError(
                f"Attention items may be snoozed for at most {MAX_SNOOZE_DAYS} days"
            )
        state.dismissed_at = None
        state.snoozed_until = until
    db.commit()
    db.refresh(state)
    return {
        "attention_key": state.attention_key,
        "dismissed_at": _iso(state.dismissed_at),
        "snoozed_until": _iso(state.snoozed_until),
    }


def clear_personal_attention_state(
    db: Session,
    *,
    case_id: UUID,
    user: User,
    attention_key: str,
) -> None:
    db.query(WorkspaceAttentionState).filter(
        WorkspaceAttentionState.case_id == case_id,
        WorkspaceAttentionState.user_id == user.id,
        WorkspaceAttentionState.attention_key == attention_key,
    ).delete(synchronize_session=False)
    db.commit()
