"""Re-prepare finished batch files after a release changes how statements are read.

Preparing a batch file turns its saved reading (text and table geometry, no
OCR) into statement reviews. A release that changes the statement readers
changes what that preparation produces, but until now nothing re-prepared a
file that had already been prepared: an investigator had to press "Check for
additional statement periods" in each batch, and files the queue called
"waiting for a reader fix" stayed waiting after the fix shipped.

This sweep does it automatically, from the batch loop, never from a read:

* ``reader_stamp()`` digests the source of the modules that turn a saved
  reading into statement reviews (``READER_MODULES``, one list) with the review
  model and proposal version. A file records the stamp it was prepared with
  (``file['reader_stamp']``, written when its preparation finishes).
* A checked file of an unfinished batch (status ``review``, a statement still
  ready or held) whose stamp differs is read again with the current code,
  read-only. It is re-prepared only when that reading differs from what its
  statements already store: another set of statements, or a statement whose
  reading revision or review model changed. Otherwise only its stamp is
  updated, so an unrelated release costs one read per file and no writes to
  statements.
* Re-preparation is the batch's own: the file goes back to ``processing``, the
  batch to ``preparing``, and the worker prepares it from the saved reading.
  Preparation keeps every edit, draft, import, exclusion and copy decision
  (``import_batches.prepare_reviews``); statements that check out completely
  are then saved automatically like any other preparation (``queue_save``).
* A file whose statements carry an investigator's saved review that the new
  reading would conflict with is left as it is (counted), never re-prepared
  into an error. A file that cannot be read now is left as it was.

Bounded per sweep (files compared, seconds) and resumable: all state is the
stamp on each batch file. One switch: ``RECHECK_AFTER_RELEASE`` (env
``FINANCIAL_RECHECK_AFTER_RELEASE``), default on.
"""
import hashlib
import logging
import os
import time
from collections import Counter
from copy import deepcopy
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial.pdf_candidates import PdfMappingError
from services.financial.read_only_session import reads_outside_transaction

log = logging.getLogger(__name__)

RECHECK_AFTER_RELEASE = os.environ.get('FINANCIAL_RECHECK_AFTER_RELEASE', '1').strip().lower() not in (
    '0', 'false', 'off', 'no')
# The code that turns a saved reading into statement reviews and their
# readiness. A change to any of these files is a reader release. Including a
# module that does not change readings costs one read-only comparison per
# prepared file after a release; leaving one out means its fixes reach
# prepared files only by hand.
READER_MODULES = (
    'statement_import*.py', 'statement_engine*.py', 'statement_engine_routes.json', 'statement_layout_context.py',
    'statement_information_pages.py', 'statement_printed_no_activity.py', 'statement_movement_scaffold.py',
    'statement_reading_quality.py', 'statement_currency.py', 'statement_totals.py', 'statement_balances.py',
    'statement_checks.py', 'statement_admission.py', 'statement_row_assignment.py', 'statement_review_checks.py',
    'pdf_tables.py', 'pdf_geometry_candidates.py', 'table_geometry.py', 'card_*.py', 'andrews_period_pinning.py',
    'late_posted_card_dates.py', 'closing_only_period.py', 'layout_memory.py', 'text_rows.py', 'printed_totals.py',
    'money.py', 'dates.py', 'source_dates.py', 'import_issues.py', 'review_arithmetic.py', 'payment_inference.py', 'payment_parties.py', 'payment_party_reasons.py',
    'spei_description.py', 'deposit_receipt_proposal.py', 'payment_document_proposal.py', 'credit_line_total_owed.py', 'scan_daily_balance.py',
    # The page-image reader of held statements: a release of it re-checks prepared files, and a file
    # whose text reading is unchanged but still holds statements is marked for it (_store).
    'vision_reader.py',
)
# Not listed: import_batches.py. Its changes (scheduling, saves) cannot change
# what the comparison looks at (the reading revision, computed by the reading
# modules, and REVIEW_MODEL, which is in the stamp itself), so listing it would
# only make every deploy read all prepared files again for nothing. Live, read
# only (2026-10-15): one full pass reads 894 files, 2,903 open statements.
FILES_PER_SWEEP = 25
SWEEP_BUDGET_SECONDS = 20.0
RECHECK_STAGE = 'reader_release'
# Why a file was not re-prepared although the reader changed. Stable keys.
LEFT = {
    'unchanged': 'The current reader reads it exactly as before.',
    'saved_review': 'A saved review of one of its statements would conflict with the new reading.',
    'unreadable': 'It cannot be read now; it is left as it was.',
    'nothing_open': 'None of its statements is still ready or held.',
}

