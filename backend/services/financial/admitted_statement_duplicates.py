"""Statements already admitted twice: count one copy, keep both as evidence.

The same printed statement reaches the ledger twice when it is produced twice
(the same records disclosed again under another Bates range) and both copies
were saved before the pre-admission check (``pending_statement_duplicates``)
could recognise them. Both productions are evidence and stay in the case.

Rule (the one new imports follow, r1-reproduced): two saved copies are the same
statement when they cover the same printed period (``same_statement`` or
``same_printed_period``) and their money is equal. Equal money here means all
of: every included payment (amount, direction, date) and printed balance read
equal (``statement_content``), the payments and period balances admitted to the
ledger are equal, and both landed in the same ledger account. A copy that
differs in any of these is never set aside; the pair is listed for comparison.
A pair where an investigator recorded why both copies are needed, or where an
investigator restored a copy, is left as the investigator decided.

Retained copy, one rule for every case (decision r2-admitted-duplicates; Neil
chose the first production for case 49494305):

1. a copy carrying investigator work (an edited saved review, a corrected row
   or a recorded row decision) is kept over one without;
2. then the copy whose evidence file was received first (the original upload
   of a reread);
3. files received together are taken in file-name order, digits compared as
   numbers, which is production order for Bates-numbered files;
4. then the first page of the statement in its file (a reprint inside one
   file keeps its first printing);
5. then the copy saved first, then its id.

The earliest *saved* copy is not used: periods of one upload are saved by
concurrent batch workers in no evidence order, so it would split one
production's periods across both files. Reverse: rank by
``document.created_at`` first in ``_rank``.

Setting a copy aside reuses the reversible document decision
(``duplicate_decisions.decide_duplicate``): the copy becomes ``superseded``,
linked to the retained copy, its rows ``superseded`` (they leave totals and,
through the graph drift check, the graph), and an adjudication records the
before and after. Restoring is that decision's exact reversal. Nothing is
deleted. Batch items of the copy show "Duplicate - Ignored by system".
"""
from __future__ import annotations

import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select

from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile, IngestionLog
from postgres.models.financial import (
    AdjudicationEvent, FinancialSourceDocument, FinancialStatementPeriod, FinancialTransaction,
)
from services.financial.decisions import Actor
from services.financial.pdf_candidates import _digest

POLICY = 'admitted-statement-duplicate-v1'
SET_ASIDE_BASIS = 'system_admitted_duplicate'
KEPT_BASIS = 'investigator_kept_copy'
SYSTEM_ACTOR = Actor(name='system: duplicate set-aside', email='duplicate-set-aside@system.local')
SET_ASIDE_REASON = ('The same printed statement was saved twice with equal payments and printed balances. '
                    'This copy is set aside as a linked duplicate; the retained copy counts once.')
RESTORE_REASON = 'Restored on request; both copies count again.'

# Why a matching pair is not set aside. Codes are reported; messages refuse.
HELD = {
    'investigator_kept_both': 'An investigator recorded why both copies are needed.',
    'not_same_period': 'The copies do not cover the same printed period.',
    'reading_not_comparable': 'A copy has no complete reading of payments and balances to compare.',
    'other_bank_without_payments': 'The bank names differ and there are no payments to prove the copies equal.',
    'money_differs': 'The payments or printed balances were read differently.',
    'ledger_differs': 'The payments or balances saved in Transactions differ between the copies.',
    'account_differs': 'The copies were saved to different accounts.',
    'edits_differ': 'This copy carries investigator edits the retained copy does not have.',
    'retained_rows_set_aside': 'The retained copy has payments set aside or corrected.',
    'rows_corrected': 'This copy has corrected payments.',
    'unverifiable': 'A saved reading of these copies could not be verified.',
}


