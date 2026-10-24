"""Prepare held batch statements again, by themselves, after a deploy changes the backend reader.

A batch item is the reading of one statement as the backend reader that
prepared it saw it. When a deploy fixes the reader, an item still held in the
queue keeps that older reading until its file is prepared again, and three
existing paths miss it:

* the engine-release campaign (``recovery_readers``) selects only readings of an
  affected ENGINE revision, so a backend-only fix leaves it 'reader_not_affected';
* ``reader_release`` compares only the statement keys and the review revision,
  and the revision deliberately leaves out most identity, period and readiness
  facts, so a file whose readiness changed is recorded 'unchanged';
* the campaign's copy check judges a held statement on its STALE period.

The only remedy was a manual ``scripts/financial_reread_file.py --apply`` per file.
This sweep does the same thing automatically, through the same product path.

Fingerprint. ``preparation_stamp()`` digests the source of every module under
``services/financial`` (the reader, its readiness, copy, overlap and duplicate
gates, and preparation itself) with the review model. Preparation records it on
the batch file (``file['prepared_stamp']``, written only when the file's
statements are actually prepared, never by a comparison) and stores, on every
item it prepares, a digest of the assessment it made (``summary[ASSESSED]``).
A file with no stamp, or an item with no digest, counts as prepared by an
older reader once.

Selection (per original, read only, all or nothing). A checked batch file that
holds a statement ('attention') and whose stamp differs from the deployed one is
judged by ``recovery_readers.classify(refresh=True)``: removed files, duplicate
decisions, any investigator work or review request, imported / queued /
skipped / ignored / assigned / removed statements, saved imports, any ready
statement (not_all_held), a file being read, and an original held in several
batches (every batch file must qualify and all are prepared together) all
leave it exactly as it is. The current reader then reads it (read only): a
file it cannot read is left; a statement whose CURRENT account and period the
case already saved is left as a copy for comparison (the campaign's copy rule,
on the current reading instead of the stale one); a file whose statements and
assessments the current reader reproduces exactly is left 'unchanged'.
Otherwise it is marked pending, and the queue shows its held statements as
being rechecked.

Hand-off. A few at a time host-wide (``AT_ONCE``, shared with the engine
campaign's hand-offs), none while other evidence is being read, and only into
batches that are not running. Under the batch locks, the protections are
judged again; then every batch file of the original goes back to 'processing'
and its batch to 'preparing', exactly as ``refresh_files`` does. The worker
prepares it from its saved text and table geometry (no engine, no OCR);
``prepare_reviews`` keeps every imported, queued, skipped and ignored item; the
readiness, reconciliation, overlap-trim, copy and duplicate gates and automatic
save apply as to any preparation. Nothing is imported here.

Deploys. All state lives on batch files: a pending mark is not running work,
and a handed file is an ordinary batch file being prepared, which resumes after
a restart. Neither is in the ingestion gate's blocking set (engine jobs,
running recovery items, uploads); a batch turn holds its lease only for one
bounded turn and the loop pauses between rounds, so the gate's turn wait finds
an idle moment. A long sweep never defers a deploy.

Switch: ``LOUPE_FINANCIAL_AUTO_REPREPARE_HELD`` (default on). Off: nothing is
selected or handed off, and pending marks are not shown as rechecking. Any
failure leaves files as they are (fail closed) and is retried by the next sweep.

Investigator work (``LOUPE_FINANCIAL_REPREPARE_CARRY_EDITS``, default on). A file
carrying her saved progress or batch drafts is no longer left for that alone:
``reprepare_carry`` plans, read only, how her work goes onto the current reading
(every other protection still applies). A file whose work cannot be carried one
to one is left ('investigator_edits', the reason recorded on the mark; like a file the worker could not
carry for any reason, it is not judged again until the next deploy). The
pending mark and the hand-off record the work's fingerprint; work saved since
leaves the file. The worker carries her work (``reprepare_carry.apply``) before
preparing, under the file's lock, and prepares nothing when the fingerprint or
the reading moved. Off: investigator work protects the file, as before.
"""
import hashlib
import json
import logging
import os
import time
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import select

from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item

log = logging.getLogger(__name__)


