"""Stale-job janitor — safety net for zombie ingestion jobs.

Catches anything the in-process cancellation handlers miss: container SIGKILLs,
OOM, network partitions during a DB write, future code paths we forgot to wrap.
Runs as an arq cron (registered in app.worker.WorkerSettings).
"""

import logging
import os
from datetime import datetime, timedelta

from sqlalchemy import select

from app.dependencies import async_session
from app.models.job import Job, JobStatus
from app.services.redis_client import publish_progress

logger = logging.getLogger(__name__)

DEFAULT_STALE_THRESHOLD_SECONDS = 7200  # 2 hours

# Pending jobs are excluded — they can sit in the queue legitimately without
# updated_at advancing. Every other non-terminal status reflects an active
# pipeline stage, so a long quiet period there means the worker died.
_NON_TERMINAL_NON_PENDING = [
    s for s in JobStatus if s not in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.PENDING)
]


async def reap_stale_jobs(ctx: dict) -> int:
    """Mark any non-terminal job whose updated_at is older than the threshold as failed.

    Returns the number of jobs reaped (for logging / tests).
    """
    threshold_seconds = int(
        os.getenv("JANITOR_STALE_THRESHOLD_SECONDS", str(DEFAULT_STALE_THRESHOLD_SECONDS))
    )
    # Job.updated_at is a naive TIMESTAMP WITHOUT TIME ZONE (no timezone=True on the
    # column), so the cutoff must also be naive — asyncpg refuses to compare otherwise.
    cutoff = datetime.utcnow() - timedelta(seconds=threshold_seconds)

    async with async_session() as db:
        result = await db.execute(
            select(Job).where(
                Job.status.in_(_NON_TERMINAL_NON_PENDING),
                Job.updated_at < cutoff,
            )
        )
        stale = list(result.scalars().all())
        if not stale:
            return 0

        snapshots: list[tuple[str, JobStatus, float, int]] = []
        for job in stale:
            stale_minutes = int((datetime.utcnow() - job.updated_at).total_seconds() // 60)
            prior_status = job.status.value
            reason = (
                f"[janitor] No progress for {stale_minutes} minutes at '{prior_status}'; "
                "worker likely crashed or hung."
            )
            existing = job.error_message or ""
            job.error_message = (existing + " | " + reason) if existing else reason
            job.status = JobStatus.FAILED
            snapshots.append((str(job.id), job.status, job.progress or 0.0, stale_minutes))
        await db.commit()

    logger.warning("janitor: marked %d stale jobs as failed", len(snapshots))

    for job_id, status, progress, stale_minutes in snapshots:
        try:
            await publish_progress(
                job_id,
                {
                    "job_id": job_id,
                    "status": status.value,
                    "progress": progress,
                    "message": f"Reaped by janitor after {stale_minutes} minutes of no progress",
                    "error_message": (
                        f"[janitor] No progress for {stale_minutes} minutes; worker likely crashed."
                    ),
                },
            )
        except Exception:
            logger.exception("janitor: failed to publish FAILED status for job %s", job_id)

    return len(snapshots)
