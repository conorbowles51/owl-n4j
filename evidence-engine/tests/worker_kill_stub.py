"""A real ARQ worker over the real run_controlled, with cheap work units, for test_worker_kill.py. Each unit appends its
number to UNIT_LOG, and unit 2 of the first attempt waits to be killed."""
import asyncio
import os

from arq.connections import RedisSettings

from app.services import ingestion_checkpoints as checkpoints
from app.services.ingestion_control import run_controlled
from app.worker import recovers

QUEUE = "arq:test-kill"
LOG = os.environ["UNIT_LOG"]


@checkpoints.checkpointed("test/kill-unit:v1")
async def unit(number):
    with open(LOG, "a") as log:
        log.write(f"{number}\n")
    if number == 2 and not os.path.exists(LOG + ".second"):
        open(LOG + ".second", "w").close()
        await asyncio.sleep(600)
    return number


async def process_batch(ctx, batch_id, case_id):
    async def operation():
        for number in (1, 2, 3):
            await unit(number)
        from sqlalchemy import update
        from app.dependencies import async_session
        from app.models.job import Job, JobStatus
        async with async_session() as db:
            await db.execute(update(Job).where(Job.batch_id == batch_id).values(status=JobStatus.COMPLETED, progress=1.0))
            await db.commit()
    await run_controlled(batch_id, case_id, operation)


class Settings:
    queue_name = QUEUE
    on_startup = recovers(QUEUE)
    functions = [process_batch]
    redis_settings = RedisSettings.from_dsn(os.environ["REDIS_URL"])
    job_timeout = 14400
    max_tries = 3
    poll_delay = 0.2
