"""Re-read held batch statements whose reading came from an earlier engine reader.

A deployment changes the reader only for new uploads. This campaign hands a
statement that is still held in a batch back to that batch's own durable
"read again" path, so the current engine reads the retained original and the
batch prepares fresh reviews. It never imports anything: admission still goes
through the ordinary readiness and reconciliation gates and the investigator's
import.

Selection is per batch file and all-or-nothing. A file qualifies only when
every one of its periods is still held, nothing about it carries an
investigator's work or decision, and its retained reading records an
affected engine revision (one the campaign names, or for the engine-release
campaign any other than the deployed one). Anything else is left exactly as
it is and counted by reason, so the scope can be explained before and after
the run.

Bounded and ingestion-safe: at most ``READ_AGAIN_AT_ONCE`` statements are
handed to batches at a time across the host, and none is handed off while
other evidence is being read (an upload's ingestion has the engine first).
A statement waiting for a slot keeps its place; nothing is lost on restart.
"""
import os
import time
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID, uuid5

from sqlalchemy import String, cast, column, exists, inspect, select, table

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
    'copy_of_saved': 'The case already saved this account and period: a copy to compare.',
}
MESSAGES = {
    'removed': 'The investigator removed this source or its imports. Recovery left it unchanged.',
    'duplicate_decision': 'A duplicate decision is recorded for this statement. Recovery left it unchanged.',
    'investigator_edits': 'Investigator corrections were saved on this statement. Recovery left them unchanged.',
    'saved_import': 'A period of this statement is imported or queued. Recovery left it unchanged.',
    'investigator_decision': 'An investigator decision was recorded on this statement. Recovery left it unchanged.',
    'not_all_held': 'A period of this statement is ready. Recovery left it unchanged.',
    'nothing_held': 'No period of this statement is still held. Recovery left it unchanged.',
    'copy_of_saved': 'This case already saved this account and period. Recovery left this copy for comparison.',
}
# Readings handed to batches at once (host-wide), and how long the count of
# evidence being read elsewhere is reused before it is counted again.
READ_AGAIN_AT_ONCE = max(1, int(os.environ.get('LOUPE_FINANCIAL_READER_RECOVERY_AT_ONCE', '4') or 4))
BUSY_SECONDS = 30.0
_busy = {}
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


def _system_entry(entry):
    """A disposition the System recorded (an automatic set-aside), never a person's."""
    actor = entry.get('actor')
    return isinstance(actor, dict) and actor.get('name') == 'System' and not actor.get('user_id')


def _person_disposition(value):
    """True unless every entry of one statement's disposition is the System's own projection or set-aside."""
    if not isinstance(value, dict):
        return True
    for entry in (value, *(value.get('history') or [])):
        if not isinstance(entry, dict):
            return True
        if (entry.get('actor') or {}).get('user_id') if isinstance(entry.get('actor'), dict) else entry.get('actor'):
            return True
        if entry.get('status') == 'restored' or (entry.get('status') == 'ignored' and not (
                SETTLED_SIBLINGS and _system_entry(entry))):
            return True
    return False


def duplicate_decision(file):
    """An ignored/restored duplicate a person recorded, or any disposition a person recorded.

    Preparation itself stores automatic dispositions (not a duplicate,
    retained, needs comparison) for nearly every period; those are system
    projections and are recomputed by the new reading, so they do not protect.
    A copy the System set aside by itself (status ignored, actor System, no
    person anywhere in its history) is such a projection too (SETTLED_SIBLINGS);
    an ignored entry without a recorded actor is treated as a person's.
    """
    dispositions = (file.metadata_ or {}).get('financial_duplicate_dispositions') or {}
    if not isinstance(dispositions, dict):
        return True
    return any(_person_disposition(value) for value in dispositions.values())


