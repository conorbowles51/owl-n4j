"""Explicit asset purchase allocations, separate from cash tracing."""
from uuid import UUID
from typing import Literal
from services.financial.money import Money
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator, model_serializer
from services.financial.ledger_summary import LedgerSummaryError


class TraceAssetUseInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    transaction_id: UUID
    asset_label: str = Field(min_length=1,max_length=256)
    basis: str = Field(min_length=1,max_length=4096)
    asset_amount_minor: str | None = Field(default=None, pattern=r'^[1-9][0-9]{0,18}$')
    allocation_basis: Literal['proportional_share'] | None = None

    @model_validator(mode='after')
    def partial_choice(self):
        if (self.asset_amount_minor is None) != (self.allocation_basis is None):
            raise ValueError('A partial asset amount requires an explicit proportional allocation assumption.')
        return self

    @model_serializer(mode='wrap')
    def serialize_portion(self, handler):
        data = handler(self)
        if self.asset_amount_minor is None:
            data.pop('asset_amount_minor', None)
            data.pop('allocation_basis', None)
        return data

    @field_validator('asset_label','basis')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('An asset interpretation requires a label and supporting basis.')
        return value


def validate_asset_uses(uses, rows, transfer_debits=()):
    ids=[str(use.transaction_id) for use in uses]
    totals = {}
    counts = {key: ids.count(key) for key in set(ids)}
    for use, key in zip(uses, ids):
        if key not in rows or rows[key]['direction']!='debit' or int(rows[key]['amount_minor'])<=0 or key in transfer_debits:
            raise LedgerSummaryError('Asset interpretations require positive selected withdrawals that are not paired transfers.')
        if counts[key] > 1 and use.asset_amount_minor is None:
            raise LedgerSummaryError('Multiple purchases from one withdrawal each require an explicit amount and proportional allocation assumption.')
        totals[key] = totals.get(key, 0) + int(use.asset_amount_minor or rows[key]['amount_minor'])
        if totals[key] > int(rows[key]['amount_minor']):
            raise LedgerSummaryError('Combined asset purchases exceed their source withdrawal.')
        if use.asset_amount_minor is not None and not 0 < int(use.asset_amount_minor) <= int(rows[key]['amount_minor']):
            raise LedgerSummaryError('The asset amount must be positive and no greater than its source withdrawal.')


def trace_asset_uses(uses, rows, calculations):
    """Attribute the selected withdrawal's existing allocation, without repricing."""
    draws={str(draw.transaction_id):draw for calculation in calculations for draw in calculation.draws}
    result=[]
    remaining_parts={}
    counts={}
    for use in uses:
        key=str(use.transaction_id);row=rows[key];draw=draws.get(key)
        if draw is None or str(draw.amount.minor_units)!=str(row['amount_minor']) or draw.amount.currency!=row['currency']:
            raise LedgerSummaryError('Asset interpretation does not match a calculated withdrawal.')
        if draw.parts_total() != draw.amount:
            raise LedgerSummaryError('Asset withdrawal allocation does not conserve its source amount.')
        asset_amount = int(use.asset_amount_minor) if use.asset_amount_minor is not None else int(row['amount_minor'])
        claims = sorted(draw.by_claim)
        original_weights = [draw.by_claim[claim].minor_units for claim in claims] + [
            draw.from_untainted.minor_units, draw.from_opening.minor_units,
            draw.unidentified.minor_units, draw.unfunded.minor_units]
        weights = remaining_parts.get(key, original_weights)
        if asset_amount > sum(weights):
            raise LedgerSummaryError('Combined asset purchases exceed the remaining withdrawal components.')
        parts = Money(asset_amount, row['currency']).allocate(weights)
        remaining_parts[key] = [weight - part.minor_units for weight, part in zip(weights, parts)]
        counts[key] = counts.get(key, 0) + 1
        attributed = {claim: str(part.minor_units) for claim, part in zip(claims, parts)}
        unidentified, unfunded = parts[-2].minor_units, parts[-1].minor_units
        result.append(dict(transaction_id=key,asset_label=use.asset_label,basis=use.basis,
            amount_minor=str(row['amount_minor']),currency=row['currency'],allocated_by_claim=attributed,
            outside_claims_minor=str(asset_amount-sum(int(v) for v in attributed.values())),
            unidentified_minor=str(unidentified),unfunded_minor=str(unfunded),
            asset_amount_minor=str(asset_amount),
            remaining_withdrawal_minor=str(sum(remaining_parts[key])),
            allocation_sequence=counts[key],
            allocation_basis=use.allocation_basis or 'whole_withdrawal',
            rounding_rule='Largest remainder; ties use claim ID Unicode order, then untainted, opening, unidentified, unfunded.',
            changes_cash_results=False,
            limitation='Conditional asset-use hypothesis. A selected partial amount is allocated proportionally across the calculated withdrawal components; this additional assumption is separate from the tracing method. Purchases sharing a withdrawal are allocated in their listed order from remaining components, using largest-remainder rounding, so no component is counted twice. Claim amounts are already included in withdrawn figures; do not add them again. This does not establish acquisition, ownership, present value, resale proceeds or legal entitlement. No value is fed back into cash tracing.'))
    return result
