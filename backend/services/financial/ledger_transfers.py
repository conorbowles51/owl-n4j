"""Reproducible transfer hypotheses over captured current ledger readings."""
import hashlib
import json
from datetime import date
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from postgres.models.enums import DateSource, TransactionDirection, LinkRelation
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.working_totals import working_totals_from_readings
from services.financial.linkage import LinkObservation, link_composite
from services.financial.money import Money
from services.financial.ledger_snapshot import MAX_EXPORT_BYTES

MAX_TRANSFER_ROWS = 500
MAX_TRANSFER_PAIRS = 1000


def ledger_transfer_candidates(export, *, population='working', tolerance_days=3):
    if population not in ('working', 'verified') or type(tolerance_days) is not int or not 0 <= tolerance_days <= 7:
        raise LedgerSummaryError('Choose working or verified readings and a date tolerance from 0 to 7 days.')
    document = json.loads(export.snapshot.content)
    ledger = document['ledger']
    if not document.get('export_ready') or not ledger.get('history_captured'):
        raise LedgerSummaryError('Transfer review requires a consistent captured ledger and history.')
    if ledger['account_id'] is not None:
        raise LedgerSummaryError('Transfer comparison requires all accounts in the selected case and date scope.')
    summary = working_totals_from_readings(ledger) if population == 'working' else ledger
    rows = [r['row'] for r in ledger['readings'] if (r['exclusion_reason'] in (None, 'proof_class_not_included') if population == 'working' else r['included'])]
    labels = {r['row']['account_id']: r.get('account', {}).get('label') for r in ledger['readings']}
    rows = [{**r, 'account_label': labels.get(r['account_id']) or 'Account ' + r['account_id'][:8]} for r in rows]
    if len(rows) > MAX_TRANSFER_ROWS:
        raise LedgerSummaryError('More than 500 current rows match. Narrow the date scope; no partial transfer comparison was made.')
    observations = []
    unavailable = []
    for row in rows:
        if row.get('ordering_date_context') == 'statement_end_ordering_only':
            unavailable.append(row['key'])
            continue
        dates = {name: date.fromisoformat(row[name]) if row[name] else None for name in ('transaction_date', 'posted_date', 'value_date', 'effective_date')}
        observations.append(LinkObservation(transaction_id=UUID(row['key']), account_id=UUID(row['account_id']),
            source_document_id=UUID(row['source_document_id']), amount=Money(int(row['amount_minor']), row['currency']),
            direction=TransactionDirection(row['direction']), ordering_date=date.fromisoformat(row['ordering_date']),
            ordering_date_source=DateSource(row['ordering_date_source']), **dates))
    linked = link_composite(observations, tolerance_days=tolerance_days)
    by_id = {row['key']: row for row in rows}
    pairs = []
    for link in linked.links:
        if link.relation != LinkRelation.counterparty:
            continue
        left, right = by_id[str(link.left_id)], by_id[str(link.right_id)]
        debit, credit = (left, right) if left['direction'] == 'debit' else (right, left)
        pairs.append(dict(debit_id=debit['key'], credit_id=credit['key'], currency=debit['currency'],
            amount_minor=debit['amount_minor'], outcome=link.outcome.value,
            date_gap_days=link.date_agreement.gap_days if link.date_agreement else None,
            compared_date_field=link.date_agreement.field if link.date_agreement else None))
    if len(pairs) > MAX_TRANSFER_PAIRS:
        raise LedgerSummaryError('More than 1,000 transfer candidates match. Narrow the date scope; no truncated comparison was returned.')
    return dict(case_id=ledger['case_id'], start_date=ledger['start_date'], end_date=ledger['end_date'],
        population=population, tolerance_days=tolerance_days, snapshot_sha256=export.snapshot.sha256,
        rows=rows, candidates=pairs, currencies=summary['currencies'], excluded_rows=summary['excluded_rows'],
        date_unavailable_ids=unavailable, applied=False,
        limitation='Equal amounts, currency and compatible dates across different accounts suggest possible transfers; they do not prove a match. Multiple possible partners remain explicit. Statement-end-only dates are not used as transaction timing. Original postings remain unchanged; any pairing is a separate investigator hypothesis.')


class TransferPairChoice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    debit_id: UUID
    credit_id: UUID


class LedgerTransferScenario(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_snapshot_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    population: str = Field(pattern=r'^(working|verified)$')
    tolerance_days: int = Field(ge=0, le=7, strict=True)
    start_date: date | None = None
    end_date: date | None = None
    pairs: list[TransferPairChoice] = Field(min_length=1, max_length=250)
    basis: str = Field(min_length=1, max_length=4096)


def evaluate_transfer_scenario(export, request):
    request = LedgerTransferScenario.model_validate(request)
    if not request.basis.strip(): raise LedgerSummaryError('Record a reason for the selected pairings.')
    result = ledger_transfer_candidates(export, population=request.population, tolerance_days=request.tolerance_days)
    if request.expected_snapshot_sha256 != result['snapshot_sha256']:
        raise LedgerSummaryError('Ledger readings or decisions changed. Reload transfer candidates before pairing.')
    if result['start_date'] != (request.start_date.isoformat() if request.start_date else None) or result['end_date'] != (request.end_date.isoformat() if request.end_date else None):
        raise LedgerSummaryError('Transfer scenario date scope differs from its captured ledger.')
    indexed = {(p['debit_id'], p['credit_id']): p for p in result['candidates']}
    used, selected, matched = set(), [], {}
    for choice in request.pairs:
        key = (str(choice.debit_id), str(choice.credit_id))
        if key not in indexed or any(value in used for value in key):
            raise LedgerSummaryError('Choose proposed pairs without using a reading more than once.')
        used.update(key); pair = indexed[key]; selected.append(pair)
        group = matched.setdefault(pair['currency'], dict(amount=0, count=0))
        group['amount'] += int(pair['amount_minor']); group['count'] += 1
    figures = []
    for group in result['currencies']:
        paired = matched.get(group['currency'], dict(amount=0, count=0))
        credits, debits = int(group['credits_minor']), int(group['debits_minor'])
        figures.append(dict(currency=group['currency'], posting_rows=group['rows'],
            paired_transfers=paired['count'], movement_count=group['rows']-paired['count'],
            paired_amount_minor=str(paired['amount']), unpaired_credits_minor=str(credits-paired['amount']),
            unpaired_debits_minor=str(debits-paired['amount']), movement_volume_minor=str(credits+debits-paired['amount'])))
    document = dict(schema='loupe.financial.transfer_scenario/1', case_id=result['case_id'], applied=False,
        pairings_verified=False, inputs=request.model_dump(mode='json'), selected_pairs=selected, figures=figures,
        ledger_snapshot=json.loads(export.snapshot.content), ledger_manifest=json.loads(export.manifest),
        limitation='Conditional pairing only. Selected debit/credit pairs count once in this scenario; unpaired postings remain separate. This is not a deduplication decision, ownership conclusion or change to the ledger. Missing records and date scope can change candidate matches.')
    content = json.dumps(document, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    encoded = content.encode('utf-8')
    if len(encoded) > MAX_EXPORT_BYTES: raise LedgerSummaryError('Transfer report exceeds 16 MiB; no partial report was returned.')
    return dict(case_id=result['case_id'], applied=False, figures=figures, scenario_json=content,
        scenario_sha256=hashlib.sha256(encoded).hexdigest(), scenario_byte_count=len(encoded))
