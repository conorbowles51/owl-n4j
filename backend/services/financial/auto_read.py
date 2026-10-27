"""Statements are read and prepared without anyone starting a batch.

Before: upload -> reading -> the investigator ticks files and starts (or
continues) a batch -> preparation -> review. Now a statement file that enters
Financial is added to the case's automatic batch, and the existing batch worker
reads it (when it has no reading yet) and prepares its statement reviews, which
then appear in the review queue. Nothing is saved or admitted here: saving stays
the investigator's action (or whatever rule the queue already applies).

Which files enter
-----------------
* A PDF uploaded or read from Financial (``POST /api/evidence/process/background``
  with ``preparation_mode='pdf_review'``): the investigator put it in Financial,
  which is the statement decision. This is the only PDF statement signal the
  product had before this module; there was no "is this PDF a bank statement"
  detector on the general Evidence upload.
* A PDF uploaded anywhere else in Evidence, only when the text-layer detector
  (``statement_detection``) finds statement furniture on its first pages and
  ``LOUPE_FINANCIAL_AUTO_DETECT_STATEMENTS`` is on. Media, office files, archives
  and scanned PDFs without a text layer never enter.
  Such a file keeps its ordinary Evidence processing (search, entities): the
  statement reading runs on an internal copy of the same bytes (a statement
  version), never on the original (``prepare_detected``).
* Evidence PDFs registered before detection existed get the same check from the
  sweep (``_backfill_marks``, ``LOUPE_FINANCIAL_AUTO_DETECT_BACKFILL``).
* Files already in Financial that were never read or prepared enter only through
  the explicit "Read N unread statement files" action (or its CLI), never on
  deploy.

Exact copies (the same bytes as a file already in Financial in this case) are
not read again: the copy is recorded on the file, in its history, and named to
the uploader, and it stays in Evidence. Choosing it from Evidence later still
works (an explicit choice).

Load: files enter as ``waiting`` in an automatic batch; the worker starts at
most ``IN_FLIGHT`` readings per automatic batch at a time, and the PDF reading
queue keeps its own concurrency. Detection reads only the first pages' text
layer of at most ``SWEEP_LIMIT`` files per sweep, within a time budget.

Every automatic step is audited with actor "System" (batch actor, file history
entries) and is reversible through the existing paths: pause or remove the
batch, remove the file from Financial. ``LOUPE_FINANCIAL_AUTO_READ_STATEMENTS=0``
switches all of it off.
"""
import logging
import os
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, text, func

from postgres.models.evidence import EvidenceFile, IngestionLog
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item

log = logging.getLogger(__name__)

MARK = 'financial_auto_read'
SYSTEM_NAME = 'System'
SYSTEM_EMAIL = 'system@loupe.local'
# Readings one automatic batch may have queued or running at once. The PDF
# reading worker runs two jobs at a time; keeping the batch at that width
# leaves room for an investigator's own reading instead of a queue of hundreds.
IN_FLIGHT = 2
# A rolling batch keeps receiving files while it is still reading; past this
# size (or once idle) the next file opens a new automatic batch, so the stored
# file list stays small enough to rewrite on every worker step.
MAX_FILES_PER_BATCH = 300
SWEEP_LIMIT = 20
# Unmarked older PDFs given a mark per sweep (no file I/O; detection stays at SWEEP_LIMIT).
BACKFILL_LIMIT = 200
SWEEP_BUDGET_SECONDS = 8.0
LOCK_TIMEOUT = '2s'
ACTIVE_STATES = ('preparing', 'pausing', 'paused')


def enabled():
    return os.environ.get('LOUPE_FINANCIAL_AUTO_READ_STATEMENTS', '1').strip() != '0'


def backfill_enabled():
    """PDFs registered before automatic detection get the same statement check."""
    return detect_enabled() and os.environ.get('LOUPE_FINANCIAL_AUTO_DETECT_BACKFILL', '1').strip() != '0'


