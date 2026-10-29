"""Save ready statements straight from the review queue, across batches.

The queue lists every statement once, whichever batch prepared it. Saving from
it uses the batch save's own admission, statement by statement:

* every requested statement is projected again against its current reading
  (``validate_reviews=True, reading='all'``, the projection a batch save
  validates with), and only one the batch save would import is claimed;
* a statement already saved (or being saved) through another batch or an
  individual review is held, never imported twice;
* each batch's claimed statements get the batch save's receipt (an import
  operation), and the batch worker imports them exactly as after a batch
  save: the strict writer takes the case lock, and a temporary database or
  lock failure is retried automatically with the existing bounded backoff.

Automatic save (``AUTO_SAVE_READY``): when a file's preparation finishes, its
statements that are ready with no check at all (no problem, not even a note)
and no investigator edit or draft are claimed with the actor "System".
Details missing only where a proposal is automatically confirmed
(``field_proposals``) are filled first, as System, through the statement
details save; such a statement then saves only if it checks out completely. It
fires for files prepared with it on: preparation marks the batch's file entry
(``AUTO_SAVE_MARK``), so statements read before deploy are untouched; that
backlog is an explicit action (the queue's "Save all N ready statements", or
``scripts/financial_save_ready_backlog.py``). Every automatic save is an
ordinary import receipt with actor System, reversible with the existing
import removal.

A statement of such a file that becomes ready later (the background readiness
sweep, or a readiness refresh after a change elsewhere), or whose automatic
save failed (a database lock), is saved by ``sweep_save`` in the batch
worker's next readiness round, exactly as at the end of preparation: the same
fill, the same checks, the same System actor and switch. A statement with an
investigator's draft or saved review is never saved by it.
"""
import logging
import os
import random
import time
from collections import Counter, OrderedDict
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select

from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile
from postgres.models.financial_import_batches import (FinancialImportBatch as Batch, FinancialImportBatchItem as Item,
                                                      FinancialImportOperation as Operation)
from services.financial.decisions import Actor
from services.financial.pdf_candidates import PdfMappingError

log = logging.getLogger(__name__)

# One switch: False (or FINANCIAL_AUTO_SAVE_READY=0) stops automatic saves.
AUTO_SAVE_READY = os.environ.get('FINANCIAL_AUTO_SAVE_READY', '1').strip().lower() not in ('0', 'false', 'off', 'no')
SYSTEM_ACTOR = Actor(name='System', email='auto-save@system.local')
MAX_ITEMS = 500
PAUSED = ('pausing', 'paused')


def _held(item, reason):
    summary = (item.summary or {}) if item is not None else {}
    return dict(item_id=str(item.id) if item is not None else None, filename=summary.get('filename') or '',
                period_start=summary.get('period_start') or '', period_end=summary.get('period_end') or '',
                reason=reason)


def _not_ready_reason(projection):
    from services.financial.review_queue import describe
    detail = describe(projection.summary)
    if detail:
        return detail['sentence']
    if projection.status == 'imported':
        return 'Already saved'
    if projection.status == 'duplicate_ignored':
        return 'Set aside as a copy of another statement'
    if projection.summary.get('readiness_pending') or projection.summary.get('comparison_pending'):
        return 'Being rechecked: try again in a minute'
    return 'No longer ready: open it in the queue'


def restored_saved_copy(item, file):
    """A copy of a saved statement that a person restored after the System set it aside (saved_copies): the
    person saves it, never the System, so the account and period are not counted twice unasked."""
    from services.financial.pending_statement_duplicates import METADATA_KEY
    from services.financial.saved_copies import BASIS
    stored = ((file.metadata_ or {}).get(METADATA_KEY) or {}).get(item.statement_key or '') if file is not None else None
    return bool(stored and stored.get('status') == 'restored' and stored.get('basis') == BASIS)


def system_filled_only(item, file):
    """The statement's only saved review is details System filled from confirmed proposals, or the
    investigator's statement details an engine re-read carried onto this reading after every payment of hers
    matched one to one (reread_carry.DETAILS_MATCHED): its rows are the reading's own."""
    from services.financial.field_proposals import SYSTEM_NAME
    from services.financial.reread_carry import DETAILS_CARRY, DETAILS_MATCHED
    from services.financial.statement_progress import review_progress
    progress = review_progress(file, item.statement_key) if file is not None else None
    if not (progress and item.review_request and progress.get('request') == item.review_request):
        return False
    return ((progress.get('saved_by') or {}).get('name') == SYSTEM_NAME
            or (DETAILS_CARRY and (progress.get('carried_from') or {}).get('basis') == DETAILS_MATCHED))