# A held statement is read again even when another statement of the same file was already settled without
# a person's work on it: saved (imported; its saved review carries no edit, since any edit protects the whole
# file) or set aside by the System as a copy. The new reading never touches a settled statement: its own item,
# admitted records and disposition stay; the new reading's twin of it meets the ordinary copy and
# already-saved gates (pending_statement_duplicates, queue_save). A 'ready' listing of a statement the same
# original already saved is settled as well. Still protected: queued imports, a person's skip, ignore, restore,
# assignment or removal, any other ready statement, and any edit. Off: every settled statement
# protects its file, as before.
SETTLED_SIBLINGS = os.environ.get('LOUPE_FINANCIAL_RECOVERY_SETTLED_SIBLINGS', '1').strip().lower() not in (
    '0', 'false', 'no', 'off')


# A held statement whose printed account and period the case already saved (from another original, or from
# this one under another statement key) is a copy for the duplicate workflow to compare, not for a new reading
# to save: a copy read under other bank wording, product type or statement split can be saved into a second
# ledger account (the live double admission), and the save gates key on (bytes, statement key). Fail closed:
# such a file is left as it is. Off: not checked, as before.
COPY_OF_SAVED_PROTECTS = os.environ.get('LOUPE_FINANCIAL_RECOVERY_COPY_OF_SAVED', '1').strip().lower() not in (
    '0', 'false', 'no', 'off')


def _digits(value):
    return ''.join(ch for ch in str(value or '') if ch.isdigit())


def _same_account(saved, read):
    """Fail closed: an older reading can misread a digit, so the last six digits decide (all, when shorter)."""
    if not saved or not read:
        return False
    if min(len(saved), len(read)) < 6:
        return saved == read
    return saved[-6:] == read[-6:]


def copy_of_saved(session, case_id, source, held, cache=None):
    """True when a held statement's account and period are already admitted in the case. Read only.

    A saved period of another Santander product sharing the last six digits (santander_subaccounts) is not a
    copy of it.
    """
    if not COPY_OF_SAVED_PROTECTS:
        return False
    from datetime import date
    from postgres.models.financial import FinancialAccount, FinancialStatementPeriod
    from services.financial.santander_subaccounts import another_product
    wanted = {}
    for item in held:
        summary = item.summary or {}
        try:
            start, end = date.fromisoformat(summary['period_start']), date.fromisoformat(summary['period_end'])
        except (KeyError, TypeError, ValueError):
            continue
        if _digits(summary.get('account')):
            wanted.setdefault((start, end), []).append(item)
    memo = {}
    for (start, end), items in wanted.items():
        rows = session.execute(select(FinancialStatementPeriod, FinancialAccount)
            .join(FinancialSourceDocument, FinancialSourceDocument.id == FinancialStatementPeriod.source_document_id)
            .join(FinancialAccount, FinancialAccount.id == FinancialStatementPeriod.account_id)
            .join(EvidenceFile, EvidenceFile.id == FinancialSourceDocument.evidence_file_id)
            .where(FinancialStatementPeriod.case_id == case_id, FinancialSourceDocument.status == 'admitted',
                   FinancialStatementPeriod.period_start == start, FinancialStatementPeriod.period_end == end)).all()
        for period, account in rows:
            for item in items:
                wanted_digits = _digits((item.summary or {}).get('account'))
                if not any(_same_account(_digits(saved), wanted_digits)
                           for saved in (account.identifier_normalised, account.identifier_as_printed)):
                    continue
                if another_product(session, case_id, item, period, account, cache=cache, memo=memo):
                    continue
                return True
    return False


def settled_sibling(item, file, saved_keys=()):
    """True for a statement settled with no person's work on it (see SETTLED_SIBLINGS). Read only.

    ``saved_keys``: statement keys of the same original saved through another item. A 'ready' item of such a
    key is a stale listing of a statement already saved (it cannot be saved again), so it is settled too.
    """
    if not SETTLED_SIBLINGS or item.review_request:
        return False
    if item.status == 'imported':
        return True
    if item.status == 'ready' and item.statement_key and item.statement_key in saved_keys:
        return True
    if item.status == 'duplicate_ignored' and file is not None:
        dispositions = (file.metadata_ or {}).get('financial_duplicate_dispositions') or {}
        value = dispositions.get(item.statement_key or '') if isinstance(dispositions, dict) else None
        return isinstance(value, dict) and value.get('status') == 'ignored' and not _person_disposition(value)
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


