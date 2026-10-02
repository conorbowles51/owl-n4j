"""Re-read held batch statements whose reading came from an earlier engine reader.

A deployment changes the reader only for new uploads. This campaign hands a
statement that is still held in a batch back to that batch's own durable
"read again" path, so the current engine reads the retained original and the
batch prepares fresh reviews. It never imports anything: admission still goes
through the ordinary readiness and reconciliation gates and the investigator's
import.

Selection is per batch file and all-or-nothing. A file qualifies only when
every one of its periods is still held, nothing about it carries an
investigator's work or decision, and its retained reading records an exact
affected engine revision. Anything else is left exactly as it is and counted
by reason, so the scope can be explained before and after the run.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID, uuid5

from sqlalchemy import select

from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, IngestionLog
from postgres.models.financial import FinancialSourceDocument
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as BatchItem
from postgres.models.financial_recovery import FinancialRecoveryRun as Run, FinancialRecoveryItem as Item
from services.financial.file_visibility import financial_file_visibility

ELIGIBLE = 'eligible'
HELD = 'attention'
# Retired by an earlier reading of the same original; history only.
HISTORY = 'superseded_reading'
PAUSED = ('pausing', 'paused')
# Why a batch file was left unchanged. Stable keys: tests, logs and the
# dry-run estimate all report these.
REASONS = {
    'standalone_import': 'A single accepted period, not a whole-file preparation.',
    'not_prepared': 'The file is not in a finished preparation (waiting, reading or failed).',
    'unavailable': 'The original or its reading is not available in this case.',
    'not_pdf': 'Only PDF statements are re-read.',
    'removed': 'The investigator removed the source or its imports.',
    'duplicate_decision': 'A duplicate decision is recorded for this statement.',
    'investigator_edits': 'Saved investigator corrections or review progress exist.',
    'saved_import': 'A period is imported, queued for import or admitted.',
    'investigator_decision': 'An investigator left a period unimported, ignored it, removed it or assigned it.',
    'not_all_held': 'At least one period is already ready; a new reading could change it.',
    'nothing_held': 'No held period remains for this file.',
    'several_batches': 'The original is in more than one batch.',
    'processing': 'A reading is already running.',
    'unrecorded_reader': 'The reading has no valid engine record; its reader cannot be proven.',
    'reader_not_affected': 'The reading came from the current or an unrecognised engine revision.',
}
MESSAGES = {
    'removed': 'The investigator removed this source or its imports. Recovery left it unchanged.',
    'duplicate_decision': 'A duplicate decision is recorded for this statement. Recovery left it unchanged.',
    'investigator_edits': 'Investigator corrections were saved on this statement. Recovery left them unchanged.',
    'saved_import': 'A period of this statement is imported or queued. Recovery left it unchanged.',
    'investigator_decision': 'An investigator decision was recorded on this statement. Recovery left it unchanged.',
    'not_all_held': 'A period of this statement is ready. Recovery left it unchanged.',
    'nothing_held': 'No period of this statement is still held. Recovery left it unchanged.',
}
PROTECTED_STATUSES = {
    'imported': 'saved_import', 'pending_import': 'saved_import',
    'skipped': 'investigator_decision', 'duplicate_ignored': 'investigator_decision',
    'removed': 'investigator_decision', 'assigned': 'investigator_decision',
}


def reading_fingerprint(session, file):
    """The engine revision recorded by the reading itself, or None if unproven."""
    from services.financial.pdf_processing_manifest import validate_pdf_processing_manifest
    document = session.get(EvidenceDocumentText, file.id)
    if document is None:
        return None
    try:
        preparation = validate_pdf_processing_manifest(document.processing_manifest)
    except ValueError:
        return None
    if not preparation:
        return None
    content = preparation['content']
    return dict(sources=dict(content['source_files_sha256']),
        reading_mode=content['settings'].get('pdf_reading_mode', 'automatic'))


def duplicate_decision(file):
    """An ignored/restored duplicate, or any disposition a person recorded.

    Preparation itself stores automatic dispositions (not a duplicate,
    retained, needs comparison) for nearly every period; those are system
    projections and are recomputed by the new reading, so they do not protect.
    """
    dispositions = (file.metadata_ or {}).get('financial_duplicate_dispositions') or {}
    if not isinstance(dispositions, dict):
        return True
    for value in dispositions.values():
        if not isinstance(value, dict):
            return True
        for entry in (value, *(value.get('history') or [])):
            if not isinstance(entry, dict):
                return True
            if entry.get('status') in ('ignored', 'restored') or (entry.get('actor') or {}).get('user_id'):
                return True
    return False


def context(session, case_id, cutoff=None):
    query = select(Batch).where(Batch.case_id == case_id, Batch.status != 'removed')
    if cutoff is not None:
        query = query.where(Batch.created_at <= cutoff)
    batches = list(session.scalars(query.order_by(Batch.created_at, Batch.id)))
    every = list(session.scalars(select(Batch).where(Batch.case_id == case_id, Batch.status != 'removed')))
    membership = Counter(entry.get('source_id') for batch in every for entry in batch.files or [])
    admitted = set(session.scalars(select(FinancialSourceDocument.evidence_file_id).where(
        FinancialSourceDocument.case_id == case_id, FinancialSourceDocument.status == 'admitted')))
    return dict(batches=batches, membership=membership, admitted=admitted)


def _uuid(value):
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def classify(session, case_id, batch, entry, campaign, scope):
    """Return (reason, detail). Only ELIGIBLE may be re-read."""
    if entry.get('standalone_import'):
        return 'standalone_import', {}
    if entry.get('status') != 'checked':
        return 'not_prepared', {}
    source_id, reading_id = _uuid(entry.get('source_id')), _uuid(entry.get('file_id'))
    files = {file.id: file for file in session.scalars(select(EvidenceFile).where(
        EvidenceFile.case_id == case_id, EvidenceFile.id.in_([i for i in (source_id, reading_id) if i])))}
    source, reading = files.get(source_id), files.get(reading_id)
    if source is None or reading is None:
        return 'unavailable', {}
    if not reading.original_filename.lower().endswith('.pdf'):
        return 'not_pdf', {}
    if scope['membership'][entry.get('source_id')] > 1:
        return 'several_batches', {}
    pair = (source, reading) if source.id != reading.id else (source,)
    if any(financial_file_visibility(file)['financial_removed'] or financial_file_visibility(file)['financial_imports_removed']
           for file in pair):
        return 'removed', {}
    if any(duplicate_decision(file) for file in pair):
        return 'duplicate_decision', {}
    if any((file.metadata_ or {}).get('financial_review_progress') for file in pair):
        return 'investigator_edits', {}
    # Every period of this reading or its original, in any batch, counts:
    # work saved elsewhere on the same statement is still investigator work.
    items = list(session.scalars(select(BatchItem).join(Batch, BatchItem.batch_id == Batch.id).where(
        Batch.case_id == case_id, Batch.status != 'removed', BatchItem.file_id.in_([file.id for file in pair]))))
    if any(item.review_request for item in items):
        return 'investigator_edits', {}
    for item in items:
        if item.status in PROTECTED_STATUSES:
            return PROTECTED_STATUSES[item.status], {}
    if any(file.id in scope['admitted'] for file in pair):
        return 'saved_import', {}
    own = [item for item in items if item.batch_id == batch.id and item.file_id == reading.id]
    if any(item.status not in (HELD, HISTORY) for item in own) or any(
            item.status not in (HELD, HISTORY) for item in items):
        return 'not_all_held', {}
    held = [item for item in own if item.status == HELD]
    if not held:
        return 'nothing_held', {}
    if any(file.status == 'processing' for file in pair):
        return 'processing', {}
    fingerprint = reading_fingerprint(session, reading)
    if fingerprint is None:
        return 'unrecorded_reader', {}
    if not campaign.eligible(None, fingerprint['sources']):
        return 'reader_not_affected', {}
    return ELIGIBLE, dict(source=source, reading=reading, held=held, reading_mode=fingerprint['reading_mode'],
        extraction_sha256=fingerprint['sources'].get('pdf_extraction.py'))


def candidates(session, case_id, campaign, cutoff=None):
    """Classify every batch file of a case. Read only: used by the dry run too."""
    scope = context(session, case_id, cutoff)
    reasons, selected = Counter(), []
    for batch in scope['batches']:
        for entry in batch.files or []:
            reason, detail = classify(session, case_id, batch, entry, campaign, scope)
            reasons[reason] += 1
            if reason == ELIGIBLE:
                selected.append((batch, entry, detail))
    return selected, reasons


def snapshot(session, case_id, cutoff, campaign, run_id):
    """Durable selection at the release cutoff; the run is the idempotency key."""
    selected, reasons = candidates(session, case_id, campaign, cutoff)
    run = Run(id=run_id, case_id=case_id, release=campaign.release, status='running' if selected else 'complete')
    session.add(run)
    session.flush()
    for batch, entry, detail in selected:
        reading = detail['reading']
        session.add(Item(id=uuid5(run_id, str(reading.id)), run_id=run_id, file_id=reading.id, status='pending',
            result=dict(reader_recovery=True, filename=reading.original_filename, batch_id=str(batch.id),
                source_id=entry['source_id'], from_file_id=str(reading.id), lineage_ids=[str(reading.id)],
                reading_mode=detail['reading_mode'], extraction_sha256=detail['extraction_sha256'],
                held_items=sorted(str(item.id) for item in detail['held']), added=0,
                visibility_revision=financial_file_visibility(detail['source'])['financial_visibility_revision'])))
    scope = dict(considered=sum(reasons.values()), scheduled=len(selected),
        excluded={key: value for key, value in sorted(reasons.items()) if key != ELIGIBLE})
    session.add(IngestionLog(case_id=case_id, level='info',
        message=f'Reader recovery scheduled {len(selected)} held statements for a new reading. '
            f'{scope["considered"] - len(selected)} batch files were left unchanged.',
        extra=dict(operation='statement_recovery_reader_snapshot', release=campaign.release,
            run_id=str(run.id), scope=scope)))
    session.commit()
    return True


def _record(session, item, file, status, message, **values):
    item.status = status
    item.result = {**item.result, **values, 'message': message}
    item.updated_at = datetime.now(timezone.utc)
    session.add(IngestionLog(case_id=file.case_id, evidence_file_id=file.id, filename=file.original_filename,
        level='info', message=message, extra=dict(operation='deployment_statement_recovery',
            release=session.get(Run, item.run_id).release, status=status, added=0)))


def _wait(session, item, status, message):
    if item.status != status or item.result.get('message') != message:
        item.status = status
        item.result = {**item.result, 'message': message}
    item.updated_at = datetime.now(timezone.utc)


def advance(session, item, file, campaign):
    """One step for one statement, under the caller's case lock. Commits."""
    batch = session.scalar(select(Batch).where(Batch.id == UUID(item.result['batch_id']),
        Batch.case_id == file.case_id).with_for_update())
    if batch is None or batch.status == 'removed':
        _record(session, item, file, 'kept', 'The batch was removed. Recovery retained that choice.')
        session.commit()
        return
    files = deepcopy(batch.files or [])
    entry = next((value for value in files if value.get('source_id') == item.result['source_id']), None)
    handoff = item.result.get('handoff')
    if entry is None:
        _record(session, item, file, 'kept', 'The batch no longer contains this statement. Recovery left it unchanged.')
        session.commit()
        return
    if handoff:
        return _follow(session, item, file, batch, entry, handoff)
    if batch.status in PAUSED:
        # The investigator's pause is never lifted by recovery.
        _wait(session, item, 'waiting', 'Waiting for the batch to be resumed. Its pause is unchanged.')
        session.commit()
        return
    if entry.get('file_id') != item.result['from_file_id']:
        _record(session, item, file, 'kept', 'A newer reading of this statement exists. Recovery left it unchanged.')
        session.commit()
        return
    reason, detail = classify(session, file.case_id, batch, entry, campaign, context(session, file.case_id))
    if reason == 'processing':
        _wait(session, item, 'waiting', 'Waiting for the existing reading to finish. It has not been interrupted.')
        session.commit()
        return
    if reason != ELIGIBLE:
        _record(session, item, file, 'kept', MESSAGES.get(reason, 'This statement changed after recovery was scheduled. Recovery left it unchanged.'),
            kept_reason=reason)
        session.commit()
        return
    now = datetime.now(timezone.utc).isoformat()
    attempt = str(uuid5(item.id, 'reader-recovery'))
    # The batch's own durable retry path makes the new version (idempotent per
    # attempt), reads it, prepares reviews and retires only unedited held
    # periods of the earlier reading. Its own guard refuses again if a review
    # is saved before the reading starts.
    entry['recovery'] = dict(attempt_id=attempt, action='reader_recovery', stage='queued',
        message='A newer statement reader is reading this held statement again. The earlier reading and all saved work are retained.',
        fresh_reading=True, read_from_file_id=item.result['from_file_id'],
        reading_file_id=item.result['from_file_id'], review_file_id=item.result['from_file_id'],
        reading_mode=detail['reading_mode'], release=campaign.release, updated_at=now)
    entry.update(status='waiting', expected_revision=financial_file_visibility(detail['source'])['financial_visibility_revision'])
    entry.pop('error', None)
    entry.pop('preparation_retries', None)
    batch.files = files
    batch.status = 'preparing'
    _record(session, item, file, 'waiting', 'Handed to the batch for a new reading. Earlier readings and saved work are retained.',
        handoff=dict(batch_id=str(batch.id), source_id=item.result['source_id'], attempt_id=attempt, at=now))
    session.commit()


