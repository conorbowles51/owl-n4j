"""Conditional account tracing over an immutable, source-bound ledger export.

The investigator supplies opening funds, attribution and same-day order. These
are recorded assumptions, never promoted to ledger facts or legal conclusions.
"""
import hashlib
import json
from dataclasses import fields, is_dataclass
from datetime import date
from enum import Enum
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from postgres.models.enums import ProofClass, TransactionDirection
from services.financial.money import Money
from services.financial.proof_class import DEFAULT_TOTAL_CLASSES
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.ledger_snapshot import MAX_EXPORT_BYTES
from services.financial.tracing import Movement, Attribution, Doctrine, compare_doctrines

MAX_TRACE_ROWS = 1000


class TraceAttributionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    transaction_id: UUID
    claim_id: str = Field(min_length=1, max_length=128)
    amount_minor: str = Field(pattern=r'^[1-9][0-9]{0,18}$')
    basis: str = Field(min_length=1, max_length=4096)

    @field_validator('claim_id', 'basis')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('A nonblank claim and attribution basis are required.')
        return value


class LedgerTraceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    population: str = Field(default="verified", pattern=r"^(working|verified)$")
    account_id: UUID
    start_date: date
    end_date: date
    expected_snapshot_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    opening_balance_minor: str = Field(pattern=r'^(0|[1-9][0-9]{0,18})$')
    opening_basis: str = Field(min_length=1, max_length=4096)
    order_basis: str = Field(min_length=1, max_length=4096)
    ordered_transaction_ids: list[UUID] = Field(min_length=1, max_length=MAX_TRACE_ROWS)
    attributions: list[TraceAttributionInput] = Field(min_length=1, max_length=50)
    doctrines: list[Doctrine] = Field(min_length=1, max_length=5)

    @field_validator('opening_basis', 'order_basis')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Opening balance and ordering require explicit bases.')
        return value


def ledger_trace_inputs(export, *, population="verified"):
    if population not in ("working", "verified"):
        raise LedgerSummaryError("Choose working or verified readings for tracing.")
    document = json.loads(export.snapshot.content)
    ledger = document['ledger']
    if not document.get('export_ready') or not ledger.get('history_captured'):
        raise LedgerSummaryError('Tracing requires a consistent captured ledger and history.')
    if not ledger['account_id'] or not ledger['start_date'] or not ledger['end_date']:
        raise LedgerSummaryError('Choose one account and a closed ordering-date interval for tracing.')
    rows = [r for r in ledger['readings'] if r['included'] or (population == 'working' and r['exclusion_reason'] == 'proof_class_not_included')]
    if not rows or len(rows) > MAX_TRACE_ROWS:
        raise LedgerSummaryError('Tracing requires between 1 and 1000 included readings; narrow the scope without omitting relevant activity.')
    currencies = {r['row']['currency'] for r in rows}
    if len(currencies) != 1:
        raise LedgerSummaryError('An account tracing scenario must have one currency; currencies cannot be combined.')
    return dict(population=population, case_id=ledger['case_id'], account_id=ledger['account_id'], start_date=ledger['start_date'],
        end_date=ledger['end_date'], currency=next(iter(currencies)), snapshot_sha256=export.snapshot.sha256,
        included_rows=len(rows), excluded_rows=len(ledger['readings'])-len(rows), readings=rows,
        applied=False, limitation='Opening funds, deposit attribution and same-day order require explicit investigator assumptions. This input list does not establish evidence completeness or the applicable tracing method.')


def _exact_json(value):
    if isinstance(value, Money):
        return dict(minor_units=str(value.minor_units), currency=value.currency)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value):
        return {f.name: _exact_json(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, dict):
        return {str(k.value if isinstance(k, Enum) else k): _exact_json(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_exact_json(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_exact_json(v) for v in value)
    return value


def evaluate_ledger_trace(export, request: LedgerTraceInput):
    scope = ledger_trace_inputs(export, population=request.population)
    if request.expected_snapshot_sha256 != export.snapshot.sha256:
        raise LedgerSummaryError('Ledger readings or decisions changed. Reload tracing inputs and review assumptions.')
    if (str(request.account_id) != scope['account_id'] or request.start_date.isoformat() != scope['start_date']
            or request.end_date.isoformat() != scope['end_date']):
        raise LedgerSummaryError('Tracing assumptions do not match the captured account/date scope.')
    if len(set(request.doctrines)) != len(request.doctrines):
        raise LedgerSummaryError('Choose each tracing method only once.')
    indexed = {r['row']['key']: r['row'] for r in scope['readings']}
    ordered = [str(key) for key in request.ordered_transaction_ids]
    if len(ordered) != len(set(ordered)) or set(ordered) != set(indexed):
        raise LedgerSummaryError('Explicit order must include every eligible scoped reading exactly once.')
    dates = [date.fromisoformat(indexed[key]['ordering_date']) for key in ordered]
    if dates != sorted(dates):
        raise LedgerSummaryError('Explicit order cannot reverse the recorded ordering dates.')
    currency = scope['currency']
    movements = [Movement(transaction_id=UUID(key), ordering_date=dates[index], row_index=index,
        amount=Money(int(indexed[key]['amount_minor']), currency),
        direction=TransactionDirection(indexed[key]['direction']), proof_class=ProofClass(indexed[key]['proof_class']),
        description=indexed[key]['description']) for index, key in enumerate(ordered)]
    attributions = [Attribution(transaction_id=a.transaction_id, claim_id=a.claim_id,
        amount=Money(int(a.amount_minor), currency), basis=a.basis) for a in request.attributions]
    comparison = compare_doctrines(movements, attributions, opening_balance=Money(int(request.opening_balance_minor), currency),
                                   doctrines=request.doctrines,
                                   proof_classes=DEFAULT_TOTAL_CLASSES | ({ProofClass.p3} if request.population == "working" else set()))
    payload = dict(schema='loupe.financial.conditional_trace/1', case_id=scope['case_id'], account_id=scope['account_id'],
        applied=False, assumptions_verified=False, inputs=request.model_dump(mode='json'),
        ledger_snapshot=json.loads(export.snapshot.content), ledger_manifest=json.loads(export.manifest),
        comparison=_exact_json(comparison), limitations=[
            'Population: ' + request.population + '. Original proof classes are retained; working P3 readings are assumptions in this scenario, not verified postings.',
            'Conditional scenario only. Opening balance, deposit attributions and same-day order are investigator-supplied assumptions, not verified ledger facts.',
            'The opening balance is treated as unattributed funds before this interval; claims on opening funds are not represented.',
            'Missing evidence and incomplete extraction may change every result. Excluded readings remain outside this scenario and are listed in the captured snapshot.',
            'The selected methods are calculation rules, not a recommendation of which rule legally applies. No default method or legal conclusion is supplied.',
            'Single-account scenario only; no cross-account transfer matching or downstream tracing is established.',
        ])
    content = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    encoded = content.encode('utf-8')
    if len(encoded) > MAX_EXPORT_BYTES:
        raise LedgerSummaryError('Tracing scenario exceeds 16 MiB; no partial report was produced.')
    return dict(case_id=scope['case_id'], account_id=scope['account_id'], applied=False, scenario_json=content,
                scenario_sha256=hashlib.sha256(encoded).hexdigest(), scenario_byte_count=len(encoded))
