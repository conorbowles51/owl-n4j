import unittest
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.agent import (
    AgentArtifactRecord,
    AgentMessage,
    AgentRun,
    AgentThread,
    AgentToolCall,
    SavedAgentArtifact,
)
from postgres.models.case import Case
from postgres.models.case_membership import CaseMembership
from postgres.models.enums import CaseMembershipRole, GlobalRole
from postgres.models.user import User
from postgres.permissions import EDITOR_PERMISSIONS, VIEWER_PERMISSIONS, clone_permissions
from services.agent import storage
from services.agent.exports import render_artifact_export
from services.agent.schemas import SaveAgentArtifactRequest
from services.case_service import CaseAccessDenied


class AgentSavedArtifactTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

        @event.listens_for(self.engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(
            self.engine,
            tables=[
                User.__table__,
                Case.__table__,
                CaseMembership.__table__,
                AgentThread.__table__,
                AgentRun.__table__,
                AgentMessage.__table__,
                AgentToolCall.__table__,
                AgentArtifactRecord.__table__,
                SavedAgentArtifact.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )

        with self.SessionLocal() as db:
            self.editor = self._user("editor@example.com")
            self.viewer = self._user("viewer@example.com")
            self.other_editor = self._user("other-editor@example.com")
            self.outsider = self._user("outsider@example.com")
            db.add_all([self.editor, self.viewer, self.other_editor, self.outsider])
            db.flush()

            self.case = Case(
                title="Saved artifact case",
                created_by_user_id=self.editor.id,
                owner_user_id=self.editor.id,
            )
            db.add(self.case)
            db.flush()
            db.add_all(
                [
                    self._membership(self.editor, EDITOR_PERMISSIONS),
                    self._membership(self.other_editor, EDITOR_PERMISSIONS),
                    self._membership(self.viewer, VIEWER_PERMISSIONS),
                ]
            )
            db.flush()
            self.editor_artifact_id = self._create_artifact(db, self.editor, title="Payments table")
            self.viewer_artifact_id = self._create_artifact(db, self.viewer, title="Viewer table")
            db.commit()

    def tearDown(self):
        self.engine.dispose()

    def _user(self, email: str) -> User:
        return User(
            email=email,
            name=email.split("@")[0],
            password_hash="hash",
            global_role=GlobalRole.user,
        )

    def _membership(self, user: User, permissions: dict) -> CaseMembership:
        return CaseMembership(
            case_id=self.case.id,
            user_id=user.id,
            membership_role=CaseMembershipRole.collaborator,
            permissions=clone_permissions(permissions),
            added_by_user_id=self.editor.id,
        )

    def _create_artifact(self, db, user: User, *, title: str):
        thread = AgentThread(
            case_id=self.case.id,
            owner_user_id=user.id,
            title=f"{title} thread",
            status="active",
        )
        db.add(thread)
        db.flush()
        run = AgentRun(
            thread_id=thread.id,
            case_id=self.case.id,
            user_id=user.id,
            status="completed",
            provider="openai",
            model_id="gpt-5-mini",
            input_message="Build a payments table",
            final_answer="Built a payments table.",
        )
        db.add(run)
        db.flush()
        db.add(
            AgentToolCall(
                run_id=run.id,
                sequence_number=1,
                name="build_table_artifact",
                arguments={"reason": "payments"},
                status="success",
                duration_ms=25,
                result_id="res_1",
                summary="Built payments table",
            )
        )
        artifact = AgentArtifactRecord(
            thread_id=thread.id,
            run_id=run.id,
            type="table",
            title=title,
            payload={
                "columns": [{"key": "person"}, {"key": "amount"}],
                "rows": [{"person": "Daniel Rook", "amount": 145000}],
            },
            extra_metadata={"source_result_ids": ["res_1"]},
        )
        db.add(artifact)
        db.flush()
        return artifact.id

    def _save(self, db, *, artifact_id=None, user=None, title="Case payments", destination="workspace"):
        request = SaveAgentArtifactRequest(
            destination=destination,
            title=title,
            note="Use in the report memo",
        )
        saved = storage.save_artifact_for_user(
            db=db,
            user=user or self.editor,
            artifact_id=artifact_id or self.editor_artifact_id,
            destination=request.destination,
            title=request.title,
            note=request.note,
        )
        db.commit()
        db.refresh(saved)
        return storage.to_api_saved_artifact(saved)

    def test_save_lists_and_exports_snapshot(self):
        with self.SessionLocal() as db:
            saved = self._save(db)
            listed = storage.list_saved_artifacts(db=db, user=self.viewer, case_id=self.case.id)

            self.assertEqual(saved.title, "Case payments")
            self.assertEqual(saved.destination, "workspace")
            self.assertEqual(saved.artifact.data["rows"][0]["person"], "Daniel Rook")
            self.assertEqual(saved.provenance["run"]["model_id"], "gpt-5-mini")
            self.assertEqual(saved.provenance["tool_trace"][0]["name"], "build_table_artifact")
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0].id, saved.id)

            saved_record = storage.get_saved_artifact_for_user(
                db=db,
                user=self.viewer,
                saved_artifact_id=UUID(saved.id),
            )
            exported = render_artifact_export(
                artifact_type=saved_record.artifact_type,
                title=saved_record.title,
                payload=saved_record.artifact_payload or {},
                export_format="csv",
            )
            self.assertIn(b"Daniel Rook", exported.content)

    def test_save_requires_case_edit(self):
        with self.SessionLocal() as db:
            with self.assertRaises(CaseAccessDenied):
                self._save(db, artifact_id=self.viewer_artifact_id, user=self.viewer)

    def test_save_rejects_no_membership_missing_artifact_and_cross_user_source(self):
        with self.SessionLocal() as db:
            with self.assertRaises(CaseAccessDenied):
                self._save(db, user=self.outsider)

            with self.assertRaises(ValueError):
                self._save(db, artifact_id=uuid4(), user=self.editor)

            with self.assertRaises(PermissionError):
                self._save(db, user=self.other_editor)

    def test_empty_list_and_duplicate_save_allowed(self):
        with self.SessionLocal() as db:
            self.assertEqual(
                storage.list_saved_artifacts(db=db, user=self.viewer, case_id=self.case.id),
                [],
            )

            first = self._save(db, title="Case payments")
            second = self._save(db, title="Case payments")
            listed = storage.list_saved_artifacts(db=db, user=self.viewer, case_id=self.case.id)

            self.assertNotEqual(first.id, second.id)
            self.assertEqual(len(listed), 2)

    def test_saved_snapshot_survives_source_thread_delete(self):
        with self.SessionLocal() as db:
            saved = self._save(db)
            saved_id = UUID(saved.id)
            source_thread_id = UUID(saved.source_thread_id)

            thread = db.query(AgentThread).filter(AgentThread.id == source_thread_id).one()
            db.delete(thread)
            db.commit()

            durable_record = storage.get_saved_artifact_for_user(
                db=db,
                user=self.viewer,
                saved_artifact_id=saved_id,
            )
            durable = storage.to_api_saved_artifact(durable_record)

            self.assertIsNone(durable.source_thread_id)
            self.assertIsNone(durable.source_run_id)
            self.assertIsNone(durable.source_artifact_id)
            self.assertEqual(durable.artifact.data["rows"][0]["amount"], 145000)
            self.assertEqual(durable.provenance["source"]["thread_id"], str(source_thread_id))

    def test_validation_rejects_blank_title_and_bad_destination(self):
        with self.assertRaises(ValidationError):
            SaveAgentArtifactRequest(destination="workspace", title="   ")
        with self.assertRaises(ValidationError):
            SaveAgentArtifactRequest(destination="archive", title="Case payments")


if __name__ == "__main__":
    unittest.main()
