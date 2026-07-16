import uuid
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres import session as postgres_session
from postgres.base import Base
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.user import User
from postgres.models.workspace import (
    WorkspaceDeadlineConfig,
    WorkspaceFinding,
    WorkspaceNote,
    WorkspacePinnedItem,
    WorkspaceTask,
    WorkspaceTheory,
    WorkspaceWitness,
)
from services.workspace_service import WorkspaceService


WORKSPACE_TIMELINE_TABLES = [
    User.__table__,
    Case.__table__,
    EvidenceFolder.__table__,
    EvidenceFile.__table__,
    WorkspaceWitness.__table__,
    WorkspaceTheory.__table__,
    WorkspaceTask.__table__,
    WorkspaceNote.__table__,
    WorkspaceFinding.__table__,
    WorkspacePinnedItem.__table__,
    WorkspaceDeadlineConfig.__table__,
]


class UUIDString(str):
    @property
    def hex(self):
        return uuid.UUID(str(self)).hex


class WorkspaceServiceTimelineTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=WORKSPACE_TIMELINE_TABLES)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

        self.previous_session_local = postgres_session._SessionLocal
        self.previous_engine = postgres_session._engine
        postgres_session._SessionLocal = self.SessionLocal
        postgres_session._engine = self.engine

        self.user_id = uuid.uuid4()
        self.case_uuid = uuid.uuid4()
        self.case_id = UUIDString(str(self.case_uuid))
        self.evidence_id = uuid.uuid4()
        self.theory_id = "theory_detached_evidence"

        uploaded_at = datetime(2026, 1, 10, 9, 30, tzinfo=timezone.utc)
        processed_at = datetime(2026, 1, 10, 9, 45, tzinfo=timezone.utc)

        with self.SessionLocal() as db:
            db.add(User(
                id=self.user_id,
                email="investigator@example.com",
                name="Investigator",
                password_hash="hash",
            ))
            db.add(Case(
                id=self.case_uuid,
                title="Timeline Case",
                created_by_user_id=self.user_id,
                owner_user_id=self.user_id,
            ))
            db.add(EvidenceFile(
                id=self.evidence_id,
                case_id=self.case_uuid,
                original_filename="phone_dump.zip",
                stored_path="/evidence/phone_dump.zip",
                size=1024,
                sha256="a" * 64,
                status="processed",
                created_at=uploaded_at,
                processed_at=processed_at,
            ))
            db.add(WorkspaceTheory(
                case_id=self.case_uuid,
                theory_id=self.theory_id,
                data={
                    "theory_id": self.theory_id,
                    "case_id": str(self.case_uuid),
                    "title": "Attached evidence theory",
                    "hypothesis": "Evidence should appear in the theory timeline",
                    "created_at": "2026-01-09T08:00:00+00:00",
                    "attached_evidence_ids": [str(self.evidence_id)],
                },
            ))
            db.commit()

    def tearDown(self):
        postgres_session._SessionLocal = self.previous_session_local
        postgres_session._engine = self.previous_engine
        Base.metadata.drop_all(self.engine, tables=WORKSPACE_TIMELINE_TABLES)
        self.engine.dispose()

    def test_investigation_timeline_materializes_evidence_before_session_closes(self):
        service = WorkspaceService()

        with patch(
            "services.system_log_service.system_log_service.get_logs",
            return_value={"logs": []},
        ):
            events = service.get_investigation_timeline(self.case_id)

        evidence_events = [
            event for event in events
            if event.get("metadata", {}).get("evidence_id") == str(self.evidence_id)
        ]
        self.assertEqual(
            [event["type"] for event in evidence_events],
            ["evidence_uploaded", "evidence_processed"],
        )
        self.assertEqual(evidence_events[0]["title"], "Evidence Uploaded: phone_dump.zip")
        self.assertEqual(evidence_events[1]["title"], "Evidence Processed: phone_dump.zip")

    def test_theory_timeline_materializes_attached_evidence_before_session_closes(self):
        service = WorkspaceService()

        events = service.get_theory_timeline(self.case_id, self.theory_id)

        evidence_events = [
            event for event in events
            if event.get("metadata", {}).get("evidence_id") == str(self.evidence_id)
        ]
        self.assertEqual(
            [event["type"] for event in evidence_events],
            ["evidence_uploaded", "evidence_processed"],
        )
        self.assertEqual(evidence_events[0]["thread"], "Evidence")
        self.assertEqual(evidence_events[1]["thread"], "Evidence")


if __name__ == "__main__":
    unittest.main()
