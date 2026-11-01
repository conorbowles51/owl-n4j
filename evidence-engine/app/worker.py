import asyncio
import logging

from arq import cron
from arq.connections import RedisSettings

from app.config import settings
from app.dependencies import async_session
from app.jobs.janitor import reap_stale_jobs
from app.services.chunk_publication import recover_chunk_publications
from app.services.batch_dispatch import recover_batch_dispatches
from app.pipeline.batch_orchestrator import run_batch_pipeline
from app.pipeline.merge_orchestrator import run_merge_pipeline
from app.pipeline.orchestrator import run_pipeline
from app.services.ingestion_control import run_controlled

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def process_file(ctx: dict, job_id: str) -> None:
    """Process a single file directly (for ad-hoc use)."""
    logger.info("Processing job %s", job_id)
    async with async_session() as db:
        from app.models.job import Job
        job = await db.get(Job, job_id)
        if job is None:
            raise ValueError("Processing job no longer exists")
        if job.job_type == "pdf_review":
            from app.pipeline.prepare_pdf_review import prepare_pdf_review
            from app.pipeline.batch_orchestrator import _update_job_status
            from app.models.job import JobStatus

            async def operation():
                try:
                    await prepare_pdf_review(job, _update_job_status)
                except (Exception, asyncio.CancelledError):
                    await _update_job_status(job.id, JobStatus.FAILED, job.progress or 0.0,
                        "PDF source preparation stopped", error_message="PDF source preparation stopped; retry this reading.")
                    raise
        else:
            operation = lambda: run_pipeline(job_id, db)
        await run_controlled(job_id, job.case_id, operation, batch=False)
    logger.info("Completed job %s", job_id)


async def process_batch(ctx: dict, batch_id: str, case_id: str) -> None:
    """Process a batch of files: parallel extraction + unified dedup."""
    logger.info("Processing batch %s for case %s", batch_id, case_id)
    async with async_session() as db:
        await run_controlled(batch_id, case_id, lambda: run_batch_pipeline(batch_id, case_id, db))
    logger.info("Completed batch %s", batch_id)


async def process_merge(ctx: dict, job_id: str, case_id: str) -> None:
    """Process an entity merge job: AI property merging + graph write."""
    logger.info("Processing merge job %s for case %s", job_id, case_id)
    async with async_session() as db:
        await run_merge_pipeline(job_id, db)
    logger.info("Completed merge job %s", job_id)


async def process_phone_capture(ctx: dict, job_id: str, case_id: str) -> None:
    """Capture one phone report root (01 section 10)."""
    from app.phone.job import run_phone_capture
    logger.info("Processing phone capture job %s for case %s", job_id, case_id)
    async with async_session() as db:
        await run_controlled(job_id, case_id, lambda: run_phone_capture(job_id, db), batch=False)
    logger.info("Completed phone capture job %s", job_id)


class WorkerSettings:
    functions = [process_file, process_batch, process_merge]
    cron_jobs = [
        # Stale-job janitor: every 5 minutes, mark any non-terminal job whose
        # updated_at hasn't moved in JANITOR_STALE_THRESHOLD_SECONDS (default 2h)
        # as failed. Safety net for cases where in-code CancelledError handlers
        # don't fire (SIGKILL, OOM, network partition mid-DB-write).
        cron(reap_stale_jobs, minute=set(range(0, 60, 5))),
        cron(recover_batch_dispatches, minute=set(range(0, 60))),
        cron(recover_chunk_publications, minute=set(range(0, 60))),
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 4
    job_timeout = 14400  # 4 hours — batch may process many files
    job_completion_wait = 14430  # Stop picking jobs, finish current work on SIGTERM.
    retry_jobs = True
    max_tries = 3


class PdfReviewWorkerSettings:
    """Financial PDF work keeps moving when all general ingestion slots are busy."""
    from app.services.processing_queues import PDF_REVIEW_QUEUE as queue_name
    from app.services.pdf_queue_recovery import recover_waiting_pdf_jobs
    functions = [process_batch, process_file]
    cron_jobs = [cron(recover_waiting_pdf_jobs, minute=set(range(0, 60)), run_at_startup=True)]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 2
    job_timeout = 14400
    job_completion_wait = 14430
    retry_jobs = True
    max_tries = 3


class PhoneCaptureWorkerSettings:
    """Phone extractions get their own slot so a long read never blocks statements or documents."""
    from app.services.processing_queues import PHONE_CAPTURE_QUEUE as queue_name
    from app.phone.recovery import recover_waiting_phone_jobs
    functions = [process_phone_capture]
    cron_jobs = [cron(recover_waiting_phone_jobs, minute=set(range(0, 60)), run_at_startup=True)]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 1
    # v1's longest phone ingest took 292 minutes (01 section 1.7); the 10.8 target for the largest phone is 30.
    # Six hours leaves room for the largest phone on a loaded host without a run being cut off midway.
    job_timeout = 21600
    job_completion_wait = 21630
    retry_jobs = True
    max_tries = 3
