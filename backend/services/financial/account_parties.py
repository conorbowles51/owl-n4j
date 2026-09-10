"""Replay durable investigator account-to-party decisions over source accounts.

These links group accounts for analysis; they never rewrite printed holder names,
account identifiers, postings or proof classes. Every change is an ordered event.
"""
import hashlib
import json
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from postgres.models.case import Case
from postgres.models.financial import FinancialAccount, AdjudicationEvent
from postgres.models.enums import AdjudicationSubject, AdjudicationDecision
from services.financial.decisions import record


class AccountPartyError(ValueError):
    def __init__(self, message, status_code=422):
        super().__init__(message)
        self.status_code = status_code


class AccountPartyRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    account_ids: list[UUID] = Field(min_length=1, max_length=100)
    party_id: UUID | None = None
    new_party_name: str | None = Field(default=None, min_length=1, max_length=255)
    clear: bool = False
    reason: str = Field(min_length=1, max_length=4000)

    @model_validator(mode='after')
    def valid_choice(self):
        if len(set(self.account_ids)) != len(self.account_ids):
            raise ValueError('Choose each account once.')
        if sum((self.party_id is not None, self.new_party_name is not None, self.clear)) != 1:
            raise ValueError('Choose an existing party, name a new party, or clear the link.')
        if not self.reason.strip() or self.new_party_name is not None and not self.new_party_name.strip():
            raise ValueError('A nonblank name and reason are required.')
        return self


def account_parties(session, *, case_id):
    accounts = list(session.scalars(select(FinancialAccount).where(
        FinancialAccount.case_id == case_id).order_by(FinancialAccount.id).limit(1001)))
    if len(accounts) > 1000:
        raise AccountPartyError('More than1000accounts; no incomplete party directory was returned.')
    events = list(session.scalars(select(AdjudicationEvent).where(
        AdjudicationEvent.case_id == case_id,
        AdjudicationEvent.subject_type == 'account',
        AdjudicationEvent.decision == 'set_account_party').order_by(
            AdjudicationEvent.subject_id, AdjudicationEvent.subject_sequence).limit(5001)))
    if len(events) > 5000:
        raise AccountPartyError('More than5000party decisions; no incomplete history was returned.')
    ids = {str(account.id) for account in accounts}
    assignments, parties, history = {}, {}, []
    for event in events:
        account_id = str(event.subject_id)
        if account_id not in ids:
            raise AccountPartyError('Party history refers to an unavailable account.', 409)
        if not isinstance(event.before, dict) or not isinstance(event.after, dict) or set(event.before) != {'party'} or set(event.after) != {'party'}:
            raise AccountPartyError('Account party history is malformed.', 409)
        if event.before['party'] != assignments.get(account_id):
            raise AccountPartyError('Account party history cannot be replayed consistently.', 409)
        party = event.after['party']
        if party is not None:
            if not isinstance(party, dict) or set(party) != {'id', 'name'} or not isinstance(party['name'], str) or not party['name'].strip():
                raise AccountPartyError('Saved party identity is malformed.', 409)
            try:
                UUID(party['id'])
            except (ValueError, TypeError, AttributeError) as exc:
                raise AccountPartyError('Saved party identity is malformed.', 409) from exc
            if party['id'] in parties and parties[party['id']] != party:
                raise AccountPartyError('Saved party names conflict.', 409)
            parties[party['id']] = party
        assignments[account_id] = party
        history.append(dict(id=str(event.id), account_id=account_id,
            sequence=event.subject_sequence, before=event.before, after=event.after,
            reason=event.reason, actor=event.actor_email,
            recorded_at=event.created_at.isoformat()))
    result = dict(case_id=str(case_id), accounts=[dict(id=str(a.id),
        holder_as_recorded=a.holder_name, identifier_as_printed=a.identifier_as_printed,
        institution=a.institution_name, currency=a.currency,
        party=assignments.get(str(a.id))) for a in accounts],
        parties=sorted(parties.values(), key=lambda p: (p['name'].casefold(), p['id'])),
        history=history, applied=False,
        limitation='Investigator account links are replayed from decisions. Equal printed names do not establish identity. Original source accounts and proof classes remain unchanged.')
    result['revision'] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return result


def set_account_party(session, *, case_id, request: AccountPartyRequest, actor):
    try:
        # Serializes party decisions for this case, including creation of groups.
        if session.scalar(select(Case.id).where(Case.id == case_id).with_for_update()) is None:
            raise AccountPartyError('Case not found.', 404)
        state = account_parties(session, case_id=case_id)
        if state['revision'] != request.expected_revision:
            raise AccountPartyError('Account links changed. Reload before saving this decision.', 409)
        accounts = {a['id']: a for a in state['accounts']}
        if any(str(id) not in accounts for id in request.account_ids):
            raise AccountPartyError('Selected account not found in this case.', 404)
        party = None
        if request.party_id is not None:
            party = next((p for p in state['parties'] if p['id'] == str(request.party_id)), None)
            if party is None:
                raise AccountPartyError('Selected party not found in this case.', 404)
        elif request.new_party_name is not None:
            party = dict(id=str(uuid4()), name=request.new_party_name.strip())
        events = []
        for id in sorted(request.account_ids, key=str):
            before = accounts[str(id)]['party']
            if before == party:
                continue
            account = session.scalar(select(FinancialAccount).where(
                FinancialAccount.id == id, FinancialAccount.case_id == case_id).with_for_update())
            if account is None:
                raise AccountPartyError('Selected account is no longer available.', 409)
            event = record(session, case_id=case_id, subject=account,
                subject_type=AdjudicationSubject.account,
                decision=AdjudicationDecision.set_account_party, actor=actor,
                reason=request.reason.strip(), before={'party': before}, after={'party': party})
            events.append(str(event.id))
        if not events:
            raise AccountPartyError('The selected account links are unchanged.')
        session.flush()
        result = account_parties(session, case_id=case_id)
        result.update(applied=True, event_ids=events)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
