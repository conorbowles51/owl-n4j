"""Exact, explicitly reviewed principal and fees for a split account transfer."""
from decimal import Decimal, localcontext
from services.financial.account_relationships import owners_on
from services.financial.money import get_currency


def assess_transfer_parts(request, rows, accounts, day, error):
    entries, principal, fees = [], {'debit': {}, 'credit': {}}, {}
    account_sides = {'debit': set(), 'credit': set()}
    canonical = lambda row: accounts[str(row.account_id)].get("canonical_id", str(row.account_id))
    holders = None
    principal_rows = []
    for part in request.transfer_parts:
        row = rows[str(part.transaction_id)]
        amount, fee = int(part.principal_minor), int(part.fee_minor)
        if amount + fee > row.amount_minor:
            raise error('Transfer principal plus fee exceeds a selected entry. The original amount is unchanged.')
        if fee and row.direction != 'debit':
            raise error('Assign fees to an outgoing debit. A receiving credit is the net amount received; explain any deduction in the sending debit or use a separate fee entry.')
        if amount:
            principal[row.direction][row.currency] = principal[row.direction].get(row.currency, 0) + amount
            account_sides[row.direction].add(canonical(row))
            principal_rows.append(row)
            current = {p['id']: p for p in owners_on(accounts[str(row.account_id)], day(row))}
            holders = current if holders is None else {key: holders[key] for key in holders.keys() & current.keys()}
        if fee:
            fees[row.currency] = fees.get(row.currency, 0) + fee
        entries.append(dict(transaction_id=str(row.id), direction=row.direction, currency=row.currency,
            principal_minor=str(amount), fee_minor=str(fee), original_minor=str(row.amount_minor),
            unassigned_minor=str(row.amount_minor - amount - fee)))
    if len(principal['debit']) != 1 or len(principal['credit']) != 1:
        raise error('Choose sending and receiving principal in one currency on each side. Record successive transfers or exchanges as separate links.')
    if account_sides['debit'] & account_sides['credit']:
        raise error('Sending and receiving principal must belong to different accounts. Record an onward payment separately.')
    if any(not int(p.principal_minor) and canonical(rows[str(p.transaction_id)]) not in account_sides['debit'] | account_sides['credit'] for p in request.transfer_parts):
        raise error('A separate fee must belong to a sending or receiving account in this transfer.')
    sent_currency, sent = next(iter(principal['debit'].items()))
    received_currency, received = next(iter(principal['credit'].items()))
    rate = None
    warnings = ['Principal, fees and unassigned amounts are investigator-reviewed portions of the original entries. Fees remain external spending; sources and account reconciliation are unchanged.']
    if sent_currency == received_currency:
        if sent != received:
            raise error('Sending and receiving principal do not balance. Separate a supported fee or leave an explicit unassigned portion; do not label an unexplained difference as a fee.')
    elif not request.allow_fx:
        raise error('Different currencies require an explicit exchange hypothesis. Both original amounts are retained.')
    else:
        with localcontext() as ctx:
            ctx.prec = 36
            source = Decimal(sent).scaleb(-get_currency(sent_currency).exponent)
            target = Decimal(received).scaleb(-get_currency(received_currency).exponent)
            rate = format(Decimal(format(target / source, '.12g')), 'f')
        warnings.append('The exchange rate uses the assigned principal only. Confirm the exchange and fees against evidence; no market-rate conversion is applied.')
    if not holders:
        warnings.append('Common ownership is not established for every principal entry on its payment date.')
    if len({day(row) for row in principal_rows}) > 1 or any(day(row) is None for row in principal_rows):
        warnings.append('These entries span different or unknown dates. Explain the timing; a split link does not establish exact order.')
    return dict(entries=entries, sent_currency=sent_currency, sent_minor=str(sent),
        received_currency=received_currency, received_minor=str(received),
        fees=[dict(currency=currency, amount_minor=str(value)) for currency, value in sorted(fees.items())]), list((holders or {}).values()), rate, warnings
