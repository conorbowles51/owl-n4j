import unittest
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.user import User
from postgres.models.workspace import WorkspaceNote
from routers import workspace as workspace_router
from services import workspace_service as workspace_service_module
from services.workspace_service import WorkspaceService


WORKSPACE_NOTE_TABLES = [
    User.__table__,
    Case.__table__,
    WorkspaceNote.__table__,
]


class WorkspaceNoteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=WORKSPACE_NOTE_TABLES)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

        self.user_id = uuid.uuid4()
        self.case_id = uuid.uuid4()
        self.other_case_id = uuid.uuid4()
        with self.SessionLocal() as db:
            db.add(
                User(
                    id=self.user_id,
                    email="investigator@example.com",
                    name="Investigator",
                    password_hash="hash",
                )
            )
            db.add_all(
                [
                    Case(
                        id=self.case_id,
                        title="Case One",
                        created_by_user_id=self.user_id,
                        owner_user_id=self.user_id,
                    ),
                    Case(
                        id=self.other_case_id,
                        title="Case Two",
                        created_by_user_id=self.user_id,
                        owner_user_id=self.user_id,
                    ),
                ]
            )
            db.commit()

    def tearDown(self):
        Base.metadata.drop_all(self.engine, tables=WORKSPACE_NOTE_TABLES)
        self.engine.dispose()

    def _session_scope(self):
        @contextmanager
        def scope():
            db = self.SessionLocal()
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        return scope()

    def test_client_note_id_retry_updates_one_note_per_case(self):
        service = WorkspaceService()

        with patch.object(workspace_service_module, "get_background_session", self._session_scope):
            first_id = service.save_note(
                str(self.case_id),
                {
                    "note_id": "note_retry_key",
                    "title": "Witness",
                    "content": "First attempt",
                    "tags": ["interview"],
                },
            )
            retry_id = service.save_note(
                str(self.case_id),
                {
                    "note_id": "note_retry_key",
                    "title": "Witness",
                    "content": "Recovered attempt",
                    "tags": ["interview"],
                },
            )
            other_case_id = service.save_note(
                str(self.other_case_id),
                {
                    "note_id": "note_retry_key",
                    "title": "Other case",
                    "content": "Must remain separate",
                    "tags": [],
                },
            )

        self.assertEqual(first_id, "note_retry_key")
        self.assertEqual(retry_id, "note_retry_key")
        self.assertEqual(other_case_id, "note_retry_key")

        with self.SessionLocal() as db:
            case_rows = db.execute(
                select(WorkspaceNote).where(WorkspaceNote.case_id == self.case_id)
            ).scalars().all()
            other_case_rows = db.execute(
                select(WorkspaceNote).where(WorkspaceNote.case_id == self.other_case_id)
            ).scalars().all()

        self.assertEqual(len(case_rows), 1)
        self.assertEqual(case_rows[0].data["content"], "Recovered attempt")
        self.assertEqual(len(other_case_rows), 1)
        self.assertEqual(other_case_rows[0].data["content"], "Must remain separate")

    async def test_update_note_keeps_path_note_id_when_body_contains_another_id(self):
        saved = {}

        class StubWorkspaceService:
            @staticmethod
            def get_note(case_id, note_id):
                return {
                    "note_id": note_id,
                    "case_id": case_id,
                    "title": "Original",
                    "content": "Original content",
                }

            @staticmethod
            def save_note(case_id, note):
                saved["case_id"] = case_id
                saved["note"] = note
                return note["note_id"]

        with (
            patch.object(workspace_router, "workspace_service", StubWorkspaceService),
            patch.object(workspace_router, "get_case_if_allowed", return_value=object()),
        ):
            result = await workspace_router.update_note(
                case_id=str(self.case_id),
                note_id="note_from_path",
                note=workspace_router.NoteCreate(
                    note_id="note_from_body",
                    title="Updated",
                    content="Updated content",
                ),
                db=SimpleNamespace(),
                current_user=SimpleNamespace(email="investigator@example.com"),
            )

        self.assertEqual(saved["note"]["note_id"], "note_from_path")
        self.assertEqual(result["note_id"], "note_from_path")
        self.assertEqual(result["content"], "Updated content")


if __name__ == "__main__":
    unittest.main()