def detect_enabled():
    from services.financial.statement_detection import DEFAULT_ENABLED
    value = os.environ.get('LOUPE_FINANCIAL_AUTO_DETECT_STATEMENTS')
    return enabled() and (DEFAULT_ENABLED if value is None else value.strip() == '1')


def _now():
    return datetime.now(timezone.utc).isoformat()


def _is_pdf(name):
    return (name or '').lower().endswith('.pdf')


def is_auto_batch(batch):
    return bool((batch.actor or {}).get('auto_read'))


def _set_mark(file, **values):
    metadata = dict(file.metadata_ or {})
    metadata[MARK] = {**(metadata.get(MARK) or {}), **values, 'updated_at': _now()}
    file.metadata_ = metadata


def mark_registered(file_record):
    """Called when Evidence registers a file: a PDF waits for the statement check.

    Only a marker is written (no I/O); the worker's sweep does the check. Files
    registered before this existed get the same marker from the sweep
    (``_backfill_marks``).
    """
    if not detect_enabled() or not _is_pdf(file_record.original_filename) or file_record.source_type == 'cellebrite':
        return
    metadata = dict(file_record.metadata_ or {})
    if MARK not in metadata:
        metadata[MARK] = dict(state='pending', registered_at=_now())
        file_record.metadata_ = metadata


def _history(session, file, message, **extra):
    session.add(IngestionLog(case_id=file.case_id, evidence_file_id=file.id, filename=file.original_filename,
        level='info', message=message, extra=dict(action='financial_auto_read', actor=dict(name=SYSTEM_NAME), **extra)))


# --- copies -----------------------------------------------------------------

def _in_financial(session, case_id, files):
    """Ids among ``files`` that are in Financial: prepared, saved, in a batch or chosen."""
    from postgres.models.financial import FinancialSourceDocument
    from services.financial.file_scope import SCHEMA
    ids = [f.id for f in files]
    if not ids:
        return set()
    found = set(session.scalars(select(Item.file_id).join(Batch, Batch.id == Item.batch_id).where(
        Batch.case_id == case_id, Batch.status != 'removed', Item.file_id.in_(ids),
        Item.status.notin_(('removed', 'superseded_reading'))).distinct()))
    found |= set(session.scalars(select(FinancialSourceDocument.evidence_file_id).where(
        FinancialSourceDocument.case_id == case_id, FinancialSourceDocument.evidence_file_id.in_(ids)).distinct()))
    wanted = {str(i) for i in ids}
    for entries in session.scalars(select(Batch.files).where(Batch.case_id == case_id, Batch.status != 'removed')):
        for entry in entries or []:
            for key in ('source_id', 'file_id'):
                if entry.get(key) in wanted and entry.get('status') != 'error':
                    found.add(UUID(entry[key]))
    for file in files:
        metadata = file.metadata_ or {}
        if (metadata.get('financial_workspace') or {}).get('schema') == SCHEMA or \
                (metadata.get(MARK) or {}).get('state') in ('statement', 'enrolled'):
            found.add(file.id)
    return found


def existing_copy(session, case_id, file, also=(), exclude=()):
    """Another file in this case with the same bytes that is already in Financial, if any.

    Readings of the same original (its statement versions) are the same file,
    not a copy. ``also`` holds files accepted earlier in the same request;
    ``exclude`` files not yet accepted in it (they cannot be the kept copy).
    """
    from services.financial.file_visibility import financial_file_visibility
    from services.financial.source_lineage import lineage_id
    if not file.sha256:
        return None
    own = lineage_id(file)
    earlier = [f for f in also if f.sha256 == file.sha256 and f.id != file.id and lineage_id(f) != own]
    if earlier:
        return earlier[0]
    twins = [t for t in session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id,
             EvidenceFile.sha256 == file.sha256, EvidenceFile.id != file.id))
             if lineage_id(t) != own and t.id not in exclude and not financial_file_visibility(t)['financial_removed']
             and not (t.metadata_ or {}).get('financial_import_removal')]
    known = _in_financial(session, case_id, twins)
    return next((t for t in sorted(twins, key=lambda t: (t.created_at or datetime.min.replace(tzinfo=timezone.utc), str(t.id)))
                 if t.id in known), None)


