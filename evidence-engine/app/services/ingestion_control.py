"""Cooperative pause, resume and cancel for a shared ingestion batch.

Cancel stops at the next work unit, as pause does, and removes nothing. Its rule:
- Files that finished before the stop stay finished, with everything they published.
- Nothing of a cancelled file reaches the case graph or the chunk search index: its chunks stay unpublished drafts. The
  text already read stays with the file, as after a failure: a run stores it at its first step, replacing any earlier
  text, and document search finds it. The cancel message says so, with the count.
- A person's work is never touched.
- Once a run has begun writing its result it cannot be cancelled (begin_publication): the same lock decides between
  the two, so a cancel that was accepted never loses to a write that follows it.
"""
import asyncio
from contextlib import suppress
from datetime import datetime
import logging
from sqlalchemy import func, or_, select, update
from app.dependencies import async_session
from app.models.job import EvidenceDocumentText, Job, JobStatus
from app.services.db_retry import retry_transient
from app.services.ingestion_checkpoints import checkpoint_scope, IngestionPaused
from app.services.redis_client import publish_progress

logger = logging.getLogger(__name__)

CANCELLABLE_JOB_TYPES = frozenset({"ingestion", "pdf_review", "audio_review"})
CANCELLED_PREFIX = "Cancelled on request."  # the backend reads this prefix on the file (services/evidence_job_sync.py)
PUBLICATION_BEGUN = "publication_begun"
FINISHED = (JobStatus.COMPLETED, JobStatus.FAILED)
_KEPT = {
    "pdf_review": "This PDF stays in the case; no reading was saved from this run.",
    "audio_review": "This recording stays in the case; no transcript was saved from this run.",
}
_KEPT_INGESTION = "This file stays in the case; nothing from it was added to the case graph."


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


def job_scope(job):
    """The rows a control acts on: the batch when the job has one, as pause does."""
    return scope_filter(job.batch_id or job.id, bool(job.batch_id))


def locked_scope(predicate, case_id):
    # By id, everywhere these rows are locked together, so two controls cannot deadlock.
    return (select(Job).where(predicate, Job.case_id == case_id).order_by(Job.id).with_for_update()
            .execution_options(populate_existing=True))


def cancel_message(job, rows, texts):
    """What the person reads on the card and on the file, with the counts of the whole batch."""
    words = [CANCELLED_PREFIX, _KEPT.get(job.job_type, _KEPT_INGESTION)]
    if len(rows) > 1:
        cancelled = sum(1 for row in rows if row.cancel_requested and row.status != JobStatus.COMPLETED)
        finished = sum(1 for row in rows if row.status == JobStatus.COMPLETED)
        failed = sum(1 for row in rows if row.status == JobStatus.FAILED and not row.cancel_requested)
        counts = [f"{cancelled} cancelled", f"{finished} finished and stay in the case"]
        if failed:
            counts.append(f"{failed} failed earlier")
        words.append(f"In this batch of {len(rows)}: " + ", ".join(counts) + ".")
    if texts:
        words.append(f"Text read before the stop stays with {texts} file{'s' if texts != 1 else ''}, in place of any "
                     "earlier text, and document search can find it.")
    return " ".join(words)


async def stop_rows(db, rows):
    """Finish every row asked to cancel. Safe to repeat. Returns (id, progress, message, cancelled_at).

    A file that fails after the cancel was asked for ends cancelled: that is what the person chose, and it keeps the
    file's earlier run, which a failure would clear. One that failed before it stays failed, but its Resume goes: a
    resumed run would pick up the whole batch again, cancelled files included. Process the file again instead."""
    stopping = [row for row in rows if row.cancel_requested and row.status != JobStatus.COMPLETED
                and (row.status != JobStatus.FAILED or not row.cancelled_at)]
    if not stopping:
        return []
    texts = await db.scalar(select(func.count()).select_from(EvidenceDocumentText).where(
        EvidenceDocumentText.engine_job_id.in_([row.id for row in stopping])))
    now = datetime.utcnow()
    done = []
    messages = {row.id: cancel_message(row, rows, texts or 0) for row in stopping}
    for row in stopping:
        row.status = JobStatus.FAILED
        row.cancelled_at = now
        row.error_message = messages[row.id]
        row.pause_requested = False
        row.paused = False
        done.append((str(row.id), row.progress or 0.0, messages[row.id], now.isoformat()))
    for row in rows:
        if row.status == JobStatus.FAILED and not row.cancel_requested:
            row.resumable = False
    return done