def _switch(name, default='1'):
    return os.environ.get(name, default).strip().lower() not in ('0', 'false', 'no', 'off', '')


ENABLED = _switch('LOUPE_FINANCIAL_AUTO_REPREPARE_HELD')
CARRY_EDITS = _switch('LOUPE_FINANCIAL_REPREPARE_CARRY_EDITS')
try:
    AT_ONCE = max(1, int(os.environ.get('LOUPE_FINANCIAL_AUTO_REPREPARE_AT_ONCE', '4') or 4))
except ValueError:
    AT_ONCE = 4
FILES_PER_SWEEP = 10          # originals read again (read only) per sweep
SWEEP_BUDGET_SECONDS = 20.0
MARK = 'held_reprepare'       # on the batch file: {stamp, state, reason?, at}
STAMP = 'prepared_stamp'      # on the batch file: the reader its statements were prepared by
ASSESSED = 'prepared_assessment'  # on each prepared item's summary
RECHECK_REASON = 'held_reprepare'
HELD = 'attention'
PENDING, HANDED, LEFT, UNCHANGED = 'pending', 'handed', 'left', 'unchanged'
MESSAGE = 'Loupe was updated; checking this statement again with the new reader. No action is needed.'
# Why a held file was not prepared again although the reader changed (with recovery_readers.REASONS).
LEFT_REASONS = {
    'unreadable': 'The current reader cannot read its saved reading; it is left as it was.',
    'copy_of_saved': 'The current reading names an account and period the case already saved: a copy to compare.',
    'unchanged': 'The current reader prepares it exactly as before.',
    'shared_reading': 'Two batch files of different originals resolve to this reading.',
    'recovery_scheduled': 'An engine re-read of it is scheduled or running.',
}
_stamp = None


def preparation_stamp():
    """Digest of the backend reader in this process: every module under services/financial (computed once)."""
    global _stamp
    if _stamp is None:
        from services.financial.import_batches import REVIEW_MODEL
        root = Path(__file__).resolve().parent
        digest = hashlib.sha256(f'held-reprepare-v1\0{REVIEW_MODEL}\0'.encode())
        for path in sorted(p for pattern in ('**/*.py', '**/*.json') for p in root.glob(pattern)
                           if '__pycache__' not in p.parts):
            digest.update(str(path.relative_to(root)).encode() + b'\0' + hashlib.sha256(path.read_bytes()).digest())
        _stamp = digest.hexdigest()
    return _stamp


def record_preparation(file):
    """Called when a batch file's statements were prepared (import_batches.advance_batch)."""
    file[STAMP] = preparation_stamp()
    mark = file.get(MARK)
    if isinstance(mark, dict) and mark.get('state') in (PENDING, HANDED):
        # Prepared now (handed off, or by another path meanwhile): nothing is pending any more.
        file[MARK] = {**mark, 'state': 'done', 'at': _now()}


def assessment_digest(status, summary):
    """Digest of one statement's assessment as preparation made it (before the case-level projection)."""
    body = {key: value for key, value in (summary or {}).items() if key not in (ASSESSED, 'readiness')}
    text = json.dumps([status, body], sort_keys=True, default=str, separators=(',', ':'))
    return hashlib.sha256(text.encode()).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _mark(entry):
    mark = entry.get(MARK)
    return mark if isinstance(mark, dict) else {}


def stale(entry, stamp):
    """A checked batch file prepared by another reader that this reader has not judged yet."""
    return (entry.get('status') == 'checked' and bool(entry.get('file_id')) and not entry.get('standalone_import')
            and entry.get(STAMP) != stamp and _mark(entry).get('stamp') != stamp)


def pending_files(batches):
    """(batch id, file id) of batch files marked to be prepared again (the queue shows them as rechecking)."""
    if not ENABLED:
        return set()
    return {(batch.id, entry['file_id']) for batch in batches for entry in batch.files or []
            if entry.get('file_id') and entry.get('status') == 'checked' and _mark(entry).get('state') == PENDING}


class _Campaign:
    """classify(refresh=True) never consults the campaign; this stands in for it."""
    release = RECHECK_REASON
    current_readers = ()

    def eligible(self, *_):
        return True


CAMPAIGN = _Campaign()


