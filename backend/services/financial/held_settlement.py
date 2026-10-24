"""Settle held statements that need no person: copies of saved statements, and fund statements.

Run with the engine-release snapshot of a case (recovery_readers.snapshot), under its case lock, before the
held statements are selected for a new reading:

* a held copy of an account and period the case already saved is set aside as a linked duplicate when its
  reading agrees with the saved ledger, or keeps a record of what differs (saved_copies);
* a held fund statement (holdings, no movement ledger) is set aside as not a payment statement
  (not_payment_statements).

New preparations reach the same outcomes through their own reading (the fund rule is part of the reading)
and duplicate check; this pass brings statements prepared before the rules existed in line. ``apply=False``
is the read-only estimate (counts and outcomes, nothing written).
"""
from collections import Counter

from sqlalchemy import select

from postgres.models.evidence import EvidenceDocumentText
from postgres.models.financial import FinancialAccount, FinancialSourceDocument, FinancialStatementPeriod
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item


def _saved_keys(session, case_id):
    """{(start, end): {last-six account digits}} of the case's admitted periods."""
    from services.financial.saved_copies import _digits
    keys = {}
    for start, end, normalised, printed in session.execute(select(FinancialStatementPeriod.period_start,
            FinancialStatementPeriod.period_end, FinancialAccount.identifier_normalised,
            FinancialAccount.identifier_as_printed).join(FinancialSourceDocument,
            FinancialSourceDocument.id == FinancialStatementPeriod.source_document_id).join(
            FinancialAccount, FinancialAccount.id == FinancialStatementPeriod.account_id).where(
            FinancialStatementPeriod.case_id == case_id, FinancialSourceDocument.status == 'admitted')):
        if start and end:
            keys.setdefault((start.isoformat(), end.isoformat()), set()).update(
                digits for digits in (_digits(normalised), _digits(printed)) if digits)
    return keys


def _copy_candidate(item, saved):
    from services.financial.saved_copies import _digits, _same_account
    summary = item.summary or {}
    account = _digits(summary.get('account'))
    accounts = saved.get((summary.get('period_start') or '', summary.get('period_end') or ''))
    return bool(account and accounts and any(_same_account(value, account) for value in accounts))


def settle_held_statements(session, case_id, *, apply=True):
    """Returns Counter of outcomes: 'saved_copy:<outcome>' and 'not_payment:<outcome>'."""
    from services.financial import not_payment_statements, saved_copies
    outcomes = Counter()
    if not (saved_copies.ENABLED or not_payment_statements.ENABLED):
        return outcomes
    items = list(session.scalars(select(Item).join(Batch, Batch.id == Item.batch_id).where(
        Batch.case_id == case_id, Batch.status.notin_(('removed', 'preparing', 'pausing')),
        Item.status == 'attention').order_by(Item.file_id, Item.statement_key, Item.id)))
    saved = _saved_keys(session, case_id) if saved_copies.ENABLED else {}
    titled = {}
    cache = {}
    for item in items:
        summary = item.summary or {}
        if saved_copies.ENABLED and _copy_candidate(item, saved):
            result = saved_copies.settle_item(session, case_id, item, cache=cache, apply=apply)
            outcomes['saved_copy:' + result['outcome'] + (':' + result['why'] if result.get('why') else '')] += 1
            if result['outcome'] == 'set_aside':
                continue
        if (not not_payment_statements.ENABLED or item.review_request or summary.get('not_payment_statement')
                or summary.get('transaction_count')):
            continue
        if item.file_id not in titled:
            text = session.get(EvidenceDocumentText, item.file_id)
            titled[item.file_id] = bool(text and not_payment_statements.TITLE.search(text.content or ''))
        if not titled[item.file_id]:
            continue
        from services.financial.pdf_candidates import PdfMappingError
        from services.financial.statement_import import read_statement_import
        try:
            proposal = read_statement_import(session, case_id=case_id, evidence_file_id=item.file_id,
                currency=summary.get('currency') or None, statement_id=item.statement_key or None, _cache=cache)
        except PdfMappingError:
            outcomes['not_payment:unreadable'] += 1
            continue
        if not proposal.get('not_payment_statement'):
            outcomes['not_payment:kept_in_review'] += 1
            continue
        if apply:
            not_payment_statements.reassess_items(session, case_id, item.file_id, item.statement_key or '', proposal)
        outcomes['not_payment:set_aside'] += 1
    if apply:
        session.flush()
    return outcomes
