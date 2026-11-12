"""The stored facts of an imported statement, for comparing a held possible duplicate with it side by side.

Read-only. Money in, money out and the payment count are summed from the statement's current ledger rows only
(admitted and not superseded), so a corrected payment counts at its corrected value and the reading it replaced
does not count. Rows held out of the ledger (quarantined) are counted separately and
never added to the totals, so the comparison can say how many there are instead of leaving them out silently.
"""
from uuid import UUID

from sqlalchemy import case, func, select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialTransaction
from services.financial.statement_details import read_statement_details


def statement_compare_facts(session, *, case_id, source_id):
    details = read_statement_details(session, case_id=case_id, source_id=source_id)
    T = FinancialTransaction
    current = (T.ledger_status == 'admitted') & T.superseded_by_id.is_(None)
    count, money_in, money_out, held, currencies = session.execute(select(
        func.count(case((current, 1))),
        func.coalesce(func.sum(case((current & (T.direction == 'credit'), T.amount_minor), else_=0)), 0),
        func.coalesce(func.sum(case((current & (T.direction == 'debit'), T.amount_minor), else_=0)), 0),
        func.count(case(((T.ledger_status == 'quarantined') & T.superseded_by_id.is_(None), 1))),
        func.count(func.distinct(case((current, T.currency)))))
        .where(T.case_id == case_id, T.source_document_id == source_id)).one()
    file = session.get(EvidenceFile, UUID(details['evidence_file_id']))
    saved = details['details']
    return dict(
        case_id=details['case_id'], source_document_id=details['source_document_id'],
        evidence_file_id=details['evidence_file_id'], filename=file.original_filename if file else '',
        institution=saved.get('institution', ''), account_number=saved.get('account_number', ''),
        holder=saved.get('holder', ''), period_start=saved.get('period_start', ''),
        period_end=saved.get('period_end', ''), currency=details['currency'] or '',
        balance_convention=details['balance_convention'], pages=details['pages'],
        opening_balance_minor=details['balances']['opening']['amount_minor'],
        closing_balance_minor=details['balances']['closing']['amount_minor'],
        payment_count=int(count), money_in_minor=str(int(money_in)), money_out_minor=str(int(money_out)),
        held_from_ledger=int(held), mixed_currency=int(currencies) > 1)
