from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from postgres.models.enums import GlobalRole
from routers import notebook
from services.notebook_service import create_note
from tests.notebook_fixtures import (
    create_test_engine,
    drop_test_engine,
    make_case,
    make_editor_membership,
    make_membership,
    make_user,
    make_viewer_membership,
)


class NotebookPermissionRouterTests(unittest.TestCase):
    def setUp(self):
        self.engine, self.SessionLocal = create_test_engine()
        self.current_user = None

        self.app = FastAPI()
        self.app.include_router(notebook.router)

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[notebook.get_db] = override_get_db
        self.app.dependency_overrides[notebook.get_current_db_user] = lambda: self.current_user
        self.client = TestClient(self.app)

        with self.SessionLocal() as db:
            self.owner = make_user(db, "owner@example.com")
            self.editor = make_user(db, "editor@example.com")
            self.viewer = make_user(db, "viewer@example.com")
            self.no_permission_member = make_user(db, "blocked@example.com")
            self.non_member = make_user(db, "outsider@example.com")
            self.super_admin = make_user(
                db,
                "super.admin@example.com",
                global_role=GlobalRole.super_admin,
            )
            self.case = make_case(db, self.owner, title="Primary Case")
            self.other_case = make_case(db, self.owner, title="Other Case")
            make_editor_membership(db, case=self.case, user=self.editor, added_by=self.owner)
            make_viewer_membership(db, case=self.case, user=self.viewer, added_by=self.owner)
            make_membership(
                db,
                case=self.case,
                user=self.no_permission_member,
                permissions={"case": {"view": False, "edit": False, "delete": False}},
                added_by=self.owner,
            )
            self.note = create_note(
                db,
                case_id=self.case.id,
                current_user=self.owner,
                title="Seed note",
                body="Visible in the primary case only",
                tags=["seed"],
                links=[{"target_type": "entity", "target_id": "person-1"}],
            )
            self.other_note = create_note(
                db,
                case_id=self.other_case.id,
                current_user=self.owner,
                title="Other case note",
                body="Visible in the other case only",
                tags=["other"],
                links=[{"target_type": "entity", "target_id": "person-1"}],
            )

    def tearDown(self):
        self.app.dependency_overrides.clear()
        drop_test_engine(self.engine)

    def _as(self, user):
        self.current_user = user

    def test_non_member_is_denied_for_all_notebook_endpoints(self):
        self._as(self.non_member)

        checks = [
            self.client.get(f"/api/notebook/{self.case.id}/notes"),
            self.client.get(f"/api/notebook/{self.case.id}/targets/entity/person-1/notes"),
            self.client.post(f"/api/notebook/{self.case.id}/notes", json={"body": "No access"}),
            self.client.patch(
                f"/api/notebook/{self.case.id}/notes/{self.note['id']}",
                json={"body": "No access"},
            ),
            self.client.delete(f"/api/notebook/{self.case.id}/notes/{self.note['id']}"),
        ]

        self.assertEqual(
            [response.status_code for response in checks],
            [403, 403, 403, 403, 403],
        )

    def test_viewer_can_list_but_cannot_mutate_notes(self):
        self._as(self.viewer)

        list_response = self.client.get(f"/api/notebook/{self.case.id}/notes")
        target_response = self.client.get(
            f"/api/notebook/{self.case.id}/targets/entity/person-1/notes"
        )
        create_response = self.client.post(
            f"/api/notebook/{self.case.id}/notes",
            json={"body": "Viewer write attempt"},
        )
        update_response = self.client.patch(
            f"/api/notebook/{self.case.id}/notes/{self.note['id']}",
            json={"body": "Viewer update attempt"},
        )
        delete_response = self.client.delete(
            f"/api/notebook/{self.case.id}/notes/{self.note['id']}"
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["total"], 1)
        self.assertEqual(target_response.status_code, 200)
        self.assertEqual(target_response.json()["total"], 1)
        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(update_response.status_code, 403)
        self.assertEqual(delete_response.status_code, 403)

    def test_member_without_case_permissions_is_denied(self):
        self._as(self.no_permission_member)

        list_response = self.client.get(f"/api/notebook/{self.case.id}/notes")
        create_response = self.client.post(
            f"/api/notebook/{self.case.id}/notes",
            json={"body": "Blocked write attempt"},
        )

        self.assertEqual(list_response.status_code, 403)
        self.assertEqual(create_response.status_code, 403)

    def test_editor_can_create_update_and_delete_notes(self):
        self._as(self.editor)

        create_response = self.client.post(
            f"/api/notebook/{self.case.id}/notes",
            json={
                "title": "Editor note",
                "body": "Editor-created content",
                "tags": ["draft", "draft"],
                "links": [
                    {
                        "target_type": "evidence",
                        "target_id": "file-1",
                        "target_label": "Report.pdf",
                    }
                ],
            },
        )
        self.assertEqual(create_response.status_code, 201)
        created = create_response.json()
        self.assertEqual(created["case_id"], str(self.case.id))
        self.assertEqual(created["author_email"], "editor@example.com")
        self.assertEqual(created["tags"], ["draft"])
        self.assertEqual(created["links"][0]["case_id"], str(self.case.id))

        update_response = self.client.patch(
            f"/api/notebook/{self.case.id}/notes/{created['id']}",
            json={
                "title": "Editor note updated",
                "body": "Updated editor content",
                "links": [
                    {
                        "target_type": "entity",
                        "target_id": "person-2",
                    }
                ],
            },
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["body"], "Updated editor content")
        self.assertEqual(update_response.json()["links"][0]["target_id"], "person-2")

        delete_response = self.client.delete(
            f"/api/notebook/{self.case.id}/notes/{created['id']}"
        )
        self.assertEqual(delete_response.status_code, 204)

        list_response = self.client.get(f"/api/notebook/{self.case.id}/notes")
        self.assertEqual([item["id"] for item in list_response.json()["notes"]], [self.note["id"]])

    def test_note_id_from_another_case_is_not_mutated_through_current_case(self):
        self._as(self.owner)

        list_response = self.client.get(f"/api/notebook/{self.case.id}/notes")
        update_response = self.client.patch(
            f"/api/notebook/{self.case.id}/notes/{self.other_note['id']}",
            json={"body": "Wrong case update"},
        )
        delete_response = self.client.delete(
            f"/api/notebook/{self.case.id}/notes/{self.other_note['id']}"
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual([item["id"] for item in list_response.json()["notes"]], [self.note["id"]])
        self.assertEqual(update_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)

    def test_super_admin_can_access_case_without_membership(self):
        self._as(self.super_admin)

        list_response = self.client.get(f"/api/notebook/{self.case.id}/notes")
        create_response = self.client.post(
            f"/api/notebook/{self.case.id}/notes",
            json={"body": "Super-admin note"},
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.json()["author_email"], "super.admin@example.com")


if __name__ == "__main__":
    unittest.main()
