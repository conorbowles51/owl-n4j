import json
import unittest
from unittest.mock import AsyncMock, patch

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


if __name__ == "__main__":
    unittest.main()
