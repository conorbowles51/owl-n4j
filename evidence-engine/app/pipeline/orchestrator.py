import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus
from app.pipeline.chunk_embed import chunk_and_embed
from app.pipeline.context_injector import build_enriched_context
from app.pipeline.extract_entities import extract_entities_and_relationships
from app.pipeline.extract_text import extract_text
from app.pipeline.generate_summaries import generate_summaries
from app.pipeline.resolve_entities import resolve_entities
from app.pipeline.link_transaction_parties import link_transaction_parties
from app.pipeline.resolve_relationships import resolve_relationships
from app.pipeline.write_graph import write_graph
from app.services.redis_client import publish_progress

logger = logging.getLogger(__name__)


async def _update_job(
    job: Job,
    status: JobStatus,
    progress: float,
    db: AsyncSession,
    message: str = "",
) -> None:
    job.status = status
    job.progress = progress
    await db.commit()
    await publish_progress(
        str(job.id),
        {
            "job_id": str(job.id),
            "status": status.value,
            "progress": progress,
            "message": message,
        },
    )


async def run_pipeline(job_id: str, db: AsyncSession) -> None:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one()

    try:
        # Stage 1: Text extraction
        await _update_job(job, JobStatus.EXTRACTING_TEXT, 0.0, db, "Extracting text…")
        doc = await extract_text(job.file_path, job.file_name)
        await _update_job(job, JobStatus.EXTRACTING_TEXT, 1.0, db, "Text extracted")

        # Stage 2: Chunking & embedding
        await _update_job(job, JobStatus.CHUNKING, 0.0, db, "Chunking document…")
        chunks = await chunk_and_embed(doc, job.case_id, str(job.id), job.file_name)
        await _update_job(
            job, JobStatus.CHUNKING, 1.0, db, f"Created {len(chunks)} chunks"
        )

        # Stage 3: Entity & relationship extraction
        await _update_job(
            job, JobStatus.EXTRACTING_ENTITIES, 0.0, db, "Extracting entities…"
        )
        enriched_context = build_enriched_context(
            job.folder_context, job.sibling_files, job.llm_profile or ""
        )
        raw_entities, raw_rels = await extract_entities_and_relationships(
            chunks, enriched_context, job.file_name
        )
        await _update_job(
            job,
            JobStatus.EXTRACTING_ENTITIES,
            1.0,
            db,
            f"Extracted {len(raw_entities)} entities, {len(raw_rels)} relationships",
        )

        # Stage 4: Entity resolution / deduplication
        await _update_job(
            job, JobStatus.RESOLVING_ENTITIES, 0.0, db, "Resolving entities…"
        )
        resolved_ents, resolved_rels = await resolve_entities(
            raw_entities, raw_rels, job.case_id
        )
        await _update_job(
            job,
            JobStatus.RESOLVING_ENTITIES,
            1.0,
            db,
            f"Resolved to {len(resolved_ents)} entities",
        )

        # Stage 5: Relationship deduplication
        await _update_job(
            job,
            JobStatus.RESOLVING_RELATIONSHIPS,
            0.0,
            db,
            "Deduplicating relationships…",
        )
        resolved_rels = await resolve_relationships(resolved_rels)
        await _update_job(
            job,
            JobStatus.RESOLVING_RELATIONSHIPS,
            1.0,
            db,
            f"Deduplicated to {len(resolved_rels)} relationships",
        )

        # Stage 5.5: Link transaction sender/receiver to entity nodes
        resolved_rels = link_transaction_parties(resolved_ents, resolved_rels)

        # Stage 6: Generate entity summaries
        await _update_job(
            job,
            JobStatus.GENERATING_SUMMARIES,
            0.0,
            db,
            "Generating entity summaries…",
        )
        resolved_ents = await generate_summaries(resolved_ents, resolved_rels)
        await _update_job(
            job,
            JobStatus.GENERATING_SUMMARIES,
            1.0,
            db,
            "Summaries generated",
        )

        # Stage 7: Write to Neo4j + embed for RAG
        await _update_job(
            job, JobStatus.WRITING_GRAPH, 0.0, db, "Writing graph…"
        )
        await write_graph(resolved_ents, resolved_rels, job.case_id, str(job.id))

        job.entity_count = len(resolved_ents)
        job.relationship_count = len(resolved_rels)
        await _update_job(job, JobStatus.COMPLETED, 1.0, db, "Processing complete")

    except Exception as e:
        logger.exception("Pipeline failed for job %s", job_id)
        job.error_message = str(e)
        await _update_job(
            job, JobStatus.FAILED, job.progress, db, f"Failed: {e}"
        )
        raise
