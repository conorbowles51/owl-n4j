import json
import logging
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from services import job_status_subscriber as module
from services.job_status_subscriber import JobStatusSubscriber


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _message(job_id, status):
    return {"type": "message", "data": json.dumps({"job_id": job_id, "status": status})}


class JobStatusSubscriberRetryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.clock = _Clock()
        patcher = patch.object(module.time, "monotonic", self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.subscriber = JobStatusSubscriber()
        self.subscriber._pubsub = AsyncMock()
        self.subscriber._tracked["job-1"] = "case-1"
        self.subscriber._last_seen["job-1"] = self.clock.now

    async def test_failed_sync_is_retried_without_another_message(self):
        # The engine publishes "completed" once; the first sync hits a deadlock.
        dispatch = AsyncMock(side_effect=[RuntimeError("deadlock detected"), True])
        engine = AsyncMock(return_value={"id": "job-1", "status": "completed"})
        with patch.object(self.subscriber, "_dispatch_terminal", dispatch), \
                patch("services.evidence_engine_client.get_job", engine):
            await self.subscriber._handle_message(_message("job-1", "completed"))
            self.assertIn("job-1", self.subscriber._tracked)

            await self.subscriber._check_quiet_jobs()  # not due yet
            self.assertEqual(dispatch.await_count, 1)

            self.clock.now += module._RETRY_DELAYS[0]
            await self.subscriber._check_quiet_jobs()

        self.assertEqual(dispatch.await_count, 2)
        self.assertEqual(dispatch.await_args.args[2], "completed")
        self.assertNotIn("job-1", self.subscriber._tracked)
        self.assertNotIn("job-1", self.subscriber._retry_at)
        self.subscriber._pubsub.unsubscribe.assert_awaited_once_with("job:job-1:progress")

    async def test_repeated_failures_back_off(self):
        dispatch = AsyncMock(side_effect=RuntimeError("deadlock detected"))
        engine = AsyncMock(return_value={"id": "job-1", "status": "failed", "error_message": "bad pdf"})
        with patch.object(self.subscriber, "_dispatch_terminal", dispatch), \
                patch("services.evidence_engine_client.get_job", engine):
            await self.subscriber._handle_message(_message("job-1", "failed"))
            for delay in module._RETRY_DELAYS[1:]:
                self.clock.now = self.subscriber._retry_at["job-1"]
                await self.subscriber._check_quiet_jobs()
                self.assertEqual(self.subscriber._retry_at["job-1"], self.clock.now + delay)

        self.assertIn("job-1", self.subscriber._tracked)
        self.assertEqual(dispatch.await_count, len(module._RETRY_DELAYS))

    async def test_quiet_job_found_terminal_is_settled(self):
        # Its terminal message never arrived (e.g. lost on a reconnect).
        dispatch = AsyncMock(return_value=True)
        engine = AsyncMock(return_value={"id": "job-1", "status": "completed"})
        with patch.object(self.subscriber, "_dispatch_terminal", dispatch), \
                patch("services.evidence_engine_client.get_job", engine):
            self.clock.now += module._QUIET_SWEEP_SECONDS - 1
            await self.subscriber._check_quiet_jobs()
            dispatch.assert_not_awaited()

            self.clock.now += 1
            await self.subscriber._check_quiet_jobs()

        dispatch.assert_awaited_once()
        self.assertNotIn("job-1", self.subscriber._tracked)

    async def test_quiet_job_still_running_stays_tracked(self):
        dispatch = AsyncMock(return_value=True)
        engine = AsyncMock(return_value={"id": "job-1", "status": "processing"})
        with patch.object(self.subscriber, "_dispatch_terminal", dispatch), \
                patch("services.evidence_engine_client.get_job", engine):
            self.clock.now += module._QUIET_SWEEP_SECONDS
            await self.subscriber._check_quiet_jobs()

        dispatch.assert_not_awaited()
        self.assertIn("job-1", self.subscriber._tracked)

    async def test_recent_message_defers_the_quiet_sweep(self):
        dispatch = AsyncMock(return_value=True)
        engine = AsyncMock(return_value={"id": "job-1", "status": "completed"})
        with patch.object(self.subscriber, "_dispatch_terminal", dispatch), \
                patch("services.evidence_engine_client.get_job", engine):
            self.clock.now += module._QUIET_SWEEP_SECONDS - 10
            await self.subscriber._handle_message(_message("job-1", "processing"))
            self.clock.now += 10
            await self.subscriber._check_quiet_jobs()

        engine.assert_not_awaited()
        self.assertIn("job-1", self.subscriber._tracked)


def _engine_404(job_id):
    request = httpx.Request("GET", f"http://localhost:8003/jobs/{job_id}")
    response = httpx.Response(404, request=request)
    return httpx.HTTPStatusError("Client error '404 Not Found'", request=request, response=response)


def _merge(job_id):
    return SimpleNamespace(
        id=f"row-{job_id}", engine_job_id=job_id, case_id="case-1", status="processing",
        error_message=None, merged_entity_key=None, source_entity_keys=["a", "b"],
        recycled_source_keys=None, created_by="someone",
    )


class RecoverInFlightTests(unittest.IsolatedAsyncioTestCase):
    """Startup recovery: rows left 'processing' are asked about at the engine."""

    def setUp(self):
        self.subscriber = JobStatusSubscriber()
        self.subscriber._pubsub = AsyncMock()
        self.db = MagicMock()

    async def _recover(self, files, merges, engine):
        self.db.scalars.side_effect = [
            MagicMock(all=MagicMock(return_value=files)),
            MagicMock(all=MagicMock(return_value=merges)),
        ]

        @contextmanager
        def session():
            yield self.db

        with patch("postgres.session.get_background_session", session), \
                patch("services.evidence_engine_client.get_job", engine):
            await self.subscriber._recover_in_flight()

    async def test_merge_job_the_engine_no_longer_has_is_failed_not_tracked(self):
        mj = _merge("gone-1")
        with self.assertLogs(module.logger, level=logging.INFO) as logs:
            await self._recover([], [mj], AsyncMock(side_effect=_engine_404("gone-1")))

        self.assertEqual(mj.status, "failed")
        self.assertEqual(mj.error_message, module._MISSING_MERGE_REASON)
        self.assertEqual(mj.recycled_source_keys, None)  # sources left as they were
        self.assertNotIn("gone-1", self.subscriber._tracked)
        self.subscriber._pubsub.subscribe.assert_not_awaited()
        self.db.commit.assert_called()
        self.assertFalse([line for line in logs.output if "Could not check" in line])

    async def test_merge_job_with_engine_unreachable_is_tracked_and_warned_once(self):
        mj = _merge("job-2")
        engine = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        with self.assertLogs(module.logger, level=logging.WARNING) as logs:
            await self._recover([], [mj], engine)
            self.subscriber._retry_at["job-2"] = 0  # the sweep asks again; still down
            await self.subscriber._check_quiet_jobs()

        self.assertEqual(mj.status, "processing")
        self.assertIn("job-2", self.subscriber._tracked)
        self.subscriber._pubsub.subscribe.assert_awaited_once_with("job:job-2:progress")
        self.assertEqual(sum("job-2" in line for line in logs.output), 1)

    async def test_merge_job_already_failed_at_engine_is_failed(self):
        mj = _merge("job-3")
        engine = AsyncMock(return_value={"id": "job-3", "status": "failed", "error_message": "Failed: llm error"})
        await self._recover([], [mj], engine)

        self.assertEqual(mj.status, "failed")
        self.assertEqual(mj.error_message, "llm error")
        self.assertNotIn("job-3", self.subscriber._tracked)

    async def test_merge_job_already_completed_at_engine_is_handled(self):
        mj = _merge("job-4")
        job = {"id": "job-4", "status": "completed", "merged_entity_key": "m"}
        with patch.object(self.subscriber, "_handle_merge_completion") as handle:
            await self._recover([], [mj], AsyncMock(return_value=job))

        handle.assert_called_once_with(self.db, mj, job, "completed", "case-1")
        self.assertNotIn("job-4", self.subscriber._tracked)

    async def test_merge_job_still_running_is_tracked(self):
        mj = _merge("job-5")
        await self._recover([], [mj], AsyncMock(return_value={"id": "job-5", "status": "processing"}))

        self.assertEqual(mj.status, "processing")
        self.assertIn("job-5", self.subscriber._tracked)

    async def test_evidence_file_the_engine_no_longer_has_is_failed_not_tracked(self):
        ef = SimpleNamespace(id="ef-1", case_id="case-1", engine_job_id="gone-2", original_filename="a.pdf")
        with patch("services.evidence_db_storage.EvidenceDBStorage.mark_processed") as mark, \
                patch("services.evidence_db_storage.EvidenceDBStorage.add_log") as add_log:
            await self._recover([ef], [], AsyncMock(side_effect=_engine_404("gone-2")))

        mark.assert_called_once_with(self.db, ["ef-1"], error=module._MISSING_FILE_REASON)
        self.assertEqual(add_log.call_args.kwargs["level"], "error")
        self.assertNotIn("gone-2", self.subscriber._tracked)
        self.subscriber._pubsub.subscribe.assert_not_awaited()


class QuietSweepMissingJobTests(unittest.IsolatedAsyncioTestCase):
    async def test_tracked_merge_job_that_disappears_is_failed_and_dropped(self):
        subscriber = JobStatusSubscriber()
        subscriber._pubsub = AsyncMock()
        subscriber._tracked["gone-3"] = "case-1"
        subscriber._retry_at["gone-3"] = 0
        mj = _merge("gone-3")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mj

        @contextmanager
        def session():
            yield db

        with patch("postgres.session.get_background_session", session), \
                patch("services.evidence_engine_client.get_job", AsyncMock(side_effect=_engine_404("gone-3"))):
            await subscriber._check_quiet_jobs()

        self.assertEqual(mj.status, "failed")
        self.assertEqual(mj.error_message, module._MISSING_MERGE_REASON)
        self.assertNotIn("gone-3", subscriber._tracked)
        subscriber._pubsub.unsubscribe.assert_awaited_once_with("job:gone-3:progress")


if __name__ == "__main__":
    unittest.main()
