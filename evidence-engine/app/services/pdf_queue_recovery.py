"""Move still-waiting legacy PDF jobs; never submit a second processing job."""
from arq.constants import default_queue_name, in_progress_key_prefix, job_key_prefix
from sqlalchemy import select, exists
from sqlalchemy.orm import aliased
from app.dependencies import async_session
from app.models.job import Job, JobStatus
from app.services.processing_queues import PDF_REVIEW_QUEUE

# ARQ takes a shared in-progress lock before execution. Moving the sorted-set
# member is atomic and retains the same job payload/id; an already running job
# stays with its worker. A worker that read the old queue concurrently still has
# to take that same lock. Do not manufacture jobs whose Redis payload expired.
MOVE_WAITING_PDF = """
if redis.call('EXISTS', KEYS[3]) == 1 or redis.call('EXISTS', KEYS[4]) == 0 then return 0 end
local score = redis.call('ZSCORE', KEYS[1], ARGV[1])
if not score then return 0 end
-- Invalidate an old worker's WATCH if it read this member just before the move.
redis.call('SET', KEYS[3], 'moving', 'PX', 1000)
redis.call('ZREM', KEYS[1], ARGV[1])
redis.call('ZADD', KEYS[2], score, ARGV[1])
redis.call('DEL', KEYS[3])
return 1
"""


async def recover_waiting_pdf_jobs(ctx):
    pool = ctx['redis']
    sibling = aliased(Job)
    async with async_session() as db:
        owners = (await db.execute(select(Job).where(Job.job_type == 'pdf_review',
            Job.status == JobStatus.PENDING,
            Job.pipeline_state['batch_dispatch']['state'].astext == 'dispatched',
            ~exists(select(sibling.id).where(sibling.batch_id == Job.batch_id,
                sibling.case_id == Job.case_id, sibling.job_type != 'pdf_review')))
            .order_by(Job.created_at).limit(100))).scalars().all()
        moved = 0
        for job in owners:
            identity = job.pipeline_state['batch_dispatch']['queue_job_id']
            moved += await pool.eval(MOVE_WAITING_PDF, 4, default_queue_name, PDF_REVIEW_QUEUE,
                in_progress_key_prefix + identity, job_key_prefix + identity, identity)
        return moved