def _record_copy(session, file, retained, reason):
    _set_mark(file, state='copy', copy_of=str(retained.id), reason=reason)
    _history(session, file, 'Same file as one already in Financial; not read again.',
             copy_of=str(retained.id), reason=reason)


# --- intake from Financial ----------------------------------------------------

def intake_pdf_review(session, *, case_id, file_ids):
    """Before a Financial reading request: separate exact copies from files to read.

    Returns (ids to read, copies). Files to read are marked for the automatic
    batch; the sweep adds them (bounded lock waits, never in this request).
    """
    if not enabled():
        return list(file_ids), []
    files = {f.id: f for f in session.scalars(select(EvidenceFile).where(
        EvidenceFile.case_id == case_id, EvidenceFile.id.in_(list(file_ids))))}
    to_read, copies, accepted = [], [], []
    for identifier in file_ids:
        file = files.get(identifier)
        if file is None or not _is_pdf(file.original_filename):
            to_read.append(identifier)  # process_db_files gives its own answer
            continue
        state = (file.metadata_ or {}).get(MARK) or {}
        retained = None if state.get('state') in ('statement', 'enrolled') else existing_copy(session, case_id, file, accepted)
        if retained is not None:
            _record_copy(session, file, retained, 'financial_upload')
            copies.append(dict(file_id=str(file.id), filename=file.original_filename,
                               copy_of_file_id=str(retained.id), copy_of=retained.original_filename))
            continue
        # Re-marked even when added before: a file whose batch preparation
        # failed and is read again joins the automatic batch again.
        _set_mark(file, state='statement', reason='financial_upload')
        accepted.append(file)
        to_read.append(identifier)
    session.commit()
    return to_read, copies


# --- the automatic batch -------------------------------------------------------

def _owner(session, case_id, file):
    from postgres.models.case import Case
    return file.created_by_id or session.scalar(select(Case.owner_user_id).where(Case.id == case_id))


def _open_auto_batch(session, case_id):
    for batch in session.scalars(select(Batch).where(Batch.case_id == case_id, Batch.status.in_(ACTIVE_STATES))
            .order_by(Batch.created_at.desc(), Batch.id).with_for_update()):
        if is_auto_batch(batch) and len(batch.files or []) < MAX_FILES_PER_BATCH:
            return batch
    return None


def _lineage_busy(session, case_id, files):
    """Lineage ids already in a batch (other than a failed preparation)."""
    from services.financial.source_lineage import lineage_id, case_lineage
    busy = set()
    ids = {str(f.id) for f in files}
    lineage = case_lineage(session, case_id)
    member = {str(v.id): root for root, versions in lineage.items() for v in versions}
    wanted_roots = {member.get(i, i) for i in ids}
    for entries in session.scalars(select(Batch.files).where(Batch.case_id == case_id, Batch.status != 'removed')):
        for entry in entries or []:
            if entry.get('status') == 'error':
                continue
            for key in ('source_id', 'file_id'):
                root = member.get(entry.get(key) or '', entry.get(key))
                if root in wanted_roots:
                    busy.add(root)
    return {lineage_id(f) for f in files if member.get(str(f.id), str(f.id)) in busy}


def _reason(file, default):
    """Why the file is read: the reason recorded when it was accepted, else the caller's."""
    return ((file.metadata_ or {}).get(MARK) or {}).get('reason') or default


