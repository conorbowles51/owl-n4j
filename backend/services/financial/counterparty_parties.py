"""Investigator links for individual payment counterparties, preserving raw names."""
import hashlib
import json
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from postgres.models.case import Case
from postgres.models.financial import FinancialTransaction, AdjudicationEvent
from postgres.models.enums import AdjudicationSubject, AdjudicationDecision
from services.financial.decisions import record
from services.financial.account_parties import AccountPartyError, _account_party_state


class CounterpartyPartyRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_revision:str=Field(pattern=r'^[a-f0-9]{64}$')
    transaction_ids:list[UUID]=Field(min_length=1,max_length=100)
    party_id:UUID|None=None
    new_party_name:str|None=Field(default=None,min_length=1,max_length=255)
    clear:bool=Field(default=False,strict=True)
    reason:str=Field(min_length=1,max_length=4000)

    @model_validator(mode='after')
    def choice(self):
        if len(set(self.transaction_ids))!=len(self.transaction_ids):raise ValueError('Choose each reading once.')
        if sum((self.party_id is not None,self.new_party_name is not None,self.clear))!=1:raise ValueError('Choose an existing party, a new name, or clear links.')
        if not self.reason.strip() or self.new_party_name is not None and not self.new_party_name.strip():raise ValueError('A nonblank name and reason are required.')
        return self


def _identity_state(rows, events, known_parties=()):
    indexed={str(r.id):r for r in rows}
    parties={p["id"]:p for p in known_parties}
    assignments={};history=[]
    for event in events:
        key=str(event.subject_id)
        if key not in indexed or not isinstance(event.before,dict) or not isinstance(event.after,dict) or set(event.before)!={'party','override'} or set(event.after)!={'party','override'}:raise AccountPartyError('Counterparty history is malformed.',409)
        if event.before['party']!=assignments.get(key) or event.before['override'] is not (key in assignments) or event.after['override'] is not True:raise AccountPartyError('Counterparty history cannot be replayed.',409)
        party=event.after['party']
        if party is not None:
            if not isinstance(party,dict) or set(party)!={'id','name'} or not isinstance(party['name'],str) or not party['name'].strip():raise AccountPartyError('Counterparty party identity is malformed.',409)
            try:UUID(party['id'])
            except (ValueError,TypeError,AttributeError) as exc:raise AccountPartyError('Counterparty party identity is malformed.',409) from exc
            if party['id'] in parties and parties[party['id']]!=party:raise AccountPartyError('Party names conflict.',409)
            parties[party['id']]=party
        assignments[key]=party
        history.append(dict(id=str(event.id),transaction_id=key,sequence=event.subject_sequence,before=event.before,after=event.after,reason=event.reason,actor=event.actor_email,recorded_at=event.created_at.isoformat()))
    parents={}
    for row in rows:
        if row.superseded_by_id:
            child=str(row.superseded_by_id)
            if child in parents:raise AccountPartyError('Correction ancestry is ambiguous.',409)
            parents[child]=str(row.id)
    def inherited(key):
        seen=set();cursor=key
        while cursor not in assignments and cursor in parents:
            if cursor in seen:raise AccountPartyError('Correction ancestry is circular.',409)
            seen.add(cursor);parent=parents[cursor]
            a,b=indexed.get(cursor),indexed.get(parent)
            if a is None or b is None or (a.account_id,a.currency,a.counterparty_raw)!=(b.account_id,b.currency,b.counterparty_raw):return None,None
            cursor=parent
        return assignments.get(cursor),cursor if cursor in assignments else None
    readings=[]
    for row in rows:
        if row.superseded_by_id is not None:continue
        party,origin=inherited(str(row.id))
        readings.append(dict(transaction_id=str(row.id),ref_id=row.ref_id,account_id=str(row.account_id),currency=row.currency,counterparty_raw=row.counterparty_raw,description=row.description,amount_minor=str(row.amount_minor),direction=row.direction.value if hasattr(row.direction,'value') else row.direction,party=party,decision_transaction_id=origin))
    return readings, parties, history


