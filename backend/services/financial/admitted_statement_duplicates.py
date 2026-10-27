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

Copies read by different readers (r11-copy-audit). Another reader can word the
bank differently, give the statement another product type, group its pages
differently or capture one more printed balance, and file the copy in another
ledger account. The printed facts do not change, so two saved copies are also
the same printed statement when either

* their files are one document (identical bytes, or every page rendering
  identically: ``page_identity``) and the statements sit on the same pages, or
* they print the same account reference (with digits), currency and dates and
  carry at least one payment

and their money does not conflict: the same payments (amount, direction, date)
and balance convention, printed balances of one reading a subset of the
other's, and the same payments and period balances in the ledger. Measured on
every pair of verified real truth periods: 168 pairs share a printed reference,
dates and money with at least one payment, all true copies; with no payment 17
pairs do, all different sub-accounts of one statement, hence the payment rule.
Product type and bank wording are not compared. A pair equal in everything but
its ledger account is listed in ``split_across_accounts`` with the account merge
it needs; it is set aside only on request (``across_accounts``) and only with
the proof the pre-admission rule uses for a reader-independent copy, one
document. Accounts are never merged here. Reverse: ``READER_INDEPENDENT``.

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

import os
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlalchemy import func, select

from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile, IngestionLog
from postgres.models.financial import (
    AdjudicationEvent, FinancialAccount, FinancialSourceDocument, FinancialStatementPeriod, FinancialTransaction,
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
# Switch: False compares only copies of the same product and bank wording
# (the r2 rule), with no page identity and no listing across accounts.
READER_INDEPENDENT = True
# The proof a copy filed in another ledger account may be set aside with: the
# files are one document, as the pre-admission rule requires across readers.
SAME_DOCUMENT = ('identical_bytes', 'identical_pages')
# A copy is compared as its statement now stands: the holder, number, bank and currency a person corrected in the
# statement details, not the values first read. Reverse: LOUPE_FINANCIAL_DUPLICATE_CORRECTED_DETAILS=0.
CORRECTED_DETAILS = os.environ.get('LOUPE_FINANCIAL_DUPLICATE_CORRECTED_DETAILS', '1').strip().lower() not in (
    '0', 'false', 'off', 'no')
# 2026-10-26 fin-queue3 L30c: a copy filed in a multi-currency contract's old single account (Monex 2836625,
# 'institution_account' records holding every currency) is in the same account as a copy filed in that contract's
# account of the period's currency (same bank, number and currency), and that copy is the one kept. Reverse:
# LOUPE_FINANCIAL_DUPLICATE_CONTRACT_ACCOUNT=0.
CONTRACT_ACCOUNT = os.environ.get('LOUPE_FINANCIAL_DUPLICATE_CONTRACT_ACCOUNT', '1').strip().lower() not in (
    '0', 'false', 'off', 'no')

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
    key: tuple | None = None
    pages: dict | None = None
    section: frozenset = frozenset()
    raw_accounts: frozenset = frozenset()
    account: tuple | None = None  # (identity tier, bank, number, currency) of its one ledger account
    folio: str | None = None  # the document folio its file's first page prints (read only for copies without payments)


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
    as well, so dropping them cannot hide a payment. An unread row a person
    completed in the saved review (amount, direction and date) is read: its
    payment is in the ledger, which must still equal the other copy's.
    """
    from services.financial.pending_statement_duplicates import _financial_reading
    if _financial_reading(original)[1]:
        return True
    unread = ('unresolved', 'unclassified')
    settled = {row.get('id') for row in request.get('rows', []) if row.get('excluded') or _completed(row)}
    if any(row.get('kind') in unread and row.get('id') not in settled for row in original.get('rows', [])):
        return False
    return _financial_reading({**original, 'rows': [row for row in original.get('rows', [])
                                                    if row.get('kind') not in unread]})[1]


def _completed(row):
    """A saved review row a person filled in: money, a direction and a printed date."""
    return bool(str(row.get('amount_minor') or '').lstrip('-').isdigit() and int(row['amount_minor'])
                and row.get('direction') in ('debit', 'credit') and row.get('date'))


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


def _canonical_accounts(session, case_id):
    """Account records consolidated into one reviewed account map to it; {} when unreadable."""
    from services.financial.account_consolidation import canonical_map
    try:
        return canonical_map(session, case_id)
    except Exception:  # an inconsistent consolidation history: compare the records themselves
        return {}


def _load(session, case_id, *, document_ids=None, identities=None):
    """Every saved statement copy of a case (or the given ones), with what decides equality.

    ``identities``: {evidence file id: page identity} computed by the caller
    (a read-only dry run that renders files without stored identities); a
    stored identity is used otherwise.
    """
    from services.financial import page_identity
    from services.financial.pending_statement_duplicates import (
        _initial, _printed_key, _review_shape, _section_pages, statement_content)
    from services.financial.statement_import_overlap import scope
    from services.financial.statement_details import saved_currency, saved_details
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
    ledger_accounts = {a.id: a for a in session.scalars(select(FinancialAccount).where(
        FinancialAccount.case_id == case_id, FinancialAccount.id.in_(
            {p.account_id for periods in periods_by.values() for p in periods}
            | {r.account_id for rows in rows_by.values() for r in rows})))} if CONTRACT_ACCOUNT else {}
    latest = {}
    for event in session.scalars(select(AdjudicationEvent).where(
            AdjudicationEvent.case_id == case_id, AdjudicationEvent.subject_type == 'source_document',
            AdjudicationEvent.subject_id.in_(ids)).order_by(AdjudicationEvent.subject_sequence)):
        latest[event.subject_id] = event
    row_ids = {row.id for rows in rows_by.values() for row in rows}
    decided_rows = set(session.scalars(select(AdjudicationEvent.subject_id).where(
        AdjudicationEvent.case_id == case_id, AdjudicationEvent.subject_type == 'transaction'))) & row_ids
    roots = {}
    canonical = _canonical_accounts(session, case_id) if READER_INDEPENDENT else {}
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
            stands = {**request, **saved_details(document), 'currency': saved_currency(document) or request.get('currency')} \
                if CORRECTED_DETAILS else request
            copy.scope = scope({**stands, 'account_type': (original.get('metadata') or {}).get('account_type') or ''})
            copy.key = _printed_key(copy.scope)
            copy.section = _section_pages(original)
        if file is not None and READER_INDEPENDENT:
            given = (identities or {}).get(str(file.id))
            copy.pages = given if given and given.get('source_sha256') == file.sha256 else page_identity.stored(file)
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
        copy.raw_accounts = frozenset({r.account_id for r in admitted} | {p.account_id for p in periods})
        if CONTRACT_ACCOUNT and len(copy.raw_accounts) == 1:
            account = ledger_accounts.get(next(iter(copy.raw_accounts)))
            if account is not None:
                from services.financial.account_consolidation import bank_key
                from services.financial.accounts import read_identity_tier
                copy.account = (read_identity_tier(account), bank_key(account.institution_name or ''),
                                account.identifier_normalised or '', account.currency)
        copy.accounts = frozenset(canonical.get(a, a) for a in copy.raw_accounts)
        copy.rows_clean = all(r.ledger_status == 'admitted' and r.superseded_by_id is None for r in rows)
        copy.corrected = any(r.superseded_by_id is not None for r in rows)
        copy.work = bool(copy.edited or copy.corrected or any(r.id in decided_rows for r in rows))
        copies.append(copy)
    from services.financial.candidate_sources import PRINTED_FOLIO, printed_folio
    if PRINTED_FOLIO:
        folios = {}
        for copy in copies:
            if copy.verified and copy.scope and not copy.payments and copy.file is not None:
                if copy.file.id not in folios:
                    folios[copy.file.id] = printed_folio(session, case_id=case_id, evidence_file_id=copy.file.id)
                copy.folio = folios[copy.file.id]
    return copies


def _rank(copy):
    return (not copy.work, not _in_contract_account(copy), copy.received, copy.first_page, str(copy.document.created_at),
            str(copy.document.id))


def _in_contract_account(copy):
    from services.financial.accounts import TIER_CONTRACT_CURRENCY
    return bool(CONTRACT_ACCOUNT and copy.account and copy.account[0] == TIER_CONTRACT_CURRENCY)


def _contract_account_copy(copy, retained):
    """Whether ``copy`` sits in the contract's old single account and ``retained`` in its account of this currency."""
    return bool(_in_contract_account(retained) and copy.account and not _in_contract_account(copy)
                and copy.scope and retained.scope and copy.scope['currency'] == retained.scope['currency']
                and copy.account[1:3] == retained.account[1:3] and all(copy.account[1:3])
                and retained.account[3] == retained.scope['currency'])


def _kept_reason(copy):
    return bool((copy.request.get('coverage_review_reason') or '').strip())


def _same_period(left, right):
    from services.financial.statement_import_overlap import same_printed_period, same_statement
    return bool(left.scope and right.scope and (same_statement(left.scope, right.scope)
                                                or same_printed_period(left.scope, right.scope)))


def _same_document(left, right):
    """The basis on which two copies' files are one document, or None."""
    if left.file is None or right.file is None or left.file.id == right.file.id:
        return None
    if left.file.sha256 and left.file.sha256 == right.file.sha256:
        return 'identical_bytes'
    a, b = left.pages, right.pages
    if a and b and a.get('identity') and (a['identity'], a.get('renderer'), a.get('page_count')) == (
            b['identity'], b.get('renderer'), b.get('page_count')):
        return 'identical_pages'
    return None


def _match(left, right):
    """Why two saved copies are the same printed statement, or None.

    ``same_printed_period``: the r2 rule (same product and, for a full
    reference, bank). Otherwise, whatever either reader said about bank or
    product: ``identical_bytes`` / ``identical_pages`` for statements on the
    same pages of one document, ``printed_reference`` for the same printed
    account reference, currency and dates.
    """
    if _same_period(left, right):
        return 'same_printed_period'
    if not READER_INDEPENDENT or not (left.scope and right.scope) or any(
            left.scope.get(key) != right.scope.get(key) for key in ('currency', 'start', 'end')):
        return None
    from services.financial.pending_statement_duplicates import _page_copy
    document = _same_document(left, right)
    same_key = bool(left.key and left.key == right.key)
    if document and (_page_copy(left.original, right.original) or (same_key and left.section & right.section)):
        return document
    # Without a payment the same reference and dates are as often two
    # sub-accounts of one statement (measured: 17 of 20 truth pairs).
    return 'printed_reference' if same_key and left.payments and right.payments else None


def _same_printed_folio(copy, retained):
    """(fin-queue3 L26) Two files printing the same bank document folio, the statement the only one of its account
    reference, currency and dates in each file's reading: one printed statement however its readers named the bank
    or grouped its pages, even with no payment to compare (Monex 'Print To PDF' reprints of the bank's own files,
    read by section in one and over every page in the other). Its money is still compared after this."""
    from services.financial.pending_statement_duplicates import only_section_of_its_period
    return bool(copy.folio and copy.folio == retained.folio and copy.file is not None and retained.file is not None
                and copy.file.id != retained.file.id and only_section_of_its_period(copy.original)
                and only_section_of_its_period(retained.original))


def _reviewed_to_same_ledger(copy, retained):
    """A person completed one copy's reading in review, and both saved the same money.

    The readings then differ only by what the review supplied; the ledger (every
    admitted payment and every saved period balance) is the money compared.
    """
    return bool((copy.edited or retained.edited) and copy.admitted_rows and retained.admitted_rows
                and copy.ledger == retained.ledger)


def _compare(copy, retained):
    """None when ``copy`` may be set aside in favour of ``retained``; otherwise why not.

    ``account_differs`` is decided last: it means everything else is equal.
    """
    if not (copy.verified and retained.verified):
        return 'unverifiable'
    if _kept_reason(copy) or _kept_reason(retained):
        return 'investigator_kept_both'
    basis = _match(copy, retained)
    if basis is None:
        return 'not_same_period'
    if not (copy.usable and retained.usable):
        return 'reading_not_comparable'
    code = None
    if basis == 'same_printed_period':
        if (copy.scope['identity'] != retained.scope['identity'] and not copy.payments
                and not _contract_account_copy(copy, retained) and not _same_printed_folio(copy, retained)):
            code = 'other_bank_without_payments'
        elif copy.content != retained.content and not _reviewed_to_same_ledger(copy, retained):
            code = 'money_differs'
        if code and READER_INDEPENDENT and copy.key and copy.key == retained.key and copy.payments and retained.payments:
            basis = 'printed_reference'  # the same printed facts, read by another reader: compare as such
            code = None
        elif code:
            return code
    if basis != 'same_printed_period':
        from services.financial.pending_statement_duplicates import _money_conflicts
        if _money_conflicts(copy.original, retained.original):
            return 'money_differs'
    if copy.ledger != retained.ledger:
        return 'ledger_differs'
    if copy.edited and copy.review != retained.review:
        return 'edits_differ'
    if copy.corrected:
        return 'rows_corrected'
    if not retained.rows_clean:
        return 'retained_rows_set_aside'
    if copy.accounts != retained.accounts and not _contract_account_copy(copy, retained):
        return 'account_differs'
    return None


def same_admitted_statement(session, document, primary, *, across_accounts=False):
    """Refusal message, or None when ``document`` may be set aside for ``primary``.

    Called by ``decide_duplicate`` under its row locks, so the comparison is
    made again on exactly the state being changed. ``across_accounts`` also
    accepts a copy filed in another ledger account, only when the two files are
    one document by their stored identities.
    """
    if document.case_id != primary.case_id:
        return 'The documents belong to different cases.'
    copies = {c.document.id: c for c in _load(session, document.case_id, document_ids=[document.id, primary.id])}
    if len(copies) != 2:
        return 'A saved statement copy is unavailable.'
    copy, retained = copies[document.id], copies[primary.id]
    code = _compare(copy, retained)
    if code == 'account_differs' and across_accounts and READER_INDEPENDENT and _match(copy, retained) in SAME_DOCUMENT:
        return None
    return HELD[code] if code else None


def _restored(copy):
    return bool(copy.latest is not None and copy.latest.decision == 'restore_document')


def _set_aside_here(copy):
    return bool(copy.document.status == 'superseded' and copy.document.superseded_by_id
                and copy.latest is not None and copy.latest.decision == 'supersede_duplicate')


def _entry(copy, retained, code=None):
    basis = _match(copy, retained) if retained is not None and copy.scope and retained.scope else None
    return dict(document_id=str(copy.document.id), evidence_file_id=str(copy.document.evidence_file_id),
        statement_id=copy.statement_id, transactions=copy.admitted_rows,
        file_sha256=(copy.file.sha256 if copy.file else None),
        retained_document_id=str(retained.document.id) if retained else None,
        retained_evidence_file_id=str(retained.document.evidence_file_id) if retained else None,
        retained_file_sha256=(retained.file.sha256 if retained and retained.file else None),
        retained_saved_first=bool(retained and str(retained.document.created_at) <= str(copy.document.created_at)),
        basis=basis, code=code, reason=HELD.get(code) if code else None,
        **(dict(printed_folio=copy.folio) if retained is not None and _same_printed_folio(copy, retained) else {}))


def _account_merge(session, copy, retained):
    """The account merge a copy split across two ledger accounts needs, and what blocks it.

    Mirrors the checks of ``account_consolidation.preview_consolidation``
    (bank, complete identifier, currency, product type); merging is a reviewed
    decision there, never made here.
    """
    from postgres.models.financial import FinancialAccount
    from services.financial.account_consolidation import bank_key
    ids = sorted(copy.raw_accounts | retained.raw_accounts, key=str)
    accounts = {a.id: a for a in session.scalars(select(FinancialAccount).where(FinancialAccount.id.in_(ids)))}
    chosen = [accounts[i] for i in ids if i in accounts]
    blockers = []
    if len({bank_key(a.institution_name) for a in chosen if a.institution_name}) > 1:
        blockers.append('banks_differ')
    printed = {re.sub(r'[^A-Z0-9]', '', (a.identifier_as_printed or '').upper()) for a in chosen
               if a.identifier_as_printed and not (a.metadata_ or {}).get('identity_provisional')}
    if len(printed) > 1:
        blockers.append('identifiers_differ')
    if len({a.currency for a in chosen} - {None}) > 1:
        blockers.append('currencies_differ')
    if len({a.account_type for a in chosen} - {None}) > 1:
        blockers.append('product_types_differ')
    others = session.scalar(select(func.count()).select_from(FinancialStatementPeriod).join(
        FinancialSourceDocument, FinancialSourceDocument.id == FinancialStatementPeriod.source_document_id).where(
        FinancialStatementPeriod.account_id.in_(list(copy.raw_accounts) or [uuid.uuid4()]),
        FinancialSourceDocument.status == 'admitted', FinancialSourceDocument.id != copy.document.id)) or 0
    return dict(copy_account_ids=sorted(str(a) for a in copy.raw_accounts),
        retained_account_ids=sorted(str(a) for a in retained.raw_accounts),
        retained_account_id=str(sorted(retained.raw_accounts, key=str)[0]) if retained.raw_accounts else None,
        blockers=blockers, other_saved_periods_in_copy_account=int(others))


def find_admitted_duplicates(session, case_id, *, identities=None):
    """What a set-aside would do in this case. Reads only.

    ``set_aside``: copies equal to their retained copy; ``split_across_accounts``:
    copies equal to their retained copy but saved to another ledger account,
    with the account merge they need (``automatic``: the files are one
    document, so ``across_accounts`` may set the copy aside); ``held``:
    matching periods whose copies differ (listed for comparison, never set
    aside); ``kept``: an investigator recorded why both are needed;
    ``restored``: periods where a copy was restored, left as decided;
    ``already_set_aside``: copies set aside by an earlier decision.
    ``identities``: page identities computed by a dry run (see ``_load``).
    """
    copies = _load(session, case_id, identities=identities)
    by_id = {c.document.id: c for c in copies}
    report = dict(case_id=str(case_id), saved_copies=sum(c.document.status == 'admitted' for c in copies),
        set_aside=[], split_across_accounts=[], held=[], kept=[], restored=[], already_set_aside=[],
        not_compared=Counter())
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
            buckets[(copy.scope['currency'], copy.scope['start'], copy.scope['end'])
                    + (() if READER_INDEPENDENT else (copy.scope['account_type'],))].append(copy)
    for bucket in buckets.values():
        parent = list(range(len(bucket)))

        def find(index):
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                if _match(bucket[i], bucket[j]):
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
                if code == 'account_differs' and READER_INDEPENDENT:
                    entry = _entry(copy, retained, code)
                    entry.update(account_merge=_account_merge(session, copy, retained),
                                 automatic=entry['basis'] in SAME_DOCUMENT)
                    report['split_across_accounts'].append(entry)
                    continue
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
    from services.financial.saved_reading_replacement import is_replacement_link
    # A reading replaced by a reader replacement is not a copy (it is shown in the replacement notice).
    return [_link(session, copy) for copy in copies if not is_replacement_link(session, copy, document)]


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


def _exclude(session, case_id, document, primary, actor, reason, basis, touched, match='same_printed_statement'):
    from services.financial.duplicate_decisions import decide_duplicate, duplicate_revision
    result = decide_duplicate(session, case_id=case_id, document_id=document.id, action='exclude',
        expected_revision=duplicate_revision(session, document), primary_id=primary.id,
        expected_primary_revision=duplicate_revision(session, primary), actor=actor, reason=reason,
        match=match, basis=basis, commit=False)
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
                   basis=SET_ASIDE_BASIS, across_accounts=False):
    """Set one saved copy aside in favour of ``retained_id``; commits. A repeat changes nothing.

    ``across_accounts``: the copy may sit in another ledger account, accepted
    only when the two files are one document (checked again under the locks).
    """
    match = 'same_document_across_accounts' if across_accounts else 'same_printed_statement'

    def work(touched):
        _lock_case(session, case_id)
        documents = _locked(session, case_id, {document_id, retained_id})
        document = documents[document_id]
        if document.status == 'superseded' and document.superseded_by_id == retained_id:
            return dict(applied=False, already=True, document_id=str(document_id))
        return {**_exclude(session, case_id, document, documents[retained_id], actor, reason, basis, touched, match),
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


def set_aside_admitted_duplicates(session, case_id, *, actor=SYSTEM_ACTOR, across_accounts=False):
    """Apply ``find_admitted_duplicates`` for one case. Each copy commits on its own.

    Copies split across two ledger accounts are set aside only with
    ``across_accounts`` and only when ``automatic`` (one document); the account
    merge they need is never made here.
    """
    plan = find_admitted_duplicates(session, case_id)
    session.rollback()
    applied, refused = [], []
    entries = [(entry, False) for entry in plan['set_aside']]
    if across_accounts:
        entries += [(entry, True) for entry in plan['split_across_accounts'] if entry['automatic']]
    for entry, split in entries:
        try:
            result = set_aside_copy(session, case_id=case_id, document_id=uuid.UUID(entry['document_id']),
                retained_id=uuid.UUID(entry['retained_document_id']), actor=actor, across_accounts=split)
        except Exception as error:  # Reported per copy; the rest continue.
            refused.append({**entry, 'refusal': str(error)})
            continue
        (applied if not result.get('already') else refused).append({**entry, **result})
    return dict(plan=plan, applied=applied, refused=refused)