# A removal recorded on an original before the batch that holds a newer reading of it was made is the start
# of that restart (remove imports, then add the file again: ``evidence_intake.prepare_existing_financial_file``
# reads a new version for the new batch), not a decision about the statements the restart prepared. Such a
# batch file is judged like any other (every other guard still applies). Off: every removal protects, as before.
RESTARTED_AFTER_REMOVAL = os.environ.get('LOUPE_FINANCIAL_RECOVERY_RESTARTED', '1').strip().lower() not in (
    '0', 'false', 'no', 'off')


def _instant(value):
    if isinstance(value, datetime):
        moment = value
    else:
        try:
            moment = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def restarted_after_removal(source, reading, batch):
    """True when every removal on this batch file predates the batch and its reading (the restart). Read only.

    Fails closed: the reading itself removed, a removal without a recorded time, or one recorded at or after
    the batch or the reading was made, keeps the file protected.
    """
    if not RESTARTED_AFTER_REMOVAL or source.id == reading.id or batch is None:
        return False
    visibility = financial_file_visibility(reading)
    if visibility['financial_removed'] or visibility['financial_imports_removed']:
        return False
    metadata = source.metadata_ or {}
    stamps = []
    if metadata.get('financial_import_removal'):
        stamps.append((metadata['financial_import_removal'] or {}).get('at'))
    if financial_file_visibility(source)['financial_removed']:
        stamps.append((metadata.get('financial_file_visibility') or {}).get('changed_at'))
    made = [_instant(getattr(batch, 'created_at', None)), _instant(getattr(reading, 'created_at', None))]
    removed = [_instant(stamp) for stamp in stamps]
    if not stamps or None in made or None in removed:
        return False
    return max(removed) < min(made)


def _uuid(value):
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def classify(session, case_id, batch, entry, campaign, scope, group=False):
    """Return (reason, detail). Only ELIGIBLE may be re-read.

    ``group``: the entry is judged as one member of its original's batches
    (``candidates`` requires every member to qualify), so being in several
    batches is not itself a reason to leave it.
    """
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
    if scope['membership'][entry.get('source_id')] > 1 and not group:
        return 'several_batches', {}
    pair = (source, reading) if source.id != reading.id else (source,)
    if any(financial_file_visibility(file)['financial_removed'] or financial_file_visibility(file)['financial_imports_removed']
           for file in pair) and not restarted_after_removal(source, reading, batch):
        return 'removed', {}
    if any(duplicate_decision(file) for file in pair):
        return 'duplicate_decision', {}
    from services.financial.reread_carry import CARRY_EDITS, work_fingerprint
    carry = {}
    if any((file.metadata_ or {}).get('financial_review_progress') for file in pair):
        if not CARRY_EDITS:
            return 'investigator_edits', {}
        carry = dict(carry_work=work_fingerprint(session, case_id, [file.id for file in pair]))
    # Every period of this reading or its original, in any batch, counts:
    # work saved elsewhere on the same statement is still investigator work.
    items = list(session.scalars(select(BatchItem).join(Batch, BatchItem.batch_id == Batch.id).where(
        Batch.case_id == case_id, Batch.status != 'removed', BatchItem.file_id.in_([file.id for file in pair]))))
    if any(item.review_request for item in items):
        if not CARRY_EDITS:
            return 'investigator_edits', {}
        carry = carry or dict(carry_work=work_fingerprint(session, case_id, [file.id for file in pair]))
    files = {file.id: file for file in pair}
    saved_keys = {item.statement_key for item in items if item.status == 'imported' and item.statement_key}
    settled = [item for item in items if settled_sibling(item, files.get(item.file_id), saved_keys)]
    for item in items:
        if item.status in PROTECTED_STATUSES and item not in settled:
            return PROTECTED_STATUSES[item.status], {}
    if any(file.id in scope['admitted'] for file in pair) and not (SETTLED_SIBLINGS and any(
            item.status == 'imported' for item in settled)):
        return 'saved_import', {}
    own = [item for item in items if item.batch_id == batch.id and item.file_id == reading.id]
    if any(item.status not in (HELD, HISTORY) and item not in settled for item in items):
        return 'not_all_held', {}
    held = [item for item in own if item.status == HELD]
    if not held:
        return 'nothing_held', {}
    if copy_of_saved(session, case_id, source, held):
        return 'copy_of_saved', {}
    if any(file.status == 'processing' for file in pair):
        return 'processing', {}
    fingerprint = reading_fingerprint(session, reading)
    if fingerprint is None:
        return 'unrecorded_reader', {}
    if not campaign.eligible(None, fingerprint['sources']):
        return 'reader_not_affected', {}
    return ELIGIBLE, dict(source=source, reading=reading, held=held, reading_mode=fingerprint['reading_mode'],
        extraction_sha256=fingerprint['sources'].get('pdf_extraction.py'), **carry)


