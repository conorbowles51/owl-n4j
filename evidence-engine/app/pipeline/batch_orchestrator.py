import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import async_session
from app.models.job import Job, JobStatus
from app.pipeline.chunk_embed import (
    StagedChunkRevision,
    activate_chunk_revision,
    chunk_and_embed,
    get_document_revision_id,
)
from app.pipeline.consolidate_entities import consolidate_entities
from app.pipeline.context_injector import build_enriched_context
from app.pipeline.extract_entities import (
    RawEntity,
    RawRelationship,
    extract_entities_and_relationships,
)
from app.pipeline.extract_text import extract_text, get_transcription
from app.pipeline.pdf_extraction import PdfExtractionProgress
from app.pipeline.generate_document_summary import generate_document_summary
from app.pipeline.generate_summaries import generate_summaries
from app.pipeline.link_transaction_parties import link_transaction_parties
from app.pipeline.resolve_entities import resolve_entities
from app.pipeline.resolve_relationships import resolve_relationships
from app.pipeline.write_graph import write_graph
from app.services.cost_tracking import ingestion_cost_context
from app.services.ai_model_policy import get_ai_runtime_snapshot, load_ai_model_policy
from app.services.evidence_document_text import upsert_evidence_document_text
from app.services.redis_client import publish_progress
from app.services.pipeline_run_state import (
    add_verification_quality,
    build_extraction_quality_report,
    transition_chunk_publication,
    transition_pipeline_state,
)
from app.services.chunk_publication import publish_chunk_revision
from app.services.claim_ledger import (
    attach_claim_ids,
    compile_grounded_claims,
    persist_grounded_claims,
)
from app.pipeline.verify_claims import verify_grounded_claims

logger = logging.getLogger(__name__)


