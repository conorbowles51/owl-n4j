from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.case_context import CaseContext, CaseMandateVersion
from postgres.models.case_deadline import CaseDeadline
from postgres.models.case_membership import CaseMembership
from postgres.models.case_profile import CaseProfile
from postgres.models.enums import CaseMembershipRole
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.user import User
from postgres.models.work import CaseTask, SharedEvidencePin
from postgres.models.workspace_attention import WorkspaceAttentionState
from postgres.models.workspace_entry import (
    WorkspaceEntry,
    WorkspaceEntryEvent,
    WorkspaceEntryLink,
)
from services.workspace_attention_service import (
    WorkspaceAttentionValidationError,
    get_workspace_overview,
    set_personal_attention_state,
)


TABLES = [
    User.__table__,
    Case.__table__,
    CaseMembership.__table__,
    CaseDeadline.__table__,
    CaseMandateVersion.__table__,
    CaseContext.__table__,
    EvidenceFolder.__table__,
    EvidenceFile.__table__,
    CaseProfile.__table__,
    WorkspaceEntry.__table__,
    WorkspaceEntryEvent.__table__,
    WorkspaceEntryLink.__table__,
    CaseTask.__table__,
    SharedEvidencePin.__table__,
    WorkspaceAttentionState.__table__,
]


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine, tables=TABLES)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _user(db, name: str) -> User:
    row = User(
        email=f"{name.lower()}@attention.test",
        name=name,
        password_hash="unused",
    )
    db.add(row)
    db.flush()
    return row


def _case_with_members(db):
    owner = _user(db, "owner")
    editor = _user(db, "editor")
    viewer = _user(db, "viewer")
    case = Case(
        title="Attention service case",
        created_by_user_id=owner.id,
        owner_user_id=owner.id,
    )
    db.add(case)
    db.flush()
    for user, role, can_edit in (
        (owner, CaseMembershipRole.owner, True),
        (editor, CaseMembershipRole.collaborator, True),
        (viewer, CaseMembershipRole.collaborator, False),
    ):
        db.add(
            CaseMembership(
                case_id=case.id,
                user_id=user.id,
                membership_role=role,
                permissions={"case": {"view": True, "edit": can_edit}},
                added_by_user_id=owner.id,
            )
        )
    db.commit()
    return case, owner, editor, viewer


def _task(db, case: Case, owner: User, **values) -> CaseTask:
    row = CaseTask(
        case_id=case.id,
        title=values.pop("title", "Task"),
        status=values.pop("status", "todo"),
        priority=values.pop("priority", "standard"),
        created_by_user_id=owner.id,
        updated_by_user_id=owner.id,
        **values,
    )
    db.add(row)
    db.flush()
    return row


def _entry(db, case: Case, owner: User, **values) -> WorkspaceEntry:
    row = WorkspaceEntry(
        case_id=case.id,
        entry_type=values.pop("entry_type", "finding"),
        title=values.pop("title", "Casework"),
        body=values.pop("body", "Material investigator-authored content."),
        lifecycle_state=values.pop("lifecycle_state", "active"),
        significance=values.pop("significance", "medium"),
        review_state=values.pop("review_state", "accepted"),
        author_user_id=values.pop("author_user_id", owner.id),
        author_name=owner.name,
        author_email=owner.email,
        updated_by_user_id=owner.id,
        updated_by_name=owner.name,
        updated_by_email=owner.email,
        **values,
    )
    db.add(row)
    db.flush()
    return row


def _find(items, source_id: UUID | str):
    return next(item for item in items if item["source_id"] == str(source_id))


