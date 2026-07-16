import unittest
import uuid
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from postgres.base import Base
from postgres.models.agent import AgentArtifactRecord, AgentRun, AgentThread, AgentToolCall
from postgres.models.case import Case
from postgres.models.user import User
from services.agent import storage
from services.case_service import CaseAccessDenied


AGENT_ARTIFACT_TABLES = [
    User.__table__,
    Case.__table__,
    AgentThread.__table__,
    AgentRun.__table__,
    AgentToolCall.__table__,
    AgentArtifactRecord.__table__,
]


class AgentArtifactApprovalTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine, tables=AGENT_ARTIFACT_TABLES)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

        self.user_id = uuid.uuid4()
        self.case_id = uuid.uuid4()
        with self.SessionLocal() as db:
            user = User(
                id=self.user_id,
                email="investigator@example.com",
                name="Investigator",
                password_hash="hash",
            )
            db.add(user)
            db.add(
                Case(
                    id=self.case_id,
                    title="Case",
                    created_by_user_id=self.user_id,
                    owner_user_id=self.user_id,
                )
            )
            db.flush()
            thread = storage.create_thread(db, user=user, case_id=self.case_id, title="Agent thread")
            run = storage.create_run(
                db,
                thread=thread,
                user=user,
                provider="openai",
                model_id="gpt-5-mini",
                input_message="Build a table",
            )
            storage.persist_tool_trace(
                db,
                run=run,
                trace=[
                    {
                        "name": "search_documents",
                        "status": "success",
                        "duration_ms": 42,
                        "result_id": "res_doc",
                        "summary": "Found one document.",
                    }
                ],
            )
            artifact = storage.persist_artifacts(
                db,
                thread=thread,
                run=run,
                artifacts=[
                    {
                        "type": "table",
                        "title": "Payments",
                        "data": {"columns": [{"key": "name"}], "rows": [{"name": "Acme"}]},
                        "metadata": {
                            "source_result_ids": ["res_doc"],
                            "citations": [{"label": "Bank statement", "page": 2}],
                        },
                    }
                ],
            )[0]
            db.commit()
            self.artifact_id = artifact.id
            self.run_id = run.id

    def tearDown(self):
        Base.metadata.drop_all(self.engine, tables=list(reversed(AGENT_ARTIFACT_TABLES)))
        self.engine.dispose()

    def test_generated_artifact_starts_draft_and_can_be_approved_with_provenance(self):
        with self.SessionLocal() as db:
            artifact = db.get(AgentArtifactRecord, self.artifact_id)
            self.assertEqual(artifact.status, "draft")
            self.assertEqual(artifact.version, 1)
            self.assertIn({"label": "Bank statement", "page": 2}, artifact.citations)
            self.assertIn({"type": "tool_result", "result_id": "res_doc"}, artifact.citations)

        with self.SessionLocal() as db, patch(
            "services.agent.storage.check_case_access",
            return_value=(object(), None),
        ) as access:
            user = db.get(User, self.user_id)
            approved = storage.approve_artifact(db, artifact_id=self.artifact_id, user=user)
            body = storage.to_api_artifact(approved).model_dump(mode="json")
            db.commit()

        self.assertEqual(body["status"], "approved")
        self.assertEqual(body["version"], 1)
        self.assertEqual(body["approved_by_user_id"], str(self.user_id))
        self.assertIsNotNone(body["approved_at"])
        self.assertEqual(body["provenance"]["creator_user_id"], str(self.user_id))
        self.assertEqual(body["provenance"]["model_id"], "gpt-5-mini")
        self.assertEqual(body["provenance"]["run_id"], str(self.run_id))
        self.assertEqual(body["provenance"]["tool_calls"][0]["name"], "search_documents")
        self.assertIn({"label": "Bank statement", "page": 2}, body["citations"])
        self.assertEqual(access.call_args.kwargs["required_permission"], ("case", "edit"))

        with self.SessionLocal() as db:
            artifact = db.get(AgentArtifactRecord, self.artifact_id)
            self.assertEqual(artifact.status, "approved")
            self.assertEqual(artifact.approved_by_user_id, self.user_id)

    def test_approval_requires_case_edit_permission(self):
        with self.SessionLocal() as db, patch(
            "services.agent.storage.check_case_access",
            side_effect=CaseAccessDenied("denied"),
        ):
            user = db.get(User, self.user_id)
            with self.assertRaises(CaseAccessDenied):
                storage.approve_artifact(db, artifact_id=self.artifact_id, user=user)
            db.rollback()

        with self.SessionLocal() as db:
            artifact = db.get(AgentArtifactRecord, self.artifact_id)
            self.assertEqual(artifact.status, "draft")
            self.assertIsNone(artifact.approved_by_user_id)
            self.assertIsNone(artifact.approved_at)


if __name__ == "__main__":
    unittest.main()