def fully_reconciled(item, projection, file):
    """Ready under today's admission with no check at all and no investigator edit or draft.

    Details System filled from automatically confirmed proposals are not an
    investigator edit; any other saved review or draft is.
    """
    from services.financial.import_batches import import_available
    from services.financial.statement_progress import review_progress
    summary = projection.summary
    untouched = not item.review_request and not (file is not None and review_progress(file, item.statement_key))
    return (projection.status == 'ready' and import_available(projection) and not summary.get('problems')
            and not summary.get('problem_count') and not summary.get('auto_save_hold')
            and (untouched or system_filled_only(item, file)))


def fill_confirmed(session, *, case_id, entries, owned_batch_id=None):
    """Save the automatically confirmed proposals of queue entries (System), before a save. Never raises.

    Returns (report, item ids whose statement is ready after the fill).
    """
    from services.financial.field_proposals import apply_confirmed_proposals
    wanted = [e for e in entries if any(p.get('confirmed') for p in (e.get('proposals') or {}).values())]
    if not wanted:
        return dict(statements=0, saved=0, failed=0, groups=[]), []
    try:
        report = apply_confirmed_proposals(session, case_id=case_id, entries=wanted, apply=True,
                                           owned_batch_id=owned_batch_id)
    except Exception:
        session.rollback()
        log.exception('Filling confirmed proposals failed; the statements stay in the queue')
        return dict(statements=len(wanted), saved=0, failed=len(wanted), groups=[]), []
    session.expire_all()
    ids = [UUID(e['id']) for e in wanted if e.get('id') and ':' not in e['id']]
    ready = [str(i) for i in session.scalars(select(Item.id).where(Item.id.in_(ids), Item.status == 'ready'))] if ids else []
    return report, ready


def fill_from_queue(session, *, case_id, file_ids=None):
    """The queue save's first step: fill confirmed details of 'filled' (and waiting) statements."""
    from services.financial.review_queue import case_review_queue
    queue = case_review_queue(session, case_id=case_id, file_ids=file_ids)
    session.rollback()
    report, ready = fill_confirmed(session, case_id=case_id, entries=queue.get('filled', []) + queue['items'])
    return dict(case_id=str(case_id), filled=report.get('saved', 0), statements=report.get('statements', 0),
                failed=report.get('failed', 0), ready_item_ids=ready)


def _prepared_entries(session, case_id, batch_id, file_id):
    """Queue-like entries with proposals for a just-prepared file's held, untouched statements."""
    from services.financial import field_proposals
    from services.financial.review_queue import actionable_problems
    if not field_proposals.enabled_fields():
        return []
    items = [i for i in session.scalars(select(Item).where(Item.batch_id == batch_id, Item.file_id == file_id,
             Item.status == 'attention')) if not i.review_request]
    if not items:
        return []
    knowledge = field_proposals.case_knowledge(session, case_id)
    entries = []
    for item in items:
        summary = item.summary or {}
        proposals = field_proposals.propose(field_proposals.summary_values(summary), knowledge)
        reasons = {p['review_reason'] for p in actionable_problems(summary)}
        if proposals and field_proposals.resolves_all(reasons, proposals):
            entries.append(dict(id=str(item.id), batch_id=str(batch_id), file_id=str(file_id),
                                statement_id=item.statement_key or None, proposals=proposals))
    return entries


def operation_id_for(request_id, batch_id):
    return uuid5(UUID(str(request_id)), f'queue-save:{batch_id}')