# A member of a several-batch original that no longer holds anything there
# (every period retired by an earlier reading) needs no new preparation.
IDLE_MEMBER = 'nothing_held'
# A member whose preparation failed in its batch and that holds no statement there (an error waiting for a
# person's retry, which makes its own reading) is idle too: it does not keep the original's held statements in
# the other batches from being read again, and it is left exactly as it is. Off: it protects them, as before.
FAILED_MEMBER_IDLE = os.environ.get('LOUPE_FINANCIAL_RECOVERY_FAILED_MEMBER_IDLE', '1').strip().lower() not in (
    '0', 'false', 'no', 'off')


def failed_idle(session, batch, entry):
    """True for a batch file whose preparation failed and that holds no statement in its batch. Read only."""
    if not FAILED_MEMBER_IDLE or entry.get('status') != 'error' or entry.get('standalone_import'):
        return False
    ids = [i for i in (_uuid(entry.get('file_id')), _uuid(entry.get('source_id'))) if i]
    return not ids or not session.scalar(select(BatchItem.id).where(BatchItem.batch_id == batch.id,
        BatchItem.file_id.in_(ids), BatchItem.status != HISTORY).limit(1))


def _group_reason(session, case_id, members, campaign, scope):
    """(reason, [(batch, entry, detail)] to read again) for one original held in several batches.

    All or nothing: every batch file of the original must be in scope and
    qualify on its own (no investigator work or decision on any reading of
    it, in any batch, nothing ready, an affected reader); a member whose
    periods were all retired already is skipped. Otherwise the whole
    original is left, with the first member's reason.
    """
    if len(members) < scope['membership'][members[0][1].get('source_id')]:
        return 'several_batches', []  # a batch made after the release cutoff holds it too
    chosen = []
    for batch, entry in members:
        if failed_idle(session, batch, entry):
            continue
        reason, detail = classify(session, case_id, batch, entry, campaign, scope, group=True)
        if reason == IDLE_MEMBER:
            continue
        if reason != ELIGIBLE:
            return reason, []
        chosen.append((batch, entry, detail))
    return (ELIGIBLE, chosen) if chosen else (IDLE_MEMBER, [])


def candidates(session, case_id, campaign, cutoff=None):
    """Classify every batch file of a case. Read only: used by the dry run too.

    Returns ([(batch, entry, detail, members)], reasons by batch file). An
    original held in several batches is one selection: ``members`` lists each
    of its batch files to read again (newest batch last, which is the one the
    queue shows); every batch file of the group is counted with its reason.
    """
    scope = context(session, case_id, cutoff)
    reasons, selected, groups = Counter(), [], {}
    for batch in scope['batches']:
        for entry in batch.files or []:
            reason, detail = classify(session, case_id, batch, entry, campaign, scope)
            if reason == 'several_batches' or (scope['membership'][entry.get('source_id')] > 1
                                               and failed_idle(session, batch, entry)):
                groups.setdefault(entry.get('source_id'), []).append((batch, entry))
                continue
            reasons[reason] += 1
            if reason == ELIGIBLE:
                selected.append((batch, entry, detail, [(batch, entry, detail)]))
    for members in groups.values():
        reason, chosen = _group_reason(session, case_id, members, campaign, scope)
        reasons[reason] += len(members)
        if reason == ELIGIBLE:
            selected.append((*chosen[-1], chosen))
    # Batch files under different source ids can resolve to one reading (one original in two batches through
    # its lineage). One reading is one item, so such a reading is not chosen for either: it stays held.
    readings = Counter(str(detail['reading'].id) for _, _, detail, _ in selected)
    shared = [pick for pick in selected if readings[str(pick[2]['reading'].id)] > 1]
    for pick in shared:
        reasons[ELIGIBLE] -= len(pick[3])
        reasons['several_batches'] += len(pick[3])
    selected = [pick for pick in selected if readings[str(pick[2]['reading'].id)] == 1]
    return selected, reasons


