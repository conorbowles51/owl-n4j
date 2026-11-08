"""Durable, idempotent dispatch for newly accepted ingestion batches."""

import logging
from typing import Any

from sqlalchemy import func, select, text

from app.dependencies import async_session
from app.models.job import Job
from app.services.pipeline_run_state import transition_batch_dispatch
from app.services.processing_queues import PDF_REVIEW_QUEUE
from arq.constants import default_queue_name

logger = logging.getLogger(__name__)


async def dispatch_ingestion_batch(job: Job | Any, db: Any, pool: Any) -> bool:
    """Submit one outbox record using a stable ARQ job ID.

    A duplicate ARQ submission is safe: ARQ returns ``None`` when the stable
    job ID already exists, which still means the durable dispatch is satisfied.
    """
    dispatch = dict((job.pipeline_state or {}).get("batch_dispatch") or {})
    state = dispatch.get("state")
    if state == "dispatched":
        return True
    if state not in {"ready", "retry", "dispatching"}:
        raise RuntimeError(
            f"Batch dispatch for job {job.id} is not ready (state={state!r})"
        )

    job.pipeline_state = transition_batch_dispatch(
        job.pipeline_state,
        dispatch_state="dispatching",
    )
    await db.commit()

    try:
        function = dispatch.get("function", "process_batch")
        args = [str(job.id)] if function == "process_file" else [dispatch["batch_id"], dispatch["case_id"]]
        await pool.enqueue_job(
            function, *args,
            _job_id=dispatch["queue_job_id"],
            _queue_name=(job.pipeline_state or {}).get('processing_queue') or (
                PDF_REVIEW_QUEUE if getattr(job, 'job_type', None) == 'pdf_review' else default_queue_name),
        )
    except Exception as exc:
        job.pipeline_state = transition_batch_dispatch(
            job.pipeline_state,
            dispatch_state="retry",
            error=str(exc),
        )
        await db.commit()
        await db.refresh(job)
        logger.exception(
            "batch-dispatch-failed owner_job_id=%s batch_id=%s",
            job.id,
            dispatch.get("batch_id"),
        )
        return False

    job.pipeline_state = transition_batch_dispatch(
        job.pipeline_state,
        dispatch_state="dispatched",
    )
    await db.commit()
    await db.refresh(job)
    logger.info(
        "batch-dispatch-completed owner_job_id=%s batch_id=%s",
        job.id,
        dispatch["batch_id"],
    )
    return True


async def recover_batch_dispatches(ctx: dict[str, Any]) -> int:
    """Retry accepted batches whose original queue submission was interrupted."""
    pool = ctx.get("redis")
    if pool is None:
        raise RuntimeError("ARQ Redis pool is unavailable in worker context")

    recovered = 0
    async with async_session() as db:
        result = await db.execute(
            select(Job)
            .where(
                Job.pipeline_state["batch_dispatch"]["state"].astext.in_(
                    ["ready", "retry", "dispatching"]
                )
            )
            .order_by(Job.created_at)
            .limit(50)
        )
        for job in result.scalars().all():
            if await dispatch_ingestion_batch(job, db, pool):
                recovered += 1
    return recovered


async def refuse_closed_or_foreign_batch(db: Any, case_id: str, batch_id: Any) -> None:
    """A chunk may join only an open batch of its own case."""
    from fastapi import HTTPException
    result = await db.execute(select(Job).where(Job.batch_id == batch_id))
    existing = list(result.scalars().all())
    if any(str(job.case_id) != str(case_id) for job in existing):
        raise HTTPException(status_code=409, detail="This batch belongs to another case")
    if any((job.pipeline_state or {}).get("batch_dispatch") for job in existing):
        raise HTTPException(status_code=409, detail="This batch has already been closed")


async def close_open_batch(db: Any, case_id: str, batch_id: Any, pool: Any) -> dict[str, Any]:
    """Dispatch every job of a batch sent in chunks, once, as one batch.

    The first job (by created_at, then id) owns the dispatch record, as the first job of a one-request batch does.
    Two closes at once pick the same owner and the same stable queue job id, so the batch is queued once.
    """
    from app.services.processing_queues import batch_queue
    result = await db.execute(select(Job).where(Job.batch_id == batch_id).order_by(Job.created_at, Job.id))
    jobs = list(result.scalars().all())
    if not jobs:
        return {"batch_id": str(batch_id), "job_count": 0, "closed": False}
    if any(str(job.case_id) != str(case_id) for job in jobs):
        raise ValueError("This batch belongs to another case")
    owner = next((job for job in jobs if (job.pipeline_state or {}).get("batch_dispatch")), None)
    if owner is None:
        owner = jobs[0]
        queue = batch_queue(jobs)
        for job in jobs:
            state = dict(job.pipeline_state or {})
            state.pop("batch_open", None)
            job.pipeline_state = state
        owner.pipeline_state = {
            **transition_batch_dispatch(owner.pipeline_state, dispatch_state="ready",
                                        batch_id=str(batch_id), case_id=str(case_id)),
            "processing_queue": queue,
        }
        await db.commit()
        await db.refresh(owner)
    dispatched = await dispatch_ingestion_batch(owner, db, pool)
    logger.info("batch-closed batch_id=%s case_id=%s jobs=%d dispatched=%s", batch_id, case_id, len(jobs), dispatched)
    return {"batch_id": str(batch_id), "job_count": len(jobs), "closed": True}


OPEN_BATCH_IDLE_CLOSE = "15 minutes"


async def close_idle_open_batches(ctx: dict[str, Any]) -> int:
    """Close a chunked batch whose sender stopped before closing it (a restart mid-press), 15 minutes after its
    newest chunk, so its accepted files are read rather than left waiting."""
    pool = ctx.get("redis")
    if pool is None:
        raise RuntimeError("ARQ Redis pool is unavailable in worker context")
    closed = 0
    async with async_session() as db:
        rows = (await db.execute(
            select(Job.batch_id, Job.case_id)
            .where(Job.pipeline_state.has_key("batch_open"))
            .group_by(Job.batch_id, Job.case_id)
            .having(func.max(Job.created_at) < func.now() - text(f"interval '{OPEN_BATCH_IDLE_CLOSE}'"))
            .limit(20)
        )).all()
        for batch_id, case_id in rows:
            try:
                await close_open_batch(db, case_id, batch_id, pool)
                closed += 1
            except Exception:
                logger.exception("idle-batch-close-failed batch_id=%s", batch_id)
                await db.rollback()
    return closed
