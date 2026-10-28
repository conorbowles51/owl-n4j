"""
Job Status Subscriber — listens to Redis pub/sub for evidence engine job
progress and syncs terminal states (completed/failed) to Postgres.

Replaces the old _track_engine_jobs() polling daemon thread.
"""

import asyncio
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

    async def track_jobs(self, job_ids: list[str], case_id: str):
        """Add job IDs to the subscriber's watch list."""
        for jid in job_ids:
            self._tracked[jid] = case_id
            self._last_seen[jid] = time.monotonic()
            channel = f"job:{jid}:progress"
            await self._pubsub.subscribe(channel)
            logger.debug("Subscribed to %s", channel)

    async def _recover_in_flight(self):
        """On startup, find EvidenceFiles and MergeJobs stuck in 'processing'
        and re-subscribe (or drain immediately if already terminal)."""
        try:
            from postgres.session import get_background_session
            from services.evidence_db_storage import EvidenceDBStorage
            from services import evidence_engine_client

            with get_background_session() as db:
                from sqlalchemy import select
                from postgres.models.evidence import EvidenceFile
                from postgres.models.merge_job import MergeJob

                stuck = list(db.scalars(
                    select(EvidenceFile).where(
                        EvidenceFile.status == "processing",
                        EvidenceFile.engine_job_id.isnot(None),
                    )
                ).all())

                if stuck:
                    logger.info("Recovering %d in-flight evidence-file jobs", len(stuck))

                for ef in stuck:
                    jid = ef.engine_job_id
                    case_id = str(ef.case_id)

                    # Check current status from engine
                    try:
                        job = await evidence_engine_client.get_job(jid)
                        engine_status = job.get("status", "")

                        if engine_status in ("completed", "failed"):
                            # Already terminal — sync immediately
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
                            logger.info("Recovered job %s: %s", jid, engine_status)
                        else:
                            # Still running — subscribe for updates
                            self._tracked[jid] = case_id
                            await self._pubsub.subscribe(f"job:{jid}:progress")
                    except Exception as e:
                        if _engine_job_missing(e):
                            self._fail_missing_file(db, ef)
                            logger.info("Engine no longer has job %s; file marked failed", jid)
                            continue
                        # Engine unreachable — subscribe anyway, will catch up later
                        self._tracked[jid] = case_id
                        await self._pubsub.subscribe(f"job:{jid}:progress")
                        self._warn_unreachable(jid, e)

                # Recover MergeJobs the same way. Without this, a backend
                # restart mid-merge leaves source entities un-recycled.
                stuck_merges = list(db.scalars(
                    select(MergeJob).where(
                        MergeJob.status == "processing",
                        MergeJob.engine_job_id.isnot(None),
                    )
                ).all())

                if stuck_merges:
                    logger.info("Recovering %d in-flight merge jobs", len(stuck_merges))

                for mj in stuck_merges:
                    jid = mj.engine_job_id
                    case_id = str(mj.case_id)
                    try:
                        job = await evidence_engine_client.get_job(jid)
                        engine_status = job.get("status", "")
                        if engine_status in ("completed", "failed"):
                            self._handle_merge_completion(db, mj, job, engine_status, case_id)
                            logger.info("Recovered merge job %s: %s", jid, engine_status)
                        else:
                            self._tracked[jid] = case_id
                            await self._pubsub.subscribe(f"job:{jid}:progress")
                    except Exception as e:
                        if _engine_job_missing(e):
                            self._handle_merge_completion(db, mj, _missing_job(jid), "failed", case_id)
                            logger.info("Engine no longer has merge job %s; merge marked failed", jid)
                            continue
                        self._tracked[jid] = case_id
                        await self._pubsub.subscribe(f"job:{jid}:progress")
                        self._warn_unreachable(jid, e)

                db.commit()
        except Exception as e:
            logger.warning("Failed to recover in-flight jobs: %s", e)

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
        from postgres.session import get_background_session
        from postgres.models.merge_job import MergeJob
        from services.evidence_db_storage import EvidenceDBStorage
        from services import evidence_engine_client

        job_detail = data
        if status == "completed":
            try:
                fetched_detail = await evidence_engine_client.get_job(job_id)
                job_detail = {**data, **fetched_detail}
            except Exception:
                logger.exception("Failed to fetch completed engine job %s detail", job_id)

        with get_background_session() as db:
            merge_job = db.query(MergeJob).filter(
                MergeJob.engine_job_id == job_id
            ).first()
            if merge_job:
                self._handle_merge_completion(db, merge_job, job_detail, status, case_id)
                return True

            db_rec = EvidenceDBStorage.find_by_engine_job_id(db, job_id)
            if not db_rec:
                logger.warning("No DB record found for engine job %s", job_id)
                # No matching row will ever exist — drop the subscription.
                return True

            err = _failure_reason(data, _MISSING_FILE_REASON) if status == "failed" else None
            EvidenceDBStorage.mark_processed(db, [db_rec.id], error=err)

            if status == "completed":
                doc_summary = job_detail.get("document_summary")
                if doc_summary:
                    db_rec.summary = doc_summary

                transcription = job_detail.get("transcription")
                if transcription is not None:
                    db_rec.transcription = transcription
                transcription_segments = job_detail.get("transcription_segments")
                if transcription_segments is not None:
                    db_rec.transcription_segments = transcription_segments

                entity_count = job_detail.get("entity_count")
                rel_count = job_detail.get("relationship_count")
                if entity_count is not None:
                    db_rec.entity_count = entity_count
                if rel_count is not None:
                    db_rec.relationship_count = rel_count

                EvidenceDBStorage.add_log(
                    db,
                    case_id=db_rec.case_id,
                    evidence_file_id=db_rec.id,
                    filename=db_rec.original_filename,
                    level="info",
                    message=f"Completed: {db_rec.original_filename} ({entity_count or 0} entities, {rel_count or 0} relationships)",
                )
            else:
                EvidenceDBStorage.add_log(
                    db,
                    case_id=db_rec.case_id,
                    evidence_file_id=db_rec.id,
                    filename=db_rec.original_filename,
                    level="error",
                    message=f"Failed: {db_rec.original_filename}: {err or 'Unknown error'}",
                )

            db.commit()
            logger.info("Synced job %s → %s", job_id, status)
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
