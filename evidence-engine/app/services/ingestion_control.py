"""Cooperative pause/resume for a shared ingestion batch."""
import asyncio
from contextlib import suppress
from datetime import datetime
import logging
from sqlalchemy import select, update
from app.dependencies import async_session
from app.models.job import Job, JobStatus
from app.services.ingestion_checkpoints import checkpoint_scope, IngestionPaused

logger = logging.getLogger(__name__)


async def _keep_alive(predicate, case_id):
    # The janitor detects dead workers, not a quiet but active provider call.
    # Normal work-unit timeouts still bound stalled network operations.
    while True:
        await asyncio.sleep(30)
        try:
            async with async_session() as db:
                await db.execute(update(Job).where(predicate, Job.case_id == case_id,
                    Job.status.notin_([JobStatus.COMPLETED, JobStatus.FAILED]), Job.paused.is_(False))
                    .values(updated_at=datetime.utcnow()))
                await db.commit()
        except Exception:
            logger.warning('Unable to record ingestion worker heartbeat', exc_info=True)


def scope_filter(scope_id, batch):
    return Job.batch_id == scope_id if batch else Job.id == scope_id


async def run_controlled(scope_id, case_id, operation, *, batch=True):
    predicate = scope_filter(scope_id, batch)

    async def requested():
        async with async_session() as db:
            return bool(await db.scalar(select(Job.id).where(
                predicate, Job.case_id == case_id, Job.pause_requested.is_(True),
                Job.status != JobStatus.COMPLETED).limit(1)))

    try:
        async with checkpoint_scope(scope_id, case_id, requested):
            async with async_session() as db:
                await db.execute(update(Job).where(predicate, Job.case_id == case_id).values(resumable=True))
                await db.commit()
            heartbeat = asyncio.create_task(_keep_alive(predicate, case_id))
            try:
                await operation()
            finally:
                heartbeat.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat
    except IngestionPaused:
        async with async_session() as db:
            await db.execute(update(Job).where(predicate, Job.case_id == case_id,
                Job.status != JobStatus.COMPLETED).values(paused=True, resumable=True, status=JobStatus.PENDING))
            await db.commit()