class AdmittedDuplicateError(Exception):
    def __init__(self, message, status_code=409):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class _Copy:
    document: FinancialSourceDocument
    file: EvidenceFile | None
    received: tuple
    statement_id: str
    scope: dict | None
    original: dict
    request: dict
    first_page: int
    content: str = ''
    payments: int = 0
    usable: bool = False
    ledger: str = ''
    accounts: frozenset = frozenset()
    admitted_rows: int = 0
    rows_clean: bool = True
    corrected: bool = False
    edited: bool = False
    review: str = ''
    work: bool = False
    latest: AdjudicationEvent | None = None
    verified: bool = True
    notes: list = field(default_factory=list)


def _natural(name):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', name or '')]


def _first_page(original):
    pages = original.get('statement_page_numbers') or original.get('page_numbers') or [
        row.get('page_number') for row in original.get('rows', []) if type(row.get('page_number')) is int]
    pages = [page for page in pages if type(page) is int and page > 0]
    return min(pages) if pages else 1


def _comparable(original, request):
    """A complete reading of what was saved: the reading itself, or the reading
    once every row it could not resolve was excluded in the saved review.

    Excluded rows put nothing in the ledger, and ledger equality is required
    as well, so dropping them cannot hide a payment.
    """
    from services.financial.pending_statement_duplicates import _financial_reading
    if _financial_reading(original)[1]:
        return True
    unread = ('unresolved', 'unclassified')
    excluded = {row.get('id') for row in request.get('rows', []) if row.get('excluded')}
    if any(row.get('kind') in unread and row.get('id') not in excluded for row in original.get('rows', [])):
        return False
    return _financial_reading({**original, 'rows': [row for row in original.get('rows', [])
                                                    if row.get('kind') not in unread]})[1]


def _received(session, file, cache):
    """When and under what name the evidence first arrived (a reread's original upload)."""
    if file is None:
        return ('', [], '')
    root = file
    root_id = (file.metadata_ or {}).get('statement_root_evidence_id')
    if root_id and root_id != str(file.id):
        try:
            key = uuid.UUID(root_id)
        except (ValueError, TypeError):
            key = None
        if key is not None:
            if key not in cache:
                cache[key] = session.get(EvidenceFile, key)
            if cache[key] is not None and cache[key].case_id == file.case_id:
                root = cache[key]
    return (str(root.created_at), _natural(root.original_filename), str(root.id))


