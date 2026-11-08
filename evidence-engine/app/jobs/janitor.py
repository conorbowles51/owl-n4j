"""Stale-job janitor — safety net for zombie ingestion jobs.

Catches anything the in-process cancellation handlers miss: container SIGKILLs,
OOM, network partitions during a DB write, future code paths we forgot to wrap.
Runs as an arq cron (registered in app.worker.WorkerSettings).
"""

import logging
import os
from datetime import datetime, timedelta

from arq.constants import in_progress_key_prefix, job_key_prefix
from sqlalchemy import or_, select

from app.dependencies import async_session
from app.models.job import Job, JobStatus
from app.services.ingestion_control import announce_cancelled, CANCELLABLE_JOB_TYPES, job_scope, locked_scope, stop_rows
from app.services.redis_client import publish_progress

logger = logging.getLogger(__name__)

DEFAULT_STALE_THRESHOLD_SECONDS = 7200  # 2 hours
# A running job's heartbeat moves updated_at every 30 s. A cancel whose job has been quiet this long has no worker left
# to finish it. Finishing one that does is harmless: the worker stops at its next check and changes nothing.
CANCEL_QUIET_SECONDS = 300

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


async def batch_owners(db, jobs) -> dict:
    batches = {(job.case_id, job.batch_id) for job in jobs if job.batch_id}
    owners = {}
    if batches:
        for owner in (await db.execute(select(Job).where(
                Job.batch_id.in_({batch for _, batch in batches}),
                Job.pipeline_state.has_key("batch_dispatch")))).scalars().all():
            if (owner.case_id, owner.batch_id) in batches:
                owners[(owner.case_id, owner.batch_id)] = owner.pipeline_state["batch_dispatch"]
    return owners


async def recover_interrupted_work(pool, queue_name: str) -> int:
    """Called once when a worker starts, before it takes any job: it is the only worker of its queue, so nothing here
    is running and an in-progress mark in its queue was left by a worker that was killed. ARQ keeps that mark for the
    4 h job timeout. Clearing it makes ARQ run the job again now, and the run resumes from its checkpoints. Work a release paused
    is restarted as well. A job whose queue entry is gone (Redis lost it) is the janitor's: it fails, with its reason, and Resume is offered."""
    async with async_session() as db:
        # A release pauses rows by flag and stops the worker with the work in hand: those rows are paused but not
        # pending, and their run must restart here too, or after the release's resume nothing runs them (SB4, 8 Nov).
        # A person's pause ends at pending; its queued job finds the pause and stops at once.
        jobs = list((await db.execute(select(Job).where(
            Job.status.notin_([JobStatus.COMPLETED, JobStatus.FAILED]),
            Job.job_type.in_(CANCELLABLE_JOB_TYPES)))).scalars().all())
        if not jobs:
            return 0
        owners = await batch_owners(db, jobs)
    cleared = 0
    for identity in {queue_identity(job, owners) for job in jobs} - {None}:
        if await pool.zscore(queue_name, identity) is None:
            continue  # another worker's queue
        if await pool.delete(in_progress_key_prefix + identity):
            cleared += 1
            logger.warning("worker start: cleared the in-progress mark of %s left by a stopped worker", identity)
    return cleared


async def finish_abandoned_cancels() -> int:
    """A cancel whose worker died: the job would otherwise read "Cancelling" until the stale threshold fails it."""
    cutoff = datetime.utcnow() - timedelta(seconds=CANCEL_QUIET_SECONDS)
    done = []
    async with async_session() as db:
        quiet = list((await db.execute(select(Job).where(
            Job.cancel_requested.is_(True), Job.status != JobStatus.COMPLETED,
            or_(Job.cancelled_at.is_(None), Job.status != JobStatus.FAILED),
            Job.updated_at < cutoff))).scalars().all())
        seen = set()
        for job in quiet:
            scope = job.batch_id or job.id
            if scope in seen:
                continue
            seen.add(scope)
            rows = list((await db.execute(locked_scope(job_scope(job), job.case_id))).scalars().all())
            done += await stop_rows(db, rows)
            await db.commit()
    if done:
        logger.warning("janitor: finished %d cancelled jobs whose worker had stopped", len(done))
    await announce_cancelled(done)
    return len(done)


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
        owners = await batch_owners(db, pending)
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


PAUSED_SEEN_PREFIX = "janitor:paused-seen:"


