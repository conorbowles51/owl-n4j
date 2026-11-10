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
from postgres.models.dossier import DossierInterview
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
    DossierInterview.__table__,
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


def test_completed_deadlines_leave_attention_and_upcoming_work_until_reopened(db):
    case, owner, editor, _viewer = _case_with_members(db)
    now = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    overdue = CaseDeadline(case_id=case.id, name="Filed yesterday", due_date=date(2026, 11, 9), completed_at=now)
    upcoming = CaseDeadline(case_id=case.id, name="Filed early", due_date=date(2026, 11, 11), completed_at=now)
    db.add_all([overdue, upcoming])
    db.commit()
    overview = get_workspace_overview(db, case_id=case.id, user=editor, now=now)
    assert not any(item["source_type"] == "deadline" for item in overview["shared_attention"])
    assert overview["upcoming_work"]["deadlines"] == []
    assert overview["upcoming_work"]["past_deadline_total"] == 0
    from services.deadline_service import update_deadline
    update_deadline(db, upcoming.id, case.id, owner, completed=False)
    reopened = get_workspace_overview(db, case_id=case.id, user=editor, now=now)
    assert reopened["upcoming_work"]["upcoming_deadline_total"] == 1
    assert _find(reopened["shared_attention"], upcoming.id)["reason_code"] == "deadline_due_soon"


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


def test_overview_lists_the_cases_interviews_newest_first_with_true_total(db):
    case, owner, _editor, viewer = _case_with_members(db)
    witness = CaseProfile(case_id=case.id, profile_type="person", display_name="Witness A")
    gone = CaseProfile(case_id=case.id, profile_type="person", display_name="Archived B", archived_at=datetime(2026, 9, 1, tzinfo=timezone.utc))
    db.add_all([witness, gone])
    db.flush()
    for day in range(1, 9):
        db.add(DossierInterview(
            dossier_id=witness.id, case_id=case.id, status="completed",
            interview_date=datetime(2026, 8, day, tzinfo=timezone.utc),
            participants=["Witness A", {"name": "Det. Ruiz", "role": "interviewed_by"}],
            working_notes=f"Statement {day}",
        ))
    db.add(DossierInterview(dossier_id=gone.id, case_id=case.id, status="planned", participants=[]))
    db.commit()

    result = get_workspace_overview(db, case_id=case.id, user=viewer)

    assert result["interview_total"] == 8
    assert len(result["interviews"]) == 6
    first = result["interviews"][0]
    assert first["summary"] == "Statement 8"
    assert first["dossier_name"] == "Witness A"
    assert {"name": "Det. Ruiz", "role": "interviewed_by"} in first["participants"]
    assert first["href"] == f"/cases/{case.id}/dossiers?dossier={witness.id}"


def test_overview_puts_each_casework_kind_and_the_next_work_in_its_own_section(db):
    case, owner, _editor, viewer = _case_with_members(db)
    now = datetime(2026, 9, 2, 12, tzinfo=timezone.utc)
    for index in range(8):
        db.add(WorkspaceEntry(case_id=case.id, entry_type="note", body=f"Note {index}", author_user_id=owner.id,
                              updated_at=now - timedelta(minutes=index)))
    db.add(WorkspaceEntry(case_id=case.id, entry_type="finding", title="Control kept", body="Finding body",
                          author_user_id=owner.id, updated_at=now - timedelta(days=30)))
    db.add(WorkspaceEntry(case_id=case.id, entry_type="theory", title="Gone", body="Deleted theory",
                          author_user_id=owner.id, deleted_at=now))
    db.add_all([
        CaseDeadline(case_id=case.id, name="Last month", due_date=date(2026, 8, 1)),
        CaseDeadline(case_id=case.id, name="Tomorrow", due_date=date(2026, 9, 3)),
        CaseDeadline(case_id=case.id, name="Today", due_date=date(2026, 9, 2)),
    ])
    _task(db, case, owner, title="Open, no date")
    _task(db, case, owner, title="Open, dated", due_at=now + timedelta(days=2), assignee_user_id=viewer.id)
    _task(db, case, owner, title="Finished", status="done")
    db.commit()

    result = get_workspace_overview(db, case_id=case.id, user=viewer, now=now, timezone_name="UTC")

    sections = result["casework_by_type"]
    # The finding is older than six notes, so the mixed recent list leaves it out; its own section keeps it.
    assert all(item["entry_type"] == "note" for item in result["recent_casework"])
    assert [item["title"] for item in sections["finding"]["entries"]] == ["Control kept"]
    assert sections["finding"]["total"] == 1
    assert sections["theory"] == {"entries": [], "total": 0}
    assert len(sections["note"]["entries"]) == 6 and sections["note"]["total"] == 8

    work = result["upcoming_work"]
    assert [item["name"] for item in work["deadlines"]] == ["Today", "Tomorrow"]
    assert work["upcoming_deadline_total"] == 2 and work["past_deadline_total"] == 1
    assert [item["title"] for item in work["tasks"]] == ["Open, dated", "Open, no date"]
    assert work["tasks"][0]["assignee_name"] == "viewer"
    assert work["open_task_total"] == 2