def _load(session, case_id, *, document_ids=None):
    """Every saved statement copy of a case (or the given ones), with what decides equality."""
    from services.financial.pending_statement_duplicates import _initial, _review_shape, statement_content
    from services.financial.statement_import_overlap import scope
    query = select(FinancialSourceDocument).where(
        FinancialSourceDocument.case_id == case_id,
        FinancialSourceDocument.document_type == 'statement_review',
        FinancialSourceDocument.status.in_(('admitted', 'superseded')))
    if document_ids is not None:
        query = query.where(FinancialSourceDocument.id.in_(list(document_ids)))
    documents = [d for d in session.scalars(query.order_by(FinancialSourceDocument.id))
                 if not (d.metadata_ or {}).get('financial_import_removal')]
    if not documents:
        return []
    ids = [d.id for d in documents]
    files = {f.id: f for f in session.scalars(select(EvidenceFile).where(
        EvidenceFile.case_id == case_id, EvidenceFile.id.in_({d.evidence_file_id for d in documents})))}
    rows_by = defaultdict(list)
    for row in session.scalars(select(FinancialTransaction).where(
            FinancialTransaction.case_id == case_id, FinancialTransaction.source_document_id.in_(ids))):
        rows_by[row.source_document_id].append(row)
    periods_by = defaultdict(list)
    for period in session.scalars(select(FinancialStatementPeriod).where(
            FinancialStatementPeriod.case_id == case_id, FinancialStatementPeriod.source_document_id.in_(ids))):
        periods_by[period.source_document_id].append(period)
    latest = {}
    for event in session.scalars(select(AdjudicationEvent).where(
            AdjudicationEvent.case_id == case_id, AdjudicationEvent.subject_type == 'source_document',
            AdjudicationEvent.subject_id.in_(ids)).order_by(AdjudicationEvent.subject_sequence)):
        latest[event.subject_id] = event
    row_ids = {row.id for rows in rows_by.values() for row in rows}
    decided_rows = set(session.scalars(select(AdjudicationEvent.subject_id).where(
        AdjudicationEvent.case_id == case_id, AdjudicationEvent.subject_type == 'transaction'))) & row_ids
    roots = {}
    copies = []
    for document in documents:
        metadata = document.metadata_ or {}
        original = metadata.get('statement_import_original') or {}
        request = metadata.get('statement_import_request') or {}
        verified = bool(original and request
            and _digest(original) == metadata.get('statement_import_original_sha256')
            and _digest(request) == metadata.get('statement_import_request_sha256'))
        file = files.get(document.evidence_file_id)
        copy = _Copy(document=document, file=file, received=_received(session, file, roots),
            statement_id=metadata.get('statement_import_statement_id') or '', original=original, request=request,
            first_page=_first_page(original) if original else 1, latest=latest.get(document.id), verified=verified,
            scope=None)
        if verified and not request.get('period_start_unprinted'):
            copy.scope = scope({**request, 'account_type': (original.get('metadata') or {}).get('account_type') or ''})
        if verified:
            copy.content, copy.payments = statement_content(original)
            copy.usable = _comparable(original, request)
            copy.review = _digest(_review_shape(original, request))
            copy.edited = _review_shape(original, request) != _review_shape(original, _initial(original))
        rows = rows_by.get(document.id, [])
        admitted = [r for r in rows if r.ledger_status == 'admitted']
        periods = periods_by.get(document.id, [])
        copy.admitted_rows = len(admitted)
        copy.ledger = _digest(dict(
            payments=sorted([str(r.amount_minor), r.direction, r.currency,
                             str(r.transaction_date or r.posted_date or r.value_date or r.ordering_date)] for r in admitted),
            periods=sorted([str(p.period_start), str(p.period_end), p.currency,
                            str(p.opening_balance_minor), str(p.closing_balance_minor)] for p in periods)))
        copy.accounts = frozenset({r.account_id for r in admitted} | {p.account_id for p in periods})
        copy.rows_clean = all(r.ledger_status == 'admitted' and r.superseded_by_id is None for r in rows)
        copy.corrected = any(r.superseded_by_id is not None for r in rows)
        copy.work = bool(copy.edited or copy.corrected or any(r.id in decided_rows for r in rows))
        copies.append(copy)
    return copies


def _rank(copy):
    return (not copy.work, copy.received, copy.first_page, str(copy.document.created_at), str(copy.document.id))


def _kept_reason(copy):
    return bool((copy.request.get('coverage_review_reason') or '').strip())


def _same_period(left, right):
    from services.financial.statement_import_overlap import same_printed_period, same_statement
    return bool(left.scope and right.scope and (same_statement(left.scope, right.scope)
                                                or same_printed_period(left.scope, right.scope)))


def _compare(copy, retained):
    """None when ``copy`` may be set aside in favour of ``retained``; otherwise why not."""
    if not (copy.verified and retained.verified):
        return 'unverifiable'
    if _kept_reason(copy) or _kept_reason(retained):
        return 'investigator_kept_both'
    if not _same_period(copy, retained):
        return 'not_same_period'
    if not (copy.usable and retained.usable):
        return 'reading_not_comparable'
    if copy.scope['identity'] != retained.scope['identity'] and not copy.payments:
        return 'other_bank_without_payments'
    if copy.content != retained.content:
        return 'money_differs'
    if copy.ledger != retained.ledger:
        return 'ledger_differs'
    if copy.accounts != retained.accounts:
        return 'account_differs'
    if copy.edited and copy.review != retained.review:
        return 'edits_differ'
    if copy.corrected:
        return 'rows_corrected'
    if not retained.rows_clean:
        return 'retained_rows_set_aside'
    return None


