"""Persist deadline completion independently of linked task completion."""
from datetime import date, timedelta
from uuid import UUID

import pytest

from postgres.models.case_deadline import CaseDeadline
from services.case_service import CaseAccessDenied
from services.deadline_service import (
    DeadlineNotFound, create_deadline, get_next_deadline_for_cases, update_deadline,
)
from services.work_service import create_task, get_task, get_work_view, list_tasks
from tests.test_work_service import db, make_case, task_payload  # noqa: F401


def test_completion_persists_is_idempotent_and_preserves_linked_tasks(db):
    case, owner, editor, _, _ = make_case(db)
    deadline = create_deadline(db, case.id, owner, "File response", date.today())
    task = create_task(db, case_id=case.id, user=owner, data=task_payload(deadline_id=deadline.id))
    update_deadline(db, deadline.id, case.id, editor, completed=True)
    completed_at = deadline.completed_at
    assert completed_at is not None
    db.expire_all()
    update_deadline(db, deadline.id, case.id, editor, completed=True)
    assert deadline.completed_at == completed_at
    current_task = get_task(db, case_id=case.id, task_id=UUID(task["id"]), user=owner)
    assert current_task["status"] == "todo"
    assert current_task["deadline_id"] == str(deadline.id)
    update_deadline(db, deadline.id, case.id, editor, name="Updated response")
    assert deadline.completed_at == completed_at
    update_deadline(db, deadline.id, case.id, editor, completed=False)
    db.expire_all()
    assert deadline.completed_at is None


def test_completion_obeys_case_permissions_and_case_scope(db):
    case, owner, _, viewer, outsider = make_case(db)
    deadline = create_deadline(db, case.id, owner, "File response", date.today())
    for user in (viewer, outsider):
        with pytest.raises(CaseAccessDenied):
            update_deadline(db, deadline.id, case.id, user, completed=True)
    from uuid import uuid4
    with pytest.raises(DeadlineNotFound):
        update_deadline(db, uuid4(), case.id, owner, completed=True)
    assert deadline.completed_at is None


def test_completed_dates_are_excluded_from_case_picker_including_same_day_ties(db):
    case, owner, _, _, _ = make_case(db)
    first = create_deadline(db, case.id, owner, "Completed first", date.today())
    second = create_deadline(db, case.id, owner, "Still open", date.today())
    update_deadline(db, first.id, case.id, owner, completed=True)
    assert get_next_deadline_for_cases(db, [case.id])[case.id] == (date.today(), "Still open")
    update_deadline(db, second.id, case.id, owner, completed=True)
    assert case.id not in get_next_deadline_for_cases(db, [case.id])
    update_deadline(db, first.id, case.id, owner, completed=False)
    assert get_next_deadline_for_cases(db, [case.id])[case.id][1] == "Completed first"


def test_work_filters_and_pagination_count_open_and_completed_deadlines(db):
    case, owner, _, _, _ = make_case(db)
    first = create_deadline(db, case.id, owner, "Completed", date.today() - timedelta(days=10))
    second = create_deadline(db, case.id, owner, "Open", date.today())
    update_deadline(db, first.id, case.id, owner, completed=True)
    work = get_work_view(db, case_id=case.id, user=owner, limit=1)
    assert work["deadline_total"] == 2
    assert work["deadlines"][0]["id"] == str(second.id)
    done = get_work_view(db, case_id=case.id, user=owner, task_status="done")
    assert done["deadline_total"] == 1
    assert done["deadlines"][0]["completed_at"]
    todo = get_work_view(db, case_id=case.id, user=owner, task_status="todo")
    assert todo["deadline_total"] == 1
    assert todo["deadlines"][0]["id"] == str(second.id)
    assert get_work_view(db, case_id=case.id, user=owner, task_status="in_progress")["deadlines"] == []


def test_parent_choices_search_all_open_top_level_tasks_independent_of_work_filters(db):
    case, owner, editor, _, _ = make_case(db)
    parent = create_task(db, case_id=case.id, user=owner, data=task_payload(title="Review 100% sources", assignee_user_id=editor.id))
    create_task(db, case_id=case.id, user=owner, data=task_payload(title="Review child", parent_task_id=UUID(parent["id"])))
    create_task(db, case_id=case.id, user=owner, data=task_payload(title="Review completed", status="done"))
    rows, total = list_tasks(db, case_id=case.id, user=owner, parent_candidates=True, search="100%")
    assert total == 1
    assert rows[0]["id"] == parent["id"]
    rows, total = list_tasks(db, case_id=case.id, user=owner, parent_candidates=True, limit=1, offset=1)
    assert total == 1
    assert rows == []


def test_migration_retains_existing_dates_and_refuses_lossy_downgrade():
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, text
    path = Path(__file__).parents[1] / "postgres/alembic/versions/20261110_deadline_completion.py"
    spec = importlib.util.spec_from_file_location("deadline_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE case_deadlines (id text PRIMARY KEY, due_date date)"))
        connection.execute(text("INSERT INTO case_deadlines VALUES ('existing', '2026-11-10')"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert connection.execute(text("SELECT due_date, completed_at FROM case_deadlines")).one() == ("2026-11-10", None)
        connection.execute(text("UPDATE case_deadlines SET completed_at = '2026-11-10T12:00:00'"))
        with Operations.context(MigrationContext.configure(connection)), pytest.raises(RuntimeError, match="Completed deadlines"):
            migration.downgrade()
    engine.dispose()
