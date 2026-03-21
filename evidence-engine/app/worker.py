import logging

from arq.connections import RedisSettings

from app.config import settings
from app.dependencies import async_session
from app.pipeline.orchestrator import run_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def process_file(ctx: dict, job_id: str) -> None:
    logger.info("Processing job %s", job_id)
    async with async_session() as db:
        await run_pipeline(job_id, db)
    logger.info("Completed job %s", job_id)


class WorkerSettings:
    functions = [process_file]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 2
    job_timeout = 3600
    retry_jobs = True
    max_tries = 3
