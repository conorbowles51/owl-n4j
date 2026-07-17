import uuid
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.graph_recycle_bin import GraphRecycleBinItem
from postgres.models.user import User
from postgres.models.workspace import WorkspaceFinding
from services.workspace_service import WorkspaceService


WORKSPACE_FINDING_LINK_TABLES = [
    User.__table__,
    Case.__table__,
    EvidenceFolder.__table__,
    EvidenceFile.__table__,
    GraphRecycleBinItem.__table__,
    WorkspaceFinding.__table__,
]


class WorkspaceFindingLinkTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=WORKSPACE_FINDING_LINK_TABLES)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.service = WorkspaceService()

        self.user_id = uuid.uuid4()
        self.case_id = uuid.uuid4()
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
            db.commit()

        self.session_patch = patch(
            "services.workspace_service.get_background_session",
            self._background_session,
        )
        self.session_patch.start()

    def tearDown(self):
        self.session_patch.stop()
        self.engine.dispose()

    @contextmanager
    def _background_session(self):
        db = self.SessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _add_file(
        self,
        db,
        *,
        file_id: uuid.UUID,
        filename: str,
        summary: str | None = None,
        legacy_id: str | None = None,
    ) -> None:
        db.add(
            EvidenceFile(
                id=file_id,
                case_id=self.case_id,
                original_filename=filename,
                stored_path=f"/evidence/{filename}",
                size=100,
                sha256=file_id.hex.ljust(64, "0")[:64],
                status="processed",
                summary=summary,
                legacy_id=legacy_id,
            )
        )

    def test_finding_read_marks_broken_and_recycled_links_with_file_summaries(self):
        evidence_id = uuid.uuid4()
        document_id = uuid.uuid4()

        with self.SessionLocal() as db:
            self._add_file(
                db,
                file_id=evidence_id,
                filename="bank-report.pdf",
                summary="Transfers cluster around the suspect account.",
            )
            self._add_file(
                db,
                file_id=document_id,
                filename="warrant-return.pdf",
                summary="Return lists the devices seized on March 4.",
                legacy_id="legacy-doc-1",
            )
            db.add(
                GraphRecycleBinItem(
                    case_id=self.case_id,
                    recycle_key="recycled_entity-1",
                    item_type="entity_delete",
                    original_key="entity-1",
                    original_name="Archived Person",
                    original_type="Person",
                    reason="merged during cleanup",
                    deleted_by="investigator@example.com",
                    deleted_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
                    relationship_count=2,
                    status="active",
                )
            )
            db.commit()

        finding_id = self.service.save_finding(
            str(self.case_id),
            {
                "title": "Funds moved after contact",
                "content": "Evidence and entity links should be reviewable.",
                "priority": "HIGH",
                "linked_evidence_ids": [str(evidence_id), "missing-evidence"],
                "linked_document_ids": ["legacy-doc-1"],
                "linked_entity_keys": ["entity-1", "entity-active"],
                "linked_item_summary": {"stale": True},
            },
        )

        finding = self.service.get_finding(str(self.case_id), finding_id)

        self.assertIsNotNone(finding)
        summary = finding["linked_item_summary"]
        self.assertEqual(
            summary["counts"],
            {
                "total": 5,
                "evidence": 2,
                "documents": 1,
                "entities": 2,
                "resolved": 2,
                "missing": 1,
                "recycled": 1,
                "unverified": 1,
            },
        )
        self.assertTrue(summary["has_broken_links"])
        self.assertTrue(summary["has_recycled_links"])
        self.assertEqual(summary["evidence"][0]["resolution_status"], "resolved")
        self.assertEqual(summary["evidence"][0]["summary"], "Transfers cluster around the suspect account.")
        self.assertEqual(summary["evidence"][0]["source_open_url"], f"/api/evidence/{evidence_id}/file")
        self.assertEqual(summary["evidence"][1]["resolution_status"], "missing")
        self.assertEqual(summary["documents"][0]["id"], str(document_id))
        self.assertEqual(summary["documents"][0]["requested_id"], "legacy-doc-1")
        self.assertEqual(summary["entities"][0]["resolution_status"], "recycled")
        self.assertEqual(summary["entities"][0]["recycle_key"], "recycled_entity-1")
        self.assertEqual(summary["entities"][1]["resolution_status"], "unverified")

        with self.SessionLocal() as db:
            row = db.query(WorkspaceFinding).filter_by(finding_id=finding_id).one()
            self.assertNotIn("linked_item_summary", row.data)

    def test_large_linked_item_set_is_resolved_without_truncating_counts(self):
        real_count = 625
        missing_count = 25
        file_ids = [uuid.uuid4() for _ in range(real_count)]

        with self.SessionLocal() as db:
            for index, file_id in enumerate(file_ids):
                self._add_file(
                    db,
                    file_id=file_id,
                    filename=f"file-{index:03}.pdf",
                    summary=f"Summary {index}",
                )
            db.commit()

        linked_ids = [str(file_id) for file_id in file_ids]
        linked_ids.extend(f"missing-{index}" for index in range(missing_count))
        finding_id = self.service.save_finding(
            str(self.case_id),
            {
                "title": "Large linked item set",
                "priority": "MEDIUM",
                "linked_evidence_ids": linked_ids,
                "linked_document_ids": [],
                "linked_entity_keys": [],
            },
        )

        finding = self.service.get_finding(str(self.case_id), finding_id)

        self.assertIsNotNone(finding)
        summary = finding["linked_item_summary"]
        self.assertEqual(summary["counts"]["total"], real_count + missing_count)
        self.assertEqual(summary["counts"]["resolved"], real_count)
        self.assertEqual(summary["counts"]["missing"], missing_count)
        self.assertEqual(len(summary["evidence"]), real_count + missing_count)
        self.assertEqual(summary["evidence"][0]["summary"], "Summary 0")
        self.assertEqual(summary["evidence"][-1]["resolution_status"], "missing")


if __name__ == "__main__":
    unittest.main()
