"""Reversible account equivalence; original accounts and postings stay intact."""
import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialAccount, FinancialTransaction, FinancialStatementPeriod, FinancialSourceDocument, AdjudicationEvent
from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
from services.financial.account_parties import AccountPartyError
from services.financial.decisions import record


def bank_key(value):
    token = ' '.join((value or '').split()).casefold()
    return {'bbva mexico': 'bbva', 'bbva méxico': 'bbva', 'bbva bancomer': 'bbva',
            'banco santander mexico': 'santander', 'banco santander méxico': 'santander'}.get(token, token)


def canonical_map(session, case_id):
    accounts = list(session.scalars(select(FinancialAccount).where(FinancialAccount.case_id == case_id)))
    direct = {a.id: UUID((a.metadata_ or {}).get('canonical_account_id') or str(a.id)) for a in accounts}
    resolved = {}
    for key in direct:
        cursor, seen = key, set()
        while direct.get(cursor) != cursor:
            if cursor not in direct or cursor in seen:
                raise AccountPartyError('Account consolidation history needs review. No incomplete account scope was returned.', 409)
            seen.add(cursor); cursor = direct[cursor]
        resolved[key] = cursor
    return resolved


def expand_account_ids(session, case_id, ids):
    mapping = canonical_map(session, case_id)
    roots = {mapping.get(UUID(str(id)), UUID(str(id))) for id in ids}
    return sorted({key for key, root in mapping.items() if root in roots}, key=str)


class ConsolidationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    account_ids: list[UUID] = Field(min_length=2, max_length=100)
    retained_id: UUID
    reason: str = Field(min_length=1, max_length=4000)


class UndoConsolidationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    merge_id: UUID
    reason: str = Field(min_length=1, max_length=4000)


