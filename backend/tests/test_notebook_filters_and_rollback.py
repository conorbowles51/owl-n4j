from __future__ import annotations

import unittest
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from postgres import session as postgres_session
from postgres.models.notebook import NotebookNote, NotebookNoteLink
from postgres.models.runtime_state import SystemLog
from routers import notebook
from services.notebook_service import create_note, list_notes
from tests.notebook_fixtures import (
    create_test_engine,
    drop_test_engine,
    make_case,
    make_editor_membership,
    make_user,
)


class FailingCommitSession(Session):
    fail_next_commit = False
    rollback_calls = 0

    @classmethod
    def reset(cls) -> None:
        cls.fail_next_commit = False
        cls.rollback_calls = 0

    def commit(self):
        if FailingCommitSession.fail_next_commit:
            FailingCommitSession.fail_next_commit = False
            raise RuntimeError("simulated commit failure")
        return super().commit()

    def rollback(self):
        FailingCommitSession.rollback_calls += 1
        return super().rollback()


class NotebookFilterTests(unittest.TestCase):
    def setUp(self):
        self.engine, self.SessionLocal = create_test_engine()
        with self.SessionLocal() as db:
            self.owner = make_user(db, "owner@example.com")
            self.teammate = make_user(db, "teammate@example.com")
            self.case = make_case(db, self.owner, title="Primary Case")
            self.other_case = make_case(db, self.owner, title="Other Case")
            make_editor_membership(
                db,
                case=self.case,
                user=self.teammate,
                added_by=self.owner,
            )

            self.owner_note = create_note(
                db,
                case_id=self.case.id,
                current_user=self.owner,
                title="Alpha note",
                body="Person one narrative",
                tags=["alpha"],
                links=[{"target_type": "entity", "target_id": "person-1"}],
            )
            self.teammate_note = create_note(
                db,
                case_id=self.case.id,
                current_user=self.teammate,
                title="Beta note",
                body="Financial records",
                tags=["beta"],
                links=[
                    {
                        "target_type": "evidence",
                        "target_id": "file-1",
                        "target_label": "Bank statement",
                    }
                ],
            )
            self.other_case_note = create_note(
                db,
                case_id=self.other_case.id,
                current_user=self.owner,
                title="Other case alpha",
                body="Should never appear in the primary case",
                tags=["other"],
                links=[{"target_type": "entity", "target_id": "person-1"}],
            )

    def tearDown(self):
        drop_test_engine(self.engine)

    def test_list_notes_filters_by_case_author_search_and_link(self):
        with self.SessionLocal() as db:
            all_primary = list_notes(db, case_id=self.case.id, current_user=self.owner)
            mine = list_notes(db, case_id=self.case.id, current_user=self.teammate, mine=True)
            linked = list_notes(
                db,
                case_id=self.case.id,
                current_user=self.owner,
                linked_type="entity",
                linked_id="person-1",
            )
            searched = list_notes(
                db,
                case_id=self.case.id,
                current_user=self.owner,
                query_text="statement",
            )

        self.assertEqual(all_primary["total"], 2)
        self.assertEqual(
            {note["id"] for note in all_primary["notes"]},
            {self.owner_note["id"], self.teammate_note["id"]},
        )
        self.assertEqual([note["id"] for note in mine["notes"]], [self.teammate_note["id"]])
        self.assertEqual([note["id"] for note in linked["notes"]], [self.owner_note["id"]])
        self.assertEqual([note["id"] for note in searched["notes"]], [self.teammate_note["id"]])

    def test_link_filter_cannot_leak_note_from_another_case(self):
        with self.SessionLocal() as db:
            owner_note = db.get(NotebookNote, uuid.UUID(self.owner_note["id"]))
            db.add(
                NotebookNoteLink(
                    note_id=owner_note.id,
                    case_id=self.other_case.id,
                    target_type="agent_artifact",
                    target_id="artifact-cross",
                )
            )
            db.commit()

            linked_from_other_case = list_notes(
                db,
                case_id=self.other_case.id,
                current_user=self.owner,
                linked_type="agent_artifact",
                linked_id="artifact-cross",
            )

        self.assertEqual(linked_from_other_case["total"], 0)
        self.assertEqual(linked_from_other_case["notes"], [])


class NotebookRollbackRouterTests(unittest.TestCase):
    def setUp(self):
        self.engine, self.SeedSessionLocal = create_test_engine()
        self.FailingSessionLocal = sessionmaker(
            bind=self.engine,
            class_=FailingCommitSession,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
        FailingCommitSession.reset()

        with self.SeedSessionLocal() as db:
            self.owner = make_user(db, "owner@example.com")
            self.case = make_case(db, self.owner)
            db.commit()

        self.original_session_local = postgres_session._SessionLocal
        self.original_engine = postgres_session._engine
        postgres_session._SessionLocal = self.FailingSessionLocal
        postgres_session._engine = self.engine

        self.app = FastAPI()
        self.app.include_router(notebook.router)
        self.app.dependency_overrides[notebook.get_current_db_user] = lambda: self.owner
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def tearDown(self):
        self.app.dependency_overrides.clear()
        postgres_session._SessionLocal = self.original_session_local
        postgres_session._engine = self.original_engine
        FailingCommitSession.reset()
        drop_test_engine(self.engine)

    def test_failed_create_rolls_back_uncommitted_note_link_and_log(self):
        FailingCommitSession.fail_next_commit = True

        response = self.client.post(
            f"/api/notebook/{self.case.id}/notes",
            json={
                "title": "Will fail",
                "body": "This content must not be partially saved",
                "links": [{"target_type": "entity", "target_id": "person-1"}],
            },
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(FailingCommitSession.rollback_calls, 1)
        with self.SeedSessionLocal() as db:
            self.assertEqual(db.query(NotebookNote).count(), 0)
            self.assertEqual(db.query(NotebookNoteLink).count(), 0)
            self.assertEqual(db.query(SystemLog).count(), 0)

    def test_failed_update_restores_original_note_and_does_not_duplicate_links(self):
        with self.SeedSessionLocal() as db:
            original = create_note(
                db,
                case_id=self.case.id,
                current_user=self.owner,
                title="Original",
                body="Original body",
                tags=["original"],
                links=[
                    {
                        "target_type": "entity",
                        "target_id": "person-original",
                        "target_label": "Original person",
                    }
                ],
            )

        FailingCommitSession.fail_next_commit = True
        response = self.client.patch(
            f"/api/notebook/{self.case.id}/notes/{original['id']}",
            json={
                "body": "Replacement body",
                "links": [
                    {
                        "target_type": "entity",
                        "target_id": "person-replacement",
                        "target_label": "Replacement person",
                    }
                ],
            },
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(FailingCommitSession.rollback_calls, 1)
        with self.SeedSessionLocal() as db:
            note = db.get(NotebookNote, uuid.UUID(original["id"]))
            self.assertEqual(note.body, "Original body")
            self.assertEqual(len(note.links), 1)
            self.assertEqual(note.links[0].target_id, "person-original")
            self.assertEqual(db.query(NotebookNoteLink).count(), 1)
            self.assertEqual(db.query(SystemLog).count(), 1)


if __name__ == "__main__":
    unittest.main()
