from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import GlobalRole
from postgres.models.runtime_state import SystemLog
from postgres.models.user import User
from postgres.session import get_db
from routers import cases as cases_router
from routers.cases import CaseUpdateRequest
from routers.users import get_current_db_user
from services.case_service import CaseAccessDenied, update_case


CASE_METADATA_TABLES = [
    User.__table__,
    Case.__table__,
    SystemLog.__table__,
]


class CaseMetadataRequestTests(unittest.TestCase):
    def test_update_request_normalizes_editable_metadata(self):
        request = CaseUpdateRequest.model_validate(
            {
                "title": "  Operation   Lantern  ",
                "description": "   ",
                "status": "on_hold",
            }
        )

        self.assertEqual(request.title, "Operation Lantern")
        self.assertIsNone(request.description)
        self.assertEqual(request.status.value, "on_hold")

    def test_update_request_rejects_empty_or_invalid_metadata(self):
        invalid_payloads = (
            {},
            {"title": "   "},
            {"title": None},
            {"status": "unknown"},
            {"status": None},
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                CaseUpdateRequest.model_validate(payload)


class CaseMetadataRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(cases_router.router)
        self.db = object()
        self.user = SimpleNamespace(
            id=uuid4(),
            email="editor@example.test",
            global_role=GlobalRole.user,
            is_active=True,
        )
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.app.dependency_overrides[get_current_db_user] = lambda: self.user
        self.client = TestClient(self.app)

    def test_patch_returns_complete_updated_metadata(self):
        case_id = uuid4()
        now = datetime.now(timezone.utc)
        updated_case = SimpleNamespace(
            id=case_id,
            title="Operation Beacon",
            description=None,
            status="closed",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
            created_at=now,
            updated_at=now,
            archived=False,
        )

        with patch.object(cases_router, "update_case", return_value=updated_case) as update:
            response = self.client.patch(
                f"/api/cases/{case_id}",
                json={
                    "title": "  Operation   Beacon ",
                    "description": "   ",
                    "status": "closed",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Operation Beacon")
        self.assertIsNone(response.json()["description"])
        self.assertEqual(response.json()["status"], "closed")
        update.assert_called_once_with(
            db=self.db,
            case_id=case_id,
            user=self.user,
            title="Operation Beacon",
            description=None,
            status="closed",
        )

    def test_patch_maps_missing_edit_permission_to_forbidden(self):
        case_id = uuid4()
        with patch.object(
            cases_router,
            "update_case",
            side_effect=CaseAccessDenied("forbidden"),
        ):
            response = self.client.patch(
                f"/api/cases/{case_id}",
                json={"title": "Forbidden change"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"],
            "Access denied - case.edit permission required",
        )

    def test_patch_rejects_an_empty_update_before_calling_the_service(self):
        case_id = uuid4()
        with patch.object(cases_router, "update_case") as update:
            response = self.client.patch(f"/api/cases/{case_id}", json={})

        self.assertEqual(response.status_code, 422)
        update.assert_not_called()


class CaseMetadataServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=CASE_METADATA_TABLES)
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
        )
        self.db = self.SessionLocal()
        self.user = User(
            id=uuid4(),
            email="owner@example.test",
            name="Case Owner",
            password_hash="not-used",
            global_role=GlobalRole.user,
            is_active=True,
        )
        self.case = Case(
            id=uuid4(),
            title="Original title",
            description="Original description",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.db.add_all([self.user, self.case])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine, tables=CASE_METADATA_TABLES)
        self.engine.dispose()

    def test_update_persists_all_metadata_and_an_atomic_audit_record(self):
        with patch(
            "services.case_service.check_case_access",
            return_value=(self.case, None),
        ):
            updated = update_case(
                db=self.db,
                case_id=self.case.id,
                user=self.user,
                title="Operation Lantern",
                description=None,
                status="on_hold",
            )

        self.assertEqual(updated.title, "Operation Lantern")
        self.assertIsNone(updated.description)
        self.assertEqual(updated.status, "on_hold")

        self.db.expire_all()
        persisted = self.db.get(Case, self.case.id)
        self.assertEqual(persisted.title, "Operation Lantern")
        self.assertIsNone(persisted.description)
        self.assertEqual(persisted.status, "on_hold")

        audit = self.db.query(SystemLog).one()
        self.assertEqual(audit.log_type, "case_operation")
        self.assertEqual(audit.action, "Update Case Metadata")
        self.assertEqual(audit.user, self.user.email)
        self.assertEqual(audit.details["case_id"], str(self.case.id))
        self.assertEqual(
            audit.details["changes"],
            {
                "title": {
                    "from": "Original title",
                    "to": "Operation Lantern",
                },
                "description": {
                    "from": "Original description",
                    "to": None,
                },
                "status": {"from": "active", "to": "on_hold"},
            },
        )

    def test_update_denies_without_edit_permission_before_mutating_or_auditing(self):
        with (
            patch(
                "services.case_service.check_case_access",
                side_effect=CaseAccessDenied("forbidden"),
            ),
            patch("services.case_service.system_log_service.log") as log,
            self.assertRaises(CaseAccessDenied),
        ):
            update_case(
                db=self.db,
                case_id=self.case.id,
                user=self.user,
                title="Should not persist",
            )

        self.db.refresh(self.case)
        self.assertEqual(self.case.title, "Original title")
        log.assert_not_called()


if __name__ == "__main__":
    unittest.main()