def not_prepared_breakdown(session, case_id):
    """Why batch files never reached a finished preparation: {"batch status/file status[/auto]": n}. Read only.

    'error' files are terminal (only lock conflicts are retried); 'waiting' and
    'processing' files of a paused batch wait for the investigator; those of a
    preparing batch are queued behind the batch's in-flight limit, waiting on
    another batch preparing the same reading, or on an engine reading that
    has not finished.
    """
    counts = Counter()
    for batch in session.scalars(select(Batch).where(Batch.case_id == case_id, Batch.status != 'removed')):
        for entry in batch.files or []:
            if entry.get('status') != 'checked' and not entry.get('standalone_import'):
                counts['/'.join([batch.status, str(entry.get('status')), *(['auto'] if 'auto_read' in entry else []),
                    *(['recovery'] if entry.get('recovery') else [])])] += 1
    return dict(sorted(counts.items()))


def supersede_earlier(session, case_id, release):
    """Move an earlier engine release's statements not yet handed off to this release. Returns how many.

    Each is recorded 'kept' with its reason, so the earlier run shows where it
    went; the newer snapshot then selects it again under today's rule. A
    reading already handed to a batch is followed to its end by its own run.
    """
    from services.financial.recovery_campaigns import READER_RELEASE_PREFIX
    moved = 0
    for run in session.scalars(select(Run).where(Run.case_id == case_id, Run.release != release,
            Run.release.startswith(READER_RELEASE_PREFIX), Run.status != 'complete')):
        for item in session.scalars(select(Item).where(Item.run_id == run.id, Item.status.in_(('pending', 'waiting')))):
            if (item.result or {}).get('handoff'):
                continue
            item.status = 'kept'
            item.result = {**item.result, 'kept_reason': 'newer_release',
                'message': 'A newer reader was deployed before this statement was read again; it is rechecked with that reader.'}
            item.updated_at = datetime.now(timezone.utc)
            moved += 1
    session.flush()
    return moved


def snapshot(session, case_id, cutoff, campaign, run_id):
    """Durable selection at the release cutoff; the run is the idempotency key."""
    if campaign.current_readers:
        supersede_earlier(session, case_id, campaign.release)
    # Held statements that need no person (a copy the saved ledger agrees with, a fund statement) are set
    # aside first; the selection below then sees them settled (held_settlement).
    from services.financial.held_settlement import settle_held_statements
    settled = settle_held_statements(session, case_id)
    selected, reasons = candidates(session, case_id, campaign, cutoff)
    membership = context(session, case_id)['membership']
    run = Run(id=run_id, case_id=case_id, release=campaign.release, status='running' if selected else 'complete')
    session.add(run)
    session.flush()
    for batch, entry, detail, members in selected:
        reading = detail['reading']
        session.add(Item(id=uuid5(run_id, str(reading.id)), run_id=run_id, file_id=reading.id, status='pending',
            result=dict(reader_recovery=True, filename=reading.original_filename, batch_id=str(batch.id),
                source_id=entry['source_id'], from_file_id=str(reading.id),
                lineage_ids=sorted({str(d['reading'].id) for _, _, d in members}),
                reading_mode=detail['reading_mode'], extraction_sha256=detail['extraction_sha256'],
                member_count=membership[entry['source_id']],
                held_items=sorted(str(item.id) for _, _, d in members for item in d['held']), added=0,
                members=[dict(batch_id=str(b.id), source_id=e['source_id'], from_file_id=str(d['reading'].id),
                    reading_mode=d['reading_mode']) for b, e, d in members],
                visibility_revision=financial_file_visibility(detail['source'])['financial_visibility_revision'])))
    scope = dict(considered=sum(reasons.values()), scheduled=len(selected),
        batch_files=sum(len(members) for *_, members in selected),
        excluded={key: value for key, value in sorted(reasons.items()) if key != ELIGIBLE},
        settled=dict(sorted(settled.items())))
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