def same_admitted_statement(session, document, primary):
    """Refusal message, or None when ``document`` may be set aside for ``primary``.

    Called by ``decide_duplicate`` under its row locks, so the comparison is
    made again on exactly the state being changed.
    """
    if document.case_id != primary.case_id:
        return 'The documents belong to different cases.'
    copies = {c.document.id: c for c in _load(session, document.case_id, document_ids=[document.id, primary.id])}
    if len(copies) != 2:
        return 'A saved statement copy is unavailable.'
    code = _compare(copies[document.id], copies[primary.id])
    return HELD[code] if code else None


def _restored(copy):
    return bool(copy.latest is not None and copy.latest.decision == 'restore_document')


def _set_aside_here(copy):
    return bool(copy.document.status == 'superseded' and copy.document.superseded_by_id
                and copy.latest is not None and copy.latest.decision == 'supersede_duplicate')


def _entry(copy, retained, code=None):
    return dict(document_id=str(copy.document.id), evidence_file_id=str(copy.document.evidence_file_id),
        statement_id=copy.statement_id, transactions=copy.admitted_rows,
        file_sha256=(copy.file.sha256 if copy.file else None),
        retained_document_id=str(retained.document.id) if retained else None,
        retained_evidence_file_id=str(retained.document.evidence_file_id) if retained else None,
        retained_file_sha256=(retained.file.sha256 if retained and retained.file else None),
        retained_saved_first=bool(retained and str(retained.document.created_at) <= str(copy.document.created_at)),
        code=code, reason=HELD.get(code) if code else None)


def find_admitted_duplicates(session, case_id):
    """What a set-aside would do in this case. Reads only.

    ``set_aside``: copies equal to their retained copy; ``held``: matching
    periods whose copies differ (listed for comparison, never set aside);
    ``kept``: an investigator recorded why both are needed; ``restored``:
    periods where a copy was restored, left as decided; ``already_set_aside``:
    copies set aside by an earlier decision.
    """
    copies = _load(session, case_id)
    by_id = {c.document.id: c for c in copies}
    report = dict(case_id=str(case_id), saved_copies=sum(c.document.status == 'admitted' for c in copies),
        set_aside=[], held=[], kept=[], restored=[], already_set_aside=[], not_compared=Counter())
    buckets = defaultdict(list)
    for copy in copies:
        if copy.document.status != 'admitted':
            if _set_aside_here(copy):
                report['already_set_aside'].append(_entry(copy, by_id.get(copy.document.superseded_by_id)))
            continue
        if not copy.verified:
            report['not_compared']['unverifiable'] += 1
        elif copy.scope is None:
            report['not_compared']['no_complete_period'] += 1
        else:
            buckets[(copy.scope['currency'], copy.scope['start'], copy.scope['end'], copy.scope['account_type'])].append(copy)
    for bucket in buckets.values():
        parent = list(range(len(bucket)))

        def find(index):
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                if _same_period(bucket[i], bucket[j]):
                    parent[find(i)] = find(j)
        groups = defaultdict(list)
        for index, copy in enumerate(bucket):
            groups[find(index)].append(copy)
        for group in groups.values():
            if len(group) < 2:
                continue
            ranked = sorted(group, key=_rank)
            retained = ranked[0]
            if any(_restored(copy) for copy in group):
                report['restored'].extend(_entry(copy, retained, 'restored') for copy in ranked[1:])
                continue
            for copy in ranked[1:]:
                code = _compare(copy, retained)
                target = report['set_aside'] if code is None else (
                    report['kept'] if code == 'investigator_kept_both' else report['held'])
                target.append(_entry(copy, retained, code))
    report['not_compared'] = dict(report['not_compared'])
    return report


# Display -----------------------------------------------------------------

