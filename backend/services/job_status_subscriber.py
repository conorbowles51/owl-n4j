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
        """On startup, find EvidenceFiles stuck in 'processing' and re-subscribe."""
        try:
            from postgres.session import get_background_session
            from services.evidence_db_storage import EvidenceDBStorage
            from services import evidence_engine_client

            with get_background_session() as db:
                from sqlalchemy import select
                from postgres.models.evidence import EvidenceFile

                stuck = list(db.scalars(
                    select(EvidenceFile).where(
                        EvidenceFile.status == "processing",
                        EvidenceFile.engine_job_id.isnot(None),
                    )
                ).all())

                if not stuck:
                    return

                logger.info("Recovering %d in-flight jobs from previous run", len(stuck))

                for ef in stuck:
                    jid = ef.engine_job_id
                    case_id = str(ef.case_id)

                    # Check current status from engine
                    try:
                        loop = asyncio.get_event_loop()
                        job = await evidence_engine_client.get_job(jid)
                        engine_status = job.get("status", "")

                        if engine_status in ("completed", "failed"):
                            # Already terminal — sync immediately
                            err = job.get("error_message") if engine_status == "failed" else None
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

                db.commit()
        except Exception as e:
            logger.warning("Failed to recover in-flight jobs: %s", e)

    async def _run(self):
        """Main subscriber loop."""
        while True:
            try:
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
        """Process a single Redis pub/sub message."""
        try:
            data = json.loads(message["data"])
        except (json.JSONDecodeError, TypeError):
            return

        job_id = data.get("job_id", "")
        status = data.get("status", "")

        if status not in ("completed", "failed"):
            return  # Only sync terminal states

        case_id = self._tracked.pop(job_id, None)

        # Unsubscribe from this channel
        channel = f"job:{job_id}:progress"
        try:
            await self._pubsub.unsubscribe(channel)
        except Exception:
            pass

        # Update Postgres
        try:
            from postgres.session import get_background_session
            from services.evidence_db_storage import EvidenceDBStorage

            with get_background_session() as db:
                db_rec = EvidenceDBStorage.find_by_engine_job_id(db, job_id)
                if db_rec:
                    err = data.get("error_message") if status == "failed" else None
                    EvidenceDBStorage.mark_processed(db, [db_rec.id], error=err)

                    if status == "completed":
                        # Store document summary
                        doc_summary = data.get("document_summary")
                        if doc_summary:
                            db_rec.summary = doc_summary

                        # Store entity/relationship counts
                        entity_count = data.get("entity_count")
                        rel_count = data.get("relationship_count")
                        if entity_count is not None:
                            db_rec.entity_count = entity_count
                        if rel_count is not None:
                            db_rec.relationship_count = rel_count

                        # Write ingestion log
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

                    logger.info("Synced job %s → %s", job_id, status)
                else:
                    logger.warning("No DB record found for engine job %s", job_id)
        except Exception as e:
            logger.error("Failed to sync job %s to DB: %s", job_id, e)


# Module-level singleton
_subscriber: JobStatusSubscriber | None = None


def get_subscriber() -> JobStatusSubscriber:
    global _subscriber
    if _subscriber is None:
        _subscriber = JobStatusSubscriber()
    return _subscriber