def rereading_files(session, case_id):
    """Evidence ids (reading and original) of this case's statements scheduled to be read again.

    Pending, waiting for a slot or being read by a reader campaign: the queue
    counts their held statements as being rechecked, not as work, until the
    new reading settles them.
    """
    from services.financial.recovery_campaigns import READER_RECOVERY_RELEASE, READER_RELEASE_PREFIX
    from sqlalchemy import or_
    ids = set()
    for result in session.scalars(select(Item.result).join(Run, Item.run_id == Run.id).where(
            Run.case_id == case_id, or_(Run.release.startswith(READER_RELEASE_PREFIX), Run.release == READER_RECOVERY_RELEASE),
            Run.status == 'running', Item.status.in_(('pending', 'waiting', 'reading')))):
        if (result or {}).get('reader_recovery'):
            ids |= {result.get('from_file_id'), result.get('source_id')} - {None}
    return ids


def in_flight(session):
    """Statements of reader campaigns handed to a batch and still being read (host-wide)."""
    from services.financial.recovery_campaigns import READER_RECOVERY_RELEASE, READER_RELEASE_PREFIX
    from sqlalchemy import or_
    results = session.scalars(select(Item.result).join(Run, Item.run_id == Run.id).where(
        or_(Run.release.startswith(READER_RELEASE_PREFIX), Run.release == READER_RECOVERY_RELEASE),
        Run.status == 'running', Item.status.in_(('waiting', 'reading'))))
    return sum(1 for result in results if (result or {}).get('handoff'))


# The evidence engine's job table (same database, owned by the engine).
_engine_jobs = table('jobs', column('source_evidence_file_id'), column('status'), column('paused'))
_jobs_visible = {}


def _engine_jobs_visible(session):
    bind = session.get_bind()
    if id(bind) not in _jobs_visible:
        _jobs_visible[id(bind)] = inspect(bind).has_table('jobs')
    return _jobs_visible[id(bind)]


def evidence_being_read(session, now=None):
    """Evidence files being read now, host-wide (reused for BUSY_SECONDS).

    A file counts only while an engine job is actually working on it (not
    finished, failed or paused). ``processing`` alone is not proof: a file whose
    job died or was failed keeps that status until its case is next synced, and
    counting it held every re-read back for as long as it stayed (one such file
    blocked a case for weeks).
    """
    now = time.monotonic() if now is None else now
    if _busy and now - _busy['at'] < BUSY_SECONDS:
        return _busy['count']
    from sqlalchemy import func
    query = select(func.count()).select_from(EvidenceFile).where(EvidenceFile.status == 'processing')
    if _engine_jobs_visible(session):
        query = query.where(exists().where(_engine_jobs.c.source_evidence_file_id == EvidenceFile.id,
            cast(_engine_jobs.c.status, String).not_in(('completed', 'failed')), _engine_jobs.c.paused.is_(False)))
    count = session.scalar(query) or 0
    _busy.update(at=now, count=count)
    return count


def slot_wait(session):
    """Why a new hand-off must wait now, or None when a slot is free."""
    running = in_flight(session)
    if running >= READ_AGAIN_AT_ONCE:
        return f'Waiting its turn: {running} statements are being read again now.'
    if evidence_being_read(session) > running:
        return 'Waiting while other evidence is being read. It is read again as soon as that finishes.'
    return None


def _hold_place(session, item, message):
    """Waiting for a slot: write only when the message changes (no write per turn)."""
    if item.status != 'waiting' or item.result.get('message') != message:
        item.status = 'waiting'
        item.result = {**item.result, 'message': message}
        item.updated_at = datetime.now(timezone.utc)
        session.commit()
    else:
        session.rollback()


def _members(result):
    """The batch files one recovery item reads again (one, or every batch holding its original)."""
    return result.get('members') or [dict(batch_id=result['batch_id'], source_id=result['source_id'],
        from_file_id=result['from_file_id'])]


