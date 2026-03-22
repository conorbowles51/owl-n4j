import logging

from arq.connections import RedisSettings

from app.config import settings
from app.dependencies import async_session
from app.pipeline.batch_orchestrator import run_batch_pipeline
from app.pipeline.orchestrator import run_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def process_file(ctx: dict, job_id: str) -> None:
    """Process a single file directly (for ad-hoc use)."""
    logger.info("Processing job %s", job_id)
    async with async_session() as db:
        await run_pipeline(job_id, db)
    logger.info("Completed job %s", job_id)


async def process_batch(ctx: dict, batch_id: str, case_id: str) -> None:
    """Process a batch of files: parallel extraction + unified dedup."""
    logger.info("Processing batch %s for case %s", batch_id, case_id)
    async with async_session() as db:
        await run_batch_pipeline(batch_id, case_id, db)
    logger.info("Completed batch %s", batch_id)


class WorkerSettings:
    functions = [process_file, process_batch]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 4
    job_timeout = 14400  # 4 hours — batch may process many files
    retry_jobs = True
    max_tries = 3
