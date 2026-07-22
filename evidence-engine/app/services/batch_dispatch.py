"""Durable, idempotent dispatch for newly accepted ingestion batches."""

import logging
from typing import Any

from sqlalchemy import select

from app.dependencies import async_session
from app.models.job import Job
from app.services.pipeline_run_state import transition_batch_dispatch

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
        await pool.enqueue_job(
            "process_batch",
            dispatch["batch_id"],
            dispatch["case_id"],
            _job_id=dispatch["queue_job_id"],
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
