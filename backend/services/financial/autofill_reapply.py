"""Fill a held statement's missing currency, bank or holder by itself, once its reading is current.

The automatic fill (``field_proposals``, ``queue_save._prepared_entries``) runs when a file's preparation ends.
A held statement misses it when the answer is established only later (another statement of its account is
saved afterwards), when its file's preparation was adopted from another batch, or when its file was prepared
before the fill existed. And the fill can never work on a statement whose stored key the deployed reader no
longer produces: the details save reads the statement by that key and refuses it.

This background round brings those statements in line, with no click:

* Only a statement whose reading is current: its batch file was prepared by the deployed backend reader
  (``held_reprepare`` stamp), or the deployed reader was found to prepare it exactly the same way (its
  'unchanged' mark under that stamp). A file prepared by an older reader is left to ``held_reprepare``, which
  prepares it again (re-keying it); preparation's own fill then runs.
* Only a statement nobody worked on: held, no batch draft, no saved review, no person's duplicate decision,
  in a batch that is not removed or paused (a preparing one only while no worker holds its lease).
* Only the answers ``field_proposals.automatic_fills`` allows (the account's saved statements, with the
  balance-chain and bracketing rules; the case's usual currency only under ``CASE_CURRENCY``; never an account
  number), and only when
  they answer every question the statement asks: a statement still held by its reading or its balances is not
  filled, so it stays free to be prepared again by the next reader fix.
* Through the same product path as preparation's fill (``queue_save.fill_confirmed``): the statement-details
  save, actor System, fill-missing mode (a value a person entered is never replaced), the proposal's basis in
  the file's account-detail history; an investigator changes it in the same dialog. The statement is then
  checked again like any other; it is saved only by the automatic save (``sweep_backlog``: ready, no check,
  reconciled, every case gate), never by this round.

Switch ``LOUPE_FINANCIAL_AUTOFILL_REAPPLY`` (default on; with the proposal switches). Off, or on any failure,
nothing is written and the next round tries again (fail closed).
"""
import logging
import os
import time
from collections import OrderedDict
from uuid import UUID

from sqlalchemy import and_, func, or_, select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item

log = logging.getLogger(__name__)

HELD = 'attention'
SKIPPED_BATCHES = ('removed', 'paused', 'pausing', 'preparing')
# Neil, 2026-10-25 (BNB2 queue): a case's automatic batch is 'preparing' nearly all the time (new files keep
# joining it), so its held statements were never filled. A preparing batch is now included while no worker holds
# its lease; only files whose own preparation finished qualify (``current_reading``), and the details save refuses
# a batch whose lease is taken (retried next round). Reverse: LOUPE_FINANCIAL_AUTOFILL_REAPPLY_PREPARING=0.
INCLUDE_PREPARING = os.environ.get('LOUPE_FINANCIAL_AUTOFILL_REAPPLY_PREPARING', '1').strip().lower() not in (
    '0', 'false', 'off', 'no')
MAX_PER_ROUND = 200
# Item id -> (updated_at, the case's saved-state fingerprint) when last decided (per process, bounded).
_SEEN = OrderedDict()
SEEN_MAX = 100_000


def current_reading(entry, stamp):
    """True when the batch file's statements carry the deployed reader's keys."""
    from services.financial import held_reprepare as held
    if not isinstance(entry, dict) or entry.get('status') != 'checked':
        return False
    if entry.get(held.STAMP) == stamp:
        return True
    mark = entry.get(held.MARK)
    return (isinstance(mark, dict) and mark.get('stamp') == stamp and mark.get('state') == held.LEFT
            and mark.get('reason') == 'unchanged')


def _untouched(item, file):
    """No batch draft, no saved review and no person's duplicate decision (saved_copies' rule)."""
    from services.financial.saved_copies import _person_work
    if item.review_request or file is None:
        return False
    return not _person_work(file, item, item.statement_key or '')


def held_candidates(session):
    """(case id, batch id, item id, updated_at) of held statements in batches that can still save.

    A draft is excluded when the item is loaded (``entries_for_case``): a JSON column cleared to None can hold a
    JSON null rather than SQL NULL, so ``IS NULL`` would miss untouched statements.
    """
    allowed = Batch.status.notin_(SKIPPED_BATCHES)
    if INCLUDE_PREPARING:
        allowed = or_(allowed, and_(Batch.status == 'preparing', or_(
            Batch.worker_token.is_(None), Batch.lease_until.is_(None), Batch.lease_until < func.now())))
    return session.execute(select(Batch.case_id, Item.batch_id, Item.id, Item.updated_at)
        .join(Batch, Batch.id == Item.batch_id)
        .where(Item.status == HELD, allowed)
        .order_by(Batch.case_id, Item.id)).all()


