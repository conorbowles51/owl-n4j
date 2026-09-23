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
from postgres.models.financial import FinancialAccount, FinancialSourceDocument, AdjudicationEvent
from postgres.models.enums import AdjudicationSubject, AdjudicationDecision
from services.financial.decisions import record
from services.financial.account_relationships import AccountRelationshipInput, validate_relationship_sources


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
    relationship: AccountRelationshipInput | None = None

    @model_validator(mode='after')
    def valid_choice(self):
        if len(set(self.account_ids)) != len(self.account_ids):
            raise ValueError('Choose each account once.')
        if sum((self.party_id is not None, self.new_party_name is not None, self.clear)) != 1:
            raise ValueError('Choose an existing party, name a new party, or clear the link.')
        if not self.reason.strip() or self.new_party_name is not None and not self.new_party_name.strip():
            raise ValueError('A nonblank name and reason are required.')
        if self.clear and self.relationship and not self.relationship.id:
            raise ValueError('Choose the relationship to remove.')
        if self.relationship and self.relationship.id and len(self.account_ids) != 1:
            raise ValueError('Edit or remove one existing relationship at a time.')
        return self


def _account_party_state(session, *, case_id):
    accounts = list(session.scalars(select(FinancialAccount).where(
        FinancialAccount.case_id == case_id).order_by(FinancialAccount.id).limit(1001)))
    if len(accounts) > 1000:
        raise AccountPartyError('More than 1,000 accounts; no incomplete party directory was returned.')
    events = list(session.scalars(select(AdjudicationEvent).where(
        AdjudicationEvent.case_id == case_id,
        AdjudicationEvent.subject_type == 'account',
        AdjudicationEvent.decision == 'set_account_party').order_by(
            AdjudicationEvent.subject_id, AdjudicationEvent.subject_sequence).limit(5001)))
    if len(events) > 5000:
        raise AccountPartyError('More than 5,000 party decisions; no incomplete history was returned.')
    ids = {str(account.id) for account in accounts}
    assignments, relationships, parties, history = {}, {}, {}, []
    for event in events:
        account_id = str(event.subject_id)
        if account_id not in ids:
            raise AccountPartyError('Party history refers to an unavailable account.', 409)
        if (not isinstance(event.before, dict) or not isinstance(event.after, dict)
                or set(event.before) not in ({'party'}, {'party', 'relationships'})
                or set(event.after) != set(event.before)):
            raise AccountPartyError('Account party history is malformed.', 409)
        if event.before['party'] != assignments.get(account_id):
            raise AccountPartyError('Account party history cannot be replayed consistently.', 409)
        if 'relationships' in event.before:
            if event.before['relationships'] != relationships.get(account_id, []):
                raise AccountPartyError('Account relationship history cannot be replayed consistently.', 409)
            links = event.after['relationships']
            if not isinstance(links, list) or len(links) > 100:
                raise AccountPartyError('Account relationship history is malformed.', 409)
            seen = set()
            for link in links:
                if not isinstance(link, dict) or set(link) != {'id', 'party', 'role', 'basis', 'sources', 'effective_from', 'effective_to'}:
                    raise AccountPartyError('Account relationship history is malformed.', 409)
                try:
                    details = AccountRelationshipInput.model_validate({k: v for k, v in link.items() if k != 'party'})
                    UUID(link['party']['id'])
                    if set(link['party']) != {'id', 'name'} or not isinstance(link['party']['name'], str) or not link['party']['name'].strip():
                        raise ValueError('Missing party identity')
                    if not details.id or str(details.id) in seen:
                        raise ValueError('Repeated relationship identity')
                    seen.add(str(details.id))
                except (ValueError, TypeError, KeyError, AttributeError) as exc:
                    raise AccountPartyError('Account relationship history is malformed.', 409) from exc
                identity = link['party']
                if identity['id'] in parties and parties[identity['id']] != identity:
                    raise AccountPartyError('Saved party names conflict.', 409)
                parties[identity['id']] = identity
            relationships[account_id] = links
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
    result = dict(case_id=str(case_id), accounts=[dict(id=str(a.id), canonical_id=(a.metadata_ or {}).get('canonical_account_id') or str(a.id),
        holder_as_recorded=a.holder_name, identifier_as_printed=a.identifier_as_printed,
        institution=a.institution_name, currency=a.currency,
        party=assignments.get(str(a.id)), relationships=relationships.get(str(a.id), []),
        holder_parties=list({link['party']['id']: link['party'] for link in relationships.get(str(a.id), [])
            if link['role'] == 'holder'}.values())) for a in accounts],
        parties=sorted(parties.values(), key=lambda p: (p['name'].casefold(), p['id'])),
        history=history, applied=False,
        limitation='Reviewed holder, control, signatory and analysis relationships are separate. Only holder relationships support common ownership, within their recorded dates. Legacy party links are analysis groups. Original source accounts and proof classes remain unchanged.')
    grouped = {}
    for item in result['accounts']:
        grouped.setdefault(item['canonical_id'], []).append(item['id'])
    indexed = {item['id']: item for item in result['accounts']}
    for item in result['accounts']:
        item['alias_ids'] = grouped[item['canonical_id']]
        item['effective_relationships'] = list({link['id']: link
            for member in item['alias_ids'] for link in indexed[member]['relationships']}.values())
        item['effective_holder_parties'] = list({link['party']['id']: link['party']
            for link in item['effective_relationships'] if link['role'] == 'holder'}.values())
    result['revision'] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return result


