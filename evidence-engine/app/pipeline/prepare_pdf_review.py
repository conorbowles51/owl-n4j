"""Prepare registered PDF source text and locations locally; no AI or ledger writes."""
from pathlib import Path
from app.dependencies import async_session
from app.models.job import JobStatus
from app.pipeline.extract_text import extract_text
from app.services.evidence_document_text import upsert_evidence_document_text
from app.services.evidence_table_geometry import replace_evidence_table_geometry

async def prepare_pdf_review(job, update_status):
    if not job.source_evidence_file_id or Path(job.file_name or '').suffix.lower() != '.pdf':
        raise ValueError('A registered PDF is required')
    await update_status(job.id, JobStatus.EXTRACTING_TEXT, 0.0, 'Preparing PDF source for review')
    async def progress(update):
        fraction = min(0.9, 0.9 * update.completed / update.total) if update.total else 0.0
        await update_status(job.id, JobStatus.EXTRACTING_TEXT, fraction, update.message)
    # extract_text's PDF branch uses the native text layer and local Tesseract.
    document = await extract_text(job.file_path, job.file_name, progress_callback=progress)
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
    await update_status(job.id, JobStatus.COMPLETED, 1.0,
        'PDF source ready for review; no transactions verified or added',
        quality_report={'preparation_mode':'pdf_review','transactions_admitted':0,
            'limitation':'Source extraction only. Review is required; missing tables do not establish absence of transactions.'})