def enroll(session, *, case_id, files, reason, requested_by=None, commit=True):
    """Add statement files to the case's automatic batch. Caller holds the case lock.

    Returns the batch id (or None when nothing was added). Files whose original
    is already in a batch are left alone (that batch reads them).
    """
    from services.financial.file_visibility import financial_file_visibility
    from services.financial.source_lineage import lineage_id
    busy = _lineage_busy(session, case_id, files)
    fresh = [f for f in files if lineage_id(f) not in busy and not financial_file_visibility(f)['financial_removed']
             and not (f.metadata_ or {}).get('financial_import_removal')]
    for file in files:
        if file not in fresh:
            _set_mark(file, state='enrolled', reason=_reason(file, reason), already_in_batch=True)
    if not fresh:
        if commit:
            session.commit()
        return None
    batch = _open_auto_batch(session, case_id)
    now = _now()
    entries = [dict(source_id=str(f.id), file_id=str(f.id), filename=f.original_filename,
                    expected_revision=financial_file_visibility(f)['financial_visibility_revision'], status='waiting',
                    auto_read=dict(reason=_reason(f, reason), at=now, requested_by=requested_by)) for f in fresh]
    if batch is None:
        on_behalf = _owner(session, case_id, fresh[0])
        batch = Batch(id=uuid4(), case_id=case_id, created_by=on_behalf, status='preparing', files=entries,
            actor=dict(name=SYSTEM_NAME, email=SYSTEM_EMAIL, user_id=str(on_behalf), auto_read=True))
        session.add(batch)
    else:
        batch.files = list(batch.files or []) + entries
    session.flush()
    for file in fresh:
        _set_mark(file, state='enrolled', batch_id=str(batch.id), reason=_reason(file, reason))
        _history(session, file, 'Added to automatic statement reading; its statements will appear in the review queue.',
                 batch_id=str(batch.id), reason=reason, requested_by=requested_by)
    if commit:
        session.commit()
    return batch.id


# Reasons a file reached the automatic batch without a person putting it in Financial.
DETECTED_REASONS = frozenset({'detected', 'evidence_backfill'})


def detected_only(entry):
    """A batch entry added only because the detector recognised an Evidence upload."""
    return 'auto_read' in entry and (entry['auto_read'] or {}).get('reason') in DETECTED_REASONS


async def prepare_detected(session, *, case_id, file, actor, resolve_path, process_files):
    """Read a detected statement without touching the original's Evidence processing.

    A person who puts a PDF in Financial reads the original itself (it then
    counts as processed and the Evidence AI pipeline leaves it alone). A file
    that only the detector picked keeps its ordinary Evidence life: the
    statement reading runs on an internal copy of the same bytes (a statement
    version, hidden from Evidence listings), so Evidence search and entities
    still come from processing the original as normal. An original the
    Evidence pipeline has already processed is used as it is.
    """
    from uuid import NAMESPACE_URL, uuid5
    from services.financial.evidence_intake import prepare_existing_financial_file
    from services.financial.file_visibility import financial_file_visibility
    from services.financial.statement_reprocessing import create_statement_version
    original = session.scalar(select(EvidenceFile).where(EvidenceFile.id == UUID(file['source_id']),
        EvidenceFile.case_id == case_id))
    if original is not None and original.status == 'processed':
        return await prepare_existing_financial_file(session, case_id=case_id, evidence_file_id=original.id,
            expected_revision=file['expected_revision'], actor=actor, resolve_path=resolve_path,
            process_files=process_files)
    version = create_statement_version(session, case_id=case_id, evidence_file_id=UUID(file['source_id']),
        request_id=uuid5(NAMESPACE_URL, f"loupe-financial-auto-detect:{case_id}:{file['source_id']}"),
        actor=actor, resolve_path=resolve_path)
    return await prepare_existing_financial_file(session, case_id=case_id, evidence_file_id=version.id,
        expected_revision=financial_file_visibility(version)['financial_visibility_revision'], actor=actor,
        resolve_path=resolve_path, process_files=process_files)


