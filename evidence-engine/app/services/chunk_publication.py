import logging
from typing import Any

from sqlalchemy import select

from app.dependencies import async_session
from app.models.job import Job, JobStatus
from app.pipeline.chunk_embed import ChunkActivationResult, activate_chunk_revision
from app.services.pipeline_run_state import (
    transition_chunk_publication,
    transition_pipeline_state,
)
from app.services.redis_client import publish_progress

logger = logging.getLogger(__name__)


async def publish_chunk_revision(job: Job | Any, db: Any) -> ChunkActivationResult:
    """Dispatch one ready job-embedded outbox record idempotently."""
    publication = dict((job.pipeline_state or {}).get("chunk_publication") or {})
    state = publication.get("state")
    if state == "published":
        return ChunkActivationResult(activated_count=0, retired_count=0)
    if state not in {"ready", "retry", "publishing"}:
        raise RuntimeError(
            f"Chunk revision for job {job.id} is not ready for publication (state={state!r})"
        )

    job.pipeline_state = transition_chunk_publication(
        job.pipeline_state,
        publication_state="publishing",
    )
    await db.commit()

    try:
        result = await activate_chunk_revision(
            case_id=str(job.case_id),
            evidence_file_id=publication["evidence_file_id"],
            revision_id=publication["revision_id"],
            file_name=publication["file_name"],
        )
    except Exception as exc:
        job.pipeline_state = transition_chunk_publication(
            job.pipeline_state,
            publication_state="retry",
            error=str(exc),
        )
        await db.commit()
        logger.exception("chunk-publication-failed job_id=%s", job.id)
        raise

    job.pipeline_state = transition_chunk_publication(
        job.pipeline_state,
        publication_state="published",
    )
    await db.commit()
    logger.info(
        "chunk-publication-completed job_id=%s evidence_file_id=%s revision_id=%s",
        job.id,
        publication["evidence_file_id"],
        publication["revision_id"],
    )
    return result


async def finalize_published_job(job: Job | Any, db: Any) -> bool:
    """Complete a graph-written job after its chunk revision is visible."""
    publication = dict((job.pipeline_state or {}).get("chunk_publication") or {})
    if publication.get("state") != "published":
        return False
    if job.status in {JobStatus.COMPLETED, JobStatus.FAILED}:
        return False

    job.status = JobStatus.COMPLETED
    job.progress = 1.0
    job.pipeline_state = transition_pipeline_state(
        job.pipeline_state,
        stage=JobStatus.COMPLETED.value,
        message="Processing complete",
    )
    await db.commit()
    await publish_progress(
        str(job.id),
        {
            "job_id": str(job.id),
            "status": JobStatus.COMPLETED.value,
            "progress": 1.0,
            "message": "Processing complete",
            "entity_count": int(job.entity_count or 0),
            "relationship_count": int(job.relationship_count or 0),
            "document_summary": job.document_summary,
        },
    )
    logger.info("chunk-publication-finalized-job job_id=%s", job.id)
    return True


async def recover_chunk_publications(_ctx: dict | None = None) -> None:
    """Retry ready or interrupted chunk publications from durable job state."""
    async with async_session() as db:
        result = await db.execute(
            select(Job)
            .where(
                Job.pipeline_state["chunk_publication"]["state"].astext.in_(
                    ["ready", "retry", "publishing", "published"]
                ),
                Job.status.notin_([JobStatus.COMPLETED, JobStatus.FAILED]),
            )
            .order_by(Job.updated_at)
            .limit(50)
        )
        jobs = list(result.scalars().all())
        for job in jobs:
            try:
                await publish_chunk_revision(job, db)
                await finalize_published_job(job, db)
            except Exception:
                logger.exception("chunk-publication-recovery-failed job_id=%s", job.id)
