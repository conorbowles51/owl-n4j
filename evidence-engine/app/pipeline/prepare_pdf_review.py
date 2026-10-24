"""Prepare registered PDF source text and locations locally; no AI or ledger writes."""
from pathlib import Path
from app.dependencies import async_session
from app.models.job import JobStatus
from app.pipeline.extract_text import extract_text
from app.services.evidence_document_text import upsert_evidence_document_text
from app.services.evidence_table_geometry import replace_evidence_table_geometry
from app.services.ingestion_checkpoints import pause_boundary
from app.services.db_retry import is_transient_db_error, retry_transient

async def prepare_pdf_review(job, update_status):
    if not job.source_evidence_file_id or Path(job.file_name or '').suffix.lower() != '.pdf':
        raise ValueError('A registered PDF is required')
    reading_mode = (getattr(job, 'pipeline_state', None) or {}).get('pdf_reading_mode', 'automatic')
    if reading_mode not in ('automatic', 'page_images'):
        raise ValueError('Unknown PDF reading method')
    await update_status(job.id, JobStatus.EXTRACTING_TEXT, 0.0, 'Preparing PDF source for review')
    async def progress(update):
        await pause_boundary()
        fraction = min(0.9, 0.9 * update.completed / update.total) if update.total else 0.0
        try:
            await update_status(job.id, JobStatus.EXTRACTING_TEXT, fraction, update.message)
        except Exception as error:
            # A progress message that keeps losing a lock conflict is not a
            # reason to discard the pages already read; the next one retries.
            if not is_transient_db_error(error):
                raise
    # extract_text's PDF branch uses the native text layer and local Tesseract.
    document = await extract_text(job.file_path, job.file_name, progress_callback=progress,
        pdf_reading_mode=reading_mode)
    async def store():
        async with async_session() as db:
            # One source generation must become visible together. A cancellation,
            # invalid geometry or commit failure retains the previous generation.
            async with db.begin():
                await upsert_evidence_document_text(db, evidence_file_id=job.source_evidence_file_id,
                    engine_job_id=job.id, doc=document, commit=False)
                geometry = await replace_evidence_table_geometry(db, evidence_file_id=job.source_evidence_file_id,
                    engine_job_id=job.id, metadata=document.metadata, commit=False)
                if geometry.entries_invalid:
                    raise ValueError('Some PDF source locations could not be stored')
    # A deadlock rolls the whole generation back, so storing it again is safe.
    await retry_transient(store)
    await update_status(job.id, JobStatus.COMPLETED, 1.0,
        'PDF source ready for review; no transactions verified or added',
        quality_report={'preparation_mode':'pdf_review','pdf_reading_mode':reading_mode,'transactions_admitted':0,
            'limitation':'Source extraction only. Review is required; missing tables do not establish absence of transactions.'})
