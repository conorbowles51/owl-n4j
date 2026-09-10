"""Read-only arithmetic leads for a statement difference, never findings."""
from sqlalchemy import select
from postgres.models.financial import FinancialTransaction
from postgres.models.enums import TransactionDirection
from services.financial.money import Money
from services.financial.quarantine import RowObservation, _candidates, _signatures

MAX_HINT_ROWS = 5000
MAX_HINTS = 100


def statement_delta_hints(session, period, outcome):
    if outcome.delta is None:
        return dict(available=False, reason='No complete balance identity is available to investigate.')
    if outcome.delta.is_zero:
        return dict(available=True, difference_minor='0', candidates=[], signatures=[], rows_checked=0,
            limitation='The current identity balances; this does not prove complete or accurate extraction.')
    rows = list(session.scalars(select(FinancialTransaction).where(
        FinancialTransaction.statement_period_id == period.id,
        FinancialTransaction.ledger_status == 'admitted').order_by(
            FinancialTransaction.row_index, FinancialTransaction.id).limit(MAX_HINT_ROWS+1)))
    if len(rows) > MAX_HINT_ROWS:
        return dict(available=False, reason='More than5000current rows; no partial discrepancy screening was returned.')
    if any(r.case_id != period.case_id or r.account_id != period.account_id or
           r.source_document_id != period.source_document_id or r.currency != period.currency for r in rows):
        raise ValueError('Discrepancy screening found inconsistent row ownership or currency.')
    observations = [RowObservation(ref_id=r.ref_id, row_index=r.row_index,
        amount=Money.from_minor_units(r.amount_minor, r.currency), direction=TransactionDirection(r.direction)) for r in rows]
    by_ref = {r.ref_id: r for r in rows}
    leads = []
    for candidate in _candidates(observations, outcome.delta):
        row = by_ref[candidate.ref_id]
        signed = row.amount_minor * (1 if row.direction == 'credit' else -1)
        if candidate.kind.value == 'sign_flip':
            if outcome.delta.minor_units != 2 * signed:
                continue  # Same magnitude in the opposite direction cannot close this gap.
            effect = 'direction_change'
            explanation = 'Reversing this reading’s direction would close the current difference arithmetically. Check its original debit/credit meaning.'
        elif outcome.delta.minor_units == signed:
            effect = 'extra_entry'
            explanation = 'Removing one entry with this amount and direction would close the current difference arithmetically. Check for repeated or misread entries.'
        else:
            effect = 'missing_entry'
            explanation = 'Adding an entry with this amount and direction would close the current difference arithmetically. Check for an omitted entry; this row does not prove one is missing.'
        leads.append(dict(transaction_id=str(row.id), ref_id=row.ref_id, amount_minor=str(row.amount_minor),
            direction=row.direction, kind=effect, explanation=explanation))
    if len(leads) > MAX_HINTS:
        return dict(available=False, reason='More than100arithmetic leads; no truncated candidate list was returned.')
    labels = dict(
        transposition='The difference is divisible by nine. Digit transposition is one possible cause among many; this does not locate or prove an error.',
        opening_omitted='The difference matches the opening-balance magnitude. Check that the printed opening and its convention were applied correctly.',
        opening_sign_flipped='The difference is twice the opening-balance magnitude. Check the printed opening sign and balance convention.')
    return dict(available=True, difference_minor=str(outcome.delta.minor_units), rows_checked=len(rows),
        candidates=leads, signatures=[dict(kind=s.value, explanation=labels[s.value]) for s in _signatures(outcome.delta, outcome.opening)],
        limitation='Arithmetic leads only, not findings or permission to change a row. Missing fees, omitted ranges, source errors and other causes may not match an existing amount. No running-balance order is assumed and proof class is unchanged.')