def save_statements(session, *, case_id, item_ids, actor, request_id=None, only_reconciled=False):
    """Claim the requested ready statements for import with the batch save's checks. Commits.

    Returns {request_id, queued, held: [{item_id, filename, period_start,
    period_end, reason}], operations: [{batch_id, operation_id, queued}]}.
    """
    from services.financial.import_batches import (checked_batch_items, claim_ready, import_available,
                                                   ready_revision)
    from services.financial.import_operations import operation_view
    from services.financial.review_queue import _saved_scopes
    request_id = UUID(str(request_id)) if request_id else uuid4()
    wanted = list(dict.fromkeys(UUID(str(i)) for i in item_ids))
    if not wanted:
        raise PdfMappingError('Choose the statements to save.', 422)
    if len(wanted) > MAX_ITEMS:
        raise PdfMappingError(f'Save at most {MAX_ITEMS} statements at a time.', 422)
    rows = {item.id: item for item in session.scalars(select(Item).join(Batch, Batch.id == Item.batch_id)
            .where(Batch.case_id == case_id, Item.id.in_(wanted)))}
    held = [dict(_held(None, 'Not found in this case'), item_id=str(i)) for i in wanted if i not in rows]
    batch_ids = sorted({item.batch_id for item in rows.values()}, key=str)
    # A repeated request (a retry after a lost response) returns its receipts.
    done = {op.batch_id: op for op in session.scalars(select(Operation).where(Operation.case_id == case_id,
            Operation.id.in_([operation_id_for(request_id, b) for b in batch_ids])))} if batch_ids else {}
    # The case row first, as every case-level writer takes it (the strict
    # import writer holds it while it locks the evidence rows). A share lock:
    # saves still run side by side, but none can hold an evidence row while
    # waiting for the case behind an import, which deadlocked them.
    if session.scalar(select(Case.id).where(Case.id == case_id).with_for_update(key_share=True)) is None:
        raise PdfMappingError('Case not found.', 404)
    # Then as the batch save: batch rows, then items, then evidence rows.
    batches = {batch.id: batch for batch in session.scalars(select(Batch).where(Batch.case_id == case_id,
               Batch.id.in_(batch_ids)).order_by(Batch.id).with_for_update())} if batch_ids else {}
    candidates = []
    for item_id in wanted:
        item = rows.get(item_id)
        if item is None:
            continue
        batch = batches.get(item.batch_id)
        if item.batch_id in done:
            continue
        if batch is None or batch.status == 'removed':
            held.append(_held(item, 'Its batch was removed'))
        elif batch.status in PAUSED:
            held.append(_held(item, 'Its batch is paused: resume it to save'))
        else:
            candidates.append(item)
    locked = {item.id: item for item in session.scalars(select(Item).where(
              Item.id.in_([i.id for i in candidates])).order_by(Item.id).with_for_update()
              .execution_options(populate_existing=True))} if candidates else {}
    candidates = [locked[i.id] for i in candidates if i.id in locked]
    files = {file.id: file for file in session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id,
             EvidenceFile.id.in_({i.file_id for i in candidates})).order_by(EvidenceFile.id).with_for_update()
             .execution_options(populate_existing=True))} if candidates else {}
    # One statement is saved once: not when it is already saved, being saved
    # through another batch, or requested twice.
    saved, _ = _saved_scopes(session, case_id)
    identity = lambda item: (files[item.file_id].sha256 if item.file_id in files else None, item.statement_key or '')
    # Files whose pages render identically are one document too (page_identity):
    # each statement also carries its page key, checked beside its bytes key.
    from services.financial import page_identity
    def pages_of(file):
        value = page_identity.stored(file)
        return ('pages', value['renderer'], value['identity']) if value else None
    page_key = lambda item: (pages_of(files[item.file_id]) if item.file_id in files else None, item.statement_key or '')
    shas = {identity(i)[0] for i in candidates} - {None}
    identities = {page_identity.stored(f)['identity'] for f in files.values() if page_identity.stored(f)}
    busy = set()
    if shas or identities:
        from sqlalchemy import or_
        from services.financial import saved_reading_replacement
        matching = ([EvidenceFile.sha256.in_(shas)] if shas else []) + ([EvidenceFile.metadata_[
            page_identity.METADATA_KEY]['identity'].as_string().in_(identities)] if identities else [])
        found = list(session.execute(select(EvidenceFile, Item.statement_key, Item.status, Item.summary)
                .join(Item, Item.file_id == EvidenceFile.id).join(Batch, Batch.id == Item.batch_id)
                .where(Batch.case_id == case_id, Batch.status != 'removed', or_(*matching),
                       Item.status.in_(('pending_import', 'imported')))))
        # An item imported as an empty legacy import (a "shell": no statement, no dates, nothing paid)
        # saved nothing of this statement; the writer saves the statement and sets the shell aside
        # (saved_reading_replacement). Off with the replacement switch.
        shells = saved_reading_replacement.shell_document_ids(session, case_id, {
            (summary or {}).get('source_document_id') for _, _, status, summary in found
            if status == 'imported'} - {None}) if saved_reading_replacement.enabled() else set()
        for file, key, status, summary in found:
            if status == 'imported' and (summary or {}).get('source_document_id') in shells:
                continue
            busy.add((file.sha256, key or ''))
            if pages_of(file):
                busy.add((pages_of(file), key or ''))
    unique, seen = [], set()
    for item in candidates:
        scope = identity(item)
        pages = page_key(item) if page_key(item)[0] else None
        if item.status not in ('ready', 'attention'):
            held.append(_held(item, 'Already saved' if item.status in ('imported', 'pending_import')
                              else 'No longer ready: open it in the queue'))
        elif scope in saved or scope in busy or pages in busy:
            held.append(_held(item, 'Already saved through another batch'))
        elif scope in seen or (pages and pages in seen):
            held.append(_held(item, 'The same statement is already in this save'))
        else:
            seen.add(scope)
            if pages:
                seen.add(pages)
            unique.append(item)
    checked = {p.id: p for p in checked_batch_items(session, case_id, unique, validate_reviews=True,
                                                    reading='all')} if unique else {}
    ready_by_batch = {}
    for item in unique:
        projection = checked.get(item.id)
        if projection is None or not import_available(projection):
            held.append(_held(item, _not_ready_reason(projection) if projection is not None else
                              'No longer ready: open it in the queue'))
        elif only_reconciled and projection.summary.get('auto_save_hold'):
            # Balanced, but a fact the balances cannot prove is not proven (auto_save_guard).
            held.append(_held(item, projection.summary['auto_save_hold']['sentence']))
        elif only_reconciled and not fully_reconciled(item, projection, files.get(item.file_id)):
            held.append(_held(item, 'Has a check or an edit: left for you'))
        else:
            ready_by_batch.setdefault(item.batch_id, []).append(item)
    operations = []
    for batch_id in batch_ids:
        if batch_id in done:
            view = operation_view(done[batch_id])
            operations.append(dict(batch_id=str(batch_id), operation_id=view['id'], queued=view['statement_count']))
            continue
        ready = ready_by_batch.get(batch_id)
        if not ready:
            continue
        projections = [checked[i.id] for i in ready]
        operation = claim_ready(session, case_id=case_id, batch=batches[batch_id], ready=ready,
            checked=projections, operation_id=operation_id_for(request_id, batch_id),
            expected_revision=ready_revision(projections), actor=actor)
        if operation is None:
            # Another save claimed one of them first; nothing of this request
            # was kept (the claim rolled back). Ask for a fresh queue.
            raise PdfMappingError('Some of these statements were saved meanwhile. Refresh the queue and save again.', 409)
        operations.append(dict(batch_id=str(batch_id), operation_id=str(operation.id), queued=len(ready)))
    session.commit()
    return dict(request_id=str(request_id), queued=sum(op['queued'] for op in operations), held=held,
                operations=operations)


