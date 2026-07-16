import unittest
import uuid
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile
from postgres.models.user import User
from postgres.models.workspace import WorkspaceFinding
from services.workspace_service import WorkspaceService


WORKSPACE_FINDING_TABLES = [
    User.__table__,
    Case.__table__,
    EvidenceFile.__table__,
    WorkspaceFinding.__table__,
]


class WorkspaceFindingServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=WORKSPACE_FINDING_TABLES)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.service = WorkspaceService()

        self.user_id = uuid.uuid4()
        self.case_id = uuid.uuid4()
        self.evidence_id = uuid.uuid4()
        self.document_id = uuid.uuid4()

        with self.SessionLocal() as db:
            db.add(
                User(
                    id=self.user_id,
                    email="investigator@example.com",
                    name="Investigator",
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
            db.add(
                EvidenceFile(
                    id=self.evidence_id,
                    case_id=self.case_id,
                    original_filename="ledger.pdf",
                    stored_path="/tmp/ledger.pdf",
                    size=100,
                    sha256="a" * 64,
                    status="processed",
                    summary="Ledger summary",
                )
            )
            db.add(
                EvidenceFile(
                    id=self.document_id,
                    case_id=self.case_id,
                    original_filename="interview.txt",
                    stored_path="/tmp/interview.txt",
                    size=50,
                    sha256="b" * 64,
                    status="processed",
                    summary="Interview summary",
                )
            )
            db.commit()

    def tearDown(self):
        Base.metadata.drop_all(self.engine, tables=WORKSPACE_FINDING_TABLES)
        self.engine.dispose()

    def test_create_validates_links_and_returns_ordered_summaries(self):
        with self.SessionLocal() as db, patch(
            "services.workspace_service.neo4j_service.get_node_details",
            return_value={"key": "person-1", "name": "Person One"},
        ) as get_node_details, patch("services.workspace_service.system_log_service.log"):
            self.service.save_finding(
                str(self.case_id),
                {
                    "title": "First finding",
                    "linked_evidence_ids": [str(self.evidence_id)],
                    "linked_document_ids": [str(self.document_id)],
                    "linked_entity_keys": ["person-1"],
                },
                db=db,
                user_email="investigator@example.com",
            )
            self.service.save_finding(
                str(self.case_id),
                {"title": "Second finding"},
                db=db,
                user_email="investigator@example.com",
            )

            findings = self.service.get_findings(str(self.case_id), db=db)

        self.assertEqual([finding["title"] for finding in findings], ["First finding", "Second finding"])
        self.assertEqual([finding["position"] for finding in findings], [0, 1])
        self.assertEqual(findings[0]["linked_evidence"][0]["summary"], "Ledger summary")
        self.assertEqual(findings[0]["linked_documents"][0]["summary"], "Interview summary")
        get_node_details.assert_called_once_with("person-1", case_id=str(self.case_id))

    def test_create_rejects_missing_linked_evidence_without_writing(self):
        missing_id = uuid.uuid4()
        with self.SessionLocal() as db, patch("services.workspace_service.system_log_service.log"):
            with self.assertRaises(ValueError):
                self.service.save_finding(
                    str(self.case_id),
                    {
                        "title": "Invalid finding",
                        "linked_evidence_ids": [str(missing_id)],
                    },
                    db=db,
                    user_email="investigator@example.com",
                )

            rows = db.scalars(select(WorkspaceFinding)).all()

        self.assertEqual(rows, [])

    def test_reorder_requires_exact_active_set(self):
        with self.SessionLocal() as db, patch("services.workspace_service.system_log_service.log"):
            first_id = self.service.save_finding(
                str(self.case_id),
                {"title": "First finding"},
                db=db,
                user_email="investigator@example.com",
            )
            second_id = self.service.save_finding(
                str(self.case_id),
                {"title": "Second finding"},
                db=db,
                user_email="investigator@example.com",
            )

            reordered = self.service.reorder_findings(
                str(self.case_id),
                [second_id, first_id],
                db=db,
                user_email="investigator@example.com",
            )
            with self.assertRaises(ValueError):
                self.service.reorder_findings(
                    str(self.case_id),
                    [second_id],
                    db=db,
                    user_email="investigator@example.com",
                )

        self.assertEqual([finding["finding_id"] for finding in reordered], [second_id, first_id])
        self.assertEqual([finding["position"] for finding in reordered], [0, 1])

    def test_delete_soft_recycles_and_hides_finding(self):
        with self.SessionLocal() as db, patch("services.workspace_service.system_log_service.log"):
            finding_id = self.service.save_finding(
                str(self.case_id),
                {"title": "Recycle me", "linked_evidence_ids": [str(self.evidence_id)]},
                db=db,
                user_email="investigator@example.com",
            )

            deleted = self.service.delete_finding(
                str(self.case_id),
                finding_id,
                db=db,
                user_email="investigator@example.com",
            )
            active = self.service.get_findings(str(self.case_id), db=db)
            row = db.scalars(select(WorkspaceFinding)).one()

        self.assertTrue(deleted)
        self.assertEqual(active, [])
        self.assertIsNotNone(row.deleted_at)
        self.assertEqual(row.deleted_by, "investigator@example.com")
        self.assertEqual(row.data["linked_evidence_ids"], [str(self.evidence_id)])


if __name__ == "__main__":
    unittest.main()
