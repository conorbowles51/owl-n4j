"""Audio preparation and the adapter into the ordinary text pipeline."""
import hashlib
import uuid

from app.dependencies import async_session
from app.models.job import JobStatus
from app.pipeline.extract_text import extract_text, ExtractedDocument, get_transcription, get_transcription_segments
from app.services.ai_model_policy import load_ai_model_policy
from app.services.ingestion_checkpoints import pause_boundary
from app.services.ingestion_control import begin_publication
from postgres.models.evidence import EvidenceFile
from postgres.models.transcript import TranscriptRevision, TranscriptSource
from services.transcript_review import capture_source, render_revision, feature_enabled


async def load_saved_document(revision_id, evidence_id, case_id, file_path):
    async with async_session() as db:
        revision = await db.get(TranscriptRevision, uuid.UUID(str(revision_id)))
        if revision is None or str(revision.evidence_file_id) != str(evidence_id) or str(revision.case_id) != str(case_id):
            raise ValueError('Saved transcript is not available in this case')
        source = await db.get(TranscriptSource, revision.source_id)
        def digest():
            with open(file_path, 'rb') as recording:
                return hashlib.file_digest(recording, 'sha256').hexdigest()
        import asyncio
        if await asyncio.to_thread(digest) != source.source_sha256:
            raise ValueError('Recording changed since transcription; preserve and inspect the source')
        rendered = render_revision(source, revision)
        metadata = {**rendered['metadata'], 'transcription': source.text,
                    'transcription_segments': source.segments, 'transcript_input_format': 'reviewed_turns_v1'}
        return ExtractedDocument(text=rendered['text'], metadata=metadata)


async def save_machine_document(job_id, evidence_id, case_id, doc, *, review_required=False):
    async with async_session() as db:
        def store(sync):
            file = sync.get(EvidenceFile, uuid.UUID(str(evidence_id)))
            if file is None or str(file.case_id) != str(case_id):
                raise ValueError('Recording does not belong to this case')
            from app.models.job import Job
            machine_job = sync.get(Job, uuid.UUID(str(job_id)))
            if machine_job and machine_job.sha256 and machine_job.sha256 != file.sha256:
                raise ValueError('Recording bytes differ from the registered source')
            state = capture_source(sync, file, job_id=str(job_id), text=get_transcription(doc),
                segments=get_transcription_segments(doc), review_required=review_required,
                metadata={'model': doc.metadata.get('transcription_model')})
            return str(state.working_revision_id)
        revision_id = await db.run_sync(store)
        await db.commit()
        return revision_id


async def prepare_audio_review(job, update_status):
    if not job.source_evidence_file_id:
        raise ValueError('Audio preparation requires a registered evidence file')
    async with async_session() as db:
        await load_ai_model_policy(db)
    await update_status(job.id, JobStatus.EXTRACTING_TEXT, 0.0, 'Transcribing recording for review')
    async def progress(update):
        await pause_boundary()
        await update_status(job.id, JobStatus.EXTRACTING_TEXT,
            min(.95, .95 * update.completed / update.total) if update.total else 0,
            update.message)
    doc = await extract_text(job.file_path, job.file_name, progress_callback=progress)
    if doc.metadata.get('file_type') != 'audio':
        raise ValueError('Transcript review requires an audio recording')
    await begin_publication([job.id])  # the last stop before the transcript is saved
    await save_machine_document(job.id, job.source_evidence_file_id, job.case_id, doc, review_required=True)
    await update_status(job.id, JobStatus.COMPLETED, 1.0, 'Transcript ready for review; graph processing has not started',
        transcription=get_transcription(doc), transcription_segments=get_transcription_segments(doc))


async def ingestion_document(job_id, file_path, file_name, case_id, evidence_id, revision_id=None, progress_callback=None, extractor=extract_text):
    if revision_id:
        return await load_saved_document(revision_id, evidence_id, case_id, file_path)
    doc = await extractor(file_path, file_name, progress_callback=progress_callback)
    if evidence_id and doc.metadata.get('file_type') == 'audio' and feature_enabled():
        revision_id = await save_machine_document(job_id, evidence_id, case_id, doc)
        saved = await load_saved_document(revision_id, evidence_id, case_id, file_path)
        # Fresh direct processing keeps the original plain-text pipeline input.
        # Capture its source/revision for later review without inserting labels.
        doc.metadata.update({'transcript_revision_id': revision_id,
            'transcript_digest': saved.metadata['transcript_digest'], 'transcript_input_format': 'machine_text_v1'})
    return doc


async def publish_audio_document_text(job, db):
    state = getattr(job, 'pipeline_state', None) or {}
    revision_id = state.get('transcript_revision_id')
    if not revision_id: return
    doc = await load_saved_document(revision_id, job.source_evidence_file_id, job.case_id, job.file_path)
    if state.get('transcript_input_format') == 'machine_text_v1':
        doc.text = doc.metadata['transcription']
        doc.metadata.pop('transcript_turns', None)
    from app.services.evidence_document_text import upsert_evidence_document_text
    await upsert_evidence_document_text(db, evidence_file_id=job.source_evidence_file_id,
        engine_job_id=job.id, doc=doc, commit=False, published=True)