def _follow(session, item, file, batch, entry, handoff):
    recovery = entry.get('recovery') or {}
    if recovery.get('attempt_id') != handoff['attempt_id']:
        _record(session, item, file, 'kept', 'A later request replaced this reading. Recovery left it to that request.')
    elif entry.get('status') in ('waiting', 'processing'):
        _wait(session, item, 'reading', 'Reading the original in the background; saved work is unchanged.')
    elif entry.get('status') == 'error':
        _record(session, item, file, 'review', entry.get('error') or 'The new reading needs review. Earlier work is unchanged.')
    elif entry.get('file_id') == item.result['from_file_id']:
        _record(session, item, file, 'review', 'The batch kept the earlier reading. Open its review.')
    else:
        statuses = Counter(session.scalars(select(BatchItem.status).where(BatchItem.batch_id == batch.id,
            BatchItem.file_id == UUID(entry['file_id']))))
        ready, held = statuses.get('ready', 0), statuses.get(HELD, 0)
        message = (f'{ready} of {sum(statuses.values())} periods are ready after the new reading; '
            f'{held} still need attention. The earlier reading is retained in history.')
        _record(session, item, file, 'recovered' if ready else 'unchanged', message,
            review_file_id=entry['file_id'], periods=dict(statuses))
    session.commit()