def entries_for_case(session, case_id, item_ids, stamp):
    """Queue-like entries (with only their automatic fills as proposals) for the given held items. Read only."""
    from services.financial import field_proposals as fp
    from services.financial.review_queue import actionable_problems
    items = list(session.scalars(select(Item).where(Item.id.in_(list(item_ids)), Item.status == HELD)))
    if not items:
        return []
    batches = {b.id: b for b in session.scalars(select(Batch).where(Batch.id.in_({i.batch_id for i in items})))}
    files = {f.id: f for f in session.scalars(select(EvidenceFile).where(
             EvidenceFile.case_id == case_id, EvidenceFile.id.in_({i.file_id for i in items})))}
    knowledge = None
    entries = []
    for item in items:
        batch = batches.get(item.batch_id)
        entry = next((e for e in (batch.files or []) if e.get('file_id') == str(item.file_id)), None) if batch else None
        if not current_reading(entry, stamp) or not _untouched(item, files.get(item.file_id)):
            continue
        summary = item.summary or {}
        reasons = {p['review_reason'] for p in actionable_problems(summary)}
        if not reasons or not reasons <= set(fp.REASONS.values()):
            continue
        if knowledge is None:
            knowledge = fp.case_knowledge(session, case_id)
        values = fp.summary_values(summary)
        fills = fp.automatic_fills(values, fp.propose(values, knowledge), knowledge)
        if fills and fp.resolves_all(reasons, fills):
            entries.append(dict(id=str(item.id), batch_id=str(item.batch_id), file_id=str(item.file_id),
                                statement_id=item.statement_key or None, proposals=fills))
    return entries


def _remember(key, value):
    _SEEN[key] = value
    _SEEN.move_to_end(key)
    while len(_SEEN) > SEEN_MAX:
        _SEEN.popitem(last=False)


def sweep(factory, *, budget_seconds=20.0, max_items=MAX_PER_ROUND):
    """Background round: fill held statements' established details (System). Never raises.

    Returns {considered, statements, filled, failed, cases}.
    """
    from services.financial import field_proposals as fp
    report = dict(considered=0, statements=0, filled=0, failed=0, cases=0)
    if not fp.reapply_enabled() or not fp.enabled_fields():
        return report
    from services.financial.held_reprepare import preparation_stamp
    from services.financial.queue_save import fill_confirmed
    started = time.monotonic()
    stamp = preparation_stamp()
    try:
        with factory() as db:
            by_case = OrderedDict()
            marks = {}
            for case_id, _, item_id, updated in held_candidates(db):
                if case_id not in marks:
                    marks[case_id] = fp._fingerprint(db, case_id)
                if _SEEN.get(item_id) != (updated, marks[case_id]):
                    by_case.setdefault(case_id, []).append((item_id, updated))
            db.rollback()
    except Exception:
        log.exception('Filling held statements\' established details failed; the next round retries')
        return report
    for case_id, members in by_case.items():
        if report['considered'] >= max_items or (budget_seconds is not None
                                                 and time.monotonic() - started >= budget_seconds):
            break
        members = members[:max_items - report['considered']]
        report['considered'] += len(members)
        try:
            with factory() as db:
                entries = entries_for_case(db, case_id, [i for i, _ in members], stamp)
                db.rollback()
                outcome = dict(saved=0, failed=0)
                if entries:
                    outcome, _ = fill_confirmed(db, case_id=case_id, entries=entries)
        except Exception:
            log.exception('Filling held statements\' established details failed; the next round retries')
            continue
        report['statements'] += len(entries)
        report['filled'] += outcome.get('saved', 0)
        report['failed'] += outcome.get('failed', 0)
        report['cases'] += bool(entries)
        if not outcome.get('failed'):
            # Decided for this state; looked at again when the item or the case's saved statements change.
            for item_id, updated in members:
                _remember(item_id, (updated, marks[case_id]))
    if report['filled']:
        log.info('Held statements filled from their accounts\' saved statements (System): %s', report)
    return report
