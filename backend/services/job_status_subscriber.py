"""
Job Status Subscriber — listens to Redis pub/sub for evidence engine job
progress and syncs terminal states (completed/failed) to Postgres.

Replaces the old _track_engine_jobs() polling daemon thread.
"""

import asyncio
import json
import logging
from typing import Dict, Set

from config import REDIS_URL

logger = logging.getLogger(__name__)

# Map engine statuses to backend EvidenceFile statuses
_ENGINE_STATUS_MAP = {
    "completed": "processed",
    "failed": "failed",
}


def _extract_failure_message(payload: dict) -> str | None:
    for key in ("error_message", "message"):
        value = payload.get(key)
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned.removeprefix("Failed: ").strip()
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
                        # Engine unreachable — subscribe anyway, will catch up later
                        self._tracked[jid] = case_id
                        await self._pubsub.subscribe(f"job:{jid}:progress")
                        logger.warning("Could not check engine job %s: %s", jid, e)

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
                        self._tracked[jid] = case_id
                        await self._pubsub.subscribe(f"job:{jid}:progress")
                        logger.warning("Could not check merge engine job %s: %s", jid, e)

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

        if status not in ("completed", "failed"):
            return  # Only sync terminal states

        case_id = self._tracked.get(job_id)

        try:
            handled = self._dispatch_terminal(job_id, data, status, case_id)
        except Exception:
            logger.exception(
                "Handler raised for %s; leaving subscription intact for retry",
                job_id,
            )
            return

        if handled:
            self._tracked.pop(job_id, None)
            try:
                await self._pubsub.unsubscribe(f"job:{job_id}:progress")
            except Exception:
                pass

    def _dispatch_terminal(self, job_id: str, data: dict, status: str, case_id: str | None) -> bool:
        """Route a terminal message to the right DB writer. Returns True only
        when the work succeeded; False/raise leaves the subscription in place."""
        from postgres.session import get_background_session
        from postgres.models.merge_job import MergeJob
        from services.evidence_db_storage import EvidenceDBStorage

        with get_background_session() as db:
            merge_job = db.query(MergeJob).filter(
                MergeJob.engine_job_id == job_id
            ).first()
            if merge_job:
                self._handle_merge_completion(db, merge_job, data, status, case_id)
                return True

            db_rec = EvidenceDBStorage.find_by_engine_job_id(db, job_id)
            if not db_rec:
                logger.warning("No DB record found for engine job %s", job_id)
                # No matching row will ever exist — drop the subscription.
                return True

            err = _extract_failure_message(data) if status == "failed" else None
            EvidenceDBStorage.mark_processed(db, [db_rec.id], error=err)

            if status == "completed":
                doc_summary = data.get("document_summary")
                if doc_summary:
                    db_rec.summary = doc_summary

                entity_count = data.get("entity_count")
                rel_count = data.get("relationship_count")
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
                merged_key = data.get("merged_entity_key")
                merge_job.merged_entity_key = merged_key

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
                err = _extract_failure_message(data)
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