async def _publish_job_status(
    job_id: uuid.UUID,
    status: JobStatus,
    progress: float,
    message: str = "",
    document_summary: str | None = None,
    error_message: str | None = None,
) -> None:
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
    transcription: str | None = None,
    quality_report: dict | None = None,
    staged_revision: StagedChunkRevision | None = None,
) -> None:
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
        if transcription is not None:
            job.transcription = transcription
        if quality_report is not None:
            job.quality_report = quality_report
        if staged_revision is not None and staged_revision.has_chunks:
            job.pipeline_state = transition_chunk_publication(
                getattr(job, "pipeline_state", None),
                publication_state="staged",
                evidence_file_id=staged_revision.evidence_file_id,
                revision_id=staged_revision.revision_id,
                file_name=staged_revision.file_name,
            )
        job.pipeline_state = transition_pipeline_state(
            getattr(job, "pipeline_state", None),
            stage=status.value,
            message=message,
            error=error_message,
        )
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
    requested_by_user_id: str | None = None,
    source_evidence_file_id: str | None = None,
    folder_context: str | None = None,
    sibling_files: list | None = None,
    effective_context: str | None = None,
    effective_mandatory_instructions: list | None = None,
    effective_special_entity_types: list | None = None,
) -> tuple[
    list[RawEntity],
    list[RawRelationship],
    str | None,
    str | None,
    StagedChunkRevision,
]:
    async with ingestion_cost_context(
        case_id=case_id,
        requested_by_user_id=requested_by_user_id,
        engine_job_id=str(job_id),
        source_evidence_file_id=source_evidence_file_id,
        description=f"Evidence ingestion: {file_name}",
        extra_metadata={"file_name": file_name, "pipeline_scope": "batch_extract"},
    ):
        await _update_job_status(job_id, JobStatus.EXTRACTING_TEXT, 0.0, "Extracting text...")

        async def report_pdf_progress(update: PdfExtractionProgress) -> None:
            if update.total > 0:
                fraction = min(1.0, max(0.0, update.completed / update.total))
                progress = 0.02 + (0.12 * fraction)
            else:
                progress = 0.02
            await _update_job_status(
                job_id,
                JobStatus.EXTRACTING_TEXT,
                progress,
                update.message,
            )

        doc = await extract_text(
            file_path,
            file_name,
            progress_callback=report_pdf_progress,
        )
        if source_evidence_file_id:
            async with async_session() as text_db:
                await upsert_evidence_document_text(
                    text_db,
                    evidence_file_id=source_evidence_file_id,
                    engine_job_id=job_id,
                    doc=doc,
                )
        transcription = get_transcription(doc)
        await _update_job_status(
            job_id,
            JobStatus.EXTRACTING_TEXT,
            0.15,
            "Text extracted",
            transcription=transcription,
        )

        await _update_job_status(job_id, JobStatus.EXTRACTING_TEXT, 0.15, "Generating document summary...")
        enriched_context = build_enriched_context(folder_context, sibling_files, llm_profile)
        summary_context = effective_context or enriched_context
        doc_summary = await generate_document_summary(
            doc,
            file_name,
            case_context=summary_context,
            mandatory_instructions=effective_mandatory_instructions or [],
            special_entity_types=effective_special_entity_types or [],
        )
        await _update_job_status(
            job_id,
            JobStatus.EXTRACTING_TEXT,
            0.20,
            "Document summary " + ("generated" if doc_summary else "skipped"),
            document_summary=doc_summary if doc_summary else None,
        )
        logger.info("Document summary for %s: %s", file_name, "generated" if doc_summary else "skipped/failed")

        await _update_job_status(job_id, JobStatus.CHUNKING, 0.20, "Chunking document...")
        chunk_evidence_file_id = source_evidence_file_id or str(job_id)
        chunk_revision_id = get_document_revision_id(doc)
        chunks = await chunk_and_embed(
            doc,
            case_id,
            str(job_id),
            file_name,
            evidence_file_id=chunk_evidence_file_id,
            revision_id=chunk_revision_id,
        )
        staged_revision = StagedChunkRevision(
            evidence_file_id=chunk_evidence_file_id,
            revision_id=chunk_revision_id,
            file_name=file_name,
            has_chunks=bool(chunks),
            job_id=str(job_id),
        )
        await _update_job_status(
            job_id,
            JobStatus.CHUNKING,
            0.30,
            f"Created {len(chunks)} chunks",
            staged_revision=staged_revision,
        )

        await _update_job_status(job_id, JobStatus.EXTRACTING_ENTITIES, 0.30, "Extracting entities...")
        raw_entities, raw_rels = await extract_entities_and_relationships(
            chunks,
            summary_context,
            file_name,
            mandatory_instructions=effective_mandatory_instructions or [],
            special_entity_types=effective_special_entity_types or [],
        )
        verification = None
        if settings.claim_verification_enabled:
            verification = await verify_grounded_claims(raw_entities, raw_rels)
        quality_report = build_extraction_quality_report(
            entities=raw_entities,
            relationships=raw_rels,
            chunk_count=len(chunks),
            document_metadata=doc.metadata,
        )
        if source_evidence_file_id:
            claims = compile_grounded_claims(
                entities=raw_entities,
                relationships=raw_rels,
                case_id=case_id,
                evidence_file_id=source_evidence_file_id,
                revision_id=chunk_revision_id,
                engine_job_id=str(job_id),
            )
            attach_claim_ids(raw_entities, raw_rels, claims)
            async with async_session() as claim_db:
                await persist_grounded_claims(claim_db, claims)
                await claim_db.commit()
            quality_report = {
                **quality_report,
                "grounded_claim_count": len(claims),
            }
        if verification is not None:
            quality_report = add_verification_quality(
                quality_report,
                verification.quality_metadata(),
            )
            raw_entities, raw_rels = verification.projection_inputs()
        await _update_job_status(
            job_id,
            JobStatus.EXTRACTING_ENTITIES,
            0.55,
            f"Extracted {len(raw_entities)} entities, {len(raw_rels)} relationships",
            quality_report=quality_report,
        )

        return (
            raw_entities,
            raw_rels,
            doc_summary,
            transcription,
            staged_revision,
        )