def test_ranking_is_deterministic_and_respects_boundary_dates_and_ties(db):
    case, owner, editor, _viewer = _case_with_members(db)
    now = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
    db.add_all(
        [
            CaseDeadline(case_id=case.id, name="Overdue", due_date=date(2026, 9, 1)),
            CaseDeadline(case_id=case.id, name="Today", due_date=date(2026, 9, 2)),
            CaseDeadline(case_id=case.id, name="Seven days", due_date=date(2026, 9, 9)),
            CaseDeadline(case_id=case.id, name="Eight days", due_date=date(2026, 9, 10)),
        ]
    )
    first_id = UUID("aaaaaaaa-0000-0000-0000-000000000010")
    second_id = UUID("bbbbbbbb-0000-0000-0000-000000000020")
    _task(
        db,
        case,
        owner,
        id=second_id,
        title="Urgent B",
        priority="urgent",
        due_at=now + timedelta(days=20),
        assignee_user_id=editor.id,
    )
    _task(
        db,
        case,
        owner,
        id=first_id,
        title="Urgent A",
        priority="urgent",
        due_at=now + timedelta(days=20),
        assignee_user_id=editor.id,
    )
    due_now = _task(
        db,
        case,
        owner,
        title="Due at the boundary",
        due_at=now,
        assignee_user_id=editor.id,
    )
    db.commit()

    result = get_workspace_overview(
        db,
        case_id=case.id,
        user=editor,
        timezone_name="Europe/Dublin",
        now=now,
    )
    shared = result["shared_attention"]
    assert [item["priority_band"] for item in shared] == sorted(
        item["priority_band"] for item in shared
    )
    assert _find(shared, due_now.id)["reason_code"] == "task_due_soon"
    assert next(item for item in shared if item["title"] == "Today")["reason_code"] == "deadline_due_soon"
    assert next(item for item in shared if item["title"] == "Seven days")["reason_code"] == "deadline_due_soon"
    assert next(item for item in shared if item["title"] == "Eight days")["reason_code"] == "deadline_upcoming"
    urgent_ids = [
        item["source_id"]
        for item in shared
        if item["title"] in {"Urgent A", "Urgent B"}
    ]
    assert urgent_ids == [str(first_id), str(second_id)]
    assert [item["rank"] for item in shared] == list(range(1, len(shared) + 1))


def test_date_only_deadline_uses_requested_timezone(db):
    case, _owner, _editor, viewer = _case_with_members(db)
    deadline = CaseDeadline(
        case_id=case.id,
        name="Local date boundary",
        due_date=date(2026, 9, 2),
    )
    db.add(deadline)
    db.commit()
    now = datetime(2026, 9, 2, 23, 30, tzinfo=timezone.utc)

    dublin = get_workspace_overview(
        db,
        case_id=case.id,
        user=viewer,
        timezone_name="Europe/Dublin",
        now=now,
    )
    new_york = get_workspace_overview(
        db,
        case_id=case.id,
        user=viewer,
        timezone_name="America/New_York",
        now=now,
    )
    assert _find(dublin["shared_attention"], deadline.id)["reason_code"] == "deadline_overdue"
    assert _find(new_york["shared_attention"], deadline.id)["reason_code"] == "deadline_due_soon"


def test_personal_dismiss_and_snooze_do_not_change_shared_attention(db):
    case, owner, editor, viewer = _case_with_members(db)
    now = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
    task = _task(
        db,
        case,
        owner,
        title="Assigned urgent review",
        priority="urgent",
        assignee_user_id=editor.id,
    )
    db.commit()
    before = get_workspace_overview(db, case_id=case.id, user=editor, now=now)
    personal = _find(before["personal_attention"], task.id)

    set_personal_attention_state(
        db,
        case_id=case.id,
        user=editor,
        attention_key=personal["attention_key"],
        action="dismiss",
        now=now,
    )
    editor_after = get_workspace_overview(db, case_id=case.id, user=editor, now=now)
    viewer_after = get_workspace_overview(db, case_id=case.id, user=viewer, now=now)
    assert all(item["source_id"] != str(task.id) for item in editor_after["personal_attention"])
    assert _find(editor_after["shared_attention"], task.id)
    assert _find(viewer_after["shared_attention"], task.id)
    assert db.get(CaseTask, task.id).status == "todo"

    task.updated_at = now + timedelta(minutes=1)
    db.commit()
    changed = get_workspace_overview(
        db,
        case_id=case.id,
        user=editor,
        now=now + timedelta(minutes=1),
    )
    refreshed = _find(changed["personal_attention"], task.id)
    set_personal_attention_state(
        db,
        case_id=case.id,
        user=editor,
        attention_key=refreshed["attention_key"],
        action="snooze",
        snoozed_until=now + timedelta(days=1),
        now=now,
    )
    snoozed = get_workspace_overview(db, case_id=case.id, user=editor, now=now)
    assert all(item["source_id"] != str(task.id) for item in snoozed["personal_attention"])
    awake = get_workspace_overview(
        db,
        case_id=case.id,
        user=editor,
        now=now + timedelta(days=1, seconds=1),
    )
    assert _find(awake["personal_attention"], task.id)


