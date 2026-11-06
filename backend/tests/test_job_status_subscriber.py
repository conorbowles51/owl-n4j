import json
import logging
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from services import job_status_subscriber as module
from services.job_status_subscriber import JobStatusSubscriber


def setUpModule():
    # Off PostgreSQL there is no advisory lock to take: these doubles have no database behind them.
    @contextmanager
    def claimed(_merge_id):
        yield True
    patcher = patch.object(module, "_merge_claim", claimed)
    patcher.start()
    unittest.addModuleCleanup(patcher.stop)


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
        rows = {row.id: row for row in files + merges}
        self.db.get.side_effect = lambda model, row_id, **options: rows.get(row_id)
        self.open_sessions = 0

        @contextmanager
        def session():
            self.open_sessions += 1
            try:
                yield self.db
            finally:
                self.open_sessions -= 1

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
        ef = SimpleNamespace(id="ef-1", case_id="case-1", engine_job_id="gone-2", original_filename="a.pdf",
                             status="processing")
        with patch("services.evidence_db_storage.EvidenceDBStorage.mark_processed") as mark, \
                patch("services.evidence_db_storage.EvidenceDBStorage.add_log") as add_log:
            await self._recover([ef], [], AsyncMock(side_effect=_engine_404("gone-2")))

        mark.assert_called_once_with(self.db, ["ef-1"], error=module._MISSING_FILE_REASON)
        self.assertEqual(add_log.call_args.kwargs["level"], "error")
        self.assertNotIn("gone-2", self.subscriber._tracked)
        self.subscriber._pubsub.subscribe.assert_not_awaited()


    async def test_no_session_is_open_while_the_engine_is_asked(self):
        # 1 Nov: the session held across these awaits sat idle in transaction while the loop was blocked.
        ef = SimpleNamespace(id="ef-2", case_id="case-1", engine_job_id="job-6", original_filename="b.pdf",
                             status="processing", summary=None, transcription=None, transcription_segments=None,
                             entity_count=None, relationship_count=None)
        open_while_asked = []

        async def engine(job_id):
            open_while_asked.append(self.open_sessions)
            return {"id": job_id, "status": "completed", "entity_count": 4, "relationship_count": 2}

        with patch("services.evidence_db_storage.EvidenceDBStorage.mark_processed") as mark:
            await self._recover([ef], [_merge("job-7")], AsyncMock(side_effect=engine))

        self.assertEqual(open_while_asked, [0, 0])
        mark.assert_called_once_with(self.db, ["ef-2"], error=None)
        self.assertEqual((ef.entity_count, ef.relationship_count), (4, 2))

    async def test_a_row_settled_while_the_engine_was_asked_is_left_alone(self):
        ef = SimpleNamespace(id="ef-3", case_id="case-1", engine_job_id="job-8", original_filename="c.pdf",
                             status="processing")

        async def engine(job_id):
            ef.status = "processed"  # its own message settled it meanwhile
            return {"id": job_id, "status": "failed", "error_message": "late"}

        with patch("services.evidence_db_storage.EvidenceDBStorage.mark_processed") as mark:
            await self._recover([ef], [], AsyncMock(side_effect=engine))

        mark.assert_not_called()
        self.assertNotIn("job-8", self.subscriber._tracked)


class TerminalWriteThreadTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_database_write_runs_off_the_event_loop_thread(self):
        # 1 Nov: an UPDATE evidence_files run on the loop thread waited on a row lock held by a
        # coroutine of the same loop: neither could move for 2 h 28 min.
        import threading
        subscriber = JobStatusSubscriber()
        threads = []
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        @contextmanager
        def session():
            threads.append(threading.get_ident())
            yield db

        with patch("postgres.session.get_background_session", session), \
                patch("services.evidence_db_storage.EvidenceDBStorage.find_by_engine_job_id", return_value=None):
            handled = await subscriber._dispatch_terminal("job-9", {"job_id": "job-9", "status": "failed"},
                                                          "failed", "case-1")

        self.assertTrue(handled)
        self.assertEqual(len(threads), 1)
        self.assertNotEqual(threads[0], threading.get_ident())


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


