import unittest
from uuid import UUID, uuid4

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.notebook import NotebookNote, NotebookNoteLink
from postgres.models.runtime_state import SystemLog
from postgres.models.user import User
from postgres.models.workspace_entry import (
    WorkspaceEntry,
    WorkspaceEntryEvent,
    WorkspaceEntryLink,
    WorkspaceEntryRevision,
    WorkspaceLegacyMapping,
)
from services.notebook_service import create_note, delete_note, list_notes, update_note


TABLES = [
    User.__table__,
    Case.__table__,
    NotebookNote.__table__,
    NotebookNoteLink.__table__,
    WorkspaceEntry.__table__,
    WorkspaceEntryRevision.__table__,
    WorkspaceEntryLink.__table__,
    WorkspaceEntryEvent.__table__,
    WorkspaceLegacyMapping.__table__,
    SystemLog.__table__,
]


class NotebookCanonicalAdapterTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=TABLES)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.user_id = uuid4()
        self.case_id = uuid4()
        with self.SessionLocal() as db:
            db.add(
                User(
                    id=self.user_id,
                    email="investigator@example.test",
                    name="Investigator",
                    password_hash="hash",
                )
            )
            db.add(
                Case(
                    id=self.case_id,
                    title="Canonical Notebook",
                    created_by_user_id=self.user_id,
                    owner_user_id=self.user_id,
                )
            )
            db.commit()

    def tearDown(self):
        Base.metadata.drop_all(self.engine, tables=reversed(TABLES))
        self.engine.dispose()

    def test_create_update_list_and_delete_use_only_canonical_storage(self):
        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            created = create_note(
                db,
                case_id=self.case_id,
                current_user=user,
                title="Interview",
                body="Henry described the transfer.",
                tags=["interview"],
                links=[
                    {
                        "target_type": "entity",
                        "target_id": "person:henry",
                        "target_label": "Henry",
                        "metadata": {
                            "relationship": "supports",
                            "source_anchor": {"selection": "the transfer"},
                        },
                    }
                ],
            )
            note_id = UUID(created["id"])

            legacy_count = db.scalar(select(func.count()).select_from(NotebookNote))
            canonical = db.get(WorkspaceEntry, note_id)
            mapping = db.scalar(
                select(WorkspaceLegacyMapping).where(
                    WorkspaceLegacyMapping.source_type == "notebook_note",
                    WorkspaceLegacyMapping.source_id == str(note_id),
                )
            )

            updated = update_note(
                db,
                case_id=self.case_id,
                note_id=note_id,
                current_user=user,
                body="Henry described and dated the transfer.",
            )
            listed = list_notes(
                db,
                case_id=self.case_id,
                current_user=user,
                linked_type="entity",
                linked_id="person:henry",
            )
            delete_note(
                db,
                case_id=self.case_id,
                note_id=note_id,
                current_user=user,
            )
            visible_after_delete = list_notes(
                db,
                case_id=self.case_id,
                current_user=user,
            )
            db.refresh(canonical)

        self.assertEqual(legacy_count, 0)
        self.assertIsNotNone(mapping)
        self.assertEqual(canonical.legacy_source, "notebook_note")
        self.assertEqual(updated["body"], "Henry described and dated the transfer.")
        self.assertEqual(updated["links"][0]["target_type"], "entity")
        self.assertEqual(updated["links"][0]["metadata"]["relationship"], "supports")
        self.assertEqual(listed["total"], 1)
        self.assertEqual(visible_after_delete["total"], 0)
        self.assertIsNotNone(canonical.deleted_at)


if __name__ == "__main__":
    unittest.main()