def _link(session, document):
    file = session.get(EvidenceFile, document.evidence_file_id)
    statement_id = (document.metadata_ or {}).get('statement_import_statement_id') or None
    if statement_id is not None and not re.fullmatch(r'[a-f0-9]{64}', statement_id):
        statement_id = None
    return dict(evidence_file_id=str(document.evidence_file_id), statement_id=statement_id,
        source_document_id=str(document.id), filename=file.original_filename if file else '',
        page_number=_first_page((document.metadata_ or {}).get('statement_import_original') or {}))


def _latest_event(session, document):
    return session.scalar(select(AdjudicationEvent).where(
        AdjudicationEvent.case_id == document.case_id, AdjudicationEvent.subject_type == 'source_document',
        AdjudicationEvent.subject_id == document.id).order_by(AdjudicationEvent.subject_sequence.desc()).limit(1))


def excluded_copy_disposition(session, document, revision):
    """How a saved copy set aside as a duplicate is shown in its review and batch."""
    retained = session.get(FinancialSourceDocument, document.superseded_by_id) if document.superseded_by_id else None
    if retained is None or retained.case_id != document.case_id:
        return None
    event = _latest_event(session, document)
    basis = ((event.after or {}).get('basis') if event is not None else None)
    link = _link(session, retained)
    where = f"{link['filename']}, page {link['page_number']}" if link['filename'] else f"page {link['page_number']}"
    system = basis == SET_ASIDE_BASIS
    reason = (f'Same statement as {where}. Its payments and printed balances are equal, so they are counted once, '
              'from that copy. This copy stays in the case as evidence. Restore it, or keep this copy instead, '
              'from the duplicate decision.') if system else (
              f'Excluded as a copy of {where}. This copy stays in the case as evidence. '
              'Restore it from the duplicate decision.')
    return dict(policy=POLICY, reading_revision=revision, revision=revision, status='ignored',
        label='Duplicate - Ignored by system' if system else 'Duplicate - Excluded by investigator',
        reason=reason, current=True, admitted_copy=True,
        matched_fields=['account_reference', 'period_start', 'period_end', 'currency', 'payments_and_balances'],
        basis='identical_financial_reading' if system else 'investigator_decision', retained=link,
        decided_at=event.created_at.isoformat() if event is not None and event.created_at else None,
        decided_by=event.actor_name if event is not None else None)


def duplicate_copies(session, document):
    """Copies of this saved statement that are set aside in its favour."""
    copies = session.scalars(select(FinancialSourceDocument).where(
        FinancialSourceDocument.case_id == document.case_id,
        FinancialSourceDocument.superseded_by_id == document.id,
        FinancialSourceDocument.status == 'superseded',
        FinancialSourceDocument.duplicate_match_rung.is_not(None)).order_by(FinancialSourceDocument.id))
    return [_link(session, copy) for copy in copies]


# Writes -------------------------------------------------------------------

def _lock_case(session, case_id):
    if session.scalar(select(Case.id).where(Case.id == case_id).with_for_update()) is None:
        raise AdmittedDuplicateError('Case not found.', 404)


def _locked(session, case_id, ids):
    documents = {d.id: d for d in session.scalars(select(FinancialSourceDocument).where(
        FinancialSourceDocument.case_id == case_id, FinancialSourceDocument.id.in_(list(ids)))
        .order_by(FinancialSourceDocument.id).with_for_update().execution_options(populate_existing=True))}
    if set(documents) != set(ids):
        raise AdmittedDuplicateError('Statement copy not found in this case.', 404)
    return documents