def test_shared_items_clear_only_when_source_is_resolved(db):
    case, owner, editor, _viewer = _case_with_members(db)
    task = _task(db, case, owner, title="Resolve me", priority="urgent")
    deadline = CaseDeadline(
        case_id=case.id,
        name="Shared only",
        due_date=date(2026, 9, 1),
    )
    db.add(deadline)
    db.commit()
    now = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
    before = get_workspace_overview(db, case_id=case.id, user=editor, now=now)
    assert _find(before["shared_attention"], task.id)
    shared_key = _find(before["shared_attention"], deadline.id)["attention_key"]
    with pytest.raises(WorkspaceAttentionValidationError, match="not a current personal"):
        set_personal_attention_state(
            db,
            case_id=case.id,
            user=editor,
            attention_key=shared_key,
            action="dismiss",
            now=now,
        )
    task.status = "done"
    task.completed_at = now
    db.commit()
    after = get_workspace_overview(db, case_id=case.id, user=editor, now=now)
    assert all(item["source_id"] != str(task.id) for item in after["shared_attention"])


def test_overview_summaries_are_bounded_and_include_review_signals(db):
    case, owner, editor, _viewer = _case_with_members(db)
    context = CaseContext(
        case_id=case.id,
        case_summary="Trace assets across jurisdictions",
        background="A" * 500,
        investigation_type="Asset tracing",
        created_by_user_id=owner.id,
    )
    db.add(context)
    pending = _entry(
        db,
        case,
        owner,
        title="Awaiting review",
        review_state="pending",
    )
    draft = _entry(
        db,
        case,
        editor,
        title="Editor draft",
        lifecycle_state="draft",
        significance="high",
        author_user_id=editor.id,
    )
    for index in range(10):
        db.add(
            CaseProfile(
                case_id=case.id,
                profile_type="person",
                display_name=f"Dossier {index:02d}",
                importance="Material",
                created_by_user_id=owner.id,
            )
        )
        evidence = EvidenceFile(
            case_id=case.id,
            original_filename=f"evidence-{index:02d}.pdf",
            stored_path=f"/fixtures/evidence-{index:02d}.pdf",
            size=100 + index,
            sha256=f"{index:064x}",
            status="processed",
            created_by_id=owner.id,
        )
        db.add(evidence)
        db.flush()
        db.add(
            SharedEvidencePin(
                case_id=case.id,
                evidence_file_id=evidence.id,
                pinned_by_user_id=owner.id,
            )
        )
    db.commit()
    result = get_workspace_overview(
        db,
        case_id=case.id,
        user=editor,
        now=datetime(2026, 9, 2, tzinfo=timezone.utc),
    )
    assert result["bounded"] is True
    assert len(result["dossier_highlights"]) == 4
    assert len(result["pinned_evidence"]) == 6
    assert len(result["recent_casework"]) <= 6
    assert len(result["context"]["background"]) <= 360
    assert _find(result["shared_attention"], pending.id)["reason_code"] == "review_required"
    assert _find(result["personal_attention"], draft.id)["reason_code"] == "personal_draft"
    assert "kind=finding" in _find(result["shared_attention"], pending.id)["href"]


def test_unknown_timezone_is_rejected(db):
    case, _owner, _editor, viewer = _case_with_members(db)
    with pytest.raises(WorkspaceAttentionValidationError, match="Unknown IANA"):
        get_workspace_overview(
            db,
            case_id=case.id,
            user=viewer,
            timezone_name="Mars/Olympus_Mons",
        )
