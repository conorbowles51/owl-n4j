import uuid
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.user import User
from routers import workspace


WORKSPACE_EVIDENCE_TABLES = [
    User.__table__,
    Case.__table__,
    EvidenceFolder.__table__,
    EvidenceFile.__table__,
]


class WorkspaceEvidenceSummaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=WORKSPACE_EVIDENCE_TABLES)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

        self.user_id = uuid.uuid4()
        self.case_id = uuid.uuid4()
        self.file_id = uuid.uuid4()

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
                    id=self.file_id,
                    case_id=self.case_id,
                    original_filename="case-notes.txt",
                    stored_path="/tmp/case-notes.txt",
                    size=128,
                    sha256="a" * 64,
                    status="processed",
                    summary="AI summary",
                    summary_source="ai",
                )
            )
            db.commit()

    async def test_update_evidence_summary_marks_human_and_logs(self):
        with self.SessionLocal() as db:
            current_user = db.get(User, self.user_id)
            with (
                patch.object(workspace, "get_case_if_allowed", return_value=object()),
                patch.object(workspace.system_log_service, "log") as log,
            ):
                result = await workspace.update_evidence_summary(
                    case_id=str(self.case_id),
                    file_id=str(self.file_id),
                    payload=workspace.EvidenceSummaryUpdate(summary="  Human reviewed summary  "),
                    db=db,
                    current_user=current_user,
                )

            record = db.get(EvidenceFile, self.file_id)
            self.assertEqual(result["summary"], "Human reviewed summary")
            self.assertEqual(result["summary_source"], "human")
            self.assertEqual(record.summary, "Human reviewed summary")
            self.assertEqual(record.summary_source, "human")
            self.assertEqual(record.summary_edited_by, "investigator@example.com")
            self.assertIsNotNone(record.summary_edited_at)
            log.assert_called_once()
            self.assertEqual(log.call_args.kwargs["action"], "Edit File Summary")

    async def test_update_evidence_summary_rejects_blank_summary(self):
        with self.SessionLocal() as db:
            current_user = db.get(User, self.user_id)
            with (
                patch.object(workspace, "get_case_if_allowed", return_value=object()),
                patch.object(workspace.system_log_service, "log") as log,
            ):
                with self.assertRaises(HTTPException) as raised:
                    await workspace.update_evidence_summary(
                        case_id=str(self.case_id),
                        file_id=str(self.file_id),
                        payload=workspace.EvidenceSummaryUpdate(summary="   \n\t  "),
                        db=db,
                        current_user=current_user,
                    )

            self.assertEqual(raised.exception.status_code, 400)
            self.assertEqual(db.get(EvidenceFile, self.file_id).summary_source, "ai")
            log.assert_not_called()

    async def test_update_evidence_summary_collapses_case_denial_to_not_found(self):
        with self.SessionLocal() as db:
            current_user = db.get(User, self.user_id)
            with patch.object(
                workspace,
                "get_case_if_allowed",
                side_effect=workspace.CaseAccessDenied("denied"),
            ):
                with self.assertRaises(HTTPException) as raised:
                    await workspace.update_evidence_summary(
                        case_id=str(self.case_id),
                        file_id=str(self.file_id),
                        payload=workspace.EvidenceSummaryUpdate(summary="Human summary"),
                        db=db,
                        current_user=current_user,
                    )

            self.assertEqual(raised.exception.status_code, 404)
            self.assertEqual(db.get(EvidenceFile, self.file_id).summary_source, "ai")


if __name__ == "__main__":
    unittest.main()
