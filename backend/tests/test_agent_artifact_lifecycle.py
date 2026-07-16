import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from postgres.base import Base
from postgres.models.agent import AgentArtifactRecord, AgentRun, AgentThread, AgentToolCall
from postgres.models.case import Case
from postgres.models.user import User
from routers.agent import _raise_case_artifact_http_error
from services.agent import storage
from services.agent.schemas import AgentArtifactRenameRequest
from services.agent.service import agent_service
from services.case_service import CaseAccessDenied


AGENT_ARTIFACT_LIFECYCLE_TABLES = [
    User.__table__,
    Case.__table__,
    AgentThread.__table__,
    AgentRun.__table__,
    AgentToolCall.__table__,
    AgentArtifactRecord.__table__,
]


class AgentArtifactLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine, tables=AGENT_ARTIFACT_LIFECYCLE_TABLES)
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )

        self.owner_id = uuid.uuid4()
        self.member_id = uuid.uuid4()
        self.case_id = uuid.uuid4()
        with self.SessionLocal() as db:
            owner = User(
                id=self.owner_id,
                email="owner@example.com",
                name="Owner",
                password_hash="hash",
            )
            member = User(
                id=self.member_id,
                email="member@example.com",
                name="Member",
                password_hash="hash",
            )
            db.add_all([owner, member])
            db.add(
                Case(
                    id=self.case_id,
                    title="Case",
                    created_by_user_id=self.owner_id,
                    owner_user_id=self.owner_id,
                )
            )
            db.flush()
            thread = storage.create_thread(db, user=owner, case_id=self.case_id, title="Agent thread")
            run = storage.create_run(
                db,
                thread=thread,
                user=owner,
                provider="openai",
                model_id="gpt-5-mini",
                input_message="Build a table",
            )
            approved, draft = storage.persist_artifacts(
                db,
                thread=thread,
                run=run,
                artifacts=[
                    {
                        "type": "table",
                        "title": "Approved payments",
                        "data": {"rows": [{"name": "Acme"}]},
                        "metadata": {"source_result_ids": ["res_doc"]},
                    },
                    {
                        "type": "chart",
                        "title": "Draft chart",
                        "data": {"series": []},
                    },
                ],
            )
            approved.status = storage.ARTIFACT_STATUS_APPROVED
            approved.approved_by_user_id = owner.id
            approved.approved_at = datetime.now(timezone.utc)
            db.commit()
            self.artifact_id = approved.id
            self.draft_artifact_id = draft.id

    def tearDown(self):
        Base.metadata.drop_all(self.engine, tables=list(reversed(AGENT_ARTIFACT_LIFECYCLE_TABLES)))
        self.engine.dispose()

    def test_list_and_open_use_case_scope_without_thread_ownership(self):
        with self.SessionLocal() as db, patch(
            "services.agent.storage.check_case_access",
            return_value=(object(), None),
        ) as access:
            member = db.get(User, self.member_id)
            listed = storage.list_artifacts_for_case(db, case_id=self.case_id, user=member)
            opened = storage.get_artifact_in_case(
                db,
                artifact_id=self.artifact_id,
                case_id=self.case_id,
                user=member,
            )

        self.assertEqual([artifact.id for artifact in listed], [self.artifact_id])
        self.assertEqual(opened.id, self.artifact_id)
        self.assertNotIn(self.draft_artifact_id, [artifact.id for artifact in listed])
        self.assertEqual(access.call_count, 2)
        self.assertEqual(access.call_args_list[0].kwargs["required_permission"], ("case", "view"))
        self.assertEqual(access.call_args_list[1].kwargs["required_permission"], ("case", "view"))

    def test_permission_denied_preserves_view_and_edit_permissions(self):
        with self.SessionLocal() as db, patch(
            "services.agent.storage.check_case_access",
            side_effect=CaseAccessDenied("denied"),
        ) as access:
            member = db.get(User, self.member_id)
            with self.assertRaises(CaseAccessDenied):
                storage.list_artifacts_for_case(db, case_id=self.case_id, user=member)
            self.assertEqual(access.call_args.kwargs["required_permission"], ("case", "view"))

        with self.SessionLocal() as db, patch(
            "services.agent.storage.check_case_access",
            side_effect=CaseAccessDenied("denied"),
        ) as access:
            member = db.get(User, self.member_id)
            with self.assertRaises(CaseAccessDenied):
                storage.rename_artifact_in_case(
                    db,
                    artifact_id=self.artifact_id,
                    case_id=self.case_id,
                    user=member,
                    title="Denied",
                )
            self.assertEqual(access.call_args.kwargs["required_permission"], ("case", "edit"))

    def test_rename_and_update_increment_version_and_enforce_conflict(self):
        with self.SessionLocal() as db, patch(
            "services.agent.storage.check_case_access",
            return_value=(object(), None),
        ):
            member = db.get(User, self.member_id)
            renamed = storage.rename_artifact_in_case(
                db,
                artifact_id=self.artifact_id,
                case_id=self.case_id,
                user=member,
                title="  Reviewed payments  ",
                expected_version=1,
            )
            self.assertEqual(renamed.title, "Reviewed payments")
            self.assertEqual(renamed.version, 2)

            with self.assertRaises(storage.ArtifactConcurrencyError) as raised:
                storage.rename_artifact_in_case(
                    db,
                    artifact_id=self.artifact_id,
                    case_id=self.case_id,
                    user=member,
                    title="Stale title",
                    expected_version=1,
                )
            self.assertEqual(raised.exception.current_version, 2)

            updated = storage.update_artifact_in_case(
                db,
                artifact_id=self.artifact_id,
                case_id=self.case_id,
                user=member,
                artifact={"rows": [{"name": "Beta"}]},
                citations=[{"label": "Ledger", "page": 4}],
                expected_version=2,
            )
            db.commit()

        self.assertEqual(updated.version, 3)
        self.assertEqual(updated.payload, {"rows": [{"name": "Beta"}]})
        self.assertEqual(updated.citations, [{"label": "Ledger", "page": 4}])

    def test_recycle_hides_artifact_and_records_deleter(self):
        with self.SessionLocal() as db, patch(
            "services.agent.storage.check_case_access",
            return_value=(object(), None),
        ):
            member = db.get(User, self.member_id)
            recycled = storage.recycle_artifact_in_case(
                db,
                artifact_id=self.artifact_id,
                case_id=self.case_id,
                user=member,
                expected_version=1,
            )
            db.commit()

        self.assertEqual(recycled.version, 2)
        self.assertIsNotNone(recycled.deleted_at)
        self.assertEqual(recycled.deleted_by_user_id, self.member_id)

        with self.SessionLocal() as db, patch(
            "services.agent.storage.check_case_access",
            return_value=(object(), None),
        ):
            member = db.get(User, self.member_id)
            self.assertEqual(storage.list_artifacts_for_case(db, case_id=self.case_id, user=member), [])
            recycled_list = storage.list_artifacts_for_case(
                db,
                case_id=self.case_id,
                user=member,
                include_deleted=True,
            )
            self.assertEqual([artifact.id for artifact in recycled_list], [self.artifact_id])
            with self.assertRaises(storage.ArtifactNotFoundError):
                storage.get_artifact_in_case(
                    db,
                    artifact_id=self.artifact_id,
                    case_id=self.case_id,
                    user=member,
                )

    def test_service_audits_rename_success_and_failure(self):
        with self.SessionLocal() as db, patch(
            "services.agent.storage.check_case_access",
            return_value=(object(), None),
        ), patch("services.agent.service.system_log_service.log") as audit_log:
            member = db.get(User, self.member_id)
            response = agent_service.rename_case_artifact(
                db=db,
                user=member,
                case_id=self.case_id,
                artifact_id=self.artifact_id,
                request=AgentArtifactRenameRequest(title="Renamed", expected_version=1),
            )
            self.assertEqual(response.artifact.version, 2)

            with self.assertRaises(storage.ArtifactConcurrencyError):
                agent_service.rename_case_artifact(
                    db=db,
                    user=member,
                    case_id=self.case_id,
                    artifact_id=self.artifact_id,
                    request=AgentArtifactRenameRequest(title="Stale", expected_version=1),
                )

        success_call = audit_log.call_args_list[0]
        failure_call = audit_log.call_args_list[-1]
        self.assertEqual(success_call.args[2], "agent_artifact_renamed")
        self.assertTrue(success_call.kwargs["success"])
        self.assertEqual(failure_call.args[2], "agent_artifact_renamed")
        self.assertFalse(failure_call.kwargs["success"])
        self.assertEqual(failure_call.kwargs["error"], "artifact version conflict")

    def test_router_maps_version_conflict_to_409(self):
        with self.assertRaises(HTTPException) as raised:
            _raise_case_artifact_http_error(storage.ArtifactConcurrencyError(current_version=7))

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(
            raised.exception.detail,
            {"message": "artifact version conflict", "current_version": 7},
        )


if __name__ == "__main__":
    unittest.main()