def save_result(session, *, case_id, operation_ids):
    """Progress and outcome of a queue save: its import receipts added together."""
    from services.financial.import_operations import operation_view
    ids = list(dict.fromkeys(UUID(str(i)) for i in operation_ids))
    views = [operation_view(op) for op in session.scalars(select(Operation).where(
             Operation.case_id == case_id, Operation.id.in_(ids)))] if ids else []
    failed = [dict(item_id=row['item_id'], filename=row.get('filename', ''), period_start=row.get('period_start', ''),
                   period_end=row.get('period_end', ''), reason=row.get('message') or 'Saving did not finish')
              for view in views for row in view['outcomes'] if row['status'] == 'failed']
    total = lambda key: sum(view[key] for view in views)
    return dict(case_id=str(case_id), found=len(views), pending=total('pending'), imported=total('imported'),
                already_present=total('already_present'), duplicate_ignored=total('duplicate_ignored'),
                failed=failed, transaction_count=total('transaction_count'),
                incomplete_count=total('incomplete_count'))


def held_summary(held):
    """'3 currency not printed, 1 already saved' — the reasons, most common first."""
    counts = Counter(entry['reason'] for entry in held)
    return ', '.join(f'{n} {reason[0].lower() + reason[1:]}' for reason, n in counts.most_common())