_stamp = None


def reader_stamp():
    """Digest of the statement-reading code in this process (computed once)."""
    global _stamp
    if _stamp is None:
        from services.financial.import_batches import REVIEW_MODEL
        from services.financial.statement_import_proposal import VERSION
        root = Path(__file__).resolve().parent
        digest = hashlib.sha256(f'{REVIEW_MODEL}\0{VERSION}\0'.encode())
        for path in sorted({p for pattern in READER_MODULES for p in root.glob(pattern)}):
            digest.update(path.name.encode() + b'\0' + hashlib.sha256(path.read_bytes()).digest())
        _stamp = digest.hexdigest()
    return _stamp


def _open_items(session, batch_id, file_id):
    return list(session.scalars(select(Item).where(Item.batch_id == batch_id, Item.file_id == file_id,
                                                   Item.status.notin_(('removed', 'superseded_reading')))))


def reading_changed(session, *, case_id, batch_file, items):
    """'changed', or the LEFT key saying why the file stays as it is. Read only."""
    from services.financial.import_batches import REVIEW_MODEL
    from services.financial.statement_import import read_statement_import
    from services.financial.statement_progress import review_progress
    open_items = [item for item in items if item.status in ('ready', 'attention')]
    if not open_items:
        return 'nothing_open'
    file = session.get(EvidenceFile, UUID(batch_file['file_id']))
    if file is None:
        return 'unreadable'
    cache = {}
    try:
        first = read_statement_import(session, case_id=case_id, evidence_file_id=file.id,
                                      currency=batch_file.get('currency'), _cache=cache)
        keys = {choice['id'] for choice in first.get('statement_choices', [])} or {first.get('statement_id') or ''}
        if batch_file.get('standalone_import'):
            keys &= {batch_file.get('statement_id') or ''}
        changed = keys != {item.statement_key or '' for item in items}
        revisions = {}
        for item in open_items:
            proposal = read_statement_import(session, case_id=case_id, evidence_file_id=file.id,
                currency=item.summary.get('currency') or None, statement_id=item.statement_key or None, _cache=cache)
            revisions[item.statement_key or ''] = proposal['revision']
            if proposal['revision'] != item.summary.get('revision') or item.summary.get('review_model') != REVIEW_MODEL:
                changed = True
    except PdfMappingError:
        return 'unreadable'
    finally:
        session.rollback()
    if not changed:
        return 'unchanged'
    # Preparation refuses a file whose shared saved review was made on another
    # reading (it asks the investigator to compare first). Leave those as they
    # are rather than turning a prepared file into an error.
    for key, revision in revisions.items():
        progress = review_progress(file, key)
        request = (progress or {}).get('request') or {}
        if progress and request.get('expected_revision') not in (None, revision):
            return 'saved_review'
    return 'changed'


def _candidates(session, stamp):
    """{batch: [(file index, batch file, has an open statement)]} of checked files prepared by other code.

    Only batches in 'review' (prepared, not running): a running batch's files
    belong to its worker.
    """
    result = {}
    for batch in session.scalars(select(Batch).where(Batch.status == 'review').order_by(Batch.updated_at, Batch.id)):
        stale = [(index, entry) for index, entry in enumerate(batch.files or []) if entry.get('status') == 'checked'
                 and entry.get('reader_stamp') != stamp and entry.get('file_id')]
        if not stale:
            continue
        open_files = {str(i) for i in session.scalars(select(Item.file_id).where(
            Item.batch_id == batch.id, Item.status.in_(('ready', 'attention'))))}
        result[(batch.id, batch.case_id)] = [(index, deepcopy(entry), entry['file_id'] in open_files)
                                             for index, entry in stale]
    return result