def _lock_case(session, case_id):
    """The case row, waiting at most LOCK_TIMEOUT. False when another unit holds it."""
    from postgres.models.case import Case
    from services.financial.import_batches import _lock_busy_error
    postgres = session.get_bind().dialect.name == 'postgresql'
    try:
        if postgres:
            session.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
        session.execute(select(Case.id).where(Case.id == case_id).with_for_update()).all()
        if postgres:
            session.execute(text('SET LOCAL lock_timeout TO DEFAULT'))
        return True
    except Exception as error:
        if not _lock_busy_error(error):
            raise
        session.rollback()
        return False


# --- the worker sweep ---------------------------------------------------------

def _marked(session, states, limit, extra=()):
    query = (select(EvidenceFile).where(EvidenceFile.metadata_[MARK]['state'].as_string().in_(states), *extra)
             .order_by(EvidenceFile.created_at, EvidenceFile.id).limit(limit))
    if session.get_bind().dialect.name == 'postgresql':
        query = query.with_for_update(skip_locked=True)
    return list(session.scalars(query))


def _backfill_marks(session):
    """Mark PDFs registered before automatic detection, as ``mark_registered`` would have.

    Evidence uploaded before detection existed carried no mark, so a statement
    in it was never read unless someone ran the evidence CLI. Such a PDF that is
    not in Financial waits for the statement check like a new upload; one that
    is already in Financial is left to the explicit "Read unread" action.
    """
    from services.financial.file_scope import financial_file_ids
    files = _marked_none(session)
    by_case = {}
    for file in files:
        by_case.setdefault(file.case_id, []).append(file)
    for case_id, group in by_case.items():
        library = financial_file_ids(session, case_id=case_id)
        for file in group:
            if file.id in library:
                _set_mark(file, state='in_financial', reason='evidence_backfill')
            else:
                _set_mark(file, state='pending', reason='evidence_backfill')
    session.commit()
    return len(files)


def _marked_none(session):
    query = (select(EvidenceFile).where(EvidenceFile.metadata_[MARK]['state'].as_string().is_(None),
             func.lower(EvidenceFile.original_filename).like('%.pdf'),
             func.coalesce(EvidenceFile.source_type, '') != 'cellebrite')
             .order_by(EvidenceFile.created_at, EvidenceFile.id).limit(BACKFILL_LIMIT))
    if session.get_bind().dialect.name == 'postgresql':
        query = query.with_for_update(skip_locked=True)
    return list(session.scalars(query))


def _detect_pending(session, resolve_path, deadline):
    from services.financial.statement_detection import detect
    checked = 0
    # A file the Evidence pipeline is reading now is looked at after it finishes.
    for file in _marked(session, ('pending',), SWEEP_LIMIT, (EvidenceFile.status != 'processing',)):
        if time.monotonic() >= deadline:
            break
        checked += 1
        result = detect(resolve_path(file.stored_path))
        if not result['statement']:
            _set_mark(file, state='not_statement', detection=result)
            continue
        retained = existing_copy(session, file.case_id, file)
        if retained is not None:
            _record_copy(session, file, retained, 'detected')
            continue
        _set_mark(file, state='statement', reason='detected', detection=result)
        _history(session, file, 'Recognised as a bank or card statement from its printed text.', detection=result)
    session.commit()
    return checked


def _enroll_marked(session, deadline):
    added = 0
    files = _marked(session, ('statement',), 200)
    by_case = {}
    for file in files:
        by_case.setdefault(file.case_id, []).append(file)
    session.commit()  # release the row locks before taking a case lock
    for case_id, group in by_case.items():
        if time.monotonic() >= deadline:
            break
        if not _lock_case(session, case_id):
            continue  # a statement review holds the case; next sweep
        current = [f for f in session.scalars(select(EvidenceFile).where(EvidenceFile.id.in_([f.id for f in group]))
                   .with_for_update().execution_options(populate_existing=True))
                   if ((f.metadata_ or {}).get(MARK) or {}).get('state') == 'statement']
        if current:
            enroll(session, case_id=case_id, files=current, reason='automatic')
            added += len(current)
        else:
            session.commit()
    return added


