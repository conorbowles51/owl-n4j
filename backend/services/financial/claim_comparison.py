"""Conditional comparison of an investigator-transcribed claim and ledger rows."""
import hashlib
import json
from datetime import date
from uuid import UUID, uuid5, NAMESPACE_URL
from pydantic import BaseModel, ConfigDict, Field
from postgres.models.enums import ProofClass, TransactionDirection
from services.financial.correlation import Claim, AmountRange, DateRange, Materiality, LedgerEntry, Coverage, AccountCoverage, correlate
from services.financial.money import Money
from services.financial.ledger_timeline import ledger_timeline
from services.financial.ledger_tracing import _exact_json
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.ledger_snapshot import MAX_EXPORT_BYTES

class ClaimComparisonInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    account_id: UUID
    source_file_id: UUID
    quote: str = Field(min_length=1,max_length=8192)
    source_location: str = Field(min_length=1,max_length=1024)
    speaker: str | None = Field(default=None,max_length=512)
    payer: str | None = Field(default=None,max_length=512)
    payee: str | None = Field(default=None,max_length=512)
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    amount_low_minor: str = Field(pattern=r'^(0|[1-9][0-9]{0,18})$')
    amount_high_minor: str = Field(pattern=r'^(0|[1-9][0-9]{0,18})$')
    earliest: date
    latest: date
    account_holder: str = Field(min_length=1,max_length=512)
    interpretation_basis: str = Field(min_length=1,max_length=4096)
    materiality_basis_points: int = Field(default=0,ge=0,le=10000,strict=True)
    materiality_floor_major_units: int = Field(default=0,ge=0,le=1000000,strict=True)
    population: str = Field(default='verified',pattern=r'^(verified|working)$')


def compare_ledger_claim(export, request, source):
    request=ClaimComparisonInput.model_validate(request)
    if any(not value.strip() for value in (request.quote,request.source_location,request.account_holder,request.interpretation_basis)):
        raise LedgerSummaryError('Quote, source location, holder assumption and interpretation basis must be explicit.')
    scope=ledger_timeline(export,population=request.population)
    if scope['account_id']!=str(request.account_id) or scope['start_date'] is not None or scope['end_date'] is not None:
        raise LedgerSummaryError('Claim comparison needs the complete captured account, without ordering-date truncation.')
    if source['case_id']!=scope['case_id'] or source['id']!=str(request.source_file_id):
        raise LedgerSummaryError('The claim source must belong to this case.')
    claim=Claim(claim_id=uuid5(NAMESPACE_URL,json.dumps(request.model_dump(mode='json'),sort_keys=True)),
        amounts=AmountRange(Money(int(request.amount_low_minor),request.currency),Money(int(request.amount_high_minor),request.currency)),
        dates=DateRange(request.earliest,request.latest),quote=request.quote,source_document_id=request.source_file_id,
        payer=request.payer,payee=request.payee,speaker=request.speaker,locator=request.source_location)
    entries=[];unknown_dates=[]
    for row in scope['rows']:
        if row['chronology_basis'] in ('ordering_date','statement_end_ordering_only'):
            unknown_dates.append(row['key']);continue
        entries.append(LedgerEntry(transaction_id=UUID(row['key']),account_id=request.account_id,
            ordering_date=date.fromisoformat(row['chronology_date']),amount=Money(int(row['amount_minor']),row['currency']),
            direction=TransactionDirection(row['direction']),proof_class=ProofClass(row['proof_class']),
            holder=request.account_holder,counterparty=row.get('counterparty_raw'),description=row['description'],reconciled=False))
    # Printed bounds alone do not certify extraction or completeness. No user-entered
    # checkbox may turn absence into contradiction. Coverage remains unknown here.
    result=correlate(claim,entries,coverage=Coverage([AccountCoverage(request.account_id,holder=request.account_holder)]),
        materiality=Materiality(request.materiality_basis_points,request.materiality_floor_major_units))
    comparison=_exact_json(result)
    comparison['notes']=[('Statement reconciliation was not independently assessed in this comparison.' if note == 'corroborated only by rows whose statement does not reconcile' else note) for note in comparison['notes']]
    for candidate in comparison['candidates']:
        candidate['entry']['reconciled']=None
        candidate['entry']['chronology_basis']=next(row['chronology_basis'] for row in scope['rows'] if row['key']==candidate['entry']['transaction_id'])
    document=dict(schema='loupe.financial.claim_comparison/1',case_id=scope['case_id'],applied=False,claim_proof_class='p4',
        inputs=request.model_dump(mode='json'),claim_source=source,comparison=comparison,date_unavailable_ids=unknown_dates,
        ledger_snapshot=json.loads(export.snapshot.content),ledger_manifest=json.loads(export.manifest),snapshot_sha256=scope['snapshot_sha256'],
        limitations=['Investigator-transcribed quotation, amount/date ranges and account-holder interpretation. The quotation has not been machine-verified against the source.',
            'Rule output is a proposal, not a determination. Name comparison does not resolve party identity; missing counterparty names remain untested.',
            'Chronology uses value date first, with labelled transaction/posted/effective fallbacks. Unknown statement-end-only dates cannot establish a match.',
            'This comparison does not certify complete account records. Absence cannot produce a contradiction; inspect requested-date coverage and missing evidence.',
            'Working results may include P3 readings. Claims remain P4, source classes are unchanged, and neither a match nor an investigator decision promotes them.'])
    content=json.dumps(document,sort_keys=True,separators=(',',':'),ensure_ascii=False);encoded=content.encode()
    if len(encoded)>MAX_EXPORT_BYTES:raise LedgerSummaryError('Claim comparison exceeds 16 MiB; no partial result was returned.')
    return dict(case_id=scope['case_id'],applied=False,scenario_json=content,scenario_sha256=hashlib.sha256(encoded).hexdigest(),scenario_byte_count=len(encoded))