def _attempt(item, member):
    """One durable attempt per distinct earlier reading: batches sharing a reading share one new reading.

    The batch's retry path makes the new version idempotently per attempt, so a
    second batch holding the same reading finds that version (read once, or
    being read) instead of starting another engine reading.
    """
    if member['from_file_id'] == item.result['from_file_id']:
        return str(uuid5(item.id, 'reader-recovery'))
    return str(uuid5(item.id, 'reader-recovery:' + member['from_file_id']))


def advance(session, item, file, campaign):
    """One step for one statement (its original, in every batch holding it), under the caller's case lock. Commits."""
    if not item.result.get('handoff') and (wait := slot_wait(session)):
        return _hold_place(session, item, wait)
    members = _members(item.result)
    ids = sorted({UUID(member['batch_id']) for member in members}, key=str)
    batches = {batch.id: batch for batch in session.scalars(select(Batch).where(Batch.id.in_(ids),
        Batch.case_id == file.case_id).order_by(Batch.id).with_for_update())}
    handoff = item.result.get('handoff')
    if handoff:
        return _follow(session, item, file, batches, handoff)
    found = []
    for member in members:
        batch = batches.get(UUID(member['batch_id']))
        if batch is None or batch.status == 'removed':
            _record(session, item, file, 'kept', 'The batch was removed. Recovery retained that choice.')
            session.commit()
            return
        files = deepcopy(batch.files or [])
        entry = next((value for value in files if value.get('source_id') == member['source_id']), None)
        if entry is None:
            _record(session, item, file, 'kept', 'The batch no longer contains this statement. Recovery left it unchanged.')
            session.commit()
            return
        found.append((member, batch, files, entry))
    if any(batch.status in PAUSED for _, batch, _, _ in found):
        # The investigator's pause is never lifted by recovery.
        _wait(session, item, 'waiting', 'Waiting for the batch to be resumed. Its pause is unchanged.')
        session.commit()
        return
    if any(entry.get('file_id') != member['from_file_id'] for member, _, _, entry in found):
        _record(session, item, file, 'kept', 'A newer reading of this statement exists. Recovery left it unchanged.')
        session.commit()
        return
    scope = context(session, file.case_id)
    group = len(found) > 1 or scope['membership'][item.result['source_id']] > 1
    handed = {(str(batch.id), entry.get('source_id')) for _, batch, _, entry in found}
    others = [(batch, entry) for batch in scope['batches'] for entry in batch.files or []
              if entry.get('source_id') == item.result['source_id'] and (str(batch.id), entry.get('source_id')) not in handed]
    # Every batch holding the original when it was scheduled, idle ones included (older items: those handed).
    expected = item.result.get('member_count', len(found))
    if group and (scope['membership'][item.result['source_id']] != expected or any(
            not failed_idle(session, batch, entry) and classify(session, file.case_id, batch, entry, campaign, scope,
                                                                 group=True)[0] != IDLE_MEMBER for batch, entry in others)):
        # Another batch took the original after scheduling: its work is not judged here.
        _record(session, item, file, 'kept', 'Another batch now holds this statement. Recovery left it unchanged.',
            kept_reason='several_batches')
        session.commit()
        return
    chosen = []
    for member, batch, files, entry in found:
        reason, detail = classify(session, file.case_id, batch, entry, campaign, scope, group=group)
        if reason == 'processing':
            _wait(session, item, 'waiting', 'Waiting for the existing reading to finish. It has not been interrupted.')
            session.commit()
            return
        if group and reason == IDLE_MEMBER:
            continue
        if reason != ELIGIBLE:
            _record(session, item, file, 'kept', MESSAGES.get(reason, 'This statement changed after recovery was scheduled. Recovery left it unchanged.'),
                kept_reason=reason)
            session.commit()
            return
        chosen.append((member, batch, files, entry, detail))
    if not chosen:
        _record(session, item, file, 'kept', MESSAGES['nothing_held'], kept_reason='nothing_held')
        session.commit()
        return
    now = datetime.now(timezone.utc).isoformat()
    handed = []
    for member, batch, files, entry, detail in chosen:
        attempt = _attempt(item, member)
        # The batch's own durable retry path makes the new version (idempotent per
        # attempt), reads it, prepares reviews and retires only unedited held
        # periods of the earlier reading. Its own guard refuses again if a review
        # is saved before the reading starts.
        entry['recovery'] = dict(attempt_id=attempt, action='reader_recovery', stage='queued',
            message='A newer statement reader is reading this held statement again. The earlier reading and all saved work are retained.',
            fresh_reading=True, read_from_file_id=member['from_file_id'],
            reading_file_id=member['from_file_id'], review_file_id=member['from_file_id'],
            reading_mode=detail['reading_mode'], release=campaign.release, updated_at=now,
            **({'carry_work': detail['carry_work']} if detail.get('carry_work') else {}))
        entry.update(status='waiting', expected_revision=financial_file_visibility(detail['source'])['financial_visibility_revision'])
        entry.pop('error', None)
        entry.pop('preparation_retries', None)
        batch.files = files
        batch.status = 'preparing'
        handed.append(dict(batch_id=str(batch.id), source_id=member['source_id'], from_file_id=member['from_file_id'],
            attempt_id=attempt))
    first = handed[-1]
    _record(session, item, file, 'waiting', 'Handed to the batch for a new reading. Earlier readings and saved work are retained.'
        if len(handed) == 1 else f'Handed to its {len(handed)} batches for one new reading. Earlier readings and saved work are retained.',
        handoff=dict(batch_id=first['batch_id'], source_id=first['source_id'], attempt_id=first['attempt_id'],
            batches=handed, at=now))
    session.commit()