def _held_files(session, case_id):
    """{(batch id, file id)} holding a statement in this case."""
    return {(batch_id, str(file_id)) for batch_id, file_id in session.execute(
        select(Item.batch_id, Item.file_id).join(Batch, Item.batch_id == Batch.id).where(
            Batch.case_id == case_id, Batch.status != 'removed', Item.status == HELD).distinct())}


def judge_protections(session, case_id, source_id, scope):
    """(reason, [(batch, entry, detail)]) for one original under recovery_readers' rules. Read only."""
    from services.financial import recovery_readers as readers
    members = [(batch, entry) for batch in scope['batches'] for entry in batch.files or []
               if entry.get('source_id') == source_id]
    if not members:
        return 'unavailable', []
    if scope['membership'][source_id] > 1:
        return readers._group_reason(session, case_id, members, CAMPAIGN, scope, refresh=True, carry_edits=CARRY_EDITS)
    batch, entry = members[0]
    reason, detail = readers.classify(session, case_id, batch, entry, CAMPAIGN, scope, refresh=True,
                                      carry_edits=CARRY_EDITS)
    return reason, ([(batch, entry, detail)] if reason == readers.ELIGIBLE else [])


def _shared_reading(scope, chosen):
    """True when another original's batch file resolves to one of these readings (one reading, one item)."""
    readings = {str(detail['reading'].id) for _, _, detail in chosen}
    sources = {entry.get('source_id') for _, entry, _ in chosen}
    return any(entry.get('file_id') in readings and entry.get('source_id') not in sources
               for batch in scope['batches'] for entry in batch.files or [])


def _sharing_blocks(session, case_id, scope, chosen):
    """Whether another original's batch file on one of these readings keeps them from being prepared again.

    Without investigator work to carry: any such batch file does (one reading, one item; as before). With her
    work to carry (CARRY_EDITS): her work lives on the reading, and recovery_readers.classify already judged
    every batch's statements of it; the other original must also pass every protection on its own (or hold
    nothing). Each original is then prepared by its own judgement; the carry is done once, by the first."""
    if not _shared_reading(scope, chosen):
        return False
    if not (CARRY_EDITS and any(detail.get('carry_work') for _, _, detail in chosen)):
        return True
    from services.financial.recovery_readers import ELIGIBLE, IDLE_MEMBER
    readings = {str(detail['reading'].id) for _, _, detail in chosen}
    sources = {entry.get('source_id') for _, entry, _ in chosen}
    others = {entry.get('source_id') for batch in scope['batches'] for entry in batch.files or []
              if entry.get('file_id') in readings and entry.get('source_id') not in sources}
    for other in sorted(others, key=str):
        reason, _ = judge_protections(session, case_id, other, scope)
        if reason not in (ELIGIBLE, IDLE_MEMBER):
            return True
    return False


