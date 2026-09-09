from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.case_deadline import CaseDeadline
from postgres.models.case_membership import CaseMembership
from postgres.models.case_profile import CaseProfile
from postgres.models.enums import CaseMembershipRole
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.user import User
from postgres.models.work import CaseTask, CaseTaskLink, SharedEvidencePin
from postgres.models.workspace_entry import WorkspaceEntry
from services.work_service import (
    WorkValidationError,
    bulk_pin_evidence,
    create_task,
    get_task,
    list_pins,
    list_tasks,
    pin_evidence,
    restore_task,
    soft_delete_task,
    unpin_evidence,
    update_task,
)


TABLES = [
    User.__table__,
    Case.__table__,
    CaseMembership.__table__,
    CaseDeadline.__table__,
    EvidenceFolder.__table__,
    EvidenceFile.__table__,
    CaseProfile.__table__,
    WorkspaceEntry.__table__,
    CaseTask.__table__,
    CaseTaskLink.__table__,
    SharedEvidencePin.__table__,
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


def make_user(db, name: str) -> User:
    user = User(
        email=f"{name.lower().replace(' ', '-')}@example.test",
        name=name,
        password_hash="unused",
    )
    db.add(user)
    db.flush()
    return user


def make_case(db):
    owner = make_user(db, "Case Owner")
    editor = make_user(db, "Case Editor")
    viewer = make_user(db, "Case Viewer")
    outsider = make_user(db, "Outsider")
    case = Case(
        title="Work service case",
        created_by_user_id=owner.id,
        owner_user_id=owner.id,
    )
    db.add(case)
    db.flush()
    db.add(
        CaseMembership(
            case_id=case.id,
            user_id=owner.id,
            membership_role=CaseMembershipRole.owner,
            permissions={"case": {"view": True, "edit": True}},
            added_by_user_id=owner.id,
        )
    )
    for user, can_edit in ((editor, True), (viewer, False)):
        db.add(
            CaseMembership(
                case_id=case.id,
                user_id=user.id,
                membership_role=CaseMembershipRole.collaborator,
                permissions={"case": {"view": True, "edit": can_edit}},
                added_by_user_id=owner.id,
            )
        )
    db.commit()
    return case, owner, editor, viewer, outsider


def make_evidence(db, case: Case, owner: User, name: str) -> EvidenceFile:
    evidence = EvidenceFile(
        case_id=case.id,
        original_filename=name,
        stored_path=f"/fixtures/{name}",
        size=123,
        sha256=(name.encode().hex() + "0" * 64)[:64],
        status="processed",
        created_by_id=owner.id,
    )
    db.add(evidence)
    db.commit()
    return evidence


def task_payload(**overrides):
    return {
        "title": "Review transfer records",
        "description": "Check the source statements.",
        "status": "todo",
        "priority": "standard",
        "assignee_user_id": None,
        "due_at": None,
        "parent_task_id": None,
        "deadline_id": None,
        "links": [],
        **overrides,
    }


def test_task_assignment_uses_current_case_member_identity(db):
    case, owner, editor, _viewer, outsider = make_case(db)
    task = create_task(
        db,
        case_id=case.id,
        user=owner,
        data=task_payload(assignee_user_id=editor.id),
    )
    assert task["assignee_user_id"] == str(editor.id)
    assert task["assignee_name"] == "Case Editor"

    editor.name = "Renamed Investigator"
    db.commit()
    refreshed = get_task(db, case_id=case.id, task_id=UUID(task["id"]), user=owner)
    assert refreshed["assignee_user_id"] == str(editor.id)
    assert refreshed["assignee_name"] == "Renamed Investigator"

    with pytest.raises(WorkValidationError, match="current member"):
        create_task(
            db,
            case_id=case.id,
            user=owner,
            data=task_payload(title="Invalid assignment", assignee_user_id=outsider.id),
        )


def test_one_level_subtasks_and_cycles_are_rejected(db):
    case, owner, _editor, _viewer, _outsider = make_case(db)
    parent = create_task(db, case_id=case.id, user=owner, data=task_payload(title="Parent"))
    child = create_task(
        db,
        case_id=case.id,
        user=owner,
        data=task_payload(title="Child", parent_task_id=UUID(parent["id"])),
    )
    with pytest.raises(WorkValidationError, match="one subtask level"):
        create_task(
            db,
            case_id=case.id,
            user=owner,
            data=task_payload(title="Grandchild", parent_task_id=UUID(child["id"])),
        )
    with pytest.raises(WorkValidationError, match="one subtask level|subtasks cannot itself become"):
        update_task(
            db,
            case_id=case.id,
            task_id=UUID(parent["id"]),
            user=owner,
            updates={"parent_task_id": UUID(child["id"])},
        )
    parent_after = get_task(db, case_id=case.id, task_id=UUID(parent["id"]), user=owner)
    assert parent_after["subtask_progress"] == {"done": 0, "total": 1}


def test_task_status_soft_delete_restore_and_deadline_independence(db):
    case, owner, _editor, _viewer, _outsider = make_case(db)
    deadline = CaseDeadline(
        case_id=case.id,
        name="Disclosure",
        due_date=date(2026, 10, 1),
        created_by_user_id=owner.id,
    )
    db.add(deadline)
    db.commit()
    task = create_task(
        db,
        case_id=case.id,
        user=owner,
        data=task_payload(deadline_id=deadline.id),
    )
    done = update_task(
        db,
        case_id=case.id,
        task_id=UUID(task["id"]),
        user=owner,
        updates={"status": "done"},
    )
    assert done["completed_at"] is not None
    db.delete(deadline)
    db.commit()
    assert db.get(CaseTask, UUID(task["id"])).deadline_id is None

    soft_delete_task(db, case_id=case.id, task_id=UUID(task["id"]), user=owner)
    tasks, total = list_tasks(db, case_id=case.id, user=owner)
    assert tasks == [] and total == 0
    restored = restore_task(db, case_id=case.id, task_id=UUID(task["id"]), user=owner)
    assert restored["deleted_at"] is None


def test_task_links_validate_cross_case_targets(db):
    case, owner, _editor, _viewer, _outsider = make_case(db)
    evidence = make_evidence(db, case, owner, "statement.pdf")
    other_owner = make_user(db, "Other Owner")
    other_case = Case(title="Other", created_by_user_id=other_owner.id, owner_user_id=other_owner.id)
    db.add(other_case)
    db.commit()
    other_evidence = make_evidence(db, other_case, other_owner, "other.pdf")

    created = create_task(
        db,
        case_id=case.id,
        user=owner,
        data=task_payload(
            links=[
                {
                    "target_type": "evidence",
                    "target_id": str(evidence.id),
                    "label": evidence.original_filename,
                    "source_anchor": {"page": 2},
                }
            ]
        ),
    )
    assert created["links"][0]["source_anchor"] == {"page": 2}
    with pytest.raises(WorkValidationError, match="not found in this case"):
        create_task(
            db,
            case_id=case.id,
            user=owner,
            data=task_payload(
                title="Cross-case link",
                links=[{"target_type": "evidence", "target_id": str(other_evidence.id)}],
            ),
        )


def test_shared_pins_are_hydrated_idempotent_and_visible_to_every_member(db):
    case, owner, editor, viewer, _outsider = make_case(db)
    first_evidence = make_evidence(db, case, owner, "bank-statement.pdf")
    second_evidence = make_evidence(db, case, owner, "ledger.xlsx")
    first_pin, created = pin_evidence(
        db,
        case_id=case.id,
        evidence_file_id=first_evidence.id,
        user=owner,
    )
    repeated, repeated_created = pin_evidence(
        db,
        case_id=case.id,
        evidence_file_id=first_evidence.id,
        user=editor,
    )
    assert created is True
    assert repeated_created is False
    assert repeated["id"] == first_pin["id"]

    bulk = bulk_pin_evidence(
        db,
        case_id=case.id,
        evidence_file_ids=[first_evidence.id, second_evidence.id, first_evidence.id],
        user=editor,
    )
    assert bulk["created"] == 1
    assert bulk["already_pinned"] == 1
    pins, total = list_pins(db, case_id=case.id, user=viewer, limit=10)
    assert total == 2
    assert {pin["filename"] for pin in pins} == {"bank-statement.pdf", "ledger.xlsx"}
    assert all(pin["sha256"] for pin in pins)

    pin_id = UUID(first_pin["id"])
    unpin_evidence(db, case_id=case.id, pin_id=pin_id, user=editor)
    assert db.scalar(select(SharedEvidencePin).where(SharedEvidencePin.id == pin_id)) is None


def test_viewer_cannot_mutate_tasks_or_pins(db):
    case, owner, _editor, viewer, _outsider = make_case(db)
    evidence = make_evidence(db, case, owner, "view-only.pdf")
    with pytest.raises(Exception):
        create_task(db, case_id=case.id, user=viewer, data=task_payload())
    with pytest.raises(Exception):
        pin_evidence(db, case_id=case.id, evidence_file_id=evidence.id, user=viewer)