async def _activate_chunk_revisions(
    case_id: str,
    revisions: list[StagedChunkRevision],
) -> set[str]:
    """Publish every successfully staged document revision."""
    pending_job_ids: set[str] = set()
    for revision in revisions:
        if not revision.has_chunks:
            continue
        try:
            if getattr(revision, "job_id", None):
                async with async_session() as db:
                    result = await db.execute(select(Job).where(Job.id == revision.job_id))
                    job = result.scalar_one()
                    job.pipeline_state = transition_chunk_publication(
                        getattr(job, "pipeline_state", None),
                        publication_state="ready",
                    )
                    await db.commit()
                    await publish_chunk_revision(job, db)
            else:
                await activate_chunk_revision(
                    case_id=case_id,
                    evidence_file_id=revision.evidence_file_id,
                    revision_id=revision.revision_id,
                    file_name=revision.file_name,
                )
        except Exception:
            if revision.job_id:
                pending_job_ids.add(str(revision.job_id))
            logger.exception(
                "Chunk publication queued for recovery for job %s",
                revision.job_id,
            )
    return pending_job_ids


async def _force_fail_unfinished_batch_rows(batch_id: str, reason: str) -> None:
    """Mark every job in this batch still in non-terminal status as failed.

    Called from the cancellation/crash handlers in run_batch_pipeline so users
    aren't left looking at a "still ingesting" UI when the parent task died.
    Idempotent — only touches non-terminal rows.
    """
    async with async_session() as db:
        result = await db.execute(
            select(Job).where(
                Job.batch_id == batch_id,
                Job.status.notin_([JobStatus.COMPLETED, JobStatus.FAILED]),
            )
        )
        unfinished = list(result.scalars().all())
        for job in unfinished:
            job.status = JobStatus.FAILED
            job.error_message = reason
        await db.commit()
        snapshots = [(job.id, job.progress or 0.0) for job in unfinished]
    for job_id, progress in snapshots:
        try:
            await _publish_job_status(
                job_id,
                JobStatus.FAILED,
                progress,
                f"Failed: {reason}",
                error_message=reason,
            )
        except Exception:
            logger.exception("Failed to publish FAILED status for job %s", job_id)
    if snapshots:
        logger.warning(
            "force-failed %d unfinished jobs in batch %s (%s)",
            len(snapshots),
            batch_id,
            reason,
        )