def judge_reading(session, case_id, chosen):
    """'changed', or the LEFT_REASONS key: what the current reader makes of the chosen batch files. Read only.

    ``detail`` per chosen member gains ``differs`` (statements whose current
    assessment differs from the stored one, or that appear or vanish).
    """
    from services.financial.import_batches import assess
    from services.financial.pdf_candidates import PdfMappingError
    from services.financial.recovery_readers import copy_of_saved, settled_sibling
    from services.financial.statement_import import read_statement_import
    changed = False
    for batch, entry, detail in chosen:
        reading = detail['reading']
        items = list(session.scalars(select(Item).where(Item.batch_id == batch.id, Item.file_id == reading.id,
                                                        Item.status.notin_(('removed', 'superseded_reading')))))
        saved_keys = {item.statement_key for item in items if item.status == 'imported' and item.statement_key}
        settled = {item.statement_key or '' for item in items if settled_sibling(item, reading, saved_keys)}
        cache = {}
        try:
            first = read_statement_import(session, case_id=case_id, evidence_file_id=reading.id,
                                          currency=entry.get('currency'), _cache=cache)
            keys = [choice['id'] for choice in first.get('statement_choices', [])] or [None]
            fresh = []
            for key in keys:
                proposal = read_statement_import(session, case_id=case_id, evidence_file_id=reading.id,
                    currency=entry.get('currency') or None, statement_id=key, _cache=cache)
                fresh.append((key or proposal.get('statement_id') or '', proposal))
        except PdfMappingError:
            return 'unreadable'
        stored = {item.statement_key or '': item for item in items}
        differs = 0
        assessed = []
        for key, proposal in fresh:
            status, summary = assess(proposal, None)
            assessed.append((key, summary))
            item = stored.get(key)
            if item is None:
                differs += 1
            elif item.status == HELD and item.summary.get(ASSESSED) != assessment_digest(status, summary):
                differs += 1
        produced = {key for key, _ in fresh}
        differs += sum(1 for key, item in stored.items() if item.status == HELD and key not in produced)
        # Her work carried onto the current reading changes what is prepared, whatever the reader reproduces.
        differs += sum(1 for entry in (detail.get('carry_plan') or {}).values() if entry['kind'] != 'current')
        detail['differs'] = differs
        changed = changed or bool(differs)
        # The campaign's copy rule, on the current reading: a statement it would now list (not one already
        # settled) whose printed account and period the case already saved stays a copy for comparison.
        current = [SimpleNamespace(id=f'{reading.id}:{key}', file_id=reading.id, statement_key=key, summary=summary)
                   for key, summary in assessed if key not in settled]
        if current and copy_of_saved(session, case_id, detail['source'], current, cache=cache):
            stale_keys = any(item.status == HELD and key not in produced for key, item in stored.items())
            if not (stale_keys and exact_copies_rekeyed(session, case_id, detail['source'], reading, current,
                                                         dict(fresh), cache)):
                return 'copy_of_saved'
            detail['rekeyed_copies'] = True
    return 'changed' if changed else 'unchanged'


def exact_copies_rekeyed(session, case_id, source, reading, current, proposals, cache):
    """A held copy whose stored statement key the deployed reader no longer produces is prepared again
    (re-keyed) when every current statement that is a copy of a saved account and period agrees with that saved
    ledger exactly (saved_copies.compare: payments one for one, printed balances, currency; exactly one saved
    period). Read only.

    With a stale key nothing can judge the copy: the copy rule (held_settlement), a details fill and the
    investigator's own review all read it by a key the reader no longer makes. Prepared again, it carries the
    current key, and preparation's own duplicate check holds it as a copy of the saved statement (it can never
    be saved a second time). Switch LOUPE_FINANCIAL_AUTOFILL_REAPPLY; off, such a copy stays left as before.
    """
    from services.financial.field_proposals import reapply_enabled
    from services.financial.import_batches import initial_request
    from services.financial.recovery_readers import copy_of_saved
    from services.financial.saved_copies import compare
    if not reapply_enabled():
        return False
    try:
        for statement in current:
            if not copy_of_saved(session, case_id, source, [statement], cache=cache):
                continue
            proposal = proposals.get(statement.statement_key)
            if proposal is None:
                return False
            result = compare(session, case_id, proposal, initial_request(proposal), statement.summary,
                             own={(str(reading.id), statement.statement_key or '')})
            if result.get('outcome') != 'match':
                return False
    except Exception:  # noqa: BLE001 - fail closed: the copy stays left
        log.exception('Comparing a held copy with its saved statement failed; it is left as it is')
        return False
    return True


# Verdicts that can change by themselves soon: not recorded, so the next sweep judges the file again.
TRANSIENT = frozenset({'recovery_scheduled', 'processing', 'not_prepared'})


def judge_carry(session, case_id, chosen):
    """None when the investigator work on the chosen batch files can be carried onto the current reading
    (each detail with work gains ``carry_plan``), else the reason it cannot. Read only."""
    from services.financial.reprepare_carry import NotCarried, plan
    for batch, entry, detail in chosen:
        if not detail.get('carry_work'):
            continue
        try:
            detail['carry_plan'] = plan(session, case_id, detail['reading'], detail['source'],
                                        entry.get('currency'))['statements']
        except NotCarried as error:
            return error.reason
    return None


