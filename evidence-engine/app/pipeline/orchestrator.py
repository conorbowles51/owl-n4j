import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus
from app.pipeline.chunk_embed import chunk_and_embed
from app.pipeline.consolidate_entities import consolidate_entities
from app.pipeline.context_injector import build_enriched_context
from app.pipeline.extract_entities import extract_entities_and_relationships
from app.pipeline.extract_text import extract_text
from app.pipeline.generate_document_summary import generate_document_summary
from app.pipeline.generate_summaries import generate_summaries
from app.pipeline.link_transaction_parties import link_transaction_parties
from app.pipeline.resolve_entities import resolve_entities
from app.pipeline.resolve_relationships import resolve_relationships
from app.pipeline.write_graph import write_graph
from app.services.cost_tracking import ingestion_cost_context
from app.services.redis_client import publish_progress

logger = logging.getLogger(__name__)


async def _update_job(
    job: Job,
    status: JobStatus,
    progress: float,
    db: AsyncSession,
    message: str = "",
    error_message: str | None = None,
) -> None:
    job.status = status
    job.progress = progress
    if error_message is not None:
        job.error_message = error_message
    await db.commit()
    payload = {
        "job_id": str(job.id),
        "status": status.value,
        "progress": progress,
        "message": message,
    }
    if error_message is not None:
        payload["error_message"] = error_message
    await publish_progress(str(job.id), payload)


async def run_pipeline(job_id: str, db: AsyncSession) -> None:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one()

    try:
        async with ingestion_cost_context(
            case_id=job.case_id,
            requested_by_user_id=str(job.requested_by_user_id) if job.requested_by_user_id else None,
            engine_job_id=str(job.id),
            source_evidence_file_id=str(job.source_evidence_file_id) if job.source_evidence_file_id else None,
            description=f"Evidence ingestion: {job.file_name}",
            extra_metadata={"file_name": job.file_name, "pipeline_scope": "single_job"},
        ):
            # Stage 1: Text extraction -> 0-15%
            await _update_job(job, JobStatus.EXTRACTING_TEXT, 0.0, db, "Extracting text...")
            doc = await extract_text(job.file_path, job.file_name)
            await _update_job(job, JobStatus.EXTRACTING_TEXT, 0.15, db, "Text extracted")

            # Stage 1.5: Document summary -> 15-20%
            await _update_job(job, JobStatus.EXTRACTING_TEXT, 0.15, db, "Generating document summary...")
            doc_summary = await generate_document_summary(doc, job.file_name)
            job.document_summary = doc_summary
            await _update_job(
                job,
                JobStatus.EXTRACTING_TEXT,
                0.20,
                db,
                "Document summary " + ("generated" if doc_summary else "skipped"),
            )
            logger.info("Document summary for %s: %s", job.file_name, "generated" if doc_summary else "skipped/failed")

            # Stage 2: Chunking & embedding -> 20-30%
            await _update_job(job, JobStatus.CHUNKING, 0.20, db, "Chunking document...")
            chunks = await chunk_and_embed(doc, job.case_id, str(job.id), job.file_name)
            await _update_job(job, JobStatus.CHUNKING, 0.30, db, f"Created {len(chunks)} chunks")

            # Stage 3: Entity & relationship extraction -> 30-55%
            await _update_job(job, JobStatus.EXTRACTING_ENTITIES, 0.30, db, "Extracting entities...")
            enriched_context = build_enriched_context(
                job.folder_context,
                job.sibling_files,
                job.llm_profile or "",
            )
            raw_entities, raw_rels = await extract_entities_and_relationships(
                chunks,
                job.effective_context or enriched_context,
                job.file_name,
                mandatory_instructions=job.effective_mandatory_instructions or [],
                special_entity_types=job.effective_special_entity_types or [],
            )
            await _update_job(
                job,
                JobStatus.EXTRACTING_ENTITIES,
                0.55,
                db,
                f"Extracted {len(raw_entities)} entities, {len(raw_rels)} relationships",
            )

            # Stage 3.5: Entity consolidation -> 55-60%
            await _update_job(job, JobStatus.EXTRACTING_ENTITIES, 0.55, db, "Consolidating entities...")
            raw_entities, raw_rels = await consolidate_entities(raw_entities, raw_rels)
            await _update_job(job, JobStatus.EXTRACTING_ENTITIES, 0.60, db, "Entities consolidated")

            # Stage 4: Entity resolution / deduplication -> 60-70%
            await _update_job(job, JobStatus.RESOLVING_ENTITIES, 0.60, db, "Resolving entities...")
            resolved_ents, resolved_rels = await resolve_entities(raw_entities, raw_rels, job.case_id)
            await _update_job(
                job,
                JobStatus.RESOLVING_ENTITIES,
                0.70,
                db,
                f"Resolved to {len(resolved_ents)} entities",
            )

            # Stage 5: Relationship deduplication -> 70-75%
            await _update_job(job, JobStatus.RESOLVING_RELATIONSHIPS, 0.70, db, "Deduplicating relationships...")
            resolved_rels = await resolve_relationships(resolved_rels)
            resolved_rels = link_transaction_parties(resolved_ents, resolved_rels)
            await _update_job(
                job,
                JobStatus.RESOLVING_RELATIONSHIPS,
                0.75,
                db,
                f"Deduplicated to {len(resolved_rels)} relationships",
            )

            # Stage 6: Generate entity summaries -> 75-85%
            await _update_job(job, JobStatus.GENERATING_SUMMARIES, 0.75, db, "Generating entity summaries...")
            resolved_ents = await generate_summaries(resolved_ents, resolved_rels)
            await _update_job(job, JobStatus.GENERATING_SUMMARIES, 0.85, db, "Summaries generated")

            # Stage 7: Write to Neo4j + embed for RAG -> 85-100%
            await _update_job(job, JobStatus.WRITING_GRAPH, 0.85, db, "Writing graph...")
            await write_graph(resolved_ents, resolved_rels, job.case_id, str(job.id))

        job.entity_count = len(resolved_ents)
        job.relationship_count = len(resolved_rels)
        job.status = JobStatus.COMPLETED
        job.progress = 1.0
        await db.commit()
        await publish_progress(
            str(job.id),
            {
                "job_id": str(job.id),
                "status": JobStatus.COMPLETED.value,
                "progress": 1.0,
                "message": "Processing complete",
                "entity_count": len(resolved_ents),
                "relationship_count": len(resolved_rels),
                "document_summary": doc_summary,
            },
        )
    except asyncio.CancelledError:
        # arq cancels the task on job_timeout / shutdown; CancelledError inherits
        # from BaseException, not Exception, so the broader handler below misses
        # it and the row would otherwise stay in its last intermediate status
        # (the "zombie ingestion" failure mode). Mark failed, then re-raise to
        # honor cooperative cancellation.
        logger.warning("Pipeline cancelled for job %s at %s", job_id, job.status)
        try:
            await _update_job(
                job,
                JobStatus.FAILED,
                job.progress,
                db,
                "Cancelled (worker timeout or shutdown)",
                error_message=f"Job cancelled (worker timeout or shutdown) during '{job.status.value}'.",
            )
        except Exception:
            logger.exception("Failed to mark job %s as failed during cancellation", job_id)
        raise
    except Exception as e:
        logger.exception("Pipeline failed for job %s", job_id)
        await _update_job(
            job,
            JobStatus.FAILED,
            job.progress,
            db,
            f"Failed: {e}",
            error_message=str(e),
        )
        raise
