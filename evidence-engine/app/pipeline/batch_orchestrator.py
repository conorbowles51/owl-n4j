import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import async_session
from app.models.job import Job, JobStatus
from app.pipeline.chunk_embed import chunk_and_embed
from app.pipeline.consolidate_entities import consolidate_entities
from app.pipeline.context_injector import build_enriched_context
from app.pipeline.extract_entities import (
    RawEntity,
    RawRelationship,
    extract_entities_and_relationships,
)
from app.pipeline.extract_text import extract_text
from app.pipeline.generate_document_summary import generate_document_summary
from app.pipeline.generate_summaries import generate_summaries
from app.pipeline.link_transaction_parties import link_transaction_parties
from app.pipeline.resolve_entities import resolve_entities
from app.pipeline.resolve_relationships import resolve_relationships
from app.pipeline.write_graph import write_graph
from app.services.redis_client import publish_progress

logger = logging.getLogger(__name__)


async def _publish_job_status(
    job_id: uuid.UUID,
    status: JobStatus,
    progress: float,
    message: str = "",
    document_summary: str | None = None,
    error_message: str | None = None,
) -> None:
    """Publish progress without touching the DB session."""
    data = {
        "job_id": str(job_id),
        "status": status.value,
        "progress": progress,
        "message": message,
    }
    if document_summary is not None:
        data["document_summary"] = document_summary
    if error_message is not None:
        data["error_message"] = error_message
    await publish_progress(str(job_id), data)


async def _update_job_status(
    job_id: uuid.UUID,
    status: JobStatus,
    progress: float,
    message: str = "",
    error_message: str | None = None,
    entity_count: int | None = None,
    relationship_count: int | None = None,
    document_summary: str | None = None,
) -> None:
    """Update job status using its own dedicated DB session."""
    async with async_session() as db:
        result = await db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one()
        job.status = status
        job.progress = progress
        if error_message is not None:
            job.error_message = error_message
        if entity_count is not None:
            job.entity_count = entity_count
        if relationship_count is not None:
            job.relationship_count = relationship_count
        if document_summary is not None:
            job.document_summary = document_summary
        await db.commit()
    await _publish_job_status(
        job_id,
        status,
        progress,
        message,
        document_summary=document_summary,
        error_message=error_message,
    )


async def _extract_file(
    job_id: uuid.UUID,
    file_path: str,
    file_name: str,
    case_id: str,
    llm_profile: str,
    folder_context: str | None = None,
    sibling_files: list | None = None,
    effective_context: str | None = None,
    effective_mandatory_instructions: list | None = None,
    effective_special_entity_types: list | None = None,
) -> tuple[list[RawEntity], list[RawRelationship], str | None]:
    """Run stages 1-3 for a single file: extract text, chunk, extract entities."""
    # Stage 1: Text extraction → 0-15%
    await _update_job_status(job_id, JobStatus.EXTRACTING_TEXT, 0.0, "Extracting text…")
    doc = await extract_text(file_path, file_name)
    await _update_job_status(job_id, JobStatus.EXTRACTING_TEXT, 0.15, "Text extracted")

    # Stage 1.5: Document summary → 15-20%
    await _update_job_status(job_id, JobStatus.EXTRACTING_TEXT, 0.15, "Generating document summary…")
    doc_summary = await generate_document_summary(doc, file_name)
    await _update_job_status(
        job_id, JobStatus.EXTRACTING_TEXT, 0.20,
        "Document summary " + ("generated" if doc_summary else "skipped"),
        document_summary=doc_summary if doc_summary else None,
    )
    logger.info("Document summary for %s: %s", file_name, "generated" if doc_summary else "skipped/failed")

    # Stage 2: Chunking & embedding → 20-30%
    await _update_job_status(job_id, JobStatus.CHUNKING, 0.20, "Chunking document…")
    chunks = await chunk_and_embed(doc, case_id, str(job_id), file_name)
    await _update_job_status(job_id, JobStatus.CHUNKING, 0.30, f"Created {len(chunks)} chunks")

    # Stage 3: Entity & relationship extraction → 30-55%
    await _update_job_status(job_id, JobStatus.EXTRACTING_ENTITIES, 0.30, "Extracting entities…")
    enriched_context = build_enriched_context(
        folder_context, sibling_files, llm_profile
    )
    raw_entities, raw_rels = await extract_entities_and_relationships(
        chunks,
        effective_context or enriched_context,
        file_name,
        mandatory_instructions=effective_mandatory_instructions or [],
        special_entity_types=effective_special_entity_types or [],
    )
    await _update_job_status(
        job_id,
        JobStatus.EXTRACTING_ENTITIES,
        0.55,
        f"Extracted {len(raw_entities)} entities, {len(raw_rels)} relationships",
    )

    return raw_entities, raw_rels, doc_summary


