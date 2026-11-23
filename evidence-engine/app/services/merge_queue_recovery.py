"""Merges queued on the general queue before the merge worker existed move to the merge queue, unchanged."""
import logging

from arq.constants import default_queue_name, in_progress_key_prefix, job_key_prefix
from arq.jobs import deserialize_job

from app.services.pdf_queue_recovery import MOVE_WAITING_PDF
from app.services.processing_queues import MERGE_QUEUE

logger = logging.getLogger(__name__)


async def move_waiting_merges(ctx) -> int:
    """Only waiting merges move (same id, payload and queue time); a merge a worker already holds stays with it."""
    pool = ctx['redis']
    moved = 0
    for raw in await pool.zrange(default_queue_name, 0, -1):
        identity = raw.decode() if isinstance(raw, bytes) else raw
        payload = await pool.get(job_key_prefix + identity)
        if not payload:
            continue
        try:
            if deserialize_job(payload).function != 'process_merge':
                continue
        except Exception:
            continue
        moved += await pool.eval(MOVE_WAITING_PDF, 4, default_queue_name, MERGE_QUEUE,
            in_progress_key_prefix + identity, job_key_prefix + identity, identity)
    if moved:
        logger.warning("merge worker start: moved %d waiting merges off the general queue", moved)
    return moved