def payment_party_choices(session, *, case_id, known_parties=()):
    """Replay only payment subjects with identity decisions, not every case row."""
    events=list(session.scalars(select(AdjudicationEvent).where(
        AdjudicationEvent.case_id==case_id,
        AdjudicationEvent.subject_type=='transaction',
        AdjudicationEvent.decision=='set_counterparty_party').order_by(
            AdjudicationEvent.subject_id,AdjudicationEvent.subject_sequence).limit(10001)))
    if len(events)>10000:
        raise AccountPartyError('More than10000counterparty decisions; no partial party directory returned.')
    subjects={event.subject_id for event in events}
    rows=list(session.scalars(select(FinancialTransaction).where(
        FinancialTransaction.case_id==case_id,
        FinancialTransaction.id.in_(subjects)))) if subjects else []
    _, parties, _ = _identity_state(rows,events,known_parties)
    return parties


def counterparty_parties(session, *, case_id):
    rows=list(session.scalars(select(FinancialTransaction).where(FinancialTransaction.case_id==case_id).order_by(FinancialTransaction.id).limit(5001).execution_options(populate_existing=True)))
    if len(rows)>5000:raise AccountPartyError('More than5000historical readings; no partial counterparty directory returned.')
    events=list(session.scalars(select(AdjudicationEvent).where(AdjudicationEvent.case_id==case_id,AdjudicationEvent.subject_type=='transaction',AdjudicationEvent.decision=='set_counterparty_party').order_by(AdjudicationEvent.subject_id,AdjudicationEvent.subject_sequence).limit(10001)))
    if len(events)>10000:raise AccountPartyError('More than10000counterparty decisions; no partial history returned.')
    readings,parties,history=_identity_state(rows,events,_account_party_state(session,case_id=case_id)["parties"])
    result=dict(case_id=str(case_id),readings=readings,parties=sorted(parties.values(),key=lambda p:(p['name'].casefold(),p['id'])),history=history,applied=False,
      limitation='Investigator identity links for selected readings only. Raw source names, amounts, eligibility and proof classes are unchanged. Equal names and future imports are not linked automatically. Corrections inherit a link only while account, currency and raw name remain identical; direct decisions override inheritance.')
    result['revision']=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return result


def set_counterparty_party(session, *, case_id, request:CounterpartyPartyRequest, actor):
    try:
        if session.scalar(select(Case.id).where(Case.id==case_id).with_for_update()) is None:raise AccountPartyError('Case not found.',404)
        locked={str(r.id):r for r in session.scalars(select(FinancialTransaction).where(FinancialTransaction.case_id==case_id,FinancialTransaction.id.in_(request.transaction_ids)).order_by(FinancialTransaction.id).with_for_update().execution_options(populate_existing=True))}
        if len(locked)!=len(request.transaction_ids):raise AccountPartyError('Selected reading not found in this case.',404)
        state=counterparty_parties(session,case_id=case_id)
        if state['revision']!=request.expected_revision:raise AccountPartyError('Counterparty links or source readings changed. Reload before saving.',409)
        readings={r['transaction_id']:r for r in state['readings']}
        if any(str(id) not in readings for id in request.transaction_ids):raise AccountPartyError('Current reading not found in this case.',404)
        party=None
        if request.party_id is not None:
            party=next((p for p in state['parties'] if p['id']==str(request.party_id)),None)
            if party is None:raise AccountPartyError('Party not found in this case.',404)
        elif request.new_party_name is not None:party=dict(id=str(uuid4()),name=request.new_party_name.strip())
        event_ids=[]
        for id in sorted(request.transaction_ids,key=str):
            selected=readings[str(id)]
            if selected['party']==party:continue
            row=locked[str(id)]
            if row is None or row.superseded_by_id is not None:raise AccountPartyError('Reading changed during identity review.',409)
            direct=[h for h in state['history'] if h['transaction_id']==str(id)]
            before=direct[-1]['after']['party'] if direct else None
            event=record(session,case_id=case_id,subject=row,subject_type=AdjudicationSubject.transaction,decision=AdjudicationDecision.set_counterparty_party,actor=actor,reason=request.reason.strip(),before={'party':before,'override':bool(direct)},after={'party':party,'override':True})
            event_ids.append(str(event.id))
        if not event_ids:raise AccountPartyError('Selected links are unchanged.')
        session.flush();result=counterparty_parties(session,case_id=case_id);result.update(applied=True,event_ids=event_ids);session.commit();return result
    except Exception:
        session.rollback();raise


