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
fires only from preparation, so statements read before deploy are untouched;
the backlog is an explicit action (the queue's "Save all N ready statements",
or ``scripts/financial_save_ready_backlog.py``). Every automatic save is an
ordinary import receipt with actor System, reversible with the existing
import removal.
"""
import logging
import os
import random
import time
from collections import Counter
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


def system_filled_only(item, file):
    """The statement's only saved review is details System filled from confirmed proposals."""
    from services.financial.field_proposals import SYSTEM_NAME
    from services.financial.statement_progress import review_progress
    progress = review_progress(file, item.statement_key) if file is not None else None
    return bool(progress and item.review_request and (progress.get('saved_by') or {}).get('name') == SYSTEM_NAME
                and progress.get('request') == item.review_request)


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
            and not summary.get('problem_count') and (untouched or system_filled_only(item, file)))


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
    shas = {identity(i)[0] for i in candidates} - {None}
    busy = set()
    if shas:
        for file_sha, key in session.execute(select(EvidenceFile.sha256, Item.statement_key)
                .join(Item, Item.file_id == EvidenceFile.id).join(Batch, Batch.id == Item.batch_id)
                .where(Batch.case_id == case_id, Batch.status != 'removed', EvidenceFile.sha256.in_(shas),
                       Item.status.in_(('pending_import', 'imported')))):
            busy.add((file_sha, key or ''))
    unique, seen = [], set()
    for item in candidates:
        scope = identity(item)
        if item.status not in ('ready', 'attention'):
            held.append(_held(item, 'Already saved' if item.status in ('imported', 'pending_import')
                              else 'No longer ready: open it in the queue'))
        elif scope in saved or scope in busy:
            held.append(_held(item, 'Already saved through another batch'))
        elif scope in seen:
            held.append(_held(item, 'The same statement is already in this save'))
        else:
            seen.add(scope)
            unique.append(item)
    checked = {p.id: p for p in checked_batch_items(session, case_id, unique, validate_reviews=True,
                                                    reading='all')} if unique else {}
    ready_by_batch = {}
    for item in unique:
        projection = checked.get(item.id)
        if projection is None or not import_available(projection):
            held.append(_held(item, _not_ready_reason(projection) if projection is not None else
                              'No longer ready: open it in the queue'))
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


def _auto_save_once(session, *, case_id, batch_id, file_id):
    # Details the system can fill with certainty (confirmed proposals) are
    # filled first, as System; the statement then saves only when it
    # checks out completely like any other.
    entries = _prepared_entries(session, case_id, batch_id, file_id)
    if entries:
        fill_confirmed(session, case_id=case_id, entries=entries, owned_batch_id=batch_id)
    file = session.get(EvidenceFile, file_id)
    ids = [item.id for item in session.scalars(select(Item).where(Item.batch_id == batch_id,
           Item.file_id == file_id, Item.status == 'ready'))
           if not item.review_request or system_filled_only(item, file)]
    if not ids:
        return None
    result = save_statements(session, case_id=case_id, item_ids=ids, actor=SYSTEM_ACTOR,
                             only_reconciled=True)
    if result['queued']:
        log.info('Automatic save: %s statement(s) of file %s queued for import (actor System)',
                 result['queued'], str(file_id)[:8])
    return result