async def run_batch_pipeline(
    batch_id: str,
    case_id: str,
    db: AsyncSession,
) -> None:
    """Process a batch of files: parallel extraction + unified dedup."""
    result = await db.execute(
        select(Job).where(Job.batch_id == batch_id).order_by(Job.created_at)
    )
    jobs = list(result.scalars().all())

    if not jobs:
        logger.warning("No jobs found for batch %s", batch_id)
        return

    # Snapshot job info before closing the session scope for parallel work
    job_info = [
        {
            "id": job.id,
            "file_path": job.file_path,
            "file_name": job.file_name,
            "llm_profile": job.llm_profile or "",
            "folder_context": job.folder_context,
            "sibling_files": job.sibling_files,
            "effective_context": job.effective_context,
            "effective_mandatory_instructions": job.effective_mandatory_instructions,
            "effective_special_entity_types": job.effective_special_entity_types,
        }
        for job in jobs
    ]

    logger.info(
        "Starting batch pipeline for %d files in case %s", len(jobs), case_id
    )

    # === PARALLEL: Stages 1-3 for all files ===
    # Each _extract_file uses its own DB session for status updates
    results = await asyncio.gather(
        *(
            _extract_file(
                ji["id"], ji["file_path"], ji["file_name"],
                case_id, ji["llm_profile"],
                folder_context=ji.get("folder_context"),
                sibling_files=ji.get("sibling_files"),
                effective_context=ji.get("effective_context"),
                effective_mandatory_instructions=ji.get("effective_mandatory_instructions"),
                effective_special_entity_types=ji.get("effective_special_entity_types"),
            )
            for ji in job_info
        ),
        return_exceptions=True,
    )

    # Collect all raw entities/relationships, mark failed jobs
    all_raw_entities: list[RawEntity] = []
    all_raw_rels: list[RawRelationship] = []
    active_job_ids: list[uuid.UUID] = []
    active_file_names: list[str] = []
    job_summaries: dict[uuid.UUID, str | None] = {}

    for ji, extraction_result in zip(job_info, results):
        if isinstance(extraction_result, Exception):
            logger.exception(
                "Extraction failed for job %s (%s)", ji["id"], ji["file_name"]
            )
            await _update_job_status(
                ji["id"], JobStatus.FAILED, 0.0,
                f"Extraction failed: {extraction_result}",
                error_message=str(extraction_result),
            )
            continue

        raw_ents, raw_rels, doc_summary = extraction_result
        job_summaries[ji["id"]] = doc_summary

        # Prefix temp_ids with job_id to ensure uniqueness across files.
        # Without this, entities from different files with the same chunk
        # index (e.g., "chunk0_E0") collide in UnionFind and get falsely merged.
        prefix = f"{ji['id']}_"
        for e in raw_ents:
            e.temp_id = prefix + e.temp_id
        for r in raw_rels:
            r.source_entity_id = prefix + r.source_entity_id
            r.target_entity_id = prefix + r.target_entity_id

        all_raw_entities.extend(raw_ents)
        all_raw_rels.extend(raw_rels)
        active_job_ids.append(ji["id"])
        active_file_names.append(ji["file_name"])

    if not all_raw_entities:
        logger.warning("No entities extracted from any file in batch %s", batch_id)
        for jid in active_job_ids:
            await _update_job_status(
                jid, JobStatus.COMPLETED, 1.0, "No entities found",
                document_summary=job_summaries.get(jid),
            )
        return

    logger.info(
        "Batch extraction complete: %d entities, %d relationships from %d files",
        len(all_raw_entities), len(all_raw_rels), len(active_job_ids),
    )

    # === UNIFIED: Stages 3.5-7 across all entities ===
    try:
        # Stage 3.5: Entity consolidation → 55-60%
        for jid in active_job_ids:
            await _update_job_status(
                jid, JobStatus.EXTRACTING_ENTITIES, 0.55, "Consolidating entities…"
            )

        all_raw_entities, all_raw_rels = await consolidate_entities(
            all_raw_entities, all_raw_rels
        )
        logger.info(
            "Post-consolidation: %d entities, %d relationships",
            len(all_raw_entities), len(all_raw_rels),
        )

        for jid in active_job_ids:
            await _update_job_status(
                jid, JobStatus.EXTRACTING_ENTITIES, 0.60, "Entities consolidated"
            )

        # Stage 4: Entity resolution / deduplication → 60-70%
        for jid in active_job_ids:
            await _update_job_status(
                jid, JobStatus.RESOLVING_ENTITIES, 0.60, "Resolving entities…"
            )

        resolved_ents, resolved_rels = await resolve_entities(
            all_raw_entities, all_raw_rels, case_id
        )
        logger.info(
            "Unified entity resolution: %d → %d entities",
            len(all_raw_entities), len(resolved_ents),
        )

        for jid in active_job_ids:
            await _update_job_status(
                jid, JobStatus.RESOLVING_ENTITIES, 0.70,
                f"Resolved to {len(resolved_ents)} entities",
            )

        # Stage 5: Relationship deduplication → 70-75%
        for jid in active_job_ids:
            await _update_job_status(
                jid, JobStatus.RESOLVING_RELATIONSHIPS, 0.70,
                "Deduplicating relationships…",
            )

        resolved_rels = await resolve_relationships(resolved_rels)
        resolved_rels = link_transaction_parties(resolved_ents, resolved_rels)

        for jid in active_job_ids:
            await _update_job_status(
                jid, JobStatus.RESOLVING_RELATIONSHIPS, 0.75,
                f"Deduplicated to {len(resolved_rels)} relationships",
            )

        # Stage 6: Generate entity summaries → 75-85%
        for jid in active_job_ids:
            await _update_job_status(
                jid, JobStatus.GENERATING_SUMMARIES, 0.75,
                "Generating entity summaries…",
            )

        resolved_ents = await generate_summaries(resolved_ents, resolved_rels)

        for jid in active_job_ids:
            await _update_job_status(
                jid, JobStatus.GENERATING_SUMMARIES, 0.85, "Summaries generated"
            )

        # Stage 7: Write to Neo4j + embed for RAG → 85-100%
        for jid in active_job_ids:
            await _update_job_status(
                jid, JobStatus.WRITING_GRAPH, 0.85, "Writing graph…"
            )

        await write_graph(resolved_ents, resolved_rels, case_id, batch_id)

        # Update all active jobs as completed with per-file entity counts
        for jid, fname in zip(active_job_ids, active_file_names):
            ent_count = len(
                [e for e in resolved_ents if fname in e.source_files]
            )
            await _update_job_status(
                jid, JobStatus.COMPLETED, 1.0, "Processing complete",
                entity_count=ent_count,
                relationship_count=len(resolved_rels),
                document_summary=job_summaries.get(jid),
            )

        logger.info(
            "Batch %s complete: %d entities, %d relationships",
            batch_id, len(resolved_ents), len(resolved_rels),
        )

    except Exception as e:
        logger.exception("Batch pipeline failed for batch %s", batch_id)
        for jid in active_job_ids:
            await _update_job_status(
                jid, JobStatus.FAILED, 0.0, f"Failed: {e}",
                error_message=str(e),
            )
        raise