def _store(session, batch_id, case_id, verdicts, stamp):
    """Record the stamps and queue the re-preparations of one batch, if it is still as compared. Returns files rechecked."""
    from services.financial.import_batches import batch_for, _reading_progress
    batch = batch_for(session, case_id, batch_id, True)
    files = deepcopy(batch.files or [])
    if batch.status != 'review':
        session.rollback()
        return None
    rechecked = 0
    for index, entry, verdict in verdicts:
        if (index >= len(files) or files[index].get('file_id') != entry['file_id']
                or files[index].get('status') != 'checked' or files[index].get('reader_stamp') != entry.get('reader_stamp')):
            continue
        files[index]['reader_stamp'] = stamp
        if verdict == 'unchanged':
            # Its held statements are read from their page images (vision_reader); a re-prepared
            # file is marked when its preparation ends.
            from services.financial import vision_reader
            if vision_reader.ENABLED:
                files[index][vision_reader.MARK] = True
        if verdict == 'changed':
            # The worker prepares it again from its saved reading (no OCR).
            files[index]['status'] = 'processing'
            files[index]['recheck'] = dict(reason=RECHECK_STAGE, stamp=stamp)
            _reading_progress(files[index], 'checking_statements',
                              'Loupe was updated; checking this file again with the new version. No action is needed.')
            rechecked += 1
    if rechecked:
        batch.status = 'preparing'
    batch.files = files
    session.commit()
    return rechecked


def sweep(factory, *, max_files=None, budget_seconds=None):
    """Re-prepare files whose statements the current reader reads differently. Never raises.

    Batch by batch: its stale files are compared (read only), then every
    verdict of that batch is recorded in one write, so all of its changed
    files are prepared again in the same run of the batch.
    """
    outcome = dict(compared=0, rechecked=0, files=0, left=Counter())
    if not RECHECK_AFTER_RELEASE:
        outcome['left'] = {}
        return outcome
    max_files = FILES_PER_SWEEP if max_files is None else max_files
    budget_seconds = SWEEP_BUDGET_SECONDS if budget_seconds is None else budget_seconds
    started, stamp = time.monotonic(), reader_stamp()
    with factory() as db:
        work = _candidates(db, stamp)
    for (batch_id, case_id), entries in work.items():
        verdicts = []
        try:
            for index, entry, has_open in entries:
                if has_open and (outcome['compared'] >= max_files or time.monotonic() - started >= budget_seconds):
                    break
                if has_open:
                    with factory() as db:
                        # Read only; minutes of comparison must not hold a transaction open (read_only_session).
                        reads_outside_transaction(db)
                        items = _open_items(db, batch_id, UUID(entry['file_id']))
                        verdict = reading_changed(db, case_id=case_id, batch_file=entry, items=items)
                    outcome['compared'] += 1
                else:
                    verdict = 'nothing_open'
                verdicts.append((index, entry, verdict))
            if not verdicts:
                break
            with factory() as db:
                rechecked = _store(db, batch_id, case_id, verdicts, stamp)
            if rechecked is None:
                continue  # The batch started running meanwhile; compared again later.
            outcome['files'] += len(verdicts)
            outcome['rechecked'] += rechecked
            outcome['left'].update(verdict for _, _, verdict in verdicts if verdict != 'changed')
        except Exception:
            log.exception('Re-checking prepared statement files after a release failed; they will be tried again')
        if outcome['compared'] >= max_files or time.monotonic() - started >= budget_seconds:
            break
    outcome['left'] = dict(outcome['left'])
    return outcome