def account_parties(session, *, case_id):
    """One case-scoped party choice list, including identities created on payments."""
    from services.financial.counterparty_parties import payment_party_choices
    result = _account_party_state(session, case_id=case_id)
    parties = payment_party_choices(session, case_id=case_id, known_parties=result['parties'])
    result['parties'] = sorted(parties.values(), key=lambda p: (p['name'].casefold(), p['id']))
    from services.financial.account_ownership import ownership_suggestions
    result['ownership_review'] = ownership_suggestions(session, case_id=case_id, accounts=result['accounts'])
    result['source_choices'] = []
    for document in session.scalars(select(FinancialSourceDocument).where(
            FinancialSourceDocument.case_id == case_id, FinancialSourceDocument.status == 'admitted')
            .order_by(FinancialSourceDocument.id)):
        metadata = document.metadata_ or {}
        original = metadata.get('statement_import_original') or {}
        pages = sorted({s['page_number'] for s in original.get('sources', []) if isinstance(s.get('page_number'), int)})
        if pages:
            result['source_choices'].append(dict(source_document_id=str(document.id),
                evidence_file_id=str(document.evidence_file_id) if document.evidence_file_id else None,
                account_id=metadata.get('statement_account_id'), pages=pages,
                label=' · '.join(str(v) for v in ((original.get('metadata') or {}).get('holder'),
                    (original.get('metadata') or {}).get('account_number'),
                    (original.get('metadata') or {}).get('period')) if v) or 'Statement ' + str(document.id)[:8]))
    result.pop('revision')
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
            if any(' '.join(p['name'].split()).casefold() == ' '.join(request.new_party_name.split()).casefold() for p in state['parties']):
                raise AccountPartyError('That person or business already exists. Choose the existing identity to link these accounts.')
            party = dict(id=str(uuid4()), name=request.new_party_name.strip())
        if request.relationship and not request.clear:
            validate_relationship_sources(session, case_id, request.relationship)
        events = []
        for id in sorted(request.account_ids, key=str):
            before = accounts[str(id)]['party']
            links = accounts[str(id)]['relationships']
            if request.relationship:
                details = request.relationship
                current = next((link for link in links if link['id'] == str(details.id)), None) if details.id else None
                if details.id and current is None:
                    raise AccountPartyError('The account relationship changed or is no longer available.', 409)
                updated = [link for link in links if current is None or link['id'] != current['id']]
                if not request.clear:
                    saved = {**details.model_dump(mode='json'), 'id': str(details.id or uuid4()), 'party': party}
                    content = lambda link: {k: v for k, v in link.items() if k != 'id'}
                    if any(content(link) == content(saved) for link in links):
                        continue
                    if len(updated) >= 100:
                        raise AccountPartyError('An account may have at most 100 recorded relationships.')
                    updated.append(saved)
                before_value = {'party': before, 'relationships': links}
                after_value = {'party': before, 'relationships': updated}
            else:
                if before == party:
                    continue
                before_value, after_value = {'party': before}, {'party': party}
            account = session.scalar(select(FinancialAccount).where(
                FinancialAccount.id == id, FinancialAccount.case_id == case_id).with_for_update())
            if account is None:
                raise AccountPartyError('Selected account is no longer available.', 409)
            event = record(session, case_id=case_id, subject=account,
                subject_type=AdjudicationSubject.account,
                decision=AdjudicationDecision.set_account_party, actor=actor,
                reason=request.reason.strip(), before=before_value, after=after_value)
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
