"""Check the current engine attempt before retrying an apparently active file.

Slow progress or an unreachable engine never proves a job is dead. Only the
current, case/source/request-correlated terminal or missing attempt is recovered.
"""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select

from postgres.models.evidence import EvidenceFile
from services.financial.pdf_candidates import PdfMappingError


def _identity(file):
    return (str(file.id), file.engine_job_id,
            (file.last_processed_profile_snapshot or {}).get('ingestion_request_id'))


def _matches(job, case_id, identity):
    file_id, job_id, request_id = identity
    if str(job.get('case_id')) != str(case_id):
        return False
    source_id = job.get('source_evidence_file_id')
    if source_id and str(source_id) != file_id:
        return False
    if not source_id and (not job_id or str(job.get('id')) != job_id):
        return False
    if request_id:
        return (job.get('pipeline_state') or {}).get('ingestion_request_id') == request_id
    return bool(job_id and str(job.get('id')) == job_id)


async def retry_file_checked(session, *, case_id, batch_id, source_id):
    from services import evidence_engine_client as engine
    from services.evidence_job_sync import _sync_db_record_from_job
    from services.financial.import_batches import batch_for, require_running, retry_file

    batch = batch_for(session, case_id, batch_id)
    require_running(batch)
    entry = next((file for file in batch.files if file['source_id'] == str(source_id)), None)
    if entry is None:
        raise PdfMappingError('File not found in this batch.', 404)
    candidates = [UUID(value) for value in (entry.get('file_id'), entry['source_id']) if value]
    records = {file.id: file for file in session.scalars(select(EvidenceFile).where(
        EvidenceFile.case_id == case_id, EvidenceFile.id.in_(candidates)))}
    from services.financial.reading_recovery import retry_reference_problem
    if retry_reference_problem(session, case_id=case_id, source_id=source_id,
            source=records.get(source_id), prepared=records.get(UUID(entry['file_id'])) if entry.get('file_id') else None):
        return retry_file(session, case_id=case_id, batch_id=batch_id, source_id=source_id)
    active = next((records[identifier] for identifier in candidates
                   if identifier in records and records[identifier].status == 'processing'), None)
    if active is None:
        return retry_file(session, case_id=case_id, batch_id=batch_id, source_id=source_id)
    identity = _identity(active)
    expected_reading_id = entry.get('file_id')
    # Do not hold any database transaction while waiting for the engine.
    session.commit()
    job, missing, unavailable = None, False, False
    try:
        if identity[1]:
            try:
                job = await engine.get_job(identity[1])
            except httpx.HTTPStatusError as error:
                if error.response.status_code != 404:
                    raise
                missing = True
        if job is None:
            jobs = await engine.list_jobs(str(case_id))
            job = next((item for item in jobs if _matches(item, case_id, identity)), None)
            if job:
                missing = False
    except (httpx.HTTPError, ValueError, RuntimeError):
        unavailable = True

    batch = batch_for(session, case_id, batch_id, True)
    require_running(batch)
    files = deepcopy(batch.files)
    entry = next((file for file in files if file['source_id'] == str(source_id)), None)
    current = session.scalar(select(EvidenceFile).where(EvidenceFile.id == UUID(identity[0]),
        EvidenceFile.case_id == case_id).with_for_update().execution_options(populate_existing=True))
    if entry is None or current is None:
        raise PdfMappingError('The reading changed while its job was checked. Refresh the batch; no retry was started.', 409)
    if entry.get('file_id') != expected_reading_id or _identity(current) != identity or current.status != 'processing':
        raise PdfMappingError('The reading progressed while its job was checked. Refresh the batch to see the current attempt; no second job was started.', 409)

    def remember(action, stage, message):
        prior = entry.get('recovery') or {}
        receipt = {**prior, 'attempt_id': prior.get('attempt_id') or str(uuid4()),
            'action': action, 'stage': stage, 'message': message,
            'reading_file_id': str(current.id), 'review_file_id': str(current.id),
            'job_id': current.engine_job_id, 'updated_at': datetime.now(timezone.utc).isoformat()}
        entry['recovery'] = receipt
        batch.files = files
        session.commit()
        return dict(queued=False, status=entry['status'], **receipt)

    if unavailable or (job and not _matches(job, case_id, identity)):
        return remember('check_status', 'status_unavailable',
            'The current reading job could not be verified. No duplicate job was started. Check its status again when processing is reachable.')
    if job and (job.get('paused') or job.get('status') in ('paused', 'pausing')):
        return remember('resume_reading', 'paused',
            'This reading is paused. Resume it from PDF reading jobs; Retry has kept the paused attempt unchanged.')
    if job and job.get('status') == 'failed':
        _sync_db_record_from_job(current, job)
        entry.update(status='error', error=current.last_error or 'The reading failed.')
    elif missing and job is None:
        current.status = 'failed'
        current.last_error = 'The previously accepted reading job is no longer available. Its saved work remains retained.'
        entry.update(status='error', error=current.last_error)
    elif job and job.get('status') == 'completed':
        _sync_db_record_from_job(current, job)
        if str(current.id) != entry.get('file_id'):
            # The original's independent AI job ended while a retained
            # financial reading failed. Retry the retained financial attempt.
            session.commit()
            return retry_file(session, case_id=case_id, batch_id=batch_id, source_id=source_id)
        entry['status'] = 'processing'
        entry.pop('error', None)
        batch.status = 'preparing'
        return remember('already_running', 'checking_statements',
            'The reading has completed. The batch will now prepare its statement reviews; no new reading was started.')
    else:
        return remember('already_running', 'reading' if job else 'awaiting_dispatch',
            'The existing reading is still active. Its attempt is retained; no duplicate job was started.' if job else
            'The original reading request is still awaiting a confirmed job. Its handoff has not been restarted; check its status again.')
    batch.files = files
    session.commit()
    return retry_file(session, case_id=case_id, batch_id=batch_id, source_id=source_id)