async def note_paused(pool) -> int:
    """Remember, each pass, which unfinished jobs are paused. A release pauses by flag (jobs.paused) and resumes by
    clearing it, and neither moves updated_at, so a job resumed after a long hold read as hours of no progress the
    moment it was resumed (SB4, 8 Nov: 50 files failed as crashed at 19:50 and 19:55). The quiet time is counted from
    the last pass that saw the job paused; without Redis it counts from updated_at, as before."""
    if pool is None:
        return 0
    async with async_session() as db:
        ids = [str(i) for i in (await db.execute(select(Job.id).where(
            Job.status.notin_([JobStatus.COMPLETED, JobStatus.FAILED]), Job.paused.is_(True)))).scalars().all()]
    now = datetime.utcnow().isoformat()
    keep = int(os.getenv("JANITOR_STALE_THRESHOLD_SECONDS", str(DEFAULT_STALE_THRESHOLD_SECONDS))) + 86400
    for job_id in ids:
        await pool.set(PAUSED_SEEN_PREFIX + job_id, now, ex=keep)
    return len(ids)


async def paused_seen(pool, jobs) -> dict:
    if pool is None or not jobs:
        return {}
    values = await pool.mget(*[PAUSED_SEEN_PREFIX + str(job.id) for job in jobs])
    seen = {}
    for job, value in zip(jobs, values):
        if value:
            seen[str(job.id)] = datetime.fromisoformat(value.decode() if isinstance(value, bytes) else value)
    return seen


def quiet_since(job, seen: dict) -> datetime:
    return max(job.updated_at, seen.get(str(job.id), job.updated_at))


async def reap_stale_jobs(ctx: dict) -> int:
    """Mark any non-terminal job whose updated_at is older than the threshold as failed,
    then any pending job whose queued work no longer exists.

    Returns the number of jobs reaped (for logging / tests).
    """
    try:
        await finish_abandoned_cancels()
    except Exception:
        logger.exception("janitor: could not finish abandoned cancels")  # never stops the reaping below
    cutoff = _cutoff()
    pool = ctx.get("redis")
    try:
        await note_paused(pool)
    except Exception:
        logger.exception("janitor: could not record paused jobs")  # paused time then counts, as before

    async with async_session() as db:
        result = await db.execute(
            select(Job).where(
                Job.status.in_(_NON_TERMINAL_NON_PENDING),
                Job.paused.is_(False),
                Job.updated_at < cutoff,
            )
        )
        candidates = list(result.scalars().all())
        try:
            seen = await paused_seen(pool, candidates)
        except Exception:
            logger.exception("janitor: could not read when jobs were last paused")
            seen = {}
        stale = [job for job in candidates if quiet_since(job, seen) < cutoff]
        if not stale:
            return await reap_orphaned_pending(ctx)

        snapshots: list[tuple[str, JobStatus, float, int, str]] = []
        for job in stale:
            since = quiet_since(job, seen)
            stale_minutes = int((datetime.utcnow() - since).total_seconds() // 60)
            prior_status = job.status.value
            if since > job.updated_at:
                reason = (
                    f"[janitor] No progress for {stale_minutes} minutes at '{prior_status}' after a release paused "
                    f"and resumed it (last seen paused {since:%d %b %H:%M} UTC; the paused time is not counted); "
                    "no worker took it up again. Safe to resume."
                )
            else:
                reason = (
                    f"[janitor] No progress for {stale_minutes} minutes at '{prior_status}'; "
                    "worker likely crashed or hung."
                )
            existing = job.error_message or ""
            job.error_message = (existing + " | " + reason) if existing else reason
            job.status = JobStatus.FAILED
            snapshots.append((str(job.id), job.status, job.progress or 0.0, stale_minutes, reason))
        await db.commit()

    logger.warning("janitor: marked %d stale jobs as failed", len(snapshots))

    for job_id, status, progress, stale_minutes, reason in snapshots:
        try:
            await publish_progress(
                job_id,
                {
                    "job_id": job_id,
                    "status": status.value,
                    "progress": progress,
                    "message": f"Reaped by janitor after {stale_minutes} minutes of no progress",
                    "error_message": reason,
                },
            )
        except Exception:
            logger.exception("janitor: failed to publish FAILED status for job %s", job_id)

    return len(snapshots) + await reap_orphaned_pending(ctx)