def judge(session, case_id, source_id, scope, scheduled, notes=None):
    """(verdict, chosen, members) for one original. Read only (the caller rolls back).

    ``verdict`` is 'changed' (to be prepared again) or why it is left
    (recovery_readers.REASONS, LEFT_REASONS). ``members``: every batch file of the
    original, as (batch, index, entry). ``notes`` (a dict) gains ``carry``: why her work
    cannot be carried, when that leaves the file.
    """
    from services.financial.recovery_readers import ELIGIBLE
    members = [(batch, index, entry) for batch in scope['batches'] for index, entry in enumerate(batch.files or [])
               if entry.get('source_id') == source_id]
    ids = {source_id} | {entry.get('file_id') for _, _, entry in members}
    if ids & scheduled:
        return 'recovery_scheduled', [], members
    reason, chosen = judge_protections(session, case_id, source_id, scope)
    if reason != ELIGIBLE:
        return reason, [], members
    if _sharing_blocks(session, case_id, scope, chosen):
        return 'shared_reading', [], members
    refused = judge_carry(session, case_id, chosen)
    if refused:
        if notes is not None:
            notes['carry'] = refused
        return 'investigator_edits', [], members
    return judge_reading(session, case_id, chosen), chosen, members


def _write_marks(factory, case_id, marks):
    """marks: {(batch id, entry index, file id): mark}. Writes each batch once, only entries still checked."""
    from services.financial.import_batches import batch_for
    by_batch = {}
    for (batch_id, index, file_id), mark in marks.items():
        by_batch.setdefault(batch_id, []).append((index, file_id, mark))
    for batch_id in sorted(by_batch, key=str):
        with factory() as db:
            batch = batch_for(db, case_id, batch_id, True)
            files = deepcopy(batch.files or [])
            written = 0
            for index, file_id, mark in by_batch[batch_id]:
                if index < len(files) and files[index].get('file_id') == file_id and files[index].get('status') == 'checked':
                    files[index][MARK] = mark
                    written += 1
            if written:
                batch.files = files
                db.commit()
            else:
                db.rollback()


def stale_sources(session, case_id, stamp, scope=None):
    """Originals of this case with a held statement in a batch file not yet judged under ``stamp``. Read only."""
    from services.financial import recovery_readers as readers
    scope = scope or readers.context(session, case_id)
    held = _held_files(session, case_id)
    sources = []
    for batch in scope['batches']:
        for entry in batch.files or []:
            if (batch.id, entry.get('file_id')) in held and stale(entry, stamp) and entry.get('source_id') not in sources:
                sources.append(entry.get('source_id'))
    return sources, scope


def select_case(factory, case_id, stamp, *, out_of_time, outcome):
    """Judge this case's stale held originals (read only), then record each verdict on its batch files."""
    from services.financial import recovery_readers as readers
    with factory() as db:
        sources, _ = stale_sources(db, case_id, stamp)
        scheduled = readers.rereading_files(db, case_id) if sources else set()
        db.rollback()
    for source_id in sources:
        if out_of_time():
            outcome['deferred'] += 1
            continue
        with factory() as db:
            scope = readers.context(db, case_id)
            notes = {}
            verdict, chosen, members = judge(db, case_id, source_id, scope, scheduled, notes)
            # Plain values: the session ends here.
            chosen_keys = {(batch.id, entry.get('file_id')) for batch, entry, _ in chosen}
            work = {(batch.id, entry.get('file_id')): detail['carry_work'] for batch, entry, detail in chosen
                    if detail.get('carry_work')}
            targets = [(batch.id, index, entry.get('file_id'), (batch.id, entry.get('file_id')) in chosen_keys)
                       for batch, index, entry in members if entry.get('status') == 'checked']
            db.rollback()
        if verdict not in TRANSIENT:
            outcome['read'] += verdict in ('changed', 'unchanged', 'copy_of_saved', 'unreadable')
        outcome['verdicts'][verdict] += 1
        if verdict in TRANSIENT:
            continue
        at = _now()
        if verdict == 'changed':
            marks = {(b, i, f): dict(stamp=stamp, state=PENDING, at=at, **(
                {'carry_work': work[(b, f)]} if (b, f) in work else {})) for b, i, f, picked in targets if picked}
        else:
            marks = {(b, i, f): dict(stamp=stamp, state=LEFT, reason=verdict, at=at, **(
                {'carry': notes['carry']} if notes.get('carry') else {})) for b, i, f, _ in targets}
        _write_marks(factory, case_id, marks)
        if outcome['read'] >= FILES_PER_SWEEP:
            outcome['deferred'] += len(sources) - sources.index(source_id) - 1
            return