def sweep(factory, resolve_path=None):
    """One bounded round: check newly registered PDFs, then add statements to automatic batches."""
    if not enabled():
        return dict(checked=0, added=0)
    if resolve_path is None:
        from routers.evidence import _resolve_stored_path as resolve_path
    deadline = time.monotonic() + SWEEP_BUDGET_SECONDS
    checked = 0
    with factory() as session:
        if backfill_enabled():
            _backfill_marks(session)
        if detect_enabled():
            checked = _detect_pending(session, resolve_path, deadline)
        added = _enroll_marked(session, deadline)
    return dict(checked=checked, added=added)


# --- files in Financial never read or prepared -------------------------------

def unread_statement_files(session, *, case_id):
    """Current statement PDFs in Financial with no prepared review, no saved statement and no batch.

    Read only. These are what "Read N unread statement files" would add. Files
    in a batch or saved (and every reading of the same original) are excluded
    before any evidence row is loaded, so a large case stays cheap.
    """
    from postgres.models.financial import FinancialSourceDocument
    from postgres.models.financial_candidates import FinancialCandidateMapping, FinancialStatementReviewDraft
    from services.financial.file_scope import SCHEMA
    from services.financial.file_visibility import financial_file_visibility
    from services.financial.source_lineage import lineage_groups, current_version
    busy = {str(i) for i in session.scalars(select(FinancialSourceDocument.evidence_file_id).where(
        FinancialSourceDocument.case_id == case_id).distinct())}
    for entries in session.scalars(select(Batch.files).where(Batch.case_id == case_id, Batch.status != 'removed')):
        for entry in entries or []:
            busy |= {entry.get('source_id'), entry.get('file_id')} - {None}
    busy |= {str(i) for i in session.scalars(select(Item.file_id).join(Batch, Batch.id == Item.batch_id).where(
        Batch.case_id == case_id, Batch.status != 'removed').distinct())}
    excluded = [UUID(i) for i in busy]
    query = select(EvidenceFile).where(EvidenceFile.case_id == case_id,
        func.lower(EvidenceFile.original_filename).like('%.pdf'))
    if excluded:
        query = query.where(EvidenceFile.id.notin_(excluded))
    files = list(session.scalars(query))
    if not files:
        return []
    reviewed = set()
    ids = [f.id for f in files]
    for model in (FinancialCandidateMapping, FinancialStatementReviewDraft):
        reviewed |= set(session.scalars(select(model.evidence_file_id).where(model.case_id == case_id,
            model.evidence_file_id.in_(ids))))
    def enrolled(file):
        metadata = file.metadata_ or {}
        return ((metadata.get('financial_workspace') or {}).get('schema') == SCHEMA
                or (file.last_processed_profile_snapshot or {}).get('preparation_mode') == 'pdf_review'
                or file.id in reviewed
                or any(metadata.get(key) for key in ('financial_review_progress', 'financial_review_history',
                                                     'statement_version_request', 'financial_file_visibility')))
    result = []
    for root, versions in lineage_groups(files).items():
        if root in busy or any(str((v.metadata_ or {}).get('statement_root_evidence_id') or '') in busy for v in versions):
            continue  # another reading of this original is prepared or saved
        if not any(enrolled(v) for v in versions):
            continue
        current = current_version(versions)
        metadata = current.metadata_ or {}
        if financial_file_visibility(current)['financial_removed'] or metadata.get('financial_import_removal') \
                or current.status == 'processing' or (metadata.get(MARK) or {}).get('state') in ('statement', 'copy'):
            continue
        result.append(current)
    return result


