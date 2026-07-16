import uuid
import unittest
from datetime import datetime, timezone

from postgres.models.evidence import EvidenceFile
from services.evidence_job_sync import _sync_db_record_from_job


def _record(**overrides):
    data = {
        "id": uuid.uuid4(),
        "case_id": uuid.uuid4(),
        "original_filename": "source.txt",
        "stored_path": "/tmp/source.txt",
        "size": 128,
        "sha256": "a" * 64,
        "status": "processed",
        "processed_at": datetime.now(timezone.utc),
        "summary": "Existing summary",
        "summary_source": "ai",
    }
    data.update(overrides)
    return EvidenceFile(**data)


class EvidenceJobSyncTests(unittest.TestCase):
    def test_completed_job_preserves_human_summary(self):
        edited_at = datetime.now(timezone.utc)
        record = _record(
            summary="Human reviewed summary",
            summary_source="human",
            summary_edited_by="investigator@example.com",
            summary_edited_at=edited_at,
        )

        changed = _sync_db_record_from_job(
            record,
            {"status": "completed", "document_summary": "New AI summary"},
        )

        self.assertFalse(changed)
        self.assertEqual(record.summary, "Human reviewed summary")
        self.assertEqual(record.summary_source, "human")
        self.assertEqual(record.summary_edited_by, "investigator@example.com")
        self.assertEqual(record.summary_edited_at, edited_at)

    def test_completed_job_records_ai_summary_source(self):
        record = _record(
            summary="Old AI summary",
            summary_source="ai",
            summary_edited_by="investigator@example.com",
            summary_edited_at=datetime.now(timezone.utc),
        )

        changed = _sync_db_record_from_job(
            record,
            {"status": "completed", "document_summary": "New AI summary"},
        )

        self.assertTrue(changed)
        self.assertEqual(record.summary, "New AI summary")
        self.assertEqual(record.summary_source, "ai")
        self.assertIsNone(record.summary_edited_by)
        self.assertIsNone(record.summary_edited_at)


if __name__ == "__main__":
    unittest.main()