async def run_batch_pipeline(
    batch_id: str,
    case_id: str,
    db: AsyncSession,
) -> None:
    await load_ai_model_policy(db)
    result = await db.execute(select(Job).where(Job.batch_id == batch_id).order_by(Job.created_at))
    jobs = list(result.scalars().all())

    if not jobs:
        logger.warning("No jobs found for batch %s", batch_id)
        return

    runtime_snapshot = get_ai_runtime_snapshot()
    for job in jobs:
        job.pipeline_state = dict(getattr(job, "pipeline_state", None) or {})
        job.pipeline_state["ai_runtime"] = runtime_snapshot
    await db.commit()

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
            "requested_by_user_id": str(job.requested_by_user_id) if job.requested_by_user_id else None,
            "source_evidence_file_id": str(job.source_evidence_file_id) if job.source_evidence_file_id else None,
        }
        for job in jobs
    ]

    logger.info("Starting batch pipeline for %d files in case %s", len(jobs), case_id)

    try:
        file_semaphore = asyncio.Semaphore(max(1, settings.batch_file_max_concurrency))

        async def bounded_extract(ji: dict) -> tuple[
            list[RawEntity],
            list[RawRelationship],
            str | None,
            str | None,
            StagedChunkRevision,
        ]:
            async with file_semaphore:
                return await _extract_file(
                    ji["id"],
                    ji["file_path"],
                    ji["file_name"],
                    case_id,
                    ji["llm_profile"],
                    requested_by_user_id=ji.get("requested_by_user_id"),
                    source_evidence_file_id=ji.get("source_evidence_file_id"),
                    folder_context=ji.get("folder_context"),
                    sibling_files=ji.get("sibling_files"),
                    effective_context=ji.get("effective_context"),
                    effective_mandatory_instructions=ji.get("effective_mandatory_instructions"),
                    effective_special_entity_types=ji.get("effective_special_entity_types"),
                )

        results = await asyncio.gather(
            *(bounded_extract(ji) for ji in job_info),
            return_exceptions=True,
        )

        all_raw_entities: list[RawEntity] = []
        all_raw_rels: list[RawRelationship] = []
        active_job_ids: list[uuid.UUID] = []
        active_file_names: list[str] = []
        job_summaries: dict[uuid.UUID, str | None] = {}
        job_transcriptions: dict[uuid.UUID, str | None] = {}
        staged_chunk_revisions: list[StagedChunkRevision] = []

        for ji, extraction_result in zip(job_info, results):
            if isinstance(extraction_result, Exception):
                logger.exception("Extraction failed for job %s (%s)", ji["id"], ji["file_name"])
                await _update_job_status(
                    ji["id"],
                    JobStatus.FAILED,
                    0.0,
                    f"Extraction failed: {extraction_result}",
                    error_message=str(extraction_result),
                )
                continue

            raw_ents, raw_rels, doc_summary, transcription, staged_revision = extraction_result
            job_summaries[ji["id"]] = doc_summary
            job_transcriptions[ji["id"]] = transcription
            staged_chunk_revisions.append(staged_revision)

            prefix = f"{ji['id']}_"
            for entity in raw_ents:
                entity.temp_id = prefix + entity.temp_id
            for rel in raw_rels:
                rel.source_entity_id = prefix + rel.source_entity_id
                rel.target_entity_id = prefix + rel.target_entity_id

            all_raw_entities.extend(raw_ents)
            all_raw_rels.extend(raw_rels)
            active_job_ids.append(ji["id"])
            active_file_names.append(ji["file_name"])

        if not all_raw_entities:
            logger.warning("No entities extracted from any file in batch %s", batch_id)
            for jid in active_job_ids:
                await _update_job_status(
                    jid,
                    JobStatus.WRITING_GRAPH,
                    0.95,
                    "Publishing search index...",
                    entity_count=0,
                    relationship_count=0,
                )
            pending_publications = await _activate_chunk_revisions(
                case_id,
                staged_chunk_revisions,
            )
            for jid in active_job_ids:
                if str(jid) in pending_publications:
                    continue
                await _update_job_status(
                    jid,
                    JobStatus.COMPLETED,
                    1.0,
                    "No entities found",
                    document_summary=job_summaries.get(jid),
                    transcription=job_transcriptions.get(jid),
                )
            return

        logger.info(
            "Batch extraction complete: %d entities, %d relationships from %d files",
            len(all_raw_entities),
            len(all_raw_rels),
            len(active_job_ids),
        )

        batch_requested_by = next(
            (ji.get("requested_by_user_id") for ji in job_info if ji.get("requested_by_user_id")),
            None,
        )
        async with ingestion_cost_context(
            case_id=case_id,
            requested_by_user_id=batch_requested_by,
            description=f"Evidence ingestion batch {batch_id}",
            extra_metadata={"batch_id": str(batch_id), "pipeline_scope": "batch_unified"},
        ):
            for jid in active_job_ids:
                await _update_job_status(jid, JobStatus.EXTRACTING_ENTITIES, 0.55, "Consolidating entities...")

            all_raw_entities, all_raw_rels = await consolidate_entities(all_raw_entities, all_raw_rels)
            logger.info("Post-consolidation: %d entities, %d relationships", len(all_raw_entities), len(all_raw_rels))

            for jid in active_job_ids:
                await _update_job_status(jid, JobStatus.EXTRACTING_ENTITIES, 0.60, "Entities consolidated")

            for jid in active_job_ids:
                await _update_job_status(jid, JobStatus.RESOLVING_ENTITIES, 0.60, "Resolving entities...")

            resolved_ents, resolved_rels = await resolve_entities(all_raw_entities, all_raw_rels, case_id)
            logger.info("Unified entity resolution: %d -> %d entities", len(all_raw_entities), len(resolved_ents))

            for jid in active_job_ids:
                await _update_job_status(
                    jid,
                    JobStatus.RESOLVING_ENTITIES,
                    0.70,
                    f"Resolved to {len(resolved_ents)} entities",
                )

            for jid in active_job_ids:
                await _update_job_status(jid, JobStatus.RESOLVING_RELATIONSHIPS, 0.70, "Deduplicating relationships...")

            resolved_rels = await resolve_relationships(resolved_rels, resolved_ents)
            resolved_rels = link_transaction_parties(resolved_ents, resolved_rels)

            for jid in active_job_ids:
                await _update_job_status(
                    jid,
                    JobStatus.RESOLVING_RELATIONSHIPS,
                    0.75,
                    f"Deduplicated to {len(resolved_rels)} relationships",
                )

            for jid in active_job_ids:
                await _update_job_status(jid, JobStatus.GENERATING_SUMMARIES, 0.75, "Generating entity summaries...")

            resolved_ents = await generate_summaries(resolved_ents, resolved_rels)

            for jid in active_job_ids:
                await _update_job_status(jid, JobStatus.GENERATING_SUMMARIES, 0.85, "Summaries generated")

            for jid in active_job_ids:
                await _update_job_status(jid, JobStatus.WRITING_GRAPH, 0.85, "Writing graph...")

            await write_graph(resolved_ents, resolved_rels, case_id, batch_id)

        for jid, fname in zip(active_job_ids, active_file_names):
            ent_count = len([entity for entity in resolved_ents if fname in entity.source_files])
            await _update_job_status(
                jid,
                JobStatus.WRITING_GRAPH,
                0.95,
                "Publishing search index...",
                entity_count=ent_count,
                relationship_count=len(resolved_rels),
            )

        pending_publications = await _activate_chunk_revisions(
            case_id,
            staged_chunk_revisions,
        )

        for jid, fname in zip(active_job_ids, active_file_names):
            if str(jid) in pending_publications:
                continue
            ent_count = len([entity for entity in resolved_ents if fname in entity.source_files])
            await _update_job_status(
                jid,
                JobStatus.COMPLETED,
                1.0,
                "Processing complete",
                entity_count=ent_count,
                relationship_count=len(resolved_rels),
                document_summary=job_summaries.get(jid),
                transcription=job_transcriptions.get(jid),
            )

        logger.info("Batch %s complete: %d entities, %d relationships", batch_id, len(resolved_ents), len(resolved_rels))
    except asyncio.CancelledError:
        # arq cancels on job_timeout / shutdown. CancelledError inherits from
        # BaseException, so the broader Exception handler below misses it.
        # Force-fail every non-terminal row in this batch so the UI doesn't
        # keep showing "still ingesting" forever.
        logger.warning("Batch %s cancelled (worker timeout or shutdown)", batch_id)
        try:
            await _force_fail_unfinished_batch_rows(
                batch_id,
                "Batch task cancelled (worker timeout or shutdown). Safe to retry.",
            )
        except Exception:
            logger.exception("Failed to force-fail unfinished rows in batch %s on cancel", batch_id)
        raise
    except Exception as e:
        logger.exception("Batch pipeline failed for batch %s", batch_id)
        try:
            await _force_fail_unfinished_batch_rows(
                batch_id,
                f"Batch pipeline failed: {e}",
            )
        except Exception:
            logger.exception("Failed to force-fail unfinished rows in batch %s on crash", batch_id)
        raise
