"""System logs hold every user's actions across all cases, among them the records of other deletions. Only a super
administrator may clear them, the clear is itself recorded, and only administrators may read them
(followups m110322290610206: any signed-in user could erase every row)."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from postgres.models.enums import GlobalRole
from routers import auth, system_logs, users
from services import system_log_service as sls


@pytest.fixture()
def client_as(monkeypatch):
    calls = {"cleared": 0, "logged": []}

    def clear_logs(**kw):
        calls["cleared"] += 1
        return 7

    monkeypatch.setattr(sls.system_log_service, "clear_logs", clear_logs)
    monkeypatch.setattr(sls.system_log_service, "log", lambda **kw: calls["logged"].append(kw))
    monkeypatch.setattr(sls.system_log_service, "get_log_statistics", lambda: dict(
        total_logs=0, by_type={}, by_origin={}, success_rate=0.0, successful=0, failed=0))

    def make(role):
        user = SimpleNamespace(id=uuid4(), email=f"{role.value}@example.test", global_role=role, is_active=True)
        app = FastAPI()
        app.include_router(system_logs.router)
        app.dependency_overrides[users.get_current_db_user] = lambda: user
        app.dependency_overrides[auth.get_current_user] = lambda: {"username": user.email}
        return TestClient(app), calls

    return make


@pytest.mark.parametrize("role", [GlobalRole.guest, GlobalRole.user, GlobalRole.admin])
def test_only_a_super_admin_clears_the_logs(client_as, role):
    client, calls = client_as(role)
    assert client.delete("/api/system-logs").status_code == 403
    assert calls["cleared"] == 0


def test_a_super_admin_clear_is_recorded(client_as):
    client, calls = client_as(GlobalRole.super_admin)
    response = client.delete("/api/system-logs")
    assert response.status_code == 200
    assert response.json()["rows_removed"] == 7
    assert calls["cleared"] == 1
    [entry] = calls["logged"]
    assert entry["action"] == "System logs cleared"
    assert entry["user"] == "super_admin@example.test"
    assert entry["details"]["rows_removed"] == 7


@pytest.mark.parametrize("path", ["/api/system-logs", "/api/system-logs/statistics"])
def test_reading_the_logs_needs_an_admin(client_as, path):
    client, _ = client_as(GlobalRole.guest)
    assert client.get(path).status_code == 403
    client, _ = client_as(GlobalRole.admin)
    assert client.get(path).status_code != 403
