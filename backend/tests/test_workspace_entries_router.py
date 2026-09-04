import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from postgres.session import get_db
from routers import workspace_entries
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

    def rollback(self):
        return None


def _entry_payload(case_id):
    return {
        "id": str(uuid4()),
        "case_id": str(case_id),
        "entry_type": "note",
        "title": None,
        "body": "Review the transfer date.",
        "tags": [],
        "lifecycle_state": None,
        "significance": None,
        "confidence": None,
        "confidence_rationale": None,
        "review_state": "accepted",
        "version": 1,
        "migration_metadata": {},
        "needs_migration_review": False,
        "links": [],
        "revisions": [],
        "events": [],
    }


class WorkspaceEntriesRouterTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(workspace_entries.router)
        self.client = TestClient(self.app)

    def _configure(self, *, can_edit: bool):
        user = SimpleNamespace(
            id=uuid4(),
            email="investigator@example.test",
            name="Investigator",
            global_role="user",
            is_active=True,
        )
        db = _CaseAccessDb(
            SimpleNamespace(
                permissions={"case": {"view": True, "edit": can_edit}}
            )
        )
        self.app.dependency_overrides[get_db] = lambda: db
        self.app.dependency_overrides[get_current_db_user] = lambda: user
        return db, user

    def test_viewer_can_list_but_cannot_create_entries(self):
        db, _ = self._configure(can_edit=False)
        payload = _entry_payload(db.case.id)

        with patch.object(
            workspace_entries, "list_entries", return_value={"entries": [payload], "total": 1}
        ) as list_service:
            read_response = self.client.get(f"/api/workspace/{db.case.id}/entries")

        with patch.object(workspace_entries, "create_entry") as create_service:
            write_response = self.client.post(
                f"/api/workspace/{db.case.id}/entries",
                json={"entry_type": "note", "body": "Viewer write"},
            )

        self.assertEqual(read_response.status_code, 200)
        self.assertEqual(read_response.json()["entries"][0]["body"], payload["body"])
        list_service.assert_called_once()
        self.assertEqual(write_response.status_code, 403)
        create_service.assert_not_called()

    def test_editor_create_contract_includes_typed_fields(self):
        db, _ = self._configure(can_edit=True)
        payload = _entry_payload(db.case.id)
        payload.update(
            {
                "entry_type": "finding",
                "title": "Transfer predates the agreement",
                "lifecycle_state": "draft",
                "significance": "high",
            }
        )

        with patch.object(
            workspace_entries, "create_entry", return_value=payload
        ) as create_service:
            response = self.client.post(
                f"/api/workspace/{db.case.id}/entries",
                json={
                    "entry_type": "finding",
                    "title": "Transfer predates the agreement",
                    "body": "Review the transfer date.",
                    "significance": "high",
                },
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["entry_type"], "finding")
        self.assertEqual(response.json()["significance"], "high")
        create_service.assert_called_once()

    def test_list_forwards_pagination_confidence_and_recent_activity_filters(self):
        db, _ = self._configure(can_edit=False)
        with patch.object(
            workspace_entries,
            "list_entries",
            return_value={"entries": [], "total": 0},
        ) as list_service:
            response = self.client.get(
                f"/api/workspace/{db.case.id}/entries",
                params={
                    "entry_type": "theory",
                    "confidence_min": 30,
                    "confidence_max": 65,
                    "updated_since": "2026-08-01T00:00:00Z",
                    "limit": 25,
                    "offset": 50,
                },
            )

        self.assertEqual(response.status_code, 200)
        kwargs = list_service.call_args.kwargs
        self.assertEqual(kwargs["confidence_min"], 30)
        self.assertEqual(kwargs["confidence_max"], 65)
        self.assertEqual(kwargs["limit"], 25)
        self.assertEqual(kwargs["offset"], 50)
        self.assertEqual(kwargs["updated_since"].isoformat(), "2026-08-01T00:00:00+00:00")

    def test_attachment_lookup_forwards_only_bounded_selected_ids(self):
        db, _ = self._configure(can_edit=False)
        with patch.object(
            workspace_entries,
            "search_attachment_options",
            return_value=[],
        ) as search_service:
            response = self.client.get(
                f"/api/workspace/{db.case.id}/attachment-options",
                params=[
                    ("target_type", "evidence"),
                    ("target_ids", "evidence-1"),
                    ("target_ids", "evidence-2"),
                    ("limit", "2"),
                ],
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            search_service.call_args.kwargs["target_ids"],
            ["evidence-1", "evidence-2"],
        )


if __name__ == "__main__":
    unittest.main()
