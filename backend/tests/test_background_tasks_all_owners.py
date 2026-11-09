"""The Background Tasks admin screen lists every person's tasks; only an administrator may ask for that
(followups m11051807342805: the screen called a route that did not exist)."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from postgres.models.enums import GlobalRole
from postgres.session import get_db
from routers import auth, background_tasks, users


def row(task_id, owner):
    return dict(
        id=task_id, task_type="ingest", task_name="Reading", owner=owner, case_id=None, status="running",
        created_at="2026-11-05T12:00:00", updated_at="2026-11-05T12:00:00", started_at=None, completed_at=None,
        progress={"total": 1, "completed": 0, "failed": 0}, files=[], error=None, metadata={},
    )


@pytest.fixture()
def client_as(monkeypatch):
    seen = []

    def list_tasks(*, owner=None, case_id=None, status=None, limit=100, db=None):
        seen.append(owner)
        return [row("a", "a@example.test"), row("b", "b@example.test")] if owner is None else [row("a", owner)]

    monkeypatch.setattr(background_tasks.background_task_storage, "list_tasks", list_tasks)

    def make(role):
        user = SimpleNamespace(id=uuid4(), email="me@example.test", global_role=role, is_active=True)
        app = FastAPI()
        app.include_router(background_tasks.router)
        app.dependency_overrides[auth.get_current_user] = lambda: {"username": user.email, "email": user.email}
        app.dependency_overrides[get_db] = lambda: SimpleNamespace(rollback=lambda: None)
        monkeypatch.setattr(background_tasks, "get_current_db_user", lambda *_: user)
        return TestClient(app), seen

    return make


@pytest.mark.parametrize("role", [GlobalRole.admin, GlobalRole.super_admin])
def test_an_administrator_sees_every_persons_tasks(client_as, role):
    client, seen = client_as(role)
    response = client.get("/api/background-tasks?all_owners=true")
    assert response.status_code == 200
    assert [t["owner"] for t in response.json()["tasks"]] == ["a@example.test", "b@example.test"]
    assert seen == [None]


@pytest.mark.parametrize("role", [GlobalRole.guest, GlobalRole.user])
def test_nobody_else_may_ask(client_as, role):
    client, seen = client_as(role)
    assert client.get("/api/background-tasks?all_owners=true").status_code == 403
    assert seen == []


def test_the_default_stays_your_own(client_as):
    client, seen = client_as(GlobalRole.user)
    assert client.get("/api/background-tasks").status_code == 200
    assert seen == ["me@example.test"]


def test_running_work_and_its_stop_have_their_own_routes(client_as, monkeypatch):
    """GET /running is not read as a task id; a refused stop answers with its own status and words."""
    from services import running_work
    client, _ = client_as(GlobalRole.user)
    monkeypatch.setattr(running_work, "list_running", lambda db, user: {"scope": "owned_cases", "tasks": [],
                                                                          "stopped": []})

    async def refused(db, user, kind, task_id):
        raise running_work.StopRefused("Only an administrator or this case's owner can stop its work.", 403)
    monkeypatch.setattr(running_work, "stop_work", refused)
    monkeypatch.setattr(background_tasks, "get_current_db_user", lambda *_: SimpleNamespace(id=uuid4()))
    assert client.get("/api/background-tasks/running").json()["scope"] == "owned_cases"
    response = client.post(f"/api/background-tasks/running/processing/{uuid4()}/stop")
    assert response.status_code == 403 and "case's owner" in response.json()["detail"]
