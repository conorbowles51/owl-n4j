import uuid
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.user import User
from postgres.models.workspace import WorkspaceFinding
from services.case_service import CaseAccessDenied
from services.workspace_service import FindingVersionConflict, workspace_service
import services.workspace_service as workspace_module
from routers import workspace


WORKSPACE_FINDING_TABLES = [
    User.__table__,
    Case.__table__,
    WorkspaceFinding.__table__,
]


class WorkspaceFindingLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=WORKSPACE_FINDING_TABLES)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.user_id = uuid.uuid4()
        self.case_id = uuid.uuid4()
        self.user = SimpleNamespace(id=self.user_id, email="editor@example.com")

        with self.SessionLocal() as db:
            db.add(
                User(
                    id=self.user_id,
                    email="editor@example.com",
                    name="Editor",
                    password_hash="hash",
                )
            )
            db.add(
                Case(
                    id=self.case_id,
                    title="Case",
                    created_by_user_id=self.user_id,
                    owner_user_id=self.user_id,
                )
            )
            db.commit()

        @contextmanager
        def session_scope():
            db = self.SessionLocal()
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        self.session_patcher = patch.object(workspace_module, "get_background_session", session_scope)
        self.access_patcher = patch.object(workspace_module, "check_case_access", return_value=(None, None))
        self.log_patcher = patch.object(workspace_module.system_log_service, "log")
        self.session_patcher.start()
        self.access_patcher.start()
        self.log = self.log_patcher.start()

    def tearDown(self):
        self.log_patcher.stop()
        self.access_patcher.stop()
        self.session_patcher.stop()
        Base.metadata.drop_all(self.engine, tables=WORKSPACE_FINDING_TABLES)
        self.engine.dispose()

    def test_finding_version_conflict_and_soft_delete(self):
        finding = {"title": "Key finding", "priority": "HIGH"}

        finding_id = workspace_service.save_finding(str(self.case_id), finding, user=self.user)
        self.assertEqual(finding["version"], 1)
        self.assertEqual(finding["finding_id"], finding_id)

        updated = workspace_service.update_finding(
            str(self.case_id),
            finding_id,
            {"title": "Updated finding"},
            user=self.user,
            expected_version=1,
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated["version"], 2)
        self.assertEqual(updated["title"], "Updated finding")

        with self.assertRaises(FindingVersionConflict) as conflict:
            workspace_service.update_finding(
                str(self.case_id),
                finding_id,
                {"title": "Stale overwrite"},
                user=self.user,
                expected_version=1,
            )
        self.assertEqual(conflict.exception.current_version, 2)

        deleted = workspace_service.delete_finding(
            str(self.case_id),
            finding_id,
            user=self.user,
            expected_version=2,
        )
        self.assertTrue(deleted)
        self.assertEqual(workspace_service.get_findings(str(self.case_id), user=self.user), [])

        with self.SessionLocal() as db:
            row = db.scalars(select(WorkspaceFinding)).one()
            self.assertIsNotNone(row.deleted_at)
            self.assertEqual(row.deleted_by_user_id, self.user_id)
            self.assertEqual(row.version, 3)

        log_calls = [call.kwargs for call in self.log.call_args_list]
        self.assertTrue(any(call["action"] == "Create Finding" and call["success"] for call in log_calls))
        self.assertTrue(any(call["action"] == "Update Finding" and call["success"] for call in log_calls))
        self.assertTrue(any(call["action"] == "Update Finding" and not call["success"] for call in log_calls))
        self.assertTrue(any(call["action"] == "Delete Finding" and call["success"] for call in log_calls))

    def test_edit_permission_denial_is_audited(self):
        with patch.object(
            workspace_module,
            "check_case_access",
            side_effect=CaseAccessDenied("User does not have case.edit permission"),
        ):
            with self.assertRaises(CaseAccessDenied):
                workspace_service.save_finding(
                    str(self.case_id),
                    {"title": "Denied"},
                    user=self.user,
                )

        self.assertEqual(self.log.call_args.kwargs["action"], "Create Finding")
        self.assertFalse(self.log.call_args.kwargs["success"])
        self.assertIn("case.edit", self.log.call_args.kwargs["error"])


class WorkspaceFindingRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_update_finding_version_conflict_maps_to_409(self):
        with patch.object(
            workspace.workspace_service,
            "update_finding",
            side_effect=FindingVersionConflict(current_version=4),
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace.update_finding(
                    case_id=str(uuid.uuid4()),
                    finding_id="finding_1",
                    finding=workspace.FindingCreate(title="Finding", expected_version=3),
                    db=object(),
                    current_user=SimpleNamespace(id=uuid.uuid4(), email="editor@example.com"),
                )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["current_version"], 4)

    async def test_create_finding_permission_denial_maps_to_403(self):
        with patch.object(
            workspace.workspace_service,
            "save_finding",
            side_effect=CaseAccessDenied("User does not have case.edit permission"),
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace.create_finding(
                    case_id=str(uuid.uuid4()),
                    finding=workspace.FindingCreate(title="Finding"),
                    db=object(),
                    current_user=SimpleNamespace(id=uuid.uuid4(), email="viewer@example.com"),
                )

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(raised.exception.detail, "Access denied - case.edit permission required")


if __name__ == "__main__":
    unittest.main()
