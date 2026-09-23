"""Case-scoped typed payment identities, separate from the printed name.

A link identifies the other side of a payment. It does not establish ownership
or pair two postings as a transfer. The selected identity and actor are retained
with the reviewed reading, including in captured ledger exports.
"""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class PaymentCounterpartyLink(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['party', 'account']
    id: UUID


def resolve_link(session, *, case_id, link):
    from services.financial.account_parties import account_parties, AccountPartyError
    state = account_parties(session, case_id=case_id)
    if link.kind == 'party':
        item = next((p for p in state['parties'] if p['id'] == str(link.id)), None)
        if item is None:
            raise AccountPartyError('The selected person or business is no longer available in this case.', 409)
        label = item['name']
    else:
        item = next((a for a in state['accounts'] if a['id'] == str(link.id)), None)
        if item is None:
            raise AccountPartyError('The selected account is no longer available in this case.', 409)
        label = ' · '.join(str(item[k]) for k in ('holder_as_recorded', 'institution', 'identifier_as_printed', 'currency') if item.get(k))
        label = label or 'Account ' + item['id'][:8]
    return dict(kind=link.kind, id=str(link.id), label=label,
                **({'canonical_id': item.get('canonical_id', item['id'])} if link.kind == 'account' else {}))


def effective_link(row):
    labels = (row.metadata_ or {}).get('investigation_labels', {})
    if 'counterparty_link' in labels:
        return labels['counterparty_link']
    return (getattr(row, 'provenance', None) or {}).get('reviewed_counterparty')


def record_link(session, *, row, link, actor, reason):
    """Append to the existing payment identity decision stream, in the caller's transaction."""
    from sqlalchemy import select
    from postgres.models.financial import AdjudicationEvent
    from postgres.models.enums import AdjudicationSubject, AdjudicationDecision
    from services.financial.decisions import record
    prior = session.scalar(select(AdjudicationEvent).where(
        AdjudicationEvent.case_id == row.case_id,
        AdjudicationEvent.subject_type == 'transaction',
        AdjudicationEvent.subject_id == row.id,
        AdjudicationEvent.decision == 'set_counterparty_party'
    ).order_by(AdjudicationEvent.subject_sequence.desc()))
    before = dict(party=prior.after['party'] if prior else None,
                  account=prior.after.get('account') if prior else None, override=prior is not None)
    after = dict(party=dict(id=link['id'], name=link['label']) if link and link['kind'] == 'party' else None,
                 account=dict(id=link['id'], label=link['label']) if link and link['kind'] == 'account' else None, override=True)
    if before == after:
        return
    record(session, case_id=row.case_id, subject=row, subject_type=AdjudicationSubject.transaction,
           decision=AdjudicationDecision.set_counterparty_party, actor=actor, reason=reason, before=before, after=after)


def display_link(row):
    """Resolve the current account representation while preserving the saved ID."""
    link = effective_link(row)
    if not link or link['kind'] != 'account':
        return link
    from sqlalchemy.orm import object_session
    from postgres.models.financial import FinancialAccount
    db = object_session(row)
    if db is None:
        return link
    original_id = UUID(link['id'])
    original = db.get(FinancialAccount, original_id)
    if original is None or original.case_id != row.case_id:
        return link
    canonical_id = UUID((original.metadata_ or {}).get('canonical_account_id') or str(original_id))
    if canonical_id == original_id:
        return link
    account = db.get(FinancialAccount, canonical_id)
    label = ' · '.join(v for v in (account.holder_name, account.institution_name, account.identifier_as_printed, account.currency) if v)
    return {**link, 'id': str(canonical_id), 'recorded_id': link['id'], 'label': label or link['label']}