def _member_state(session, batch, entry, member, attempt):
    """('replaced'|'reading'|'error'|'kept_earlier'|'done', detail) of one handed-off batch file."""
    if batch is None or batch.status == 'removed' or entry is None:
        return 'replaced', 'The batch or its statement was removed. Recovery retained that choice.'
    if (entry.get('recovery') or {}).get('attempt_id') != attempt:
        return 'replaced', 'A later request replaced this reading. Recovery left it to that request.'
    if entry.get('status') in ('waiting', 'processing'):
        return 'reading', None
    if entry.get('status') == 'error':
        return 'error', entry.get('error') or 'The new reading needs review. Earlier work is unchanged.'
    if entry.get('file_id') == member['from_file_id']:
        return 'kept_earlier', 'The batch kept the earlier reading. Open its review.'
    return 'done', Counter(session.scalars(select(BatchItem.status).where(BatchItem.batch_id == batch.id,
        BatchItem.file_id == UUID(entry['file_id']))))


def _follow(session, item, file, batches, handoff):
    """Record the outcome once every batch handed the statement has finished with its new reading."""
    handed = handoff.get('batches') or [dict(batch_id=handoff['batch_id'], source_id=handoff['source_id'],
        from_file_id=item.result['from_file_id'], attempt_id=handoff['attempt_id'])]
    states = []
    for member in handed:
        batch = batches.get(UUID(member['batch_id']))
        entry = next((value for value in (batch.files or []) if value.get('source_id') == member['source_id']), None) if batch else None
        states.append((*_member_state(session, batch, entry, member, member['attempt_id']), entry))
    kinds = {kind for kind, _, _ in states}
    if 'replaced' in kinds:
        _record(session, item, file, 'kept', next(detail for kind, detail, _ in states if kind == 'replaced'))
    elif 'reading' in kinds:
        _wait(session, item, 'reading', 'Reading the original in the background; saved work is unchanged.')
    elif kinds & {'error', 'kept_earlier'}:
        _record(session, item, file, 'review', next(detail for kind, detail, _ in states if kind in ('error', 'kept_earlier')))
    else:
        statuses = sum((detail for _, detail, _ in states), Counter())
        ready, held = statuses.get('ready', 0), statuses.get(HELD, 0)
        message = (f'{ready} of {sum(statuses.values())} periods are ready after the new reading; '
            f'{held} still need attention. The earlier reading is retained in history.')
        _record(session, item, file, 'recovered' if ready else 'unchanged', message,
            review_file_id=states[-1][2]['file_id'], periods=dict(statuses))
    session.commit()