AUTO_SAVE_ATTEMPTS = 3


def auto_save_prepared(session, *, case_id, batch_id, file_id):
    """After a file's preparation: save its fully reconciled statements as System. Never raises.

    A save that loses a lock conflict (deadlock or serialization failure, when
    the same file is prepared in several batches at once) is tried again;
    statements left ready after the last attempt stay in the queue.
    """
    if not AUTO_SAVE_READY:
        return None
    from sqlalchemy.exc import OperationalError
    for attempt in range(1, AUTO_SAVE_ATTEMPTS + 1):
        try:
            return _auto_save_once(session, case_id=case_id, batch_id=batch_id, file_id=file_id)
        except OperationalError as error:
            session.rollback()
            if attempt < AUTO_SAVE_ATTEMPTS and getattr(error.orig, 'sqlstate', None) in ('40P01', '40001'):
                log.warning('Automatic save of file %s lost a lock conflict; trying again (%s of %s)',
                            str(file_id)[:8], attempt + 1, AUTO_SAVE_ATTEMPTS)
                time.sleep(attempt + random.random())
                continue
            log.exception('Automatic save of ready statements failed; they stay ready in the queue')
            return None
        except Exception:
            session.rollback()
            log.exception('Automatic save of ready statements failed; they stay ready in the queue')
            return None


def _auto_save_once(session, *, case_id, batch_id, file_id, stored_checks=False):
    # Details the system can fill with certainty (confirmed proposals) are
    # filled first, as System; the statement then saves only when it
    # checks out completely like any other.
    entries = _prepared_entries(session, case_id, batch_id, file_id)
    if entries:
        fill_confirmed(session, case_id=case_id, entries=entries, owned_batch_id=batch_id)
    file = session.get(EvidenceFile, file_id)
    # A teller receipt whose deposit a saved statement already records is not a statement (receipt_settlement).
    from services.financial.receipt_settlement import settle_receipts
    settle_receipts(session, case_id=case_id, batch_id=batch_id, file_id=file_id, actor=SYSTEM_ACTOR)
    ids = [item.id for item in session.scalars(select(Item).where(Item.batch_id == batch_id,
           Item.file_id == file_id, Item.status == 'ready'))
           if (not item.review_request or system_filled_only(item, file))
           and not (stored_checks and _stored_check(item)) and not restored_saved_copy(item, file)]
    if not ids:
        return None
    result = save_statements(session, case_id=case_id, item_ids=ids, actor=SYSTEM_ACTOR,
                             only_reconciled=True)
    if result['queued']:
        log.info('Automatic save: %s statement(s) of file %s queued for import (actor System)',
                 result['queued'], str(file_id)[:8])
    return result


# Marks a batch's file entry as prepared with automatic save on (set by the
# batch worker when the file's preparation ends). Only such files are swept.
AUTO_SAVE_MARK = 'auto_save'
SWEEP_BATCH_STATES = ('removed',) + PAUSED
# (batch id, file id) -> the signature of its open statements when the sweep
# last looked. Unchanged files are not checked again; per process, so after a
# restart every marked file is looked at once more.
_SWEPT = {}


_OPEN_VALUES = None


def _checks(values):
    summary = values['summary'] if isinstance(values['summary'], dict) else {}
    return dict(checks=(len(summary.get('problems') or ()), summary.get('problem_count') or 0,
                        bool(summary.get('readiness_pending')), (summary.get('readiness') or {}).get('inputs')))


def _open_statements(db):
    """Ready and held statements of batches that can still save, with what the sweep compares.

    The stored summaries are reused per PostgreSQL row version (row_versions):
    each round reads ids and versions, and decodes only the summaries that
    changed, not every open statement's summary every minute.
    """
    global _OPEN_VALUES
    from services.financial.row_versions import RowValues
    if _OPEN_VALUES is None:
        _OPEN_VALUES = RowValues(Item, kept=100_000)
    return _OPEN_VALUES.rows(db, (Item.id, Item.batch_id, Item.file_id, Item.status, Item.updated_at,
        Item.review_request.is_(None).label('untouched'), Batch.case_id), (Item.summary.label('summary'),),
        (Batch.id == Item.batch_id, Batch.status.notin_(SWEEP_BATCH_STATES), Item.status.in_(('ready', 'attention'))),
        order_by=Item.id, transform=_checks)


