"""Phone worker recovery (01 sections 10.2 and 10.5).

arq marks a running job with an in-progress key that expires only after the job timeout (six hours here). When the
phone worker is killed (SIGKILL, OOM, host restart) the key outlives the process, so the retry would wait hours.
There is exactly one phone worker (``max_jobs = 1``, one container), so when it starts nothing of its own is
running yet: on its first pass after start it clears the in-progress keys of phone jobs that are still waiting in
its queue, and arq retries them at once. The capture resumes from its cursor (decision D26), and the per-scope
lock in ``run_controlled`` stops two runs of one job overlapping in any case.
"""
from __future__ import annotations

import logging

from arq.constants import in_progress_key_prefix, job_key_prefix
from sqlalchemy import select

from app.dependencies import async_session
from app.models.job import Job, JobStatus

logger = logging.getLogger(__name__)
_started = {"done": False}


async def recover_waiting_phone_jobs(ctx) -> int:
    if _started["done"]:
        return 0
    _started["done"] = True
    pool = ctx["redis"]
    cleared = 0
    async with async_session() as db:
        jobs = (await db.execute(select(Job).where(
            Job.job_type == "phone_capture", Job.status.notin_([JobStatus.COMPLETED, JobStatus.FAILED]),
            Job.pipeline_state["batch_dispatch"]["state"].astext == "dispatched").order_by(Job.created_at)
            .limit(100))).scalars().all()
    for job in jobs:
        identity = (job.pipeline_state or {}).get("batch_dispatch", {}).get("queue_job_id")
        if not identity:
            continue
        if await pool.exists(job_key_prefix + identity) and await pool.delete(in_progress_key_prefix + identity):
            cleared += 1
            logger.warning("phone worker start: cleared the in-progress mark of job %s left by a stopped worker",
                           job.id)
    return cleared
