"""Read each ledger payment's printable number (the rule is in ``postgres.models.financial_transaction_number``).

Numbers are assigned by the database trigger from migration ``20261104_transaction_numbers``; this module only
reads them, in one query per case, and keeps each on its row for :func:`transaction_query.to_view`.
"""
from __future__ import annotations

from sqlalchemy import select


def table_ready(session) -> bool:
    """False on a database without the numbers table (tests that build only some tables); checked once per engine."""
    from services.financial.payment_categories import _table_ready
    return _table_ready(session.connection(), 'financial_transaction_numbers')


def numbers_for_case(session, case_id) -> dict:
    """{transaction id: number} for every numbered row of one case, in one query."""
    from postgres.models.financial_transaction_number import FinancialTransactionNumber as N
    if not table_ready(session):
        return {}
    return dict(session.execute(select(N.transaction_id, N.number).where(N.case_id == case_id)).all())


def attach_numbers(session, rows) -> None:
    """Keep each row's number on the row (``_txn_number``), one query per case among the rows. Up to 500 rows read
    only their own numbers; a longer list reads the case's."""
    from postgres.models.financial_transaction_number import FinancialTransactionNumber as N
    rows = list(rows)
    by_case: dict = {}
    for row in rows:
        by_case.setdefault(row.case_id, []).append(row)
    for case_id, members in by_case.items():
        if len(members) > 500:
            found = numbers_for_case(session, case_id)
        elif table_ready(session):
            found = dict(session.execute(select(N.transaction_id, N.number).where(
                N.case_id == case_id, N.transaction_id.in_([row.id for row in members]))).all())
        else:
            found = {}
        for row in members:
            row._txn_number = found.get(row.id)


def number_of(row):
    """The row's number: the attached one, else one bounded lookup, else None (not numbered yet)."""
    if hasattr(row, '_txn_number'):
        return row._txn_number
    from sqlalchemy.orm import object_session
    from postgres.models.financial_transaction_number import FinancialTransactionNumber as N
    session = object_session(row)
    if session is None or row.id is None or not table_ready(session):
        return None
    value = session.scalar(select(N.number).where(N.transaction_id == row.id))
    row._txn_number = value
    return value
