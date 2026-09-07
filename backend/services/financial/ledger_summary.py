"""Exact, bounded summaries of the relational ledger, with explicit exclusions.

The bound is checked before reporting any count or money. One SELECT observes
rows, source disposition/class and account ownership together. Credits/debits
are account postings, not deduplicated transfers or an opening/closing balance.
"""
from datetime import date
from sqlalchemy import select
from postgres.models.enums import ProofClass, LedgerStatus, DocumentStatus
from postgres.models.financial import FinancialTransaction, FinancialSourceDocument, FinancialAccount
from services.financial.proof_class import DEFAULT_TOTAL_CLASSES, counts_toward_totals
from services.financial.money import get_currency

MAX_SUMMARY_ROWS = 10000


class LedgerSummaryError(ValueError):
    pass


def ledger_summary(session, *, case_id, account_id=None, start_date=None, end_date=None, grouping=None):
    if grouping not in (None, "daily", "monthly"):
        raise LedgerSummaryError("Choose daily or monthly ledger grouping.")
    for value in (start_date, end_date):
        if value is not None and type(value) is not date:
            raise LedgerSummaryError("Summary date bounds must be calendar dates.")
    if start_date and end_date and start_date > end_date:
        raise LedgerSummaryError("Summary start date must be on or before end date.")
    query = select(FinancialTransaction, FinancialSourceDocument, FinancialAccount).outerjoin(
        FinancialSourceDocument, FinancialSourceDocument.id == FinancialTransaction.source_document_id
    ).outerjoin(FinancialAccount, FinancialAccount.id == FinancialTransaction.account_id).where(
        FinancialTransaction.case_id == case_id)
    if account_id is not None:
        query = query.where(FinancialTransaction.account_id == account_id)
    if start_date is not None:
        query = query.where(FinancialTransaction.ordering_date >= start_date)
    if end_date is not None:
        query = query.where(FinancialTransaction.ordering_date <= end_date)
    pairs = list(session.execute(query.order_by(FinancialTransaction.id).limit(MAX_SUMMARY_ROWS + 1).execution_options(populate_existing=True)))
    result = dict(case_id=str(case_id), account_id=str(account_id) if account_id else None,
        start_date=start_date.isoformat() if start_date else None, end_date=end_date.isoformat() if end_date else None,
        included_classes=sorted(p.value for p in DEFAULT_TOTAL_CLASSES), max_rows=MAX_SUMMARY_ROWS,
        available=False, reason=None, considered_rows=None, included_rows=None, excluded_rows=None,
        exclusions=None, currencies=[], applied=False,
        limitation="Current ledger account postings only, with admitted source documents and included row/source proof classes. Currency totals are separate. Internal transfers are not matched or netted; net postings are not an account balance. Missing evidence and incomplete extraction are not measured by these totals.")
    if grouping is not None:
        result.update(grouping=grouping, date_basis="ordering_date", points=[])
    if len(pairs) > MAX_SUMMARY_ROWS:
        result['reason'] = 'More than 10000 rows match this scope. Narrow the account or dates; no partial total was calculated.'
        return result
    exclusions = {status.value: 0 for status in LedgerStatus if status.value != 'admitted'}
    exclusions.update(source_not_admitted=0, proof_class_not_included=0)
    groups = {}
    points = {}
    for row, document, account in pairs:
        if document is None or account is None or document.case_id != case_id or account.case_id != case_id:
            raise LedgerSummaryError("Ledger source or account ownership is inconsistent; summary unavailable.")
        try:
            status = LedgerStatus(row.ledger_status)
            source_status = DocumentStatus(document.status)
            row_class, source_class = ProofClass(row.proof_class), ProofClass(document.proof_class)
        except ValueError as exc:
            raise LedgerSummaryError("Stored classification or disposition is unrecognized.") from exc
        if status.value == 'admitted' and row.superseded_by_id is not None:
            raise LedgerSummaryError("An admitted row references a replacement; summary unavailable.")
        if status.value != 'admitted':
            exclusions[status.value] += 1
            continue
        if source_status.value != 'admitted':
            exclusions['source_not_admitted'] += 1
            continue
        if not counts_toward_totals(row_class) or not counts_toward_totals(source_class):
            exclusions['proof_class_not_included'] += 1
            continue
        if type(row.amount_minor) is not int or row.amount_minor < 0 or row.direction not in ('credit', 'debit'):
            raise LedgerSummaryError("An included ledger amount or direction is invalid.")
        try:
            currency = get_currency(row.currency)
        except Exception as exc:
            raise LedgerSummaryError("An included ledger currency is unsupported.") from exc
        group = groups.setdefault(currency.code, dict(currency=currency.code, rows=0, credits_minor=0, debits_minor=0))
        group['rows'] += 1
        group[row.direction + 's_minor'] += row.amount_minor
        if grouping is not None:
            if type(row.ordering_date) is not date:
                raise LedgerSummaryError("An included ledger ordering date is invalid.")
            bucket = row.ordering_date if grouping == "daily" else row.ordering_date.replace(day=1)
            point = points.setdefault((bucket.isoformat(),currency.code),
                dict(date=bucket.isoformat(),currency=currency.code,rows=0,credits_minor=0,debits_minor=0,
                     transaction_ids=[],source_document_ids=set()))
            point['rows'] += 1
            point[row.direction + 's_minor'] += row.amount_minor
            point['transaction_ids'].append(str(row.id))
            point['source_document_ids'].add(str(document.id))
    for group in list(groups.values()) + list(points.values()):
        group['net_minor'] = str(group['credits_minor'] - group['debits_minor'])
        group['credits_minor'] = str(group['credits_minor'])
        group['debits_minor'] = str(group['debits_minor'])
    excluded = sum(exclusions.values())
    result.update(available=True, considered_rows=len(pairs), included_rows=len(pairs)-excluded,
        excluded_rows=excluded, exclusions=exclusions, currencies=[groups[c] for c in sorted(groups)])
    if grouping is not None:
        for point in points.values():
            point['source_document_ids'] = sorted(point['source_document_ids'])
        result['points'] = [points[key] for key in sorted(points)]
    return result
