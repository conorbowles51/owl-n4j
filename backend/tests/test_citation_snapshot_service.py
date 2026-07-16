import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.chat import CaseRevision, ChatCitationSnapshot
from postgres.models.enums import GlobalRole
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.user import User
from services.citation_snapshot_service import citation_snapshot_service


CITATION_SNAPSHOT_TABLES = [
    User.__table__,
    Case.__table__,
    CaseRevision.__table__,
    EvidenceFolder.__table__,
    EvidenceFile.__table__,
    ChatCitationSnapshot.__table__,
]


class CitationSnapshotServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=CITATION_SNAPSHOT_TABLES)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

        with self.SessionLocal() as db:
            self.user = User(
                email="investigator@example.com",
                name="Investigator",
                password_hash="hash",
                global_role=GlobalRole.user,
                is_active=True,
            )
            db.add(self.user)
            db.flush()
            self.case = Case(
                title="Case Alpha",
                created_by_user_id=self.user.id,
                owner_user_id=self.user.id,
            )
            db.add(self.case)
            db.commit()
            db.refresh(self.user)
            db.refresh(self.case)
            self.user_id = self.user.id
            self.case_id = self.case.id

    def tearDown(self):
        Base.metadata.drop_all(self.engine, tables=CITATION_SNAPSHOT_TABLES)
        self.engine.dispose()

    def test_create_snapshot_records_exact_context_and_available_citation(self):
        with TemporaryDirectory() as tmp, self.SessionLocal() as db:
            file_path = f"{tmp}/report.pdf"
            with open(file_path, "wb") as f:
                f.write(b"evidence bytes")
            evidence_sha = hashlib.sha256(b"evidence bytes").hexdigest()
            evidence = EvidenceFile(
                case_id=self.case_id,
                original_filename="report.pdf",
                stored_path=file_path,
                size=14,
                sha256=evidence_sha,
                status="processed",
                engine_job_id="job-1",
            )
            db.add(evidence)
            db.flush()

            snapshot = citation_snapshot_service.create_snapshot(
                db,
                case_id=self.case_id,
                case_revision_id=None,
                conversation_id=None,
                assistant_message_id=None,
                created_by_user_id=self.user_id,
                question="What happened?",
                answer="The report says it happened [report.pdf, p.2](doc://report.pdf/2).",
                model_provider="openai",
                model_id="gpt-5-mini",
                context_scope="case_overview",
                selected_entity_keys=[],
                citation_context={
                    "context": "exact context",
                    "final_prompt": "exact final prompt",
                    "retrieval_payload": {"reranked_chunks": [{"id": "chunk-1"}]},
                },
                sources=[
                    {
                        "filename": "report.pdf",
                        "page": 2,
                        "excerpt": "The report says it happened.",
                        "evidence_id": str(evidence.id),
                        "engine_job_id": "job-1",
                        "evidence_sha256": evidence_sha,
                    }
                ],
            )

            self.assertEqual(snapshot.context_text, "exact context")
            self.assertEqual(snapshot.final_prompt, "exact final prompt")
            self.assertEqual(snapshot.source_payload[0]["status"], "available")
            self.assertTrue(snapshot.source_payload[0]["openable"])
            self.assertEqual(snapshot.answer_citations[0]["source_id"], snapshot.source_payload[0]["source_id"])
            self.assertFalse(snapshot.answer_citations[0]["unsupported"])

    def test_snapshot_payload_refreshes_broken_and_deleted_sources(self):
        with TemporaryDirectory() as tmp, self.SessionLocal() as db:
            file_path = f"{tmp}/report.pdf"
            with open(file_path, "wb") as f:
                f.write(b"evidence bytes")
            evidence = EvidenceFile(
                case_id=self.case_id,
                original_filename="report.pdf",
                stored_path=file_path,
                size=14,
                sha256=hashlib.sha256(b"evidence bytes").hexdigest(),
                status="processed",
            )
            db.add(evidence)
            db.flush()
            snapshot = citation_snapshot_service.create_snapshot(
                db,
                case_id=self.case_id,
                case_revision_id=None,
                conversation_id=None,
                assistant_message_id=None,
                created_by_user_id=self.user_id,
                question="What happened?",
                answer="See [report.pdf, p.1](doc://report.pdf/1).",
                model_provider="openai",
                model_id="gpt-5-mini",
                context_scope="case_overview",
                selected_entity_keys=[],
                citation_context={},
                sources=[{"filename": "report.pdf", "page": 1, "evidence_id": str(evidence.id)}],
            )
            db.commit()

            Path(file_path).unlink()
            broken = citation_snapshot_service.snapshot_payload(db, snapshot)
            self.assertEqual(broken["source_payload"][0]["status"], "broken")
            self.assertFalse(broken["source_payload"][0]["openable"])

            db.delete(evidence)
            db.commit()
            deleted = citation_snapshot_service.snapshot_payload(db, snapshot)
            self.assertEqual(deleted["source_payload"][0]["status"], "deleted")

    def test_answer_without_citations_gets_unsupported_marker(self):
        with self.SessionLocal() as db:
            snapshot = citation_snapshot_service.create_snapshot(
                db,
                case_id=self.case_id,
                case_revision_id=None,
                conversation_id=None,
                assistant_message_id=None,
                created_by_user_id=self.user_id,
                question="What happened?",
                answer="The answer contains a material claim without a citation.",
                model_provider="openai",
                model_id="gpt-5-mini",
                context_scope="case_overview",
                selected_entity_keys=[],
                citation_context={},
                sources=[],
            )

            self.assertEqual(snapshot.answer_citations[0]["status"], "unsupported")
            self.assertTrue(snapshot.answer_citations[0]["unsupported"])


if __name__ == "__main__":
    unittest.main()
