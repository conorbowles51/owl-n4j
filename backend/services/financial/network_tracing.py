"""Conditional tracing through explicitly selected equal-value transfers.

Forward chronology is the default. Explicit backward timing is restricted to
acyclic account dependencies and preserves chronology within each account.
Each account is evaluated by the existing tracing engine. Only the claim shares
allocated to a selected debit become attributions on its selected receiving
credit. Account postings and proof classes are never changed.
"""
import hashlib
import json
from datetime import date
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from postgres.models.enums import ProofClass, TransactionDirection
from services.financial.ledger_transfers import LedgerTransferScenario, ledger_transfer_candidates
from services.financial.ledger_tracing import TraceAttributionInput, _exact_json
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.ledger_snapshot import MAX_EXPORT_BYTES
from services.financial.money import Money
from services.financial.proof_class import DEFAULT_TOTAL_CLASSES
from services.financial.tracing import Movement, Attribution, Doctrine, trace
from services.financial.trace_assets import TraceAssetUseInput, validate_asset_uses, trace_asset_uses
MAX_NETWORK_ROWS = 300

class NetworkOpening(BaseModel):
    model_config = ConfigDict(extra='forbid')
    account_id: UUID
    amount_minor: str = Field(pattern=r'^(0|[1-9][0-9]{0,18})$')
    basis: str = Field(min_length=1,max_length=4096)
    @field_validator('basis')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('An opening balance needs an explicit basis.')
        return value

class NetworkTraceInput(LedgerTransferScenario):
    start_date: date
    end_date: date
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    openings: list[NetworkOpening] = Field(min_length=2,max_length=10)
    ordered_transaction_ids: list[UUID] = Field(min_length=1,max_length=MAX_NETWORK_ROWS)
    order_basis: str = Field(min_length=1,max_length=4096)
    attributions: list[TraceAttributionInput] = Field(min_length=1,max_length=50)
    asset_uses: list[TraceAssetUseInput] = Field(default_factory=list, max_length=50)
    allow_backward: bool = Field(default=False, strict=True)
    backward_basis: str = Field(default='', max_length=4096)
    doctrines: list[Doctrine] = Field(min_length=1,max_length=5)


def network_trace_inputs(export, *, population='verified', tolerance_days=3):
    result=ledger_transfer_candidates(export,population=population,tolerance_days=tolerance_days)
    if not result['start_date'] or not result['end_date']:
        raise LedgerSummaryError('Choose both ordering-date bounds for cross-account tracing.')
    labels={r['row']['account_id']:r.get('account',{}).get('label') for r in json.loads(export.snapshot.content)['ledger']['readings']}
    accounts={}
    for row in result['rows']:
        key=(row['account_id'],row['currency'])
        accounts[key]=dict(account_id=row['account_id'],currency=row['currency'],label=labels.get(row['account_id']) or 'Account '+row['account_id'][:8])
    return {**result,'accounts':list(accounts.values()),'network_row_limit':MAX_NETWORK_ROWS,
        'network_limitation':'Forward conditional tracing is the default. An explicit backward assumption can relate an earlier receiving credit to a later debit only for acyclic account dependencies. Select a currency, declare opening funds and root claims, choose transfer pairings and review the movement order. Each selected receiving credit must follow its debit unless backward timing is explicitly enabled with a basis. No graph-path assumption, exchange conversion or verified ownership conclusion is made.'}