def _in_flight(batches):
    return sum(1 for batch in batches for entry in batch.files or []
               if _mark(entry).get('state') == HANDED and entry.get('status') in ('waiting', 'processing'))


def hand_off(factory, outcome):
    """Hand pending originals back to their batches, a few at a time host-wide. Returns originals handed."""
    from services.financial import recovery_readers as readers
    from services.financial.import_batches import _reading_progress, batch_for
    with factory() as db:
        batches = list(db.scalars(select(Batch).where(Batch.status != 'removed')))
        pending = []
        for batch in batches:
            for entry in batch.files or []:
                if entry.get('status') == 'checked' and _mark(entry).get('state') == PENDING \
                        and (batch.case_id, entry.get('source_id')) not in pending:
                    pending.append((batch.case_id, entry.get('source_id')))
        if not pending:
            return 0
        room = AT_ONCE - _in_flight(batches) - readers.in_flight(db)
        busy = readers.evidence_being_read(db) > 0
        db.rollback()
    if room <= 0 or busy:
        outcome['waiting'] = len(pending)
        return 0
    handed = 0
    for case_id, source_id in pending:
        if handed >= room:
            break
        with factory() as db:
            holders = sorted({batch.id for batch in db.scalars(select(Batch).where(
                Batch.case_id == case_id, Batch.status != 'removed'))
                for entry in batch.files or [] if entry.get('source_id') == source_id}, key=str)
            locked = [batch_for(db, case_id, batch_id, True) for batch_id in holders]
            if any(batch.status != 'review' for batch in locked):
                db.rollback()  # a running or paused batch: tried again by a later sweep
                continue
            scope = readers.context(db, case_id)
            reason, chosen = judge_protections(db, case_id, source_id, scope)
            at, stamp = _now(), preparation_stamp()
            by_batch = {batch.id: (batch, deepcopy(batch.files or [])) for batch in locked}
            if reason == readers.ELIGIBLE and not _carry_unchanged(by_batch, source_id, chosen):
                reason = 'investigator_edits'  # work saved (or changed) since it was judged: left as it is
            if reason != readers.ELIGIBLE or _sharing_blocks(db, case_id, scope, chosen):
                # Something changed since it was judged (a person's work, a save): left exactly as it is.
                for batch, files in by_batch.values():
                    for entry in files:
                        if entry.get('source_id') == source_id and _mark(entry).get('state') == PENDING:
                            entry[MARK] = dict(stamp=stamp, state=LEFT, reason=reason if reason != readers.ELIGIBLE
                                               else 'shared_reading', at=at)
                    batch.files = files
                db.commit()
                outcome['left_at_hand_off'] += 1
                continue
            for batch, entry, detail in chosen:
                current, files = by_batch[batch.id]
                target = next((e for e in files if e.get('source_id') == source_id
                               and e.get('file_id') == entry.get('file_id')), None)
                if target is None or target.get('status') != 'checked':
                    continue
                target['status'] = 'processing'
                target['recheck'] = dict(reason=RECHECK_REASON, stamp=stamp, **(
                    {'carry_work': detail['carry_work']} if detail.get('carry_work') else {}))
                target[MARK] = dict(stamp=stamp, state=HANDED, at=at)
                _reading_progress(target, 'checking_statements', MESSAGE)
                current.status = 'preparing'
            for batch, files in by_batch.values():
                # Idle members (nothing held there) are not prepared; their mark is closed.
                for entry in files:
                    if entry.get('source_id') == source_id and _mark(entry).get('state') == PENDING:
                        entry[MARK] = dict(stamp=stamp, state=LEFT, reason='nothing_held', at=at)
                batch.files = files
            db.commit()
            handed += 1
    outcome['handed'] += handed
    return handed


def _carry_unchanged(by_batch, source_id, chosen):
    """True when each chosen batch file's investigator work is exactly the work it was judged with."""
    for batch, entry, detail in chosen:
        _, files = by_batch[batch.id]
        target = next((e for e in files if e.get('source_id') == source_id
                       and e.get('file_id') == entry.get('file_id')), None)
        if target is None or _mark(target).get('carry_work') != detail.get('carry_work'):
            return False
    return True