class TwoBackendsSettleOneJobOnceTests(unittest.IsolatedAsyncioTestCase):
    """A second backend watches the same engine jobs as the first (its start recovers every job in flight); both hear
    the one terminal message. The side effects of settling must happen once."""

    @staticmethod
    def _db(rows):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = rows.get("merge")
        return db

    async def _settle_from_two_backends(self, db, job_id, status, detail=None):
        @contextmanager
        def session():
            yield db
        first, second = JobStatusSubscriber(), JobStatusSubscriber()
        for subscriber in (first, second):
            subscriber._pubsub = AsyncMock()
            subscriber._tracked[job_id] = "case-1"
        message = {"job_id": job_id, "status": status}
        with patch("postgres.session.get_background_session", session), \
                patch("services.evidence_engine_client.get_job", AsyncMock(return_value=detail or {})):
            await first._settle(job_id, message, status)
            await second._settle(job_id, message, status)
        self.assertNotIn(job_id, first._tracked)
        self.assertNotIn(job_id, second._tracked)

    async def test_a_merge_is_completed_once_by_two_backends(self):
        merge = _merge("merge-1")
        db = self._db({"merge": merge})
        calls = []

        def complete(subscriber, db_, row, data, status, case_id):
            calls.append(row)
            row.status = "completed"

        with patch.object(JobStatusSubscriber, "_handle_merge_completion", complete):
            await self._settle_from_two_backends(db, "merge-1", "completed")
        self.assertEqual(len(calls), 1)

    async def test_a_file_gets_one_completed_line_from_two_backends(self):
        file = SimpleNamespace(id="file-1", case_id="case-1", original_filename="a.pdf", status="processing",
                               summary=None, entity_count=None, relationship_count=None)
        db = self._db({})
        extras = []
        db.scalars.return_value.all.side_effect = lambda: list(extras)

        def processed(db_, ids, error=None):
            file.status = "failed" if error else "processed"

        with patch("services.evidence_db_storage.EvidenceDBStorage.find_by_engine_job_id", return_value=file), \
                patch("services.evidence_db_storage.EvidenceDBStorage.mark_processed", processed), \
                patch("services.evidence_db_storage.EvidenceDBStorage.add_log",
                      lambda db_, **line: extras.append(line["extra"])):
            await self._settle_from_two_backends(db, "file-job", "completed", {"entity_count": 3})
        self.assertEqual(extras, [{"engine_job_id": "file-job"}])

    async def test_the_log_line_is_written_when_the_jobs_poll_settled_the_row_first(self):
        file = SimpleNamespace(id="file-4", case_id="case-1", original_filename="d.pdf", status="processed",
                               summary="from the poll", entity_count=3, relationship_count=1)
        db = self._db({})
        db.scalars.return_value.all.side_effect = lambda: []
        lines = []
        with patch("services.evidence_db_storage.EvidenceDBStorage.find_by_engine_job_id", return_value=file), \
                patch("services.evidence_db_storage.EvidenceDBStorage.mark_processed") as written, \
                patch("services.evidence_db_storage.EvidenceDBStorage.add_log",
                      lambda db_, **line: lines.append(line["message"])):
            @contextmanager
            def session():
                yield db
            with patch("postgres.session.get_background_session", session):
                JobStatusSubscriber()._write_terminal("file-job-4", {}, {"entity_count": 3}, "completed", "case-1")
        written.assert_not_called()
        self.assertEqual(file.summary, "from the poll")
        self.assertEqual(len(lines), 1)

    async def test_a_merge_another_backend_is_settling_is_left_to_it(self):
        merge = _merge("merge-2")
        db = self._db({"merge": merge})

        @contextmanager
        def taken(_merge_id):
            yield False

        with patch.object(module, "_merge_claim", taken), \
                patch.object(JobStatusSubscriber, "_handle_merge_completion") as handle:
            settled = JobStatusSubscriber()._settle_merge(db, merge, {}, "completed", "case-1")
        self.assertFalse(settled)
        handle.assert_not_called()

    async def test_recovery_leaves_a_row_held_elsewhere_and_watches_it(self):
        file = SimpleNamespace(id="file-5", engine_job_id="job-5", status="processing")
        db = MagicMock()
        # The plain read finds the row; the locked read skips it.
        db.get.side_effect = lambda model, row_id, **options: None if options else file

        @contextmanager
        def session():
            yield db

        with patch("postgres.session.get_background_session", session):
            subscribe = JobStatusSubscriber()._apply_in_flight(
                [("file", "file-5", "job-5", "case-1", {"status": "completed"}, None)])
        self.assertEqual(subscribe, [("job-5", "case-1", None)])

    async def test_recovery_commits_each_row_before_locking_the_next(self):
        rows = {i: SimpleNamespace(id=i, engine_job_id=f"job-{i}", status="processing", summary=None) for i in (1, 2)}
        db = MagicMock()
        order = []
        db.get.side_effect = lambda model, row_id, **options: (order.append("lock") if options else None, rows[row_id])[1]
        db.commit.side_effect = lambda: order.append("commit")

        @contextmanager
        def session():
            yield db

        with patch("postgres.session.get_background_session", session), \
                patch("services.evidence_db_storage.EvidenceDBStorage.mark_processed"):
            JobStatusSubscriber()._apply_in_flight(
                [("file", i, f"job-{i}", "case-1", {"status": "completed"}, None) for i in rows])
        first, second = [i for i, step in enumerate(order) if step == "lock"]
        self.assertIn("commit", order[first:second])

    async def test_a_failed_file_whose_job_completes_is_still_written(self):
        # What settled means must not swallow a state that disagrees with the row.
        file = SimpleNamespace(id="file-2", case_id="case-1", original_filename="b.pdf", status="failed",
                               summary=None, entity_count=None, relationship_count=None)
        written = []
        with patch("services.evidence_db_storage.EvidenceDBStorage.find_by_engine_job_id", return_value=file), \
                patch("services.evidence_db_storage.EvidenceDBStorage.mark_processed",
                      lambda db_, ids, error=None: written.append(ids)), \
                patch("services.evidence_db_storage.EvidenceDBStorage.add_log", lambda db_, **line: None):
            await self._settle_from_two_backends(self._db({}), "file-job-2", "completed")
        self.assertEqual(len(written), 2)  # no row state to read in this double: each backend still tries

    async def test_a_cancelled_job_does_not_mark_its_file_failed(self):
        """Fails on the old code: every status 'failed' went through mark_processed(error=...)."""
        file = SimpleNamespace(id="file-4", case_id="case-1", original_filename="d.pdf", status="processing",
                               summary=None, entity_count=None, relationship_count=None)
        synced, failed, lines = [], [], []
        with patch("services.evidence_db_storage.EvidenceDBStorage.find_by_engine_job_id", return_value=file), \
                patch("services.evidence_db_storage.EvidenceDBStorage.mark_processed",
                      lambda db_, ids, error=None: failed.append(ids)), \
                patch("services.evidence_job_sync._sync_db_record_from_job", lambda *a, **k: synced.append(a)), \
                patch.object(module, "_log_once", lambda db_, rec, job, level, text: lines.append((level, text))):
            await self._settle_from_two_backends(self._db({}), "cancelled-job", "failed",
                                                 {"cancelled_at": "2026-11-05T23:00:00"})
        self.assertTrue(synced)
        self.assertEqual(failed, [])
        self.assertTrue(all(level == "info" and text.startswith("Cancelled:") for level, text in lines))

    async def test_a_new_transcript_of_a_published_file_is_not_taken_for_settled(self):
        file = SimpleNamespace(id="file-3", case_id="case-1", original_filename="c.mp3", status="processed",
                               summary=None, entity_count=None, relationship_count=None)
        synced = []
        with patch("services.evidence_db_storage.EvidenceDBStorage.find_by_engine_job_id", return_value=file), \
                patch("services.evidence_job_sync._sync_db_record_from_job", lambda *a, **k: synced.append(a)), \
                patch("services.evidence_db_storage.EvidenceDBStorage.add_log", lambda db_, **line: None):
            await self._settle_from_two_backends(self._db({}), "audio-job", "completed", {"job_type": "audio_review"})
        self.assertTrue(synced)
