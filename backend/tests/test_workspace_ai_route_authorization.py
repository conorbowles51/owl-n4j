from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from postgres.session import get_db
from routers import workspace_ai
from routers.users import get_current_db_user


class _QueryResult:
    def __init__(self, value):
        self.value = value

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.value


class _CaseAccessDb:
    def __init__(self, *, can_view: bool, can_edit: bool):
        self.case = SimpleNamespace(id=uuid4())
        self.membership = SimpleNamespace(
            permissions={"case": {"view": can_view, "edit": can_edit}}
        )

    def query(self, model):
        if model.__name__ == "Case":
            return _QueryResult(self.case)
        if model.__name__ == "CaseMembership":
            return _QueryResult(self.membership)
        raise AssertionError(f"Unexpected model query: {model}")

    def rollback(self):
        return None


def _user():
    return SimpleNamespace(
        id=uuid4(),
        email="investigator@example.test",
        name="Investigator",
        global_role="user",
        is_active=True,
    )


def _output(case_id, user_id):
    return {
        "id": str(uuid4()),
        "case_id": str(case_id),
        "target_type": "theory",
        "target_id": str(uuid4()),
        "output_type": "theory_analysis",
        "version": 1,
        "parent_output_id": None,
        "job_status": "queued",
        "review_status": "pending_review",
        "citation_status": "pending",
        "progress": 0,
        "cancel_requested": False,
        "content": {},
        "citations": [],
        "source_set": [],
        "proposed_actions": [],
        "accepted_targets": [],
        "model_metadata": {},
        "error_message": None,
        "rejection_reason": None,
        "mandate_version_id": str(uuid4()),
        "mandate_version_number": 1,
        "requested_by_user_id": str(user_id),
        "requested_by_name": "Investigator",
        "reviewed_by_user_id": None,
        "reviewed_by_name": None,
        "started_at": None,
        "completed_at": None,
        "reviewed_at": None,
        "created_at": "2026-09-02T12:00:00+00:00",
        "updated_at": "2026-09-02T12:00:00+00:00",
    }


def _client(db, user):
    app = FastAPI()
    app.include_router(workspace_ai.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_db_user] = lambda: user
    return TestClient(app)


def test_viewer_can_read_outputs_but_cannot_start_or_review():
    db = _CaseAccessDb(can_view=True, can_edit=False)
    user = _user()
    client = _client(db, user)
    with (
        patch.object(workspace_ai, "list_outputs", return_value={"outputs": [], "total": 0, "limit": 50, "offset": 0}) as read,
        patch.object(workspace_ai, "create_output") as create,
        patch.object(workspace_ai, "accept_output") as accept,
    ):
        read_response = client.get(f"/api/workspace/{db.case.id}/ai-outputs")
        start_response = client.post(
            f"/api/workspace/{db.case.id}/ai-outputs",
            json={"target_type": "theory", "target_id": str(uuid4()), "output_type": "theory_analysis"},
        )
        accept_response = client.post(
            f"/api/workspace/{db.case.id}/ai-outputs/{uuid4()}/accept"
        )
    assert read_response.status_code == 200
    assert start_response.status_code == 403
    assert accept_response.status_code == 403
    read.assert_called_once()
    create.assert_not_called()
    accept.assert_not_called()


def test_editor_can_start_and_review_output():
    db = _CaseAccessDb(can_view=True, can_edit=True)
    user = _user()
    client = _client(db, user)
    result = _output(db.case.id, user.id)
    accepted = {**result, "job_status": "completed", "citation_status": "valid", "review_status": "accepted"}
    with (
        patch.object(workspace_ai, "create_output", return_value=result) as create,
        patch.object(workspace_ai, "run_output_in_background") as background,
        patch.object(workspace_ai, "accept_output", return_value=accepted) as accept,
    ):
        start_response = client.post(
            f"/api/workspace/{db.case.id}/ai-outputs",
            json={"target_type": "theory", "target_id": result["target_id"], "output_type": "theory_analysis"},
        )
        accept_response = client.post(
            f"/api/workspace/{db.case.id}/ai-outputs/{result['id']}/accept"
        )
    assert start_response.status_code == 202
    assert accept_response.status_code == 200
    create.assert_called_once()
    background.assert_called_once()
    accept.assert_called_once()