def carry_before_preparing(db, case_id, batch_id, file):
    """Worker hook (import_batches._review_file): None to prepare as usual, or why nothing may be prepared
    (her work could not be carried now; the file's statements are left exactly as they are)."""
    recheck = file.get('recheck') or {}
    if recheck.get('reason') != RECHECK_REASON or not recheck.get('carry_work'):
        return None
    if not (ENABLED and CARRY_EDITS):
        return 'switched_off'
    from services.financial.reprepare_carry import apply
    try:
        outcome = apply(db, case_id=case_id, batch_id=batch_id, file=file, fingerprint=recheck['carry_work'])
    except Exception:
        db.rollback()
        log.exception('Carrying investigator work onto the current reading failed; the file is left as it is')
        return 'carry_failed'
    return None if outcome in ('carried', 'already', 'nothing_to_carry') else outcome


def left_after_carry(file, reason):
    """Record on a batch file that the worker prepared nothing because her work could not be carried."""
    file[MARK] = dict(stamp=preparation_stamp(), state=LEFT, reason='investigator_edits', carry=reason, at=_now())


def sweep(factory, *, budget_seconds=None):
    """One round: hand off what is pending, then judge stale held files. Never raises."""
    outcome = dict(handed=0, read=0, deferred=0, waiting=0, left_at_hand_off=0, verdicts=Counter())
    if not ENABLED:
        outcome['verdicts'] = {}
        return outcome
    budget_seconds = SWEEP_BUDGET_SECONDS if budget_seconds is None else budget_seconds
    started, stamp = time.monotonic(), preparation_stamp()
    out_of_time = lambda: time.monotonic() - started >= budget_seconds or outcome['read'] >= FILES_PER_SWEEP
    try:
        hand_off(factory, outcome)
    except Exception:
        log.exception('Handing held statements back for preparation failed; they stay pending')
    try:
        with factory() as db:
            cases = sorted({batch.case_id for batch in db.scalars(select(Batch).where(Batch.status != 'removed'))
                            if any(stale(entry, stamp) for entry in batch.files or [])}, key=str)
            db.rollback()
        for case_id in cases:
            if out_of_time():
                break
            try:
                select_case(factory, case_id, stamp, out_of_time=out_of_time, outcome=outcome)
            except Exception:
                log.exception('Judging held statements after a reader change failed for a case; retried next sweep')
    except Exception:
        log.exception('Judging held statements after a reader change failed; retried next sweep')
    outcome['verdicts'] = dict(outcome['verdicts'])
    return outcome


def estimate(session, case_id, stamp=None):
    """Read only (dry run): what a sweep would do with this case's held files now.

    Returns {verdict: dict(originals, batch_files, held_items)} and the chosen
    'changed' originals as [(source id, [(batch id, reading id, differs, held)])].
    """
    from services.financial import recovery_readers as readers
    stamp = stamp or preparation_stamp()
    sources, scope = stale_sources(session, case_id, stamp)
    scheduled = readers.rereading_files(session, case_id)
    held = Counter((str(batch_id), str(file_id)) for batch_id, file_id in session.execute(
        select(Item.batch_id, Item.file_id).join(Batch, Item.batch_id == Batch.id).where(
            Batch.case_id == case_id, Batch.status != 'removed', Item.status == HELD)))
    result, changed = {}, []
    for source_id in sources:
        notes = {}
        verdict, chosen, members = judge(session, case_id, source_id, scope, scheduled, notes)
        if notes.get('carry'):
            result.setdefault('carry_refused', Counter())[notes['carry']] += 1
        row = result.setdefault(verdict, dict(originals=0, batch_files=0, held_items=0))
        row['originals'] += 1
        row['batch_files'] += len(members)
        row['held_items'] += sum(held[(str(batch.id), str(entry.get('file_id')))] for batch, _, entry in members)
        if verdict == 'changed':
            changed.append((source_id, [(str(batch.id), str(detail['reading'].id), detail.get('differs'),
                                         len(detail.get('held') or [])) for batch, entry, detail in chosen]))
            if any(detail.get('carry_plan') for _, _, detail in chosen):
                result.setdefault('carried', []).append((source_id, chosen))
    return result, changed
