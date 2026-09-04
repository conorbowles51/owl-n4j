import unittest
from datetime import date
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.case_deadline import CaseDeadline
from postgres.models.case_profile import (
    CaseProfile,
    CaseProfileEvidenceLink,
    CaseProfileFindingLink,
    CaseProfileGraphNodeLink,
    CaseProfileNoteLink,
)
from postgres.models.evidence import EvidenceFile
from postgres.models.notebook import NotebookNote, NotebookNoteLink
from postgres.models.user import User
from postgres.models.workspace import (
    WorkspaceContext,
    WorkspaceDeadlineConfig,
    WorkspaceFinding,
    WorkspaceNote,
    WorkspacePinnedItem,
    WorkspaceTask,
    WorkspaceTheory,
    WorkspaceWitness,
)
from services.workspace_preflight_service import build_workspace_preflight_report


PREFLIGHT_TABLES = [
    User.__table__,
    Case.__table__,
    EvidenceFile.__table__,
    WorkspaceContext.__table__,
    WorkspaceWitness.__table__,
    WorkspaceTheory.__table__,
    WorkspaceTask.__table__,
    WorkspaceNote.__table__,
    WorkspaceFinding.__table__,
    WorkspacePinnedItem.__table__,
    WorkspaceDeadlineConfig.__table__,
    NotebookNote.__table__,
    NotebookNoteLink.__table__,
    CaseProfile.__table__,
    CaseProfileGraphNodeLink.__table__,
    CaseProfileEvidenceLink.__table__,
    CaseProfileNoteLink.__table__,
    CaseProfileFindingLink.__table__,
    CaseDeadline.__table__,
]


class WorkspacePreflightServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=PREFLIGHT_TABLES)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.case_id = uuid4()
        self.user_id = uuid4()
        self.evidence_id = uuid4()

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
                    title="Preflight case",
                    created_by_user_id=self.user_id,
                    owner_user_id=self.user_id,
                )
            )
            db.add(
                EvidenceFile(
                    id=self.evidence_id,
                    case_id=self.case_id,
                    original_filename="ledger.pdf",
                    stored_path="C:/evidence/ledger.pdf",
                    size=100,
                    sha256="a" * 64,
                    status="processed",
                )
            )
            db.add(
                WorkspaceContext(
                    case_id=self.case_id,
                    data={"trial_date": "2026-10-13"},
                )
            )
            db.add(WorkspaceTask(case_id=self.case_id, task_id=" ", data={"title": "Review"}))
            db.add(
                WorkspaceTheory(
                    case_id=self.case_id,
                    theory_id="theory-1",
                    data={"attached_evidence_ids": ["missing-file"]},
                )
            )
            db.add(
                CaseDeadline(
                    case_id=self.case_id,
                    name="Trial",
                    due_date=date(2026, 10, 12),
                    created_by_user_id=self.user_id,
                )
            )
            db.add_all(
                [
                    WorkspacePinnedItem(
                        case_id=self.case_id,
                        pin_id="pin-1",
                        item_type="evidence",
                        item_id=str(self.evidence_id),
                        user_id=str(self.user_id),
                        data={},
                    ),
                    WorkspacePinnedItem(
                        case_id=self.case_id,
                        pin_id="pin-2",
                        item_type="evidence",
                        item_id=str(self.evidence_id),
                        user_id="second-user",
                        data={},
                    ),
                ]
            )
            first = CaseProfile(
                case_id=self.case_id,
                profile_type="person",
                display_name="Henry Walsh",
            )
            second = CaseProfile(
                case_id=self.case_id,
                profile_type="person",
                display_name="H. Walsh",
            )
            db.add_all([first, second])
            db.flush()
            db.add_all(
                [
                    CaseProfileGraphNodeLink(
                        profile_id=first.id,
                        case_id=self.case_id,
                        node_key="person-1",
                    ),
                    CaseProfileGraphNodeLink(
                        profile_id=second.id,
                        case_id=self.case_id,
                        node_key="person-1",
                    ),
                    CaseProfileNoteLink(
                        profile_id=first.id,
                        case_id=self.case_id,
                        note_id="missing-note",
                    ),
                ]
            )
            db.commit()

    def tearDown(self):
        Base.metadata.drop_all(self.engine, tables=reversed(PREFLIGHT_TABLES))
        self.engine.dispose()

    def test_report_is_deterministic_and_does_not_mutate_the_session(self):
        with self.SessionLocal() as db:
            first = build_workspace_preflight_report(db)
            second = build_workspace_preflight_report(db)

            self.assertEqual(first, second)
            self.assertFalse(db.new)
            self.assertFalse(db.dirty)
            self.assertFalse(db.deleted)

        self.assertEqual(first["counts"]["workspace_tasks"]["total"], 1)
        self.assertEqual(first["summary"]["malformed_identifiers"], 1)
        self.assertEqual(first["summary"]["duplicate_pins"], 1)
        self.assertEqual(first["summary"]["duplicate_profile_entity_associations"], 1)
        self.assertEqual(first["summary"]["conflicting_deadline_sources"], 1)
        self.assertEqual(first["summary"]["orphaned_links"], 2)

    def test_case_scope_excludes_other_cases(self):
        other_case_id = uuid4()
        with self.SessionLocal() as db:
            db.add(
                Case(
                    id=other_case_id,
                    title="Other case",
                    created_by_user_id=self.user_id,
                    owner_user_id=self.user_id,
                )
            )
            db.add(WorkspaceNote(case_id=other_case_id, note_id="note-2", data={}))
            db.commit()

            report = build_workspace_preflight_report(db, case_id=self.case_id)

        self.assertEqual(report["scope"], {"case_id": str(self.case_id)})
        self.assertEqual(report["counts"]["workspace_notes"]["total"], 0)


if __name__ == "__main__":
    unittest.main()