def _stored_check(item):
    """The stored readiness already shows a check, so a save would hold it (the sweep's cheap filter)."""
    summary = item.summary or {}
    return bool(summary.get('problems') or summary.get('problem_count') or summary.get('readiness_pending')
                or summary.get('comparison_pending'))


# Neil, 2026-10-24 (account currency, overlap trim): a statement held only until another statement of its
# account is saved becomes saveable when that one is saved, without any change to its own row. The sweep
# therefore looks again at a case's marked files after any save in that case. Reverse: False (a file is
# looked at again only when its own open statements change, as before).
REVISIT_AFTER_SAVES = True


def _saved_marks(db, case_ids):
    """{case id: what changes when a statement of the case is saved}, or {} with the switch off."""
    if not REVISIT_AFTER_SAVES:
        return {}
    from services.financial.field_proposals import _fingerprint
    return {case_id: _fingerprint(db, case_id) for case_id in case_ids}


def _signature(rows):
    return tuple(sorted((str(identity), status, untouched, str(updated), problems)
                        for identity, status, untouched, updated, problems in rows))


def sweep_save(factory, *, budget_seconds=20.0):
    """Background round: save, as System, statements that are ready now but were not saved when their file was prepared.

    Covers a statement that became ready after its file's preparation (the
    readiness sweep, a refresh after a change elsewhere) and one whose
    automatic save failed. Only files prepared with automatic save on
    (``AUTO_SAVE_MARK``); each file goes through the preparation-end save
    (``_auto_save_once``), so the proof, the copy rule (a copy is set aside by
    the import writer, never saved) and the System actor are the same. Two
    workers may run it at once: claims are compare-and-set under the case,
    batch, item and evidence locks, and the loser saves nothing. A file whose
    open statements are unchanged since the last look is skipped. Never raises.

    Returns {queued, files, item_ids: [...]} for what this round claimed.
    """
    report = dict(queued=0, files=0, item_ids=[])
    if not AUTO_SAVE_READY:
        return report
    started = time.monotonic()
    try:
        with factory() as db:
            groups = {}
            for row in _open_statements(db):
                groups.setdefault((row.batch_id, row.file_id, row.case_id), []).append(
                    (row.id, row.status, row.untouched, row.updated_at, row.checks))
            marks = _saved_marks(db, {key[2] for key in groups})
            changed = {key: (_signature(members), marks.get(key[2])) for key, members in groups.items()
                       if _SWEPT.get(key[:2]) != (_signature(members), marks.get(key[2]))}
            marked = {}
            if changed:
                for batch_id, files in db.execute(select(Batch.id, Batch.files).where(
                        Batch.id.in_({key[0] for key in changed}))):
                    marked[batch_id] = {entry.get('file_id') for entry in files or () if entry.get(AUTO_SAVE_MARK)}
    except Exception:
        log.exception('Saving statements that became ready failed; the next round retries')
        return report
    for (batch_id, file_id, case_id), signature in sorted(changed.items(), key=lambda pair: str(pair[0][:2])):
        if budget_seconds is not None and time.monotonic() - started >= budget_seconds:
            break
        if str(file_id) not in marked.get(batch_id, ()):
            _SWEPT[(batch_id, file_id)] = signature
            continue
        outcome = _sweep_file(factory, case_id, batch_id, file_id)
        if outcome is None:
            continue  # failed: looked at again next round
        _SWEPT[(batch_id, file_id)] = signature
        if outcome.get('queued'):
            report['queued'] += outcome['queued']
            report['files'] += 1
            report['item_ids'] += outcome['item_ids']
    if report['queued']:
        log.info('Automatic save after preparation: %s statement(s) of %s file(s) queued for import (actor System)',
                 report['queued'], report['files'])
    return report


