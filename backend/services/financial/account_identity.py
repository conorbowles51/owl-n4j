"""Reviewed typed identifiers. Aliases identify accounts; holder links identify people.

Never use a customer, contract or holder tax identifier to merge bank accounts.
Referenced accounts deliberately have no imported period, balance or posting.
"""
import hashlib
import json
import re
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from postgres.models.case import Case
from postgres.models.financial import FinancialAccount, AdjudicationEvent
from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
from services.financial.account_parties import AccountPartyError, _account_party_state
from services.financial.account_relationships import AccountRelationshipInput, validate_relationship_sources
from services.financial.decisions import record
from services.financial.money import get_currency, MoneyError


class Identifier(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['account_number', 'clabe', 'iban', 'customer_number', 'contract_number', 'holder_tax_id']
    value: str = Field(min_length=1, max_length=128)

    @model_validator(mode='after')
    def valid_identifier(self):
        token = compact(self.value)
        if not token or '*' in token or '•' in token:
            raise ValueError('Use a complete identifier; masked references remain investigation leads.')
        if self.kind == 'clabe' and not re.fullmatch(r'\d{18}', token):
            raise ValueError('A CLABE must contain 18 digits. Preserve leading zeros.')
        if self.kind == 'iban' and not re.fullmatch(r'[A-Z]{2}\d{2}[A-Z0-9]{11,30}', token):
            raise ValueError('Enter a complete IBAN.')
        return self


class EntityLink(BaseModel):
    model_config = ConfigDict(extra='forbid')
    party_id: UUID
    entity_key: str = Field(min_length=1, max_length=255)


class ReferencedDetails(BaseModel):
    model_config = ConfigDict(extra='forbid')
    institution: str = Field(min_length=1, max_length=255)
    holder: str | None = Field(default=None, max_length=255)
    currency: str = Field(min_length=3, max_length=3)


class IdentityRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    account_id: UUID
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    identifiers: list[Identifier] = Field(default_factory=list, max_length=30)
    entity_links: list[EntityLink] = Field(default_factory=list, max_length=20)
    reference: ReferencedDetails | None = None
    basis: AccountRelationshipInput
    reason: str = Field(min_length=1, max_length=4000)

    @model_validator(mode='after')
    def coherent(self):
        if not self.reason.strip() or self.basis.id or self.basis.effective_from or self.basis.effective_to:
            raise ValueError('Explain the account identity decision. Ownership and effective dates are reviewed separately.')
        if len({(p.kind, compact(p.value)) for p in self.identifiers}) != len(self.identifiers):
            raise ValueError('Enter each identifier once.')
        if len({p.party_id for p in self.entity_links}) != len(self.entity_links):
            raise ValueError('Connect each reviewed person or business to one case entity.')
        if self.reference and not any(p.kind in ('account_number', 'clabe', 'iban') for p in self.identifiers):
            raise ValueError('A referenced account requires an account number, CLABE or IBAN, not only a customer or tax identifier.')
        return self


def compact(value):
    return re.sub(r'[\s.\-]', '', value or '').upper()


def identity_state(session, case_id):
    state = _account_party_state(session, case_id=case_id)
    indexed = {str(a.id): a for a in session.scalars(select(FinancialAccount).where(FinancialAccount.case_id == case_id))}
    for account in state['accounts']:
        metadata = indexed[account['id']].metadata_ or {}
        account['identity_review'] = metadata.get('identity_review') or {}
        account['referenced_only'] = bool(metadata.get('referenced_only'))
    events = list(session.scalars(select(AdjudicationEvent).where(AdjudicationEvent.case_id == case_id,
        AdjudicationEvent.decision == 'set_account_identity').order_by(AdjudicationEvent.subject_id, AdjudicationEvent.subject_sequence)))
    state['identity_history'] = [dict(id=str(e.id), account_id=str(e.subject_id), sequence=e.subject_sequence,
        before=e.before, after=e.after, reason=e.reason, actor=e.actor_email, recorded_at=e.created_at.isoformat()) for e in events]
    state.pop('revision')
    state['revision'] = hashlib.sha256(json.dumps(state, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return state


def reviewed_identifiers(account):
    return ((account.metadata_ or {}).get('identity_review') or {}).get('identifiers') or []


def matches_identifier(account, kind, value):
    token = compact(value)
    allowed = {'iban': {'iban'}, 'clabe': {'clabe'}, 'account': {'account_number', 'clabe'}, 'account_number': {'account_number'}}.get(kind, set())
    # A printed statement's main account reference is not automatically a CLABE.
    original = account.iban if kind == 'iban' else account.identifier_as_printed if kind in ('account', 'account_number') else account.identifier_as_printed if kind == 'clabe' and re.fullmatch(r'\d{18}', compact(account.identifier_as_printed)) else None
    return bool(original and compact(original) == token) or any(p['kind'] in allowed and compact(p['value']) == token for p in reviewed_identifiers(account))


def save_identity(session, *, case_id, request, actor, entity_lookup=None):
    try:
        if session.scalar(select(Case.id).where(Case.id == case_id).with_for_update()) is None:
            raise AccountPartyError('Case not found.', 404)
        state = identity_state(session, case_id)
        account = session.get(FinancialAccount, request.account_id)
        if account and account.case_id != case_id:
            raise AccountPartyError('Account not found in this case.', 404)
        saved = dict(identifiers=[p.model_dump() for p in request.identifiers],
            entity_links=[p.model_dump(mode='json') for p in request.entity_links],
            basis=request.basis.model_dump(mode='json'), reference=request.reference.model_dump() if request.reference else None)
        previous = (account.metadata_ or {}).get('identity_review') if account else None
        if previous == saved:
            session.commit()
            return {**state, 'applied': False}
        if state['revision'] != request.expected_revision:
            raise AccountPartyError('Account identities changed. Reload and review your retained draft.', 409)
        validate_relationship_sources(session, case_id, request.basis)
        if request.reference:
            try:
                get_currency(request.reference.currency)
            except MoneyError as exc:
                raise AccountPartyError(str(exc)) from exc
            if account and not (account.metadata_ or {}).get('referenced_only'):
                raise AccountPartyError('Imported account details must be corrected beside their statement.')
        elif not account:
            raise AccountPartyError('Choose an imported account or enter referenced-account details.', 404)
        parties = {p['id'] for p in state['parties']}
        for link in request.entity_links:
            if str(link.party_id) not in parties or not entity_lookup or not entity_lookup(link.entity_key, str(case_id)):
                raise AccountPartyError('Choose an existing reviewed person/business and an entity in this case.')
            if link.entity_key.startswith(('financial-party:', 'financial-account:', 'ACC-')):
                raise AccountPartyError('Choose a separate case entity. Financial identities are already linked to their accounts.')
            for other in state['accounts']:
                if other['id'] == str(request.account_id): continue
                if any(p['party_id'] == str(link.party_id) and p['entity_key'] != link.entity_key for p in other['identity_review'].get('entity_links', [])):
                    raise AccountPartyError('This person or business already has a different case-entity link. Review that link first.', 409)
        if not account:
            first = next(p for p in request.identifiers if p.kind in ('account_number', 'clabe', 'iban'))
            account = FinancialAccount(id=request.account_id, case_id=case_id, identity_key='reference:' + str(request.account_id),
                account_type='bank', identifier_as_printed=first.value, identifier_normalised=compact(first.value), metadata_={'referenced_only': True})
            session.add(account); session.flush()
        if request.reference:
            account.holder_name = request.reference.holder
            account.institution_name = request.reference.institution
            account.currency = request.reference.currency
        record(session, case_id=case_id, subject=account, subject_type=AdjudicationSubject.account,
            decision=AdjudicationDecision.set_account_identity, actor=actor, reason=request.reason.strip(),
            before={'identity_review': previous}, after={'identity_review': saved})
        account.metadata_ = {**(account.metadata_ or {}), 'identity_review': saved}
        session.flush()
        result = identity_state(session, case_id)
        session.commit()
        return {**result, 'applied': True}
    except Exception:
        session.rollback()
        raise