def counterparty_party_analysis(export, *, population='working'):
    from types import SimpleNamespace
    from datetime import datetime
    from services.financial.working_totals import working_totals_from_readings
    from services.financial.ledger_summary import LedgerSummaryError
    if population not in ('working','verified'):raise LedgerSummaryError('Choose working or verified readings.')
    document=json.loads(export.snapshot.content);ledger=document['ledger']
    if not document.get('export_ready') or not ledger.get('history_captured') or not ledger.get('available'):raise LedgerSummaryError('Identity analysis requires a complete captured ledger and history.')
    if len(ledger['readings'])>5000:raise LedgerSummaryError('More than5000historical readings; narrow the analysis scope.')
    rows=[SimpleNamespace(id=r['row']['key'],**{k:r['row'][k] for k in ('ref_id','account_id','currency','counterparty_raw','description','amount_minor','direction','superseded_by_id')}) for r in ledger['readings']]
    events=[SimpleNamespace(id=e['id'],subject_id=e['subject_id'],subject_sequence=e['subject_sequence'],before=e['before'],after=e['after'],reason=e['reason'],actor_email=e['actor_email'],created_at=datetime.fromisoformat(e['recorded_at'])) for e in document['decisions'] if e['decision']=='set_counterparty_party' and e['subject_type']=='transaction']
    effective,_,_=_identity_state(rows,events)
    identities={r['transaction_id']:r for r in effective}
    totals=working_totals_from_readings(ledger) if population=='working' else ledger
    groups={}
    for reading in ledger['readings']:
        if not (reading['exclusion_reason'] in (None,'proof_class_not_included') if population=='working' else reading['included']):continue
        row=reading['row'];party=identities[row['key']]['party'];raw=row['counterparty_raw']
        identity=['party',party['id']] if party else ['raw',raw]
        key=json.dumps([identity,row['currency']],ensure_ascii=False,separators=(',',':'))
        group=groups.setdefault(key,dict(group_id=key,label='Reviewed party: '+party['name'] if party else raw,currency=row['currency'],rows=0,credits_minor=0,debits_minor=0,transaction_ids=[],source_document_ids=set(),raw_labels=set(),party=party))
        group['rows']+=1;group[row['direction']+'s_minor']+=int(row['amount_minor']);group['transaction_ids'].append(row['key']);group['source_document_ids'].add(reading['source']['id']);group['raw_labels'].add(raw)
    for group in groups.values():
        group['net_minor']=str(group['credits_minor']-group['debits_minor'])
        for field in ('credits_minor','debits_minor'):group[field]=str(group[field])
        group['source_document_ids']=sorted(group['source_document_ids']);group['raw_labels']=sorted(group['raw_labels'],key=lambda s:(s is not None,s or ''))
    return dict(case_id=ledger['case_id'],account_id=ledger['account_id'],start_date=ledger['start_date'],end_date=ledger['end_date'],population=population,
        available=True,reason=None,applied=False,label_basis='investigator_payment_identity',included_rows=totals['included_rows'],excluded_rows=totals['excluded_rows'],currencies=totals['currencies'],counterparties=[groups[k] for k in sorted(groups)],
        snapshot_sha256=export.snapshot.sha256,snapshot_json=export.snapshot.content,
        limitation=totals['limitation'],counterparty_limitation='Only explicitly linked readings use reviewed party identities. Unlinked source labels remain verbatim and unresolved. Original labels and identity decisions are captured. Grouping does not confirm payment direction roles, merge ledger rows, net internal transfers or promote proof classes.')
