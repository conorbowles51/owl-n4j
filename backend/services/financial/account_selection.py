"""Shared person/company and account selection for every ledger read."""
from sqlalchemy import select
from postgres.models.financial import FinancialAccount, FinancialTransaction


def holder_account_ids(session, case_id, account_holders):
    """One resolver for table, totals, export and incomplete-record scopes.

    Reviewed identities use an opaque party token; source-name selections stay
    supported for existing saved views. Suggestions never change a filter.
    """
    names = {' '.join(name.split()).lower() for name in account_holders if not name.startswith('party:')}
    parties = {name[6:] for name in account_holders if name.startswith('party:')}
    ids = {id for id, name in session.execute(select(FinancialAccount.id, FinancialAccount.holder_name).where(
        FinancialAccount.case_id == case_id)) if ' '.join((name or '').split()).lower() in names}
    if parties:
        from uuid import UUID
        from services.financial.account_parties import _account_party_state
        state = _account_party_state(session, case_id=case_id)
        ids.update(UUID(a['id']) for a in state['accounts'] if
            (a['party'] and a['party']['id'] in parties) or any(p['id'] in parties for p in a['holder_parties']))
    return sorted(ids, key=str)


def apply_account_selection(query, session, case_id, account_ids=None, account_holders=None):
    if account_ids:
        query = query.where(FinancialTransaction.account_id.in_(account_ids))
    if account_holders:
        ids = holder_account_ids(session, case_id, account_holders)
        query = query.where(FinancialTransaction.account_id.in_(ids))
    return query