def _sweep_file(factory, case_id, batch_id, file_id):
    """One marked file's preparation-end save; None when it failed (retried next round)."""
    from sqlalchemy.exc import OperationalError
    for attempt in range(1, AUTO_SAVE_ATTEMPTS + 1):
        with factory() as db:
            try:
                result = _auto_save_once(db, case_id=case_id, batch_id=batch_id, file_id=file_id, stored_checks=True)
            except PdfMappingError as error:
                db.rollback()
                if error.status_code == 409:
                    # Another worker or a person saved one of them first; nothing
                    # of this claim was kept. The next round sees the new state.
                    log.info('Automatic save of file %s: saved meanwhile elsewhere', str(file_id)[:8])
                    return None
                log.exception('Automatic save of statements that became ready failed; they stay ready in the queue')
                return None
            except OperationalError as error:
                db.rollback()
                if attempt < AUTO_SAVE_ATTEMPTS and getattr(error.orig, 'sqlstate', None) in ('40P01', '40001'):
                    time.sleep(attempt + random.random())
                    continue
                log.warning('Automatic save of file %s hit a database lock; the next round retries', str(file_id)[:8])
                return None
            except Exception:
                db.rollback()
                log.exception('Automatic save of statements that became ready failed; they stay ready in the queue')
                return None
            if not result:
                return dict(queued=0, item_ids=[])
            return dict(queued=result['queued'], item_ids=_claimed(db, result))
    return None


def _claimed(db, result):
    ids = [UUID(op['operation_id']) for op in result.get('operations', ())]
    if not ids:
        return []
    return [row['item_id'] for op in db.scalars(select(Operation).where(Operation.id.in_(ids)))
            for row in op.outcomes or ()]


# The backlog: statements that were ready before automatic save existed, or
# whose file was prepared without it (no AUTO_SAVE_MARK). ``sweep_backlog``
# saves them in the background under exactly the rule of
# ``scripts/financial_save_ready_backlog.py`` (which calls the same two
# functions): ready, no stored check, no investigator edit or draft, then
# today's admission and ``fully_reconciled`` in ``save_statements``, actor
# System, an ordinary reversible import receipt. One more switch beside
# AUTO_SAVE_READY: FINANCIAL_AUTO_SAVE_BACKLOG=0 stops only the sweep.
AUTO_SAVE_BACKLOG = os.environ.get('FINANCIAL_AUTO_SAVE_BACKLOG', '1').strip().lower() not in ('0', 'false', 'off', 'no')
BACKLOG_CHUNK = 10
BACKLOG_PER_ROUND = 30
# Item id -> its updated_at when the sweep last decided about it (per process,
# bounded): a statement admission held is looked at again only after it changes.
_BACKLOG_SEEN = OrderedDict()
BACKLOG_SEEN_MAX = 100_000
# Neil, 2026-10-25 (BNB2 queue): another case's backlog of statements the save holds (already saved through
# another batch) took every round after each restart, so BNB2's ready statements were never reached. With this
# switch each case with backlog gets its share of a round, starting after the case served last.
# Reverse: LOUPE_FINANCIAL_BACKLOG_FAIR_CASES=0 (cases in id order, the first takes the round, as before).
BACKLOG_FAIR_CASES = os.environ.get('LOUPE_FINANCIAL_BACKLOG_FAIR_CASES', '1').strip().lower() not in (
    '0', 'false', 'off', 'no')
_BACKLOG_LAST_CASE = ['']


def backlog_choice(session, items):
    """Ids of ready items the backlog rule may claim: no stored check, no investigator edit or draft.

    Details System filled from confirmed proposals are not an edit. Admission
    itself (``save_statements(only_reconciled=True)``) decides afterwards.
    """
    from services.financial.statement_progress import review_progress
    items = [item for item in items if item.status == 'ready']
    files = {f.id: f for f in session.scalars(select(EvidenceFile).where(
             EvidenceFile.id.in_({i.file_id for i in items})))} if items else {}
    return [i.id for i in items if not (i.summary or {}).get('problems') and not (i.summary or {}).get('problem_count')
            and ((not i.review_request and not (i.file_id in files and review_progress(files[i.file_id], i.statement_key)))
                 or system_filled_only(i, files.get(i.file_id)))
            and not restored_saved_copy(i, files.get(i.file_id))]


# Held because today's admission disagrees with the stored "ready": the stored
# readiness is brought up to date, so the queue says what a save would do.
_STALE_READY = ('No longer ready', 'Being rechecked')