def evaluate_network_trace(export, request):
    request=NetworkTraceInput.model_validate(request)
    if not request.basis.strip() or not request.order_basis.strip():
        raise LedgerSummaryError('Record the basis for transfer pairings and movement order.')
    scope=network_trace_inputs(export,population=request.population,tolerance_days=request.tolerance_days)
    if request.expected_snapshot_sha256!=scope['snapshot_sha256'] or request.start_date.isoformat()!=scope['start_date'] or request.end_date.isoformat()!=scope['end_date']:
        raise LedgerSummaryError('Captured ledger or date scope changed. Reload cross-account inputs.')
    rows={r['key']:r for r in scope['rows'] if r['currency']==request.currency}
    if not 1<=len(rows)<=MAX_NETWORK_ROWS:
        raise LedgerSummaryError('Cross-account tracing needs 1–300 current readings in the selected currency; no partial trace was returned.')
    accounts={r['account_id'] for r in rows.values()}
    openings={str(o.account_id):o for o in request.openings}
    if len(openings)!=len(request.openings) or set(openings)!=accounts:
        raise LedgerSummaryError('Supply one opening balance for every account in the selected currency, without duplicates.')
    ordered=[str(i) for i in request.ordered_transaction_ids]
    if len(ordered)!=len(set(ordered)) or set(ordered)!=set(rows):
        raise LedgerSummaryError('The explicit order must contain every selected-currency reading exactly once.')
    dates=[rows[key]['ordering_date'] for key in ordered]
    if dates!=sorted(dates):raise LedgerSummaryError('Movement order cannot reverse recorded ordering dates.')
    positions={key:i for i,key in enumerate(ordered)}
    candidates={(p['debit_id'],p['credit_id']):p for p in scope['candidates']}
    links={};receiving=set();used=set();backward_pairs=[]
    if request.allow_backward and not request.backward_basis.strip():raise LedgerSummaryError('Explain the basis for allowing backward transfer timing.')
    for pair in request.pairs:
        debit,credit=str(pair.debit_id),str(pair.credit_id)
        if (debit,credit) not in candidates or debit not in rows or credit not in rows or debit in used or credit in used:
            raise LedgerSummaryError('Choose proposed transfer pairs in the selected currency without reusing postings.')
        if positions[credit]<=positions[debit] and not request.allow_backward:
            raise LedgerSummaryError('Forward tracing requires each selected receiving credit after its debit. Review same-day order; backward tracing is not assumed.')
        if positions[credit]<=positions[debit]:backward_pairs.append((debit,credit))
        used.update((debit,credit));receiving.add(credit);links[debit]=credit
    validate_asset_uses(request.asset_uses,rows,links,ordered_transaction_ids=ordered,transfer_credits=receiving)
    account_order=[]
    if backward_pairs:
        dependencies={a:set() for a in accounts}
        for debit,credit in links.items():dependencies[rows[credit]['account_id']].add(rows[debit]['account_id'])
        while dependencies:
            ready=sorted(a for a,parents in dependencies.items() if not parents)
            if not ready:raise LedgerSummaryError('Backward timing with a circular account dependency cannot be resolved by this calculation. No trace was returned.')
            account_order.extend(ready)
            dependencies={a:parents-set(ready) for a,parents in dependencies.items() if a not in ready}
    if len(set(request.doctrines))!=len(request.doctrines):raise LedgerSummaryError('Choose each method once.')
    roots={};root_totals={}
    for attribution in request.attributions:
        key=str(attribution.transaction_id)
        if key not in rows or rows[key]['direction']!='credit' or key in receiving:
            raise LedgerSummaryError('Root attributions must name selected-currency credits that are not receiving sides of selected transfers.')
        roots.setdefault(key,[]).append(attribution)
        root_totals[attribution.claim_id]=root_totals.get(attribution.claim_id,0)+int(attribution.amount_minor)
    classes=DEFAULT_TOTAL_CLASSES | ({ProofClass.p3} if request.population=='working' else set())
    results={}
    for method in request.doctrines:
        seen={account:[] for account in accounts};attributed={account:[] for account in accounts};pending={};hops=[]
        def account_trace(account):
            return trace(seen[account],attributed[account],doctrine=method,
                opening_balance=Money(int(openings[account].amount_minor),request.currency),proof_classes=classes)
        def add_movement(key,sequence):
            row=rows[key];account=row['account_id']
            seen[account].append(Movement(transaction_id=UUID(key),ordering_date=date.fromisoformat(row['ordering_date']),row_index=sequence,
                amount=Money(int(row['amount_minor']),request.currency),direction=TransactionDirection(row['direction']),proof_class=ProofClass(row['proof_class']),description=row['description']))
            for root in roots.get(key,[]):
                attributed[account].append(Attribution(transaction_id=UUID(key),claim_id=root.claim_id,amount=Money(int(root.amount_minor),request.currency),basis=root.basis))
            attributed[account].extend(pending.pop(key,[]))
        def propagate(key,draw):
            row=rows[key];account=row['account_id'];credit=links[key]
            pending[credit]=[Attribution(transaction_id=UUID(credit),claim_id=claim,amount=share,
                basis='Conditional propagation from selected debit '+key+' under '+method.value+(' with explicit backward timing: '+request.backward_basis if (key,credit) in backward_pairs else '')) for claim,share in draw.by_claim.items() if share.minor_units>0]
            hops.append(dict(debit_id=key,credit_id=credit,from_account=account,to_account=rows[credit]['account_id'],
                backward_timing=(key,credit) in backward_pairs,
                amount_minor=row['amount_minor'],propagated_by_claim={claim:str(m.minor_units) for claim,m in draw.by_claim.items()},
                unattributed_or_unidentified_minor=str(int(row['amount_minor'])-sum(m.minor_units for m in draw.by_claim.values())),unidentified_minor=str(draw.unidentified.minor_units),unfunded_minor=str(draw.unfunded.minor_units)))
        if backward_pairs:
            # Account dependencies, not global dates, determine calculation order.
            # Every account retains its original chronological movement order.
            # Acyclic dependencies ensure all incoming allocations are known first.
            for account in account_order:
                keys=[key for key in ordered if rows[key]['account_id']==account]
                for key in keys:add_movement(key,positions[key])
                calculation=account_trace(account)
                draws={str(d.transaction_id):d for d in calculation.draws}
                for key in keys:
                    if key in links:propagate(key,draws[key])
        else:
            for sequence,key in enumerate(ordered):
                add_movement(key,sequence)
                if key in links:
                    propagate(key,next(d for d in account_trace(rows[key]['account_id']).draws if str(d.transaction_id)==key))
        if pending:raise LedgerSummaryError('A selected transfer was not received within the supplied order.')
        final={account:account_trace(account) for account in sorted(accounts)}
        claims={}
        for claim,root_amount in sorted(root_totals.items()):
            remaining=sum(result.outcomes[claim].surviving.minor_units for result in final.values() if claim in result.outcomes)
            outside=sum(draw.by_claim.get(claim,Money.zero(request.currency)).minor_units for result in final.values() for draw in result.draws if str(draw.transaction_id) not in links)
            if remaining+outside!=root_amount:raise LedgerSummaryError('Cross-account claim allocations failed conservation; no result was produced.')
            claims[claim]=dict(root_attributed_minor=str(root_amount),reported_remaining_minor=str(remaining),withdrawn_without_selected_transfer_minor=str(outside))
        results[method.value]=dict(accounts=_exact_json(final),hops=hops,claims=claims,asset_uses=trace_asset_uses(request.asset_uses,rows,final.values()),
            unidentified_withdrawals_minor=str(sum(r.total_unidentified().minor_units for r in final.values())))
    document=dict(schema='loupe.financial.network_trace/1',case_id=scope['case_id'],applied=False,assumptions_verified=False,
        inputs=request.model_dump(mode='json'),backward_timing_used=bool(backward_pairs),calculation_account_order=account_order,results=results,ledger_snapshot=json.loads(export.snapshot.content),ledger_manifest=json.loads(export.manifest),
        limitations=[('Conditional backward timing enabled: selected earlier receiving credits are attributed from later debit allocations. This is an investigator assumption, not a legal conclusion or a finding about payment causation.' if backward_pairs else 'Conditional forward trace.'), 'All openings, root attributions, transfer pairings and same-day order are investigator assumptions.',
            'A transfer carries only the claim share allocated to its debit under that method. Unallocated, opening and unidentified funds are not promoted to a claim.',
            'Remaining claim figures must be read alongside unidentified withdrawals, especially under direct tracing; they are not a finding that those funds remain recoverable.',
            'Withdrawals without a selected transfer may have destinations outside this scope; they are not labelled dissipated.',
            'Every selected-currency current reading is included; omitted or incomplete evidence can change the result. Original proof classes remain unchanged.',
            'Recorded dates are unchanged. Backward timing requires an explicit basis and acyclic account dependencies; its legal applicability is not determined. Currency conversion is not inferred. Explicit asset-use hypotheses are separate annotations on complete withdrawals; they do not change cash results or establish asset ownership or value.'])
    content=json.dumps(document,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False);encoded=content.encode()
    if len(encoded)>MAX_EXPORT_BYTES:raise LedgerSummaryError('Cross-account report exceeds 16 MiB; no partial report was produced.')
    return dict(case_id=scope['case_id'],applied=False,scenario_json=content,scenario_sha256=hashlib.sha256(encoded).hexdigest(),scenario_byte_count=len(encoded))
