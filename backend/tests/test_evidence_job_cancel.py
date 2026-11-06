"""A cancelled engine job on the evidence side: the file stays, with a stated state, and is never counted as failed."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from services.evidence_job_sync import CANCELLED_PREFIX, _sync_db_record_from_job, file_was_cancelled
from services.evidence_page_text import absent_reason
from services.financial.import_batches import _reading_stopped

MESSAGE = f"{CANCELLED_PREFIX} This file stays in the case; nothing from it was added to the case graph."


def file(**values):
    base = dict(status="processing", last_error=None, processed_at=None, processing_stale=False, metadata_={},
                last_processed_profile_snapshot={})
    return SimpleNamespace(**{**base, **values})


def cancelled(**values):
    return {"status": "failed", "cancelled_at": "2026-11-05T23:00:00", "error_message": MESSAGE, **values}


class CancelledFileTests(unittest.TestCase):
    def test_a_file_never_processed_goes_back_to_unprocessed_with_the_reason(self):
        record = file()
        self.assertTrue(_sync_db_record_from_job(record, cancelled()))
        self.assertEqual((record.status, record.last_error), ("unprocessed", MESSAGE))

    def test_a_reprocessed_file_keeps_its_earlier_run(self):
        when = datetime(2026, 1, 1, tzinfo=timezone.utc)
        record = file(processed_at=when)
        _sync_db_record_from_job(record, cancelled())
        self.assertEqual((record.status, record.processed_at), ("processed", when))

    def test_a_cancelled_recording_is_not_failed(self):
        record = file()
        _sync_db_record_from_job(record, cancelled(job_type="audio_review"))
        self.assertEqual(record.status, "unprocessed")

    def test_repeating_changes_nothing(self):
        record = file()
        _sync_db_record_from_job(record, cancelled())
        self.assertFalse(_sync_db_record_from_job(record, cancelled()))

    def test_a_real_failure_is_still_a_failure(self):
        record = file()
        _sync_db_record_from_job(record, {"status": "failed", "error_message": "Boom"})
        self.assertEqual((record.status, record.last_error), ("failed", "Boom"))
        self.assertFalse(file_was_cancelled(record))


class FinancialBatchTests(unittest.TestCase):
    def test_a_cancelled_reading_ends_the_wait(self):
        """Fails on the old rule: an unprocessed target reads as still reading, for ever."""
        self.assertTrue(_reading_stopped(file(status="unprocessed", last_error=MESSAGE)))

    def test_a_cancelled_re_read_keeps_the_earlier_reading_in_use(self):
        self.assertFalse(_reading_stopped(file(status="processed", last_error=MESSAGE)))

    def test_other_states_are_unchanged(self):
        self.assertTrue(_reading_stopped(None))
        self.assertTrue(_reading_stopped(file(status="failed", last_error="Boom")))
        self.assertFalse(_reading_stopped(file(status="processing")))
        self.assertFalse(_reading_stopped(file(status="processed")))


class PageWordsTests(unittest.TestCase):
    def test_a_cancelled_file_is_not_called_not_processed_yet(self):
        self.assertIn("cancelled", absent_reason(file(status="unprocessed", last_error=MESSAGE)))

    def test_the_interrupted_reason_is_still_shown_with_old_and_new_words(self):
        for words in ("Batch task interrupted (worker timeout or shutdown). Safe to retry.",
                      "Batch task cancelled (worker timeout or shutdown). Safe to retry."):
            self.assertIn("Safe to retry", absent_reason(file(status="failed", last_error=words)))


class RouterTests(unittest.IsolatedAsyncioTestCase):
    async def _cancel(self, outcome):
        from routers import evidence
        record = SimpleNamespace(id="file", case_id="case", original_filename="a.txt")
        db = SimpleNamespace(commit=lambda: None)
        user = SimpleNamespace(email="person@example.test")
        client = AsyncMock(return_value=outcome)
        with patch.object(evidence.EvidenceDBStorage, "find_by_engine_job_id", return_value=record), \
                patch.object(evidence.EvidenceDBStorage, "add_log") as log, \
                patch.object(evidence, "authorize_case"), \
                patch.object(evidence.evidence_engine_client, "control_job", client):
            result = await evidence.control_engine_job("job", "cancel", current_user=user, db=db)
        return result, client, log

    async def test_cancel_reaches_the_engine_and_records_who_asked(self):
        """Fails on the old code: the router answered 409 for every file job."""
        result, client, log = await self._cancel({"state": "cancelling", "affected_jobs": 3})
        self.assertEqual(result["state"], "cancelling")
        client.assert_awaited_once_with("job", "case", "cancel")
        self.assertIn("3 file(s) requested by person@example.test", log.call_args.kwargs["message"])

    async def test_a_cancel_the_engine_accepted_is_not_answered_as_an_error(self):
        from routers import evidence
        record = SimpleNamespace(id="file", case_id="case", original_filename="a.txt")

        def broken():
            raise RuntimeError("lock timeout")
        db = SimpleNamespace(commit=broken, rollback=lambda: None)
        with patch.object(evidence.EvidenceDBStorage, "find_by_engine_job_id", return_value=record), \
                patch.object(evidence.EvidenceDBStorage, "add_log"), patch.object(evidence, "authorize_case"), \
                patch.object(evidence.evidence_engine_client, "control_job",
                             AsyncMock(return_value={"state": "cancelling", "affected_jobs": 1})):
            result = await evidence.control_engine_job("job", "cancel",
                current_user=SimpleNamespace(email="person@example.test"), db=db)
        self.assertEqual(result["state"], "cancelling")

    async def test_a_repeated_cancel_writes_no_second_log_line(self):
        _, _, log = await self._cancel({"state": "cancelled", "affected_jobs": 0})
        log.assert_not_called()
