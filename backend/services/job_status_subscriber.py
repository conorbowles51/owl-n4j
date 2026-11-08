"""
Job Status Subscriber — listens to Redis pub/sub for evidence engine job
progress and syncs terminal states (completed/failed) to Postgres.

Replaces the old _track_engine_jobs() polling daemon thread.
"""

import asyncio
from contextlib import contextmanager
import json
import logging
import time
from typing import Dict, Set

from config import REDIS_URL

logger = logging.getLogger(__name__)

# Map engine statuses to backend EvidenceFile statuses
_ENGINE_STATUS_MAP = {
    "completed": "processed",
    "failed": "failed",
}

# The engine publishes a terminal status once. When syncing it raises (e.g. a
# Postgres deadlock) no later message comes, so the subscriber retries on its
# own: backoff after a failed sync, and a sweep that asks the engine directly
# about tracked jobs that have been quiet (covers messages lost in transit).
_RETRY_DELAYS = (5, 30, 120, 300)
_QUIET_SWEEP_SECONDS = 300

# The engine answers 404 for a job it no longer has. That is final: the job
# will never report a terminal status, so the row is failed with a plain reason
# instead of being tracked forever.
_MISSING_MERGE_REASON = (
    "The processing job for this merge no longer exists, so the merge did not "
    "finish. Run the merge again."
)
_MISSING_FILE_REASON = (
    "The processing job for this file no longer exists, so processing did not "
    "finish. Process the file again."
)


def _engine_job_missing(exc: Exception) -> bool:
    import httpx
    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response is not None
        and exc.response.status_code == 404
    )


def _missing_job(job_id: str) -> dict:
    """A synthetic failed engine job for one the engine no longer has."""
    return {"job_id": job_id, "status": "failed", "engine_job_missing": True}


def _failure_reason(payload: dict, missing_reason: str) -> str | None:
    if payload.get("engine_job_missing"):
        return missing_reason
    return _extract_failure_message(payload)


def _extract_failure_message(payload: dict) -> str | None:
    for key in ("error_message", "message"):
        value = payload.get(key)
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned.removeprefix("Failed: ").strip()
    return None


def _merged_entity_key(payload: dict) -> str | None:
    direct = payload.get("merged_entity_key")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    pipeline_state = payload.get("pipeline_state")
    if not isinstance(pipeline_state, dict):
        return None
    merge_result = pipeline_state.get("merge_result")
    if not isinstance(merge_result, dict):
        return None
    persisted = merge_result.get("merged_entity_key")
    if isinstance(persisted, str) and persisted.strip():
        return persisted.strip()
    return None


# The row states that already record each terminal state. A state that disagrees is still written, as before: a file
# marked failed (the reaper, a lost engine) whose job then completes becomes processed.
_FILE_SETTLED = {"completed": ("processed",), "failed": ("failed",)}
_MERGE_SETTLED = {"completed": ("completed", "partial"), "failed": ("failed",)}


def _already_settled(row_status, engine_status, settled) -> bool:
    return row_status in settled.get(engine_status, ())


def _log_once(db, row, job_id, level, message):
    """The file's line for this engine job, unless a backend wrote it first (the caller holds the row's lock)."""
    from sqlalchemy import select
    from postgres.models.evidence import IngestionLog
    from services.evidence_db_storage import EvidenceDBStorage
    extras = db.scalars(select(IngestionLog.extra).where(IngestionLog.evidence_file_id == row.id,
                                                         IngestionLog.message == message)).all()
    if any((extra or {}).get("engine_job_id") == job_id for extra in extras):
        return
    EvidenceDBStorage.add_log(db, case_id=row.case_id, evidence_file_id=row.id, filename=row.original_filename,
                              level=level, message=message, extra={"engine_job_id": job_id})


@contextmanager
def _merge_claim(merge_id):
    """True while this process settles the merge. A session-level advisory lock on a connection of its own: settling
    commits as it goes (each source entity archived), which ends any row lock while the row is still 'processing'.
    Closing the connection releases it, if this worker dies mid-way."""
    from sqlalchemy import text
    from postgres.session import _get_background_engine
    engine = _get_background_engine()
    if engine.dialect.name != "postgresql":
        yield True
        return
    key = "hashtextextended('loupe.merge_job:' || CAST(:id AS text), 0)"
    with engine.connect() as connection:
        held = False
        try:
            held = bool(connection.execute(text(f"SELECT pg_try_advisory_lock({key})"), dict(id=str(merge_id))).scalar())
            connection.commit()
            yield held
        finally:
            if held:
                connection.execute(text(f"SELECT pg_advisory_unlock({key})"), dict(id=str(merge_id)))
                connection.commit()