def _mark_items(session, case_id, document, set_aside):
    """Batch items of this saved period follow the decision; restore puts back what they showed."""
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
    from services.financial.duplicate_decisions import duplicate_revision
    items = session.scalars(select(Item).join(Batch, Batch.id == Item.batch_id).where(
        Batch.case_id == case_id, Batch.status != 'removed', Item.file_id == document.evidence_file_id,
        Item.statement_key == ((document.metadata_ or {}).get('statement_import_statement_id') or ''),
        Item.status.in_(('imported', 'duplicate_ignored'))).order_by(Item.id))
    disposition = excluded_copy_disposition(session, document, duplicate_revision(session, document)) if set_aside else None
    for item in items:
        summary = {key: value for key, value in (item.summary or {}).items() if key != 'readiness'}
        if set_aside and item.status == 'imported':
            summary['admitted_copy_set_aside'] = {key: summary.get(key) for key in (
                'transaction_count', 'record_count', 'incomplete_count', 'source_document_id')}
            summary.update(duplicate_disposition=disposition, can_import=False, problems=[], problem_count=0,
                transaction_count=0, record_count=0, incomplete_count=0)
            item.status = 'duplicate_ignored'
        elif not set_aside and item.status == 'duplicate_ignored' and 'admitted_copy_set_aside' in summary:
            summary.update({key: value for key, value in summary.pop('admitted_copy_set_aside').items() if value is not None})
            summary.pop('duplicate_disposition', None)
            item.status = 'imported'
        else:
            continue
        item.summary = summary


def _log(session, case_id, document, message, **extra):
    file = session.get(EvidenceFile, document.evidence_file_id)
    session.add(IngestionLog(case_id=case_id, evidence_file_id=document.evidence_file_id,
        filename=file.original_filename if file else None, level='info', message=message,
        extra=dict(source_document_id=str(document.id), **extra)))


def _exclude(session, case_id, document, primary, actor, reason, basis, touched):
    from services.financial.duplicate_decisions import decide_duplicate, duplicate_revision
    result = decide_duplicate(session, case_id=case_id, document_id=document.id, action='exclude',
        expected_revision=duplicate_revision(session, document), primary_id=primary.id,
        expected_primary_revision=duplicate_revision(session, primary), actor=actor, reason=reason,
        match='same_printed_statement', basis=basis, commit=False)
    _mark_items(session, case_id, document, True)
    touched.append((document.evidence_file_id, (document.metadata_ or {}).get('statement_import_statement_id') or ''))
    _log(session, case_id, document, 'Statement period set aside as a duplicate of another saved copy. '
         'Original PDF and saved review retained.', action='financial_duplicate_set_aside',
         retained_source_document_id=str(primary.id), adjudication_id=result['adjudication_id'], basis=basis)
    return result


def _restore(session, case_id, document, actor, reason, touched):
    from services.financial.duplicate_decisions import decide_duplicate, duplicate_revision
    result = decide_duplicate(session, case_id=case_id, document_id=document.id, action='restore',
        expected_revision=duplicate_revision(session, document), actor=actor, reason=reason, commit=False)
    _mark_items(session, case_id, document, False)
    touched.append((document.evidence_file_id, (document.metadata_ or {}).get('statement_import_statement_id') or ''))
    _log(session, case_id, document, 'Statement period restored: its payments count again.',
         action='financial_duplicate_restore', adjudication_id=result['adjudication_id'])
    return result


def _guarded(session, case_id, work):
    touched = []
    try:
        result = work(touched)
        session.commit()
    except Exception:
        session.rollback()
        raise
    # Batch lists reuse stored readiness; bring the changed periods current.
    # Best effort: a failure leaves them to the background readiness sweep.
    from services.financial.import_batches import refresh_file_readiness
    for file_id, statement_key in dict.fromkeys(touched):
        refresh_file_readiness(session, case_id=case_id, file_id=file_id, statement_key=statement_key)
    return result