async def announce_cancelled(done):
    for job_id, progress, message, cancelled_at in done:
        try:
            # cancelled_at travels with the message: the backend must not read this as a failure if it cannot ask.
            await publish_progress(job_id, {"job_id": job_id, "status": JobStatus.FAILED.value, "progress": progress,
                                            "message": message, "error_message": message,
                                            "cancelled_at": cancelled_at})
        except Exception:
            logger.exception("Could not publish the cancelled state of job %s", job_id)


async def finish_cancel(predicate, case_id, *, pause=False):
    """After a run stopped: finish a requested cancel, or record the pause. Returns True when a cancel decided it."""
    async with async_session() as db:
        rows = list((await db.execute(locked_scope(predicate, case_id))).scalars().all())
        wanted = any(row.cancel_requested and row.status != JobStatus.COMPLETED for row in rows)
        done = await stop_rows(db, rows) if wanted else []
        if pause and not wanted:
            for row in rows:
                if row.status != JobStatus.COMPLETED:
                    row.paused, row.resumable, row.status = True, True, JobStatus.PENDING
        await db.commit()
    await announce_cancelled(done)
    return wanted


async def begin_publication(job_ids):
    """The last point a cancel can stop a run. Past it the batch writes to the case and a cancel is refused, for good:
    a pause or a killed worker after this point leaves work in the case, so it can only be finished."""
    async def enter():
        async with async_session() as db:
            rows = list((await db.execute(select(Job).where(Job.id.in_(job_ids)).order_by(Job.id).with_for_update()
                                          .execution_options(populate_existing=True))).scalars().all())
            if any(row.cancel_requested for row in rows):
                raise IngestionPaused()
            for row in rows:
                row.pipeline_state = {**(row.pipeline_state or {}), PUBLICATION_BEGUN: True}
            await db.commit()
    await retry_transient(enter)


async def run_controlled(scope_id, case_id, operation, *, batch=True):
    predicate = scope_filter(scope_id, batch)

    async def requested():
        async with async_session() as db:
            return bool(await db.scalar(select(Job.id).where(
                predicate, Job.case_id == case_id, or_(Job.pause_requested.is_(True), Job.cancel_requested.is_(True)),
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
        await finish_cancel(predicate, case_id, pause=True)
        return
    except Exception:
        # A failure while stopping must not hide the original error, and must not leave "Cancelling" on the card.
        try:
            await finish_cancel(predicate, case_id)
        except Exception:
            logger.exception("Could not finish a cancel after a failed run of %s", scope_id)
        raise
    await finish_cancel(predicate, case_id)


async def cancel_job(db, job):
    """POST /jobs/{id}/cancel for everything but phone readings. Repeating it is safe."""
    if job.job_type not in CANCELLABLE_JOB_TYPES:
        raise CancelRefused("This kind of processing cannot be cancelled. It stops by itself when it finishes or fails.")
    rows = list((await db.execute(locked_scope(job_scope(job), job.case_id))).scalars().all())
    active = [row for row in rows if row.status not in FINISHED]
    if not active:
        await db.commit()
        if any(row.cancelled_at for row in rows):
            return {"state": "cancelled", "affected_jobs": 0}
        raise CancelRefused("This processing has already finished, so there is nothing to cancel.")
    if all(row.cancel_requested for row in active):
        await db.commit()
        return {"state": "cancelling", "affected_jobs": 0}
    if any((row.pipeline_state or {}).get(PUBLICATION_BEGUN) for row in active):
        await db.commit()
        raise CancelRefused("This batch has already started writing to the case, so it can no longer be cancelled. "
                            "It finishes by itself; to remove a file afterwards, delete it from the case.")
    held = any(row.status != JobStatus.PENDING or (row.pause_requested and not row.paused) for row in active)
    for row in active:
        row.cancel_requested = True
    # Queued or paused work has no worker to wait for. A queued run that starts later stops at its first check,
    # which finds these rows finished.
    done = [] if held else await stop_rows(db, rows)
    await db.commit()
    await announce_cancelled(done)
    return {"state": "cancelling" if held else "cancelled", "affected_jobs": len(active)}


class CancelRefused(Exception):
    """The person's words for why this cancel cannot happen."""