def consolidation_state(session, case_id):
    from services.financial.account_identity import identity_state
    state = identity_state(session, case_id)
    mapping = canonical_map(session, case_id)
    periods = list(session.scalars(select(FinancialStatementPeriod).where(FinancialStatementPeriod.case_id == case_id)))
    counts = {str(id): count for id, count in session.execute(
        select(FinancialTransaction.account_id, func.count()).where(
            FinancialTransaction.case_id == case_id, FinancialTransaction.superseded_by_id.is_(None))
        .group_by(FinancialTransaction.account_id))}
    for account in state['accounts']:
        account['canonical_id'] = str(mapping[UUID(account['id'])])
        account['payment_count'] = counts.get(account['id'], 0)
        account['periods'] = [dict(id=str(p.id), source_document_id=str(p.source_document_id),
            start=str(p.period_start) if p.period_start else None, end=str(p.period_end) if p.period_end else None,
            currency=p.currency) for p in periods if str(p.account_id) == account['id']]
    events = list(session.scalars(select(AdjudicationEvent).where(AdjudicationEvent.case_id == case_id,
        AdjudicationEvent.decision == 'set_account_identity').order_by(AdjudicationEvent.created_at, AdjudicationEvent.id)))
    state['merges'] = [dict(**e.after['consolidation'], event_id=str(e.id), actor=e.actor_email, reason=e.reason,
        recorded_at=e.created_at.isoformat()) for e in events if isinstance(e.after, dict) and e.after.get('consolidation')]
    state['source_choices'] = []
    filenames = dict(session.execute(select(EvidenceFile.id, EvidenceFile.original_filename).where(EvidenceFile.case_id == case_id)).all())
    for document in session.scalars(select(FinancialSourceDocument).where(FinancialSourceDocument.case_id == case_id)):
        metadata = document.metadata_ or {}
        original = metadata.get('statement_import_original') or {}
        source_accounts = {str(p.account_id) for p in periods if p.source_document_id == document.id}
        if metadata.get('statement_account_id'):
            source_accounts.add(str(metadata['statement_account_id']))
        for account_id in sorted(source_accounts):
            state['source_choices'].append(dict(source_document_id=str(document.id),
                evidence_file_id=str(document.evidence_file_id) if document.evidence_file_id else None,
                account_id=account_id, pages=sorted({s['page_number'] for s in original.get('sources', []) if s.get('page_number')}),
                label=filenames.get(document.evidence_file_id) or 'Statement ' + str(document.id)[:8]))
    state['revision'] = hashlib.sha256(json.dumps(state, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return state


def preview_consolidation(session, *, case_id, request):
    state = consolidation_state(session, case_id)
    if state['revision'] != request.expected_revision:
        raise AccountPartyError('Accounts changed. Reload and review the same selection before saving.', 409)
    if len(set(request.account_ids)) != len(request.account_ids) or request.retained_id not in request.account_ids or not request.reason.strip():
        raise AccountPartyError('Choose distinct accounts, a retained identity and a reason.')
    indexed = {a['id']: a for a in state['accounts']}
    if any(str(id) not in indexed for id in request.account_ids):
        raise AccountPartyError('Selected account not found in this case.', 404)
    members = expand_account_ids(session, case_id, request.account_ids)
    chosen = [indexed[str(id)] for id in members]
    if len({a['canonical_id'] for a in chosen}) == 1:
        raise AccountPartyError('These records already use the same reviewed account. No additional merge is needed.')
    banks = {bank_key(a['institution']) for a in chosen if a['institution']}
    if len(banks) > 1:
        raise AccountPartyError('These accounts name different banks. Correct incorrect statement details, or link their common owner instead.')
    identifiers = {}
    for item in chosen:
        for ident in item['identity_review'].get('identifiers', []):
            if ident['kind'] in ('clabe', 'iban', 'account_number'):
                identifiers.setdefault(ident['kind'], set()).add(re.sub(r'[^A-Z0-9]', '', ident['value'].upper()))
        # Full printed numbers are strong evidence unless explicitly provisional.
        row = session.get(FinancialAccount, UUID(item['id']))
        if row.identifier_as_printed and not (row.metadata_ or {}).get('identity_provisional') and re.fullmatch(r'[A-Za-z0-9 -]{6,}', row.identifier_as_printed) and re.search(r'\d', row.identifier_as_printed):
            identifiers.setdefault('account_number', set()).add(re.sub(r'[^A-Z0-9]', '', row.identifier_as_printed.upper()))
    if any(len(values) > 1 for values in identifiers.values()):
        raise AccountPartyError('The selected accounts have conflicting complete identifiers. Correct the statement assignments first; common ownership does not make them the same account.')
    currencies = {item['currency'] for item in chosen} - {None}
    if len(currencies) > 1:
        raise AccountPartyError('These are different currency compartments. Keep their balances separate and link their common owner instead.')
    types = {session.get(FinancialAccount, id).account_type for id in members} - {None}
    if len(types) > 1:
        raise AccountPartyError('Different product types must remain separate accounts.')
    return dict(case_id=str(case_id), revision=state['revision'], retained_id=str(request.retained_id), accounts=chosen,
        payment_count=sum(a['payment_count'] for a in chosen),
        source_choices=[source for source in state['source_choices'] if source['account_id'] in {a['id'] for a in chosen}],
        explanation='These account records will appear as one reviewed account. Original statements, payments, currencies and citations remain unchanged. Overlapping payments are not removed. Review any earlier transfer interpretation between these records.')


def save_consolidation(session, *, case_id, request, actor):
    try:
        if session.scalar(select(Case.id).where(Case.id == case_id).with_for_update()) is None:
            raise AccountPartyError('Case not found.', 404)
        state = consolidation_state(session, case_id)
        fingerprint = hashlib.sha256(request.model_dump_json(exclude={'expected_revision'}).encode()).hexdigest()
        previous = next((m for m in state['merges'] if m['request_id'] == str(request.request_id)), None)
        if previous:
            if previous['fingerprint'] != fingerprint:
                raise AccountPartyError('This request already saved different account changes.', 409)
            session.commit(); return {**state, 'applied': False}
        preview = preview_consolidation(session, case_id=case_id, request=request)
        before = {}
        for item in preview['accounts']:
            row = session.get(FinancialAccount, UUID(item['id']))
            before[item['id']] = (row.metadata_ or {}).get('canonical_account_id')
        merge = dict(id=str(uuid4()), request_id=str(request.request_id), fingerprint=fingerprint,
            retained_id=str(request.retained_id), previous=before, account_ids=list(before), undone=False)
        retained = session.get(FinancialAccount, request.retained_id)
        record(session, case_id=case_id, subject=retained, subject_type=AdjudicationSubject.account,
            decision=AdjudicationDecision.set_account_identity, actor=actor, reason=request.reason.strip(),
            before=dict(consolidation=None), after=dict(consolidation=merge))
        for id in before:
            row = session.get(FinancialAccount, UUID(id))
            row.metadata_ = {**(row.metadata_ or {}), 'canonical_account_id': str(request.retained_id),
                             'consolidation_changed_at': datetime.now(timezone.utc).isoformat()}
        session.flush(); result = consolidation_state(session, case_id); session.commit()
        return {**result, 'applied': True}
    except Exception:
        session.rollback(); raise


def undo_consolidation(session, *, case_id, request, actor):
    try:
        session.scalar(select(Case.id).where(Case.id == case_id).with_for_update())
        state = consolidation_state(session, case_id)
        merge = next((m for m in state['merges'] if m['id'] == str(request.merge_id) and not m['undone']), None)
        undone = next((m for m in state['merges'] if m['id'] == str(request.merge_id) and m['undone']), None)
        if undone and undone['request_id'] == str(request.request_id):
            session.commit(); return {**state, 'applied': False}
        if state['revision'] != request.expected_revision or not merge or undone:
            raise AccountPartyError('The account history changed. Reload before undoing this merge.', 409)
        if not request.reason.strip(): raise AccountPartyError('Record why this merge should be undone.')
        members = expand_account_ids(session, case_id, [UUID(merge['retained_id'])])
        if {str(id) for id in members} != set(merge['account_ids']):
            raise AccountPartyError('A later merge depends on this one. Undo the later merge first.', 409)
        retained = session.get(FinancialAccount, UUID(merge['retained_id']))
        audit = {k:v for k,v in merge.items() if k not in ('event_id','actor','reason','recorded_at')}
        record(session, case_id=case_id, subject=retained, subject_type=AdjudicationSubject.account,
            decision=AdjudicationDecision.set_account_identity, actor=actor, reason=request.reason.strip(),
            before=dict(consolidation=audit), after=dict(consolidation={**audit, 'undone': True, 'request_id':str(request.request_id)}))
        for id, prior in merge['previous'].items():
            row = session.get(FinancialAccount, UUID(id))
            row.metadata_ = {**(row.metadata_ or {}), 'canonical_account_id': prior}
        session.flush(); result = consolidation_state(session, case_id); session.commit()
        return {**result, 'applied': True}
    except Exception:
        session.rollback(); raise