def save_backlog(factory, case_id, ids):
    """Claim backlog statements as System in chunks; refresh the stored readiness of those admission held.

    Returns {queued, held: Counter of reasons, refreshed}.
    """
    queued, held, stale = 0, Counter(), []
    for start in range(0, len(ids), BACKLOG_CHUNK):
        with factory() as session:
            result = save_statements(session, case_id=case_id, item_ids=ids[start:start + BACKLOG_CHUNK],
                                     actor=SYSTEM_ACTOR, only_reconciled=True)
        queued += result['queued']
        for entry in result['held']:
            held[entry['reason']] += 1
            if entry['item_id'] and not entry['reason'].startswith(('Already saved', 'Has a check', 'The same', 'Its batch')):
                stale.append(UUID(entry['item_id']))
    refreshed = 0
    if stale:
        from services.financial.import_batches import refresh_readiness
        with factory() as session:
            refreshed = refresh_readiness(session, case_id=case_id, item_ids=stale)['refreshed']
            session.commit()
    return dict(queued=queued, held=held, refreshed=refreshed)


def _ready_backlog(db):
    """(case id, item id, updated_at) of ready statements in batches that can save, not decided since they changed."""
    rows = db.execute(select(Batch.case_id, Item.id, Item.updated_at).join(Batch, Batch.id == Item.batch_id).where(
        Item.status == 'ready', Batch.status.notin_(SWEEP_BATCH_STATES)).order_by(Batch.case_id, Item.id))
    return [row for row in rows if _BACKLOG_SEEN.get(row[1]) != row[2]]


def _remember(db, ids):
    for identity, updated in db.execute(select(Item.id, Item.updated_at).where(Item.id.in_(ids))):
        _BACKLOG_SEEN[identity] = updated
        _BACKLOG_SEEN.move_to_end(identity)
    while len(_BACKLOG_SEEN) > BACKLOG_SEEN_MAX:
        _BACKLOG_SEEN.popitem(last=False)


def sweep_backlog(factory, *, budget_seconds=20.0, max_statements=BACKLOG_PER_ROUND):
    """Background round: save ready backlog statements as System, a few per round. Never raises.

    Bounded (statements and seconds per round) and resumable: a saved
    statement is no longer ready, and one admission held is skipped until it
    changes. Returns {queued, cases, considered, held: {reason: n}, refreshed}.
    """
    report = dict(queued=0, cases=0, considered=0, held=Counter(), refreshed=0)
    if not (AUTO_SAVE_READY and AUTO_SAVE_BACKLOG):
        report['held'] = {}
        return report
    started = time.monotonic()
    try:
        with factory() as db:
            pending = _ready_backlog(db)
            by_case = {}
            for case_id, identity, _ in pending:
                by_case.setdefault(case_id, []).append(identity)
        share = None
        if BACKLOG_FAIR_CASES and len(by_case) > 1:
            # Each case gets its share of the round, and the case served first rotates, so one case's long
            # backlog of statements the save holds cannot keep another case's ready statements waiting.
            share = max(1, -(-max_statements // len(by_case)))
            order = sorted(by_case, key=str)
            start = next((i for i, case_id in enumerate(order) if str(case_id) > _BACKLOG_LAST_CASE[0]), 0)
            by_case = OrderedDict((case_id, by_case[case_id]) for case_id in order[start:] + order[:start])
        for case_id, identities in by_case.items():
            if report['considered'] >= max_statements or (
                    budget_seconds is not None and time.monotonic() - started >= budget_seconds):
                break
            identities = identities[:max_statements - report['considered']]
            if share is not None:
                identities = identities[:share]
                _BACKLOG_LAST_CASE[0] = str(case_id)
            with factory() as db:
                chosen = backlog_choice(db, list(db.scalars(select(Item).where(Item.id.in_(identities)))))
                db.rollback()
            report['considered'] += len(identities)
            try:
                outcome = save_backlog(factory, case_id, chosen) if chosen else dict(queued=0, held=Counter(), refreshed=0)
            except PdfMappingError as error:
                # 409: saved meanwhile elsewhere; the next round sees the new state.
                log.info('Backlog save for case %s: %s', str(case_id)[:8], error)
                continue
            with factory() as db:
                _remember(db, identities)
            report['queued'] += outcome['queued']
            report['held'].update(outcome['held'])
            report['refreshed'] += outcome['refreshed']
            report['cases'] += 1 if outcome['queued'] else 0
    except Exception:
        log.exception('Saving the ready backlog failed; the next round retries')
    report['held'] = dict(report['held'])
    if report['queued'] or report['refreshed']:
        log.info('Ready backlog: %s statement(s) queued for import as System; %s', report['queued'], report)
    return report