def set_aside_copy(session, *, case_id, document_id, retained_id, actor=SYSTEM_ACTOR, reason=SET_ASIDE_REASON,
                   basis=SET_ASIDE_BASIS):
    """Set one saved copy aside in favour of ``retained_id``; commits. A repeat changes nothing."""
    def work(touched):
        _lock_case(session, case_id)
        documents = _locked(session, case_id, {document_id, retained_id})
        document = documents[document_id]
        if document.status == 'superseded' and document.superseded_by_id == retained_id:
            return dict(applied=False, already=True, document_id=str(document_id))
        return {**_exclude(session, case_id, document, documents[retained_id], actor, reason, basis, touched),
                'already': False}
    return _guarded(session, case_id, work)


def restore_copy(session, *, case_id, document_id, actor=SYSTEM_ACTOR, reason=RESTORE_REASON):
    """Undo one set-aside: the copy counts again. Commits."""
    def work(touched):
        _lock_case(session, case_id)
        document = _locked(session, case_id, {document_id})[document_id]
        if document.status == 'admitted':
            return dict(applied=False, already=True, document_id=str(document_id))
        return {**_restore(session, case_id, document, actor, reason, touched), 'already': False}
    return _guarded(session, case_id, work)


def keep_copy(session, *, case_id, document_id, actor, reason):
    """Swap the retained copy: this set-aside copy counts, the others are set aside in its favour.

    One transaction: the copy and every other copy linked to the same retained
    copy are restored, then the former retained copy and those others are set
    aside in favour of this one, each checked again for equal money.
    """
    def work(touched):
        _lock_case(session, case_id)
        document = _locked(session, case_id, {document_id})[document_id]
        if document.status != 'superseded' or document.superseded_by_id is None:
            raise AdmittedDuplicateError('This copy is not set aside as a duplicate.')
        former_id = document.superseded_by_id
        siblings = list(session.scalars(select(FinancialSourceDocument.id).where(
            FinancialSourceDocument.case_id == case_id, FinancialSourceDocument.superseded_by_id == former_id,
            FinancialSourceDocument.status == 'superseded').order_by(FinancialSourceDocument.id)))
        documents = _locked(session, case_id, {former_id, *siblings})
        for sibling in siblings:
            _restore(session, case_id, documents[sibling], actor, reason, touched)
        results = [_exclude(session, case_id, documents[former_id], document, actor, reason, KEPT_BASIS, touched)]
        results += [_exclude(session, case_id, documents[sibling], document, actor, reason, KEPT_BASIS, touched)
                    for sibling in siblings if sibling != document_id]
        return dict(applied=True, retained_document_id=str(document_id),
            set_aside=[r['document_id'] for r in results])
    return _guarded(session, case_id, work)


def sync_batch_items(session, *, case_id, document_id):
    """Batch items follow a document duplicate decision made elsewhere (the
    ledger's duplicate register). Best effort after that decision committed:
    a failure leaves the items to the background readiness sweep."""
    try:
        document = session.get(FinancialSourceDocument, document_id)
        if document is None or document.case_id != case_id:
            return

        def work(touched):
            _mark_items(session, case_id, document, document.status == 'superseded' and document.superseded_by_id is not None)
            touched.append((document.evidence_file_id, (document.metadata_ or {}).get('statement_import_statement_id') or ''))
        _guarded(session, case_id, work)
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Batch items did not follow a duplicate decision; the readiness sweep will retry')
        try:
            session.rollback()
        except Exception:
            pass


def set_aside_admitted_duplicates(session, case_id, *, actor=SYSTEM_ACTOR):
    """Apply ``find_admitted_duplicates`` for one case. Each copy commits on its own."""
    plan = find_admitted_duplicates(session, case_id)
    session.rollback()
    applied, refused = [], []
    for entry in plan['set_aside']:
        try:
            result = set_aside_copy(session, case_id=case_id, document_id=uuid.UUID(entry['document_id']),
                retained_id=uuid.UUID(entry['retained_document_id']), actor=actor)
        except Exception as error:  # Reported per copy; the rest continue.
            refused.append({**entry, 'refusal': str(error)})
            continue
        (applied if not result.get('already') else refused).append({**entry, **result})
    return dict(plan=plan, applied=applied, refused=refused)