class JobStatusSubscriber:
    """
    Async background task that subscribes to Redis channels for active
    evidence engine jobs and syncs their terminal states to Postgres.
    """

    def __init__(self):
        self._redis = None
        self._pubsub = None
        self._tracked: Dict[str, str] = {}  # job_id -> case_id
        self._last_seen: Dict[str, float] = {}  # job_id -> monotonic time of last message/check
        self._retry_at: Dict[str, float] = {}  # job_id -> monotonic time the failed sync is retried
        self._failures: Dict[str, int] = {}  # job_id -> consecutive failed syncs
        self._warned: Set[str] = set()  # jobs already warned unreachable this start
        self._next_sweep = time.monotonic() + _QUIET_SWEEP_SECONDS
        self._task: asyncio.Task | None = None

    async def start(self):
        """Start the subscriber background task."""
        import redis.asyncio as aioredis
        self._redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        self._pubsub = self._redis.pubsub()
        self._task = asyncio.create_task(self._run(), name="job-status-subscriber")
        logger.info("Job status subscriber started")

        # Recover in-flight jobs from previous run
        await self._recover_in_flight()

    async def stop(self):
        """Stop the subscriber and clean up."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._pubsub:
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()
        logger.info("Job status subscriber stopped")

    @property
    def running(self) -> bool:
        """True inside the backend once start() ran; a script outside it has no subscription to add to."""
        return self._pubsub is not None

    async def track_jobs(self, job_ids: list[str], case_id: str) -> bool:
        """Add job IDs to the subscriber's watch list. Returns False, tracking nothing, when the subscriber is not
        running (a script outside the backend): the jobs' files settle when the case's jobs are next synced."""
        if not self.running:
            logger.info("Job status subscriber not running; %d job(s) settle on the next sync", len(job_ids))
            return False
        for jid in job_ids:
            self._tracked[jid] = case_id
            self._last_seen[jid] = time.monotonic()
            channel = f"job:{jid}:progress"
            await self._pubsub.subscribe(channel)
            logger.debug("Subscribed to %s", channel)
        return True

    async def recover_after_handover(self):
        """A release ran this backend beside the old one: pick up what the old one started after this one's start."""
        await self._recover_in_flight()

    async def _recover_in_flight(self):
        """On startup, find EvidenceFiles and MergeJobs stuck in 'processing'
        and re-subscribe (or drain immediately if already terminal).

        No session is open while the engine is asked (the questions are
        awaited on the event loop), and the database work runs in a thread:
        a session held across those awaits kept its transaction open, and
        blocking database calls on the loop thread waited on row locks whose
        owners needed the loop to finish (1 Nov: 2 h 28 min deadlock)."""
        try:
            stuck_files, stuck_merges = await asyncio.to_thread(self._load_in_flight)
            if stuck_files:
                logger.info("Recovering %d in-flight evidence-file jobs", len(stuck_files))
            if stuck_merges:
                logger.info("Recovering %d in-flight merge jobs", len(stuck_merges))

            from services import evidence_engine_client

            answers = []
            for kind, row_id, jid, case_id in stuck_files + stuck_merges:
                try:
                    answers.append((kind, row_id, jid, case_id, await evidence_engine_client.get_job(jid), None))
                except Exception as e:
                    answers.append((kind, row_id, jid, case_id, None, e))

            to_subscribe = await asyncio.to_thread(self._apply_in_flight, answers)
            for jid, case_id, error in to_subscribe:
                # Still running, or the engine is unreachable: subscribe, catch up later.
                self._tracked[jid] = case_id
                await self._pubsub.subscribe(f"job:{jid}:progress")
                if error is not None:
                    self._warn_unreachable(jid, error)
        except Exception as e:
            logger.warning("Failed to recover in-flight jobs: %s", e)

    @staticmethod
    def _load_in_flight():
        """(kind, row id, engine job id, case id) for every row left processing, read in one short session."""
        from postgres.session import get_background_session
        from postgres.soft_delete import SHOW_DELETED
        from sqlalchemy import select
        from postgres.models.evidence import EvidenceFile
        from postgres.models.merge_job import MergeJob

        with get_background_session() as db:
            # A job of a file or case in Deleted items still lands on its row, so a restore shows the true state.
            db.info[SHOW_DELETED] = True
            files = [("file", ef.id, ef.engine_job_id, str(ef.case_id)) for ef in db.scalars(
                select(EvidenceFile).where(
                    EvidenceFile.status == "processing",
                    EvidenceFile.engine_job_id.isnot(None),
                )
            ).all()]
            # Recover MergeJobs the same way. Without this, a backend
            # restart mid-merge leaves source entities un-recycled.
            merges = [("merge", mj.id, mj.engine_job_id, str(mj.case_id)) for mj in db.scalars(
                select(MergeJob).where(
                    MergeJob.status == "processing",
                    MergeJob.engine_job_id.isnot(None),
                )
            ).all()]
        return files, merges

    def _apply_in_flight(self, answers):
        """Write the engine's answers (in a thread). Returns (job id, case id, error) to subscribe to."""
        from postgres.session import get_background_session
        from postgres.soft_delete import SHOW_DELETED
        from postgres.models.evidence import EvidenceFile
        from postgres.models.merge_job import MergeJob
        from services.evidence_db_storage import EvidenceDBStorage

        to_subscribe = []
        with get_background_session() as db:
            # A job of a file or case in Deleted items still lands on its row, so a restore shows the true state.
            db.info[SHOW_DELETED] = True
            for kind, row_id, jid, case_id, job, error in answers:
                model = EvidenceFile if kind == "file" else MergeJob
                row = db.get(model, row_id)
                if row is None or row.status != "processing" or row.engine_job_id != jid:
                    continue  # changed while the engine was asked; its own path settles it
                terminal = job is not None and job.get("status", "") in ("completed", "failed")
                if terminal or (error is not None and _engine_job_missing(error)):
                    # This row is about to be written. One row at a time, never waiting while holding another: a row
                    # held elsewhere (a save, the other workers and backends recovering the same rows) is left to the
                    # quiet sweep, and the commit below ends this row's lock before the next one.
                    db.commit()
                    row = db.get(model, row_id, with_for_update=dict(skip_locked=True), populate_existing=True)
                    if row is None:
                        to_subscribe.append((jid, case_id, None))
                        continue
                    if row.status != "processing" or row.engine_job_id != jid:
                        db.rollback()
                        continue
                if error is not None:
                    if not _engine_job_missing(error):
                        to_subscribe.append((jid, case_id, error))
                    elif kind == "file":
                        self._fail_missing_file(db, row)
                        logger.info("Engine no longer has job %s; file marked failed", jid)
                        db.commit()
                    elif self._settle_merge(db, row, _missing_job(jid), "failed", case_id):
                        logger.info("Engine no longer has merge job %s; merge marked failed", jid)
                    else:
                        to_subscribe.append((jid, case_id, None))
                    continue
                engine_status = job.get("status", "")
                if engine_status not in ("completed", "failed"):
                    to_subscribe.append((jid, case_id, None))
                    continue
                if kind == "merge":
                    if self._settle_merge(db, row, job, engine_status, case_id):
                        logger.info("Recovered merge job %s: %s", jid, engine_status)
                    else:
                        to_subscribe.append((jid, case_id, None))
                    continue
                if job.get('job_type') == 'audio_review' or job.get('cancelled_at') or (
                        job.get('pipeline_state') or {}).get('transcript_revision_id'):
                    from services.evidence_job_sync import _sync_db_record_from_job
                    _sync_db_record_from_job(row, job, db=db)
                else:
                    # Already terminal — sync immediately
                    ef = row
                    err = _extract_failure_message(job) if engine_status == "failed" else None
                    EvidenceDBStorage.mark_processed(db, [ef.id], error=err)
                    if engine_status == "completed":
                        doc_summary = job.get("document_summary")
                        if doc_summary:
                            ef.summary = doc_summary
                        transcription = job.get("transcription")
                        if transcription is not None:
                            ef.transcription = transcription
                        transcription_segments = job.get("transcription_segments")
                        if transcription_segments is not None:
                            ef.transcription_segments = transcription_segments
                        ec = job.get("entity_count")
                        rc = job.get("relationship_count")
                        if ec is not None:
                            ef.entity_count = ec
                        if rc is not None:
                            ef.relationship_count = rc
                db.commit()
                logger.info("Recovered job %s: %s", jid, engine_status)
            db.commit()
        return to_subscribe

    async def _run(self):
        """Main subscriber loop."""
        while True:
            try:
                if not self._tracked:
                    # No jobs to watch — sleep and retry
                    await asyncio.sleep(1)
                    continue
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message and message["type"] == "message":
                    await self._handle_message(message)
                await self._check_quiet_jobs()
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Error in job status subscriber: %s", e)
                await asyncio.sleep(1)

    async def _handle_message(self, message):
        """Process a single Redis pub/sub message. Subscription is only
        torn down after the handler returns success — a failure leaves the
        subscription intact so the next message gets another chance."""
        try:
            data = json.loads(message["data"])
        except (json.JSONDecodeError, TypeError):
            return

        job_id = data.get("job_id", "")
        status = data.get("status", "")
        if job_id in self._tracked:
            self._last_seen[job_id] = time.monotonic()

        if status not in ("completed", "failed"):
            return  # Only sync terminal states

        await self._settle(job_id, data, status)

    async def _settle(self, job_id: str, data: dict, status: str):
        """Sync one terminal state. On success stop tracking the job; on a
        raise keep it tracked and schedule a retry, since the engine will not
        publish this terminal status again."""
        case_id = self._tracked.get(job_id)

        try:
            handled = await self._dispatch_terminal(job_id, data, status, case_id)
        except Exception:
            failures = self._failures.get(job_id, 0) + 1
            self._failures[job_id] = failures
            delay = _RETRY_DELAYS[min(failures, len(_RETRY_DELAYS)) - 1]
            self._retry_at[job_id] = time.monotonic() + delay
            logger.exception(
                "Handler raised for %s (attempt %d); retrying in %ds",
                job_id, failures, delay,
            )
            return

        if handled:
            self._forget(job_id)
            try:
                await self._pubsub.unsubscribe(f"job:{job_id}:progress")
            except Exception:
                pass

    def _warn_unreachable(self, job_id: str, exc: Exception):
        """Warn once per job per start; later failures to reach the engine
        about the same job are debug only."""
        if job_id in self._warned:
            logger.debug("Could not check engine job %s: %s", job_id, exc)
            return
        self._warned.add(job_id)
        logger.warning("Could not check engine job %s (will keep retrying): %s", job_id, exc)

    @staticmethod
    def _fail_missing_file(db, ef):
        from services.evidence_db_storage import EvidenceDBStorage

        EvidenceDBStorage.mark_processed(db, [ef.id], error=_MISSING_FILE_REASON)
        EvidenceDBStorage.add_log(
            db,
            case_id=ef.case_id,
            evidence_file_id=ef.id,
            filename=ef.original_filename,
            level="error",
            message=f"Failed: {ef.original_filename}: {_MISSING_FILE_REASON}",
        )

    def _forget(self, job_id: str):
        self._tracked.pop(job_id, None)
        self._last_seen.pop(job_id, None)
        self._retry_at.pop(job_id, None)
        self._failures.pop(job_id, None)

    async def _check_quiet_jobs(self):
        """Ask the engine directly about tracked jobs whose sync is due for a
        retry, and (every _QUIET_SWEEP_SECONDS) about jobs quiet that long. A
        job the engine reports terminal is settled as if its message arrived."""
        now = time.monotonic()
        due = [jid for jid, at in self._retry_at.items() if at <= now and jid in self._tracked]
        if now >= self._next_sweep:
            self._next_sweep = now + _QUIET_SWEEP_SECONDS
            due += [
                jid for jid in self._tracked
                if jid not in self._retry_at
                and now - self._last_seen.get(jid, 0) >= _QUIET_SWEEP_SECONDS
            ]
        if not due:
            return

        from services import evidence_engine_client

        for jid in due:
            self._last_seen[jid] = now
            try:
                job = await evidence_engine_client.get_job(jid)
            except Exception as e:
                if _engine_job_missing(e):
                    # The engine dropped the job: it will never finish.
                    await self._settle(jid, _missing_job(jid), "failed")
                    continue
                # Engine unreachable: keep the retry pending, check again later.
                if jid in self._retry_at:
                    self._retry_at[jid] = now + _RETRY_DELAYS[-1]
                    self._warn_unreachable(jid, e)
                else:
                    logger.debug("Could not check quiet engine job %s: %s", jid, e)
                continue
            status = job.get("status", "")
            if status in ("completed", "failed"):
                await self._settle(jid, {**job, "job_id": jid, "status": status}, status)
            else:
                # Not terminal after all; the next message will sync it.
                self._retry_at.pop(jid, None)
                self._failures.pop(jid, None)

    async def _dispatch_terminal(self, job_id: str, data: dict, status: str, case_id: str | None) -> bool:
        """Route a terminal message to the right DB writer. Returns True only
        when the work succeeded; False/raise leaves the subscription in place."""
        from services import evidence_engine_client

        job_detail = data
        if status in ('completed', 'failed'):
            try:
                fetched_detail = await evidence_engine_client.get_job(job_id)
                job_detail = {**data, **fetched_detail}
            except Exception:
                logger.exception("Failed to fetch completed engine job %s detail", job_id)

        # Blocking database work runs in a thread, never on the event loop: an UPDATE
        # waiting on a row lock froze the loop, and with it the coroutine that held
        # the lock and needed the loop to commit (1 Nov, 2 h 28 min).
        return await asyncio.to_thread(self._write_terminal, job_id, data, job_detail, status, case_id)

    def _write_terminal(self, job_id: str, data: dict, job_detail: dict, status: str, case_id: str | None) -> bool:
        from postgres.session import get_background_session
        from postgres.soft_delete import SHOW_DELETED
        from postgres.models.merge_job import MergeJob
        from services.evidence_db_storage import EvidenceDBStorage

        with get_background_session() as db:
            # A job of a file or case in Deleted items still lands on its row, so a restore shows the true state.
            db.info[SHOW_DELETED] = True
            merge_job = db.query(MergeJob).filter(
                MergeJob.engine_job_id == job_id
            ).first()
            if merge_job:
                return self._settle_merge(db, merge_job, job_detail, status, case_id)

            db_rec = EvidenceDBStorage.find_by_engine_job_id(db, job_id)
            if not db_rec:
                logger.warning("No DB record found for engine job %s", job_id)
                # No matching row will ever exist — drop the subscription.
                return True

            db.refresh(db_rec, with_for_update=True)
            audio = job_detail.get('job_type') == 'audio_review' or bool(
                (job_detail.get('pipeline_state') or {}).get('transcript_revision_id'))
            # Every worker of every backend may watch the same job (the recovery at start subscribes to all of them),
            # and the jobs poll settles the row too: the row's lock decides, and whoever comes second leaves the row
            # alone. Its log line is still written once. Audio stays out: a new transcript of a published file
            # finishes with the row already 'processed'.
            cancelled = bool(job_detail.get('cancelled_at'))  # a cancel is not a failure: the file is not marked failed
            settled = not audio and not cancelled and _already_settled(db_rec.status, status, _FILE_SETTLED)

            err = _failure_reason(data, _MISSING_FILE_REASON) if status == "failed" else None
            from services.evidence_job_sync import _sync_db_record_from_job
            if audio or cancelled:
                _sync_db_record_from_job(db_rec, {**job_detail, 'id': job_id, 'status': status,
                    **({'error_message': err} if err else {})}, db=db)
            elif not settled:
                EvidenceDBStorage.mark_processed(db, [db_rec.id], error=err)
                if status == 'completed':
                    for field in ('transcription', 'transcription_segments'):
                        if job_detail.get(field) is not None:
                            setattr(db_rec, field, job_detail[field])

            if status == 'completed' and job_detail.get('job_type') == 'audio_review':
                EvidenceDBStorage.add_log(db, case_id=db_rec.case_id, evidence_file_id=db_rec.id,
                    filename=db_rec.original_filename, level='info',
                    message=f'Transcript ready for review: {db_rec.original_filename}. Graph processing has not started.')
            elif status == "completed":
                entity_count = job_detail.get("entity_count")
                rel_count = job_detail.get("relationship_count")
                if not settled:
                    doc_summary = job_detail.get("document_summary")
                    if doc_summary:
                        db_rec.summary = doc_summary
                    if entity_count is not None:
                        db_rec.entity_count = entity_count
                    if rel_count is not None:
                        db_rec.relationship_count = rel_count

                _log_once(db, db_rec, job_id, "info",
                          f"Completed: {db_rec.original_filename} ({entity_count or 0} entities, {rel_count or 0} relationships)")
            elif cancelled:
                _log_once(db, db_rec, job_id, "info", f"Cancelled: {db_rec.original_filename}: {err}")
            else:
                _log_once(db, db_rec, job_id, "error", f"Failed: {db_rec.original_filename}: {err or 'Unknown error'}")

            db.commit()
            logger.info("Synced job %s → %s", job_id, status)
            return True

    def _settle_merge(self, db, merge_job, data: dict, status: str, case_id: str | None) -> bool:
        """Once, whichever worker of whichever backend gets here. False: another is settling it now; the quiet sweep
        looks again and finds it settled."""
        with _merge_claim(merge_job.id) as claimed:
            if not claimed:
                db.rollback()
                return False
            db.refresh(merge_job)
            if _already_settled(merge_job.status, status, _MERGE_SETTLED):
                db.rollback()
                return True
            self._handle_merge_completion(db, merge_job, data, status, case_id)
            return True

    def _handle_merge_completion(self, db, merge_job, data: dict, status: str, case_id: str | None):
        """Handle completion of an entity merge job. On `completed`, soft-delete
        every source entity and record which actually got recycled — partial
        success is reflected as status='partial' rather than masked as 'completed'."""
        try:
            if status == "completed":
                merged_key = _merged_entity_key(data)
                merge_job.merged_entity_key = merged_key
                if not merged_key:
                    merge_job.status = "failed"
                    merge_job.error_message = (
                        "Merge engine completed without a persisted result key; "
                        "source entities were left active."
                    )
                    db.commit()
                    logger.error(
                        "Merge job %s completed without a result key; sources retained",
                        merge_job.engine_job_id,
                    )
                    return

                from services.neo4j import neo4j_service

                merge_case_id = case_id or str(merge_job.case_id)
                source_keys = list(merge_job.source_entity_keys or [])
                recycled: list[str] = []
                failed: list[str] = []

                for entity_key in source_keys:
                    try:
                        neo4j_service.soft_delete_entity(
                            node_key=entity_key,
                            case_id=merge_case_id,
                            deleted_by=merge_job.created_by or "system",
                            reason="merged",
                            db=db,
                        )
                        recycled.append(entity_key)
                        logger.info(
                            "Soft-deleted merged source entity %s", entity_key,
                        )
                    except Exception as e:
                        failed.append(entity_key)
                        logger.error(
                            "Failed to soft-delete source entity %s: %s",
                            entity_key, e,
                        )

                merge_job.recycled_source_keys = recycled
                if merged_key:
                    from services.significant_service import (
                        transfer_significant_membership_after_merge,
                    )

                    transfer_significant_membership_after_merge(
                        db,
                        case_id=merge_job.case_id,
                        source_entity_keys=source_keys,
                        merged_entity_key=merged_key,
                    )
                    from services.dossier_service import transfer_dossiers_after_merge

                    transfer_dossiers_after_merge(
                        db,
                        case_id=merge_job.case_id,
                        source_entity_keys=source_keys,
                        merged_entity_key=merged_key,
                    )
                if failed:
                    merge_job.status = "partial"
                    merge_job.error_message = (
                        f"Failed to recycle {len(failed)} of {len(source_keys)} "
                        f"sources: {failed}"
                    )
                else:
                    merge_job.status = "completed"

                logger.info(
                    "Merge job %s %s: merged %d entities → %s (recycled %d, failed %d)",
                    merge_job.engine_job_id,
                    merge_job.status,
                    len(source_keys),
                    merged_key,
                    len(recycled),
                    len(failed),
                )
            else:
                err = _failure_reason(data, _MISSING_MERGE_REASON)
                merge_job.status = "failed"
                merge_job.error_message = err
                logger.error(
                    "Merge job %s failed: %s",
                    merge_job.engine_job_id, err,
                )

            db.commit()
        except Exception as e:
            logger.error("Failed to handle merge completion for %s: %s", merge_job.engine_job_id, e)
            db.rollback()
            raise


# Module-level singleton
_subscriber: JobStatusSubscriber | None = None


def get_subscriber() -> JobStatusSubscriber:
    global _subscriber
    if _subscriber is None:
        _subscriber = JobStatusSubscriber()
    return _subscriber
