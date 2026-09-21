"""Shared person/company and account selection for every ledger read."""
from sqlalchemy import select
from postgres.models.financial import FinancialAccount, FinancialTransaction


def apply_account_selection(query, session, case_id, account_ids=None, account_holders=None):
    if account_ids:
        query = query.where(FinancialTransaction.account_id.in_(account_ids))
    if account_holders:
        names = {' '.join(name.split()).lower() for name in account_holders}
        ids = [id for id, name in session.execute(select(FinancialAccount.id, FinancialAccount.holder_name).where(
            FinancialAccount.case_id == case_id)) if ' '.join((name or '').split()).lower() in names]
        query = query.where(FinancialTransaction.account_id.in_(ids))
    return query
