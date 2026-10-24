"""Stale-job janitor — safety net for zombie ingestion jobs.

Catches anything the in-process cancellation handlers miss: container SIGKILLs,
OOM, network partitions during a DB write, future code paths we forgot to wrap.
Runs as an arq cron (registered in app.worker.WorkerSettings).
"""

import logging
import os
from datetime import datetime, timedelta

from arq.constants import in_progress_key_prefix, job_key_prefix
from sqlalchemy import select

from app.dependencies import async_session
from app.models.job import Job, JobStatus
from app.services.redis_client import publish_progress

logger = logging.getLogger(__name__)

DEFAULT_STALE_THRESHOLD_SECONDS = 7200  # 2 hours

# Pending jobs are excluded here — they can sit in the queue legitimately without
# updated_at advancing. Every other non-terminal status reflects an active
# pipeline stage, so a long quiet period there means the worker died. A pending
# job is reaped only by ``reap_orphaned_pending``: when the queue no longer
# holds the work that would run it.
_NON_TERMINAL_NON_PENDING = [
    s for s in JobStatus if s not in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.PENDING)
]


def _cutoff() -> datetime:
    threshold_seconds = int(
        os.getenv("JANITOR_STALE_THRESHOLD_SECONDS", str(DEFAULT_STALE_THRESHOLD_SECONDS))
    )
    # Job.updated_at is a naive TIMESTAMP WITHOUT TIME ZONE (no timezone=True on the
    # column), so the cutoff must also be naive — asyncpg refuses to compare otherwise.
    return datetime.utcnow() - timedelta(seconds=threshold_seconds)


def queue_identity(job, owners: dict) -> str | None:
    """The queue job id that would run this pending job, or None when it is not
    known to be dispatched (not yet dispatched work belongs to recover_batch_dispatches;
    a job without a dispatch record is never guessed at)."""
    dispatch = (job.pipeline_state or {}).get("batch_dispatch") or (
        (owners.get((job.case_id, job.batch_id)) or {}) if job.batch_id else {})
    if dispatch.get("state") != "dispatched":
        return None
    return dispatch.get("queue_job_id") or None


async def queue_holds(pool, identity: str) -> bool:
    """True while ARQ still has the job queued, deferred, retrying or running."""
    return bool(await pool.exists(job_key_prefix + identity, in_progress_key_prefix + identity))


async def reap_orphaned_pending(ctx: dict) -> int:
    """Fail pending jobs whose dispatched queue job no longer exists.

    A worker killed mid-batch can leave members ``pending`` after ARQ has
    dropped the batch job; nothing will ever run them, and a pending file reads
    as "being processed" to everything waiting on it. Only jobs quiet past the
    threshold, not paused, and dispatched under a queue id ARQ no longer holds
    are failed; they are safe to retry.
    """
    pool = ctx.get("redis")
    if pool is None:
        return 0
    async with async_session() as db:
        pending = list((await db.execute(select(Job).where(
            Job.status == JobStatus.PENDING, Job.paused.is_(False), Job.updated_at < _cutoff(),
        ))).scalars().all())
        if not pending:
            return 0
        batches = {(job.case_id, job.batch_id) for job in pending if job.batch_id}
        owners = {}
        if batches:
            for owner in (await db.execute(select(Job).where(
                    Job.batch_id.in_({batch for _, batch in batches}),
                    Job.pipeline_state.has_key("batch_dispatch")))).scalars().all():
                if (owner.case_id, owner.batch_id) in batches:
                    owners[(owner.case_id, owner.batch_id)] = owner.pipeline_state["batch_dispatch"]
        alive: dict[str, bool] = {}
        orphans = []
        for job in pending:
            identity = queue_identity(job, owners)
            if identity is None:
                continue
            if identity not in alive:
                alive[identity] = await queue_holds(pool, identity)
            if not alive[identity]:
                orphans.append(job)
        for job in orphans:
            reason = ("[janitor] Pending, but its queued work no longer exists (the worker "
                      "stopped mid-batch); nothing would ever run it. Safe to retry.")
            job.error_message = (job.error_message + " | " + reason) if job.error_message else reason
            job.status = JobStatus.FAILED
        await db.commit()
        snapshots = [(str(job.id), job.progress or 0.0) for job in orphans]
    if snapshots:
        logger.warning("janitor: marked %d orphaned pending jobs as failed", len(snapshots))
    for job_id, progress in snapshots:
        try:
            await publish_progress(job_id, {
                "job_id": job_id, "status": JobStatus.FAILED.value, "progress": progress,
                "message": "Reaped by janitor: its queued work no longer exists",
                "error_message": "[janitor] Pending with no queued work; safe to retry.",
            })
        except Exception:
            logger.exception("janitor: failed to publish FAILED status for job %s", job_id)
    return len(snapshots)


async def reap_stale_jobs(ctx: dict) -> int:
    """Mark any non-terminal job whose updated_at is older than the threshold as failed,
    then any pending job whose queued work no longer exists.

    Returns the number of jobs reaped (for logging / tests).
    """
    cutoff = _cutoff()

    async with async_session() as db:
        result = await db.execute(
            select(Job).where(
                Job.status.in_(_NON_TERMINAL_NON_PENDING),
                Job.paused.is_(False),
                Job.updated_at < cutoff,
            )
        )
        stale = list(result.scalars().all())
        if not stale:
            return await reap_orphaned_pending(ctx)

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

    return len(snapshots) + await reap_orphaned_pending(ctx)
