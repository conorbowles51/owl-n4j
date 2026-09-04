import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from postgres.session import get_db
from routers import work, workspace, workspace_overview
from routers.users import get_current_db_user


class _QueryResult:
    def __init__(self, value):
        self.value = value

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.value


class _CaseAccessDb:
    def __init__(self, membership):
        self.case = SimpleNamespace(id=uuid4())
        self.membership = membership

    def query(self, model):
        if model.__name__ == "Case":
            return _QueryResult(self.case)
        if model.__name__ == "CaseMembership":
            return _QueryResult(self.membership)
        raise AssertionError(f"Unexpected model query: {model}")

    def commit(self):
        return None

    def rollback(self):
        return None


class WorkspaceRouteAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(work.router)
        self.app.include_router(workspace_overview.router)
        self.app.include_router(workspace.router)
        self.client = TestClient(self.app)

    def test_view_only_member_cannot_mutate_workspace_context(self):
        current_user = SimpleNamespace(
            id=uuid4(),
            email="viewer@example.test",
            global_role="user",
            is_active=True,
        )
        db = _CaseAccessDb(
            SimpleNamespace(permissions={"case": {"view": True, "edit": False}})
        )
        self.app.dependency_overrides[get_db] = lambda: db
        self.app.dependency_overrides[get_current_db_user] = lambda: current_user

        with patch.object(workspace.mandate_context_service, "update_context") as save:
            response = self.client.put(
                f"/api/workspace/{db.case.id}/context",
                json={"case_summary": "Viewer should not change this"},
            )

        self.assertEqual(response.status_code, 403)
        save.assert_not_called()

    def test_editor_reaches_the_workspace_mutation_handler(self):
        current_user = SimpleNamespace(
            id=uuid4(),
            email="editor@example.test",
            global_role="user",
            is_active=True,
        )
        db = _CaseAccessDb(
            SimpleNamespace(permissions={"case": {"view": True, "edit": True}})
        )
        self.app.dependency_overrides[get_db] = lambda: db
        self.app.dependency_overrides[get_current_db_user] = lambda: current_user

        with (
            patch.object(
                workspace.mandate_context_service,
                "update_context",
                return_value={"case_summary": "Updated context"},
            ) as save,
            patch.object(workspace.system_log_service, "log"),
        ):
            response = self.client.put(
                f"/api/workspace/{db.case.id}/context",
                json={"case_summary": "Updated context"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["case_summary"], "Updated context")
        save.assert_called_once()

    def test_view_only_member_cannot_mutate_canonical_tasks_or_pins(self):
        current_user = SimpleNamespace(
            id=uuid4(),
            email="viewer@example.test",
            global_role="user",
            is_active=True,
        )
        db = _CaseAccessDb(
            SimpleNamespace(permissions={"case": {"view": True, "edit": False}})
        )
        self.app.dependency_overrides[get_db] = lambda: db
        self.app.dependency_overrides[get_current_db_user] = lambda: current_user

        with (
            patch.object(work, "create_task") as create,
            patch.object(work, "pin_evidence") as pin,
        ):
            task_response = self.client.post(
                f"/api/workspace/{db.case.id}/tasks",
                json={"title": "Forbidden task"},
            )
            pin_response = self.client.post(
                f"/api/workspace/{db.case.id}/pinned",
                params={"item_id": str(uuid4())},
            )

        self.assertEqual(task_response.status_code, 403)
        self.assertEqual(pin_response.status_code, 403)
        create.assert_not_called()
        pin.assert_not_called()

    def test_editor_reaches_canonical_task_and_pin_handlers(self):
        current_user = SimpleNamespace(
            id=uuid4(),
            email="editor@example.test",
            global_role="user",
            is_active=True,
        )
        db = _CaseAccessDb(
            SimpleNamespace(permissions={"case": {"view": True, "edit": True}})
        )
        self.app.dependency_overrides[get_db] = lambda: db
        self.app.dependency_overrides[get_current_db_user] = lambda: current_user
        evidence_id = uuid4()

        with (
            patch.object(work, "create_task", return_value={"id": str(uuid4()), "title": "Allowed task"}) as create,
            patch.object(work, "pin_evidence", return_value=({"id": str(uuid4())}, True)) as pin,
        ):
            task_response = self.client.post(
                f"/api/workspace/{db.case.id}/tasks",
                json={"title": "Allowed task"},
            )
            pin_response = self.client.post(
                f"/api/workspace/{db.case.id}/pinned",
                params={"item_id": str(evidence_id)},
            )

        self.assertEqual(task_response.status_code, 200)
        self.assertEqual(pin_response.status_code, 200)
        create.assert_called_once()
        pin.assert_called_once()

    def test_view_member_can_read_overview_and_manage_only_personal_attention(self):
        current_user = SimpleNamespace(
            id=uuid4(),
            email="viewer@example.test",
            global_role="user",
            is_active=True,
        )
        db = _CaseAccessDb(
            SimpleNamespace(permissions={"case": {"view": True, "edit": False}})
        )
        self.app.dependency_overrides[get_db] = lambda: db
        self.app.dependency_overrides[get_current_db_user] = lambda: current_user
        attention_key = f"task:{uuid4()}:task_assigned:1"

        with (
            patch.object(
                workspace_overview,
                "get_workspace_overview",
                return_value={"case_id": str(db.case.id), "shared_attention": [], "personal_attention": []},
            ) as read,
            patch.object(
                workspace_overview,
                "set_personal_attention_state",
                return_value={"attention_key": attention_key, "dismissed_at": "2026-09-02T12:00:00Z"},
            ) as save,
        ):
            overview_response = self.client.get(
                f"/api/workspace/{db.case.id}/overview",
                params={"timezone": "Europe/Dublin"},
            )
            state_response = self.client.put(
                f"/api/workspace/{db.case.id}/attention/{attention_key}",
                json={"action": "dismiss"},
            )

        self.assertEqual(overview_response.status_code, 200)
        self.assertEqual(state_response.status_code, 200)
        read.assert_called_once()
        save.assert_called_once()

    def test_member_without_case_view_cannot_read_or_change_attention(self):
        current_user = SimpleNamespace(
            id=uuid4(),
            email="blocked@example.test",
            global_role="user",
            is_active=True,
        )
        db = _CaseAccessDb(
            SimpleNamespace(permissions={"case": {"view": False, "edit": False}})
        )
        self.app.dependency_overrides[get_db] = lambda: db
        self.app.dependency_overrides[get_current_db_user] = lambda: current_user

        with (
            patch.object(workspace_overview, "get_workspace_overview") as read,
            patch.object(workspace_overview, "set_personal_attention_state") as save,
        ):
            overview_response = self.client.get(
                f"/api/workspace/{db.case.id}/overview"
            )
            state_response = self.client.put(
                f"/api/workspace/{db.case.id}/attention/task:item:task_assigned:1",
                json={"action": "dismiss"},
            )

        self.assertEqual(overview_response.status_code, 403)
        self.assertEqual(state_response.status_code, 403)
        read.assert_not_called()
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
