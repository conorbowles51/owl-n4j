from datetime import datetime, timedelta, timezone
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.runtime_state import BackgroundTask, PresenceSession, WiretapProcessedFolder
from services.background_task_storage import BackgroundTaskStorage, TaskStatus
from services.presence_service import PresenceService
from services.wiretap_tracking import WiretapTrackingService


RUNTIME_STATE_TABLES = [
    BackgroundTask.__table__,
    WiretapProcessedFolder.__table__,
    PresenceSession.__table__,
]


class RuntimeStateServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=RUNTIME_STATE_TABLES)
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
        )

    def tearDown(self):
        Base.metadata.drop_all(self.engine, tables=RUNTIME_STATE_TABLES)
        self.engine.dispose()

    def test_background_task_create_update_list_delete(self):
        storage = BackgroundTaskStorage(session_factory=self.SessionLocal)

        task = storage.create_task(
            task_type="evidence_processing",
            task_name="Process evidence",
            owner="investigator@example.com",
            case_id="case-1",
            metadata={"source": "test"},
        )

        self.assertEqual(task["status"], TaskStatus.PENDING.value)
        self.assertEqual(task["progress"], {"total": 0, "completed": 0, "failed": 0})
        self.assertEqual(task["metadata"], {"source": "test"})

        updated = storage.update_task(
            task["id"],
            status=TaskStatus.RUNNING.value,
            progress_total=2,
            progress_completed=1,
            progress_failed=0,
            file_status={
                "file_id": "file-1",
                "filename": "report.pdf",
                "status": "processing",
            },
            metadata={"batch": "alpha"},
        )

        self.assertIsNotNone(updated)
        self.assertEqual(updated["status"], TaskStatus.RUNNING.value)
        self.assertEqual(updated["progress"], {"total": 2, "completed": 1, "failed": 0})
        self.assertEqual(updated["files"][0]["file_id"], "file-1")
        self.assertEqual(updated["metadata"], {"source": "test", "batch": "alpha"})

        completed = storage.update_task(
            task["id"],
            status=TaskStatus.COMPLETED.value,
            progress_completed=2,
            file_status={
                "file_id": "file-1",
                "filename": "report.pdf",
                "status": "completed",
            },
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

        self.assertEqual(completed["files"][0]["status"], "completed")
        self.assertEqual(completed["progress"]["completed"], 2)

        listed = storage.list_tasks(owner="investigator@example.com", case_id="case-1")
        self.assertEqual([item["id"] for item in listed], [task["id"]])
        self.assertEqual(storage.list_tasks(status=TaskStatus.FAILED.value), [])

        self.assertTrue(storage.delete_task(task["id"]))
        self.assertIsNone(storage.get_task(task["id"]))
        self.assertFalse(storage.delete_task(task["id"]))

    def test_wiretap_processed_tracking_lifecycle(self):
        tracking = WiretapTrackingService(session_factory=self.SessionLocal)

        self.assertFalse(tracking.is_wiretap_processed("case-1", "calls/day-1"))
        tracking.mark_wiretap_processed("case-1", "calls/day-1")

        self.assertTrue(tracking.is_wiretap_processed("case-1", "calls/day-1"))
        status = tracking.get_wiretap_status("case-1", "calls/day-1")
        self.assertEqual(status["case_id"], "case-1")
        self.assertEqual(status["folder_path"], "calls/day-1")
        self.assertIsNotNone(status["processed_at"])

        tracking.mark_wiretap_processed("case-1", "calls/day-1")
        tracking.mark_wiretap_processed("case-2", "calls/day-1")

        self.assertEqual(len(tracking.list_processed_wiretaps()), 2)
        self.assertEqual(len(tracking.list_processed_wiretaps(case_id="case-1")), 1)

    def test_presence_session_lifecycle(self):
        presence = PresenceService(
            session_factory=self.SessionLocal,
            stale_timeout_minutes=30,
        )

        first_session = presence.create_session(
            case_id="case-1",
            user_id="user-1",
            username="Investigator",
            ip_address="127.0.0.1",
        )
        second_session = presence.create_session(
            case_id="case-1",
            user_id="user-1",
            username="Investigator",
            device_info="browser",
        )

        self.assertTrue(first_session.startswith("ws_"))
        self.assertEqual(
            presence.get_online_users("case-1"),
            [{"user_id": "user-1", "username": "Investigator"}],
        )

        presence.update_session_activity(first_session)
        session = presence.get_session(first_session)
        self.assertEqual(session["case_id"], "case-1")
        self.assertEqual(session["ip_address"], "127.0.0.1")

        presence.remove_session(first_session)
        self.assertIsNone(presence.get_session(first_session))
        self.assertIsNotNone(presence.get_session(second_session))

        with self.SessionLocal() as db:
            record = db.get(PresenceSession, second_session)
            record.last_active = datetime.now(timezone.utc) - timedelta(minutes=60)
            db.commit()

        self.assertEqual(presence.cleanup_stale_sessions(timeout_minutes=30), 1)
        self.assertEqual(presence.get_online_users("case-1"), [])
        self.assertIsNone(presence.get_session(second_session))


if __name__ == "__main__":
    unittest.main()
