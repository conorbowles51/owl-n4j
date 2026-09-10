"""Explicit whole-withdrawal asset interpretations, separate from cash tracing."""
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from services.financial.ledger_summary import LedgerSummaryError


class TraceAssetUseInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    transaction_id: UUID
    asset_label: str = Field(min_length=1,max_length=256)
    basis: str = Field(min_length=1,max_length=4096)

    @field_validator('asset_label','basis')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('An asset interpretation requires a label and supporting basis.')
        return value


def validate_asset_uses(uses, rows, transfer_debits=()):
    ids=[str(use.transaction_id) for use in uses]
    if len(ids)!=len(set(ids)):
        raise LedgerSummaryError('A withdrawal can fund only one whole-payment asset interpretation in this scenario.')
    for key in ids:
        if key not in rows or rows[key]['direction']!='debit' or int(rows[key]['amount_minor'])<=0 or key in transfer_debits:
            raise LedgerSummaryError('Asset interpretations require positive selected withdrawals that are not paired transfers.')


def trace_asset_uses(uses, rows, calculations):
    """Attribute the selected withdrawal's existing allocation, without repricing."""
    draws={str(draw.transaction_id):draw for calculation in calculations for draw in calculation.draws}
    result=[]
    for use in uses:
        key=str(use.transaction_id);row=rows[key];draw=draws.get(key)
        if draw is None or str(draw.amount.minor_units)!=str(row['amount_minor']) or draw.amount.currency!=row['currency']:
            raise LedgerSummaryError('Asset interpretation does not match a calculated withdrawal.')
        if draw.parts_total() != draw.amount:
            raise LedgerSummaryError('Asset withdrawal allocation does not conserve its source amount.')
        attributed={claim:str(amount.minor_units) for claim,amount in draw.by_claim.items()}
        result.append(dict(transaction_id=key,asset_label=use.asset_label,basis=use.basis,
            amount_minor=str(row['amount_minor']),currency=row['currency'],allocated_by_claim=attributed,
            outside_claims_minor=str(int(row['amount_minor'])-sum(int(v) for v in attributed.values())),
            unidentified_minor=str(draw.unidentified.minor_units),unfunded_minor=str(draw.unfunded.minor_units),
            changes_cash_results=False,
            limitation='Whole-withdrawal asset-use hypothesis. Claim amounts are already included in withdrawn figures; do not add them again. This does not establish acquisition, ownership, present value, resale proceeds or legal entitlement. No value is fed back into cash tracing.'))
    return result