def plan_unread(session, *, case_id):
    """(files to read, [(copy, kept file)]) for the unread statement files. Read only."""
    files = unread_statement_files(session, case_id=case_id)
    pending = {f.id for f in files}
    keep, copies = [], []
    for file in files:
        pending.discard(file.id)
        retained = existing_copy(session, case_id, file, keep, exclude=pending)
        if retained is None:
            keep.append(file)
        else:
            copies.append((file, retained))
    return keep, copies


def read_unread(session, *, case_id, actor=None):
    """Add the case's unread statement files to its automatic batch (explicit action)."""
    from services.financial.pdf_candidates import PdfMappingError
    if not _lock_case(session, case_id):
        raise PdfMappingError('Another save is using this case. Nothing was started; try again in a moment.', 409)
    keep, copies = plan_unread(session, case_id=case_id)
    requested = dict(name=actor.name, email=actor.email, user_id=str(actor.user_id)) if actor else None
    for file, retained in copies:
        _record_copy(session, file, retained, 'unread_action')
    batch_id = enroll(session, case_id=case_id, files=keep, reason='unread_action', requested_by=requested, commit=False)
    session.commit()
    return dict(case_id=str(case_id), added=len(keep), copies=len(copies), batch_id=str(batch_id) if batch_id else None)


def evidence_statements(session, *, case_id, resolve_path, limit=None):
    """Evidence PDFs uploaded before automatic reading that the detector recognises. Read only.

    Returns (statements to read, [(copy, kept file)], files checked). Used by the
    CLI only: checking a whole case reads every PDF's first pages, which is too
    slow for a request.
    """
    from services.financial.file_scope import financial_file_ids
    from services.financial.statement_detection import detect
    library = financial_file_ids(session, case_id=case_id)
    files = [f for f in session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id)
             .order_by(EvidenceFile.created_at, EvidenceFile.id))
             if _is_pdf(f.original_filename) and f.id not in library and f.source_type != 'cellebrite'
             and f.status != 'processing' and not ((f.metadata_ or {}).get(MARK) or {}).get('state')
             in ('statement', 'enrolled', 'copy', 'not_statement')]
    if limit:
        files = files[:limit]
    found = [f for f in files if detect(resolve_path(f.stored_path))['statement']]
    pending = {f.id for f in found}
    keep, copies = [], []
    for file in found:
        pending.discard(file.id)
        retained = existing_copy(session, case_id, file, keep, exclude=pending)
        if retained is None:
            keep.append(file)
        else:
            copies.append((file, retained))
    return keep, copies, len(files)


def accept_evidence_statements(session, *, case_id, files, copies):
    """Mark recognised Evidence statements for the automatic batch (the sweep adds them)."""
    for file, retained in copies:
        _record_copy(session, file, retained, 'evidence_backfill')
    for file in files:
        _set_mark(file, state='statement', reason='evidence_backfill')
        _history(session, file, 'Recognised as a bank or card statement from its printed text.', reason='evidence_backfill')
    session.commit()


# --- progress for the status line ---------------------------------------------

def reading_progress(session, *, case_id):
    """Files being read or prepared in this case's unfinished batches. Read only, two small queries."""
    total = done = reading = 0
    paused = False
    for status, files in session.execute(select(Batch.status, Batch.files).where(
            Batch.case_id == case_id, Batch.status.in_(ACTIVE_STATES))):
        if any(f.get('standalone_import') for f in files or []):
            continue
        entries = files or []
        total += len(entries)
        finished = sum(f.get('status') in ('checked', 'error') for f in entries)
        done += finished
        if len(entries) > finished:
            reading += len(entries) - finished
            paused = paused or status in ('pausing', 'paused')
    # Statement files accepted but not yet in a batch (the next sweep adds them).
    detecting = session.scalar(select(func.count()).select_from(EvidenceFile).where(
        EvidenceFile.case_id == case_id,
        EvidenceFile.metadata_[MARK]['state'].as_string() == 'statement')) if enabled() else 0
    return dict(files_total=total, files_done=done, files_reading=reading, paused=paused,
                files_waiting_to_start=detecting or 0)
