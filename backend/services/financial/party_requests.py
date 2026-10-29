"""What to ask the bank for: every payment of a case whose other side the case does not name, one line each.

A payment is listed when its From or To (the other side) is empty after every source the ledger reads: the
statement's counterparty field, a person's label or link, a name read from the description, and the matching
payment in another account of the case (payment_party_matches). Each line says what the bank holds that the
statement does not print (the beneficiary or sender, a cheque's image, a batch's payee list), with the line
exactly as printed so the bank can find it. Read only.
"""
from __future__ import annotations

import csv
import io
import re

# What the bank holds for a payment whose statement line names nobody, by the reason the ledger shows.
_ASK = {
    'cheque-number-only': 'Image of cheque {cheque} (front and back): payee and endorsement',
    'cheque-deposit': 'Image of the deposited cheque (front and back): drawer and drawer’s bank',
    'cashier-cheque': 'Cashier’s cheque request: purchaser and payee',
    'cancelled-cashier-cheque': 'Cashier’s cheque request: purchaser and payee',
    'bbva-batch-payment': 'Payee list of this batch payment (names, accounts and amounts)',
    'payroll-batch': 'Payroll file for this payment (employees, accounts and amounts)',
    'ach-batch': 'ACH batch detail: originator and receivers',
    'enlace-expense-advance': 'Recipient name and account of this transfer',
    'foreign-payment-order': 'Wire detail (SWIFT message): beneficiary, beneficiary bank and account',
    'returned-transfer': 'Original transfer detail: beneficiary name and account, reason for return',
    'returned-bill-payment': 'Bill payment detail: payee',
    'capture-line-payment': 'Capture line receipt: the authority paid',
    'bank-collected-premium': 'Insurance receipt: insurer and policy',
    'card-payment-source': 'Card payment detail: the paying account',
    'brokerage-cash-movement': 'Transfer detail: the other account and its holder',
}

COLUMNS = ('Bank', 'Account', 'Holder', 'Date', 'Direction', 'Amount', 'Currency', 'Printed line', 'Missing', 'Ask the bank for',
           'Why the statement does not say', 'Payment id')


def _ask(rule, direction, description):
    if rule in _ASK:
        cheque = re.search(r'\d{3,}', description or '')
        return _ASK[rule].format(cheque=cheque[0] if cheque else '')
    return ('Sender name and account of this deposit' if direction == 'credit'
            else 'Recipient name and account of this payment')


def request_rows(session, case_id):
    """One dict per admitted, current payment of the case whose other side is not named, by bank, account and date."""
    from services.financial.payment_party_matches import case_party_matches, case_rows
    # Named from another account of the case exactly as the ledger shows it.
    named = case_party_matches(session, case_id)
    rows = case_rows(session, case_id, dated_only=False)
    out = []
    for row in rows:
        if row['name'] or row['id'] in named:
            continue
        credit = row['direction'] == 'credit'
        out.append({
            'Bank': row['institution'] or '', 'Account': row['identifier'] or '', 'Holder': row['holder'] or '',
            'Date': str(row['transaction_date'] or row['ordering_date'] or ''), 'Direction': 'Money in' if credit else 'Money out',
            'Amount': f"{row['amount_minor'] / 100:.2f}", 'Currency': row['currency'] or '', 'Printed line': row['description'] or '',
            'Missing': 'Who sent it' if credit else 'Who received it',
            'Ask the bank for': _ask(row['reason_rule'], row['direction'], row['description']),
            'Why the statement does not say': row['reason'] or 'The line prints no name and no known layout explains why.',
            'Payment id': row['id']})
    out.sort(key=lambda r: (r['Bank'], r['Account'], r['Date'], r['Payment id']))
    return out


def requests_csv(rows):
    """UTF-8 with a byte-order mark so a spreadsheet opens accents correctly."""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator='\r\n')
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _cell(value) for key, value in row.items()})
    return ('﻿' + out.getvalue()).encode('utf-8')


def _cell(value):
    """A cell a spreadsheet would run as a formula is kept as text."""
    value = str(value)
    return "'" + value if value[:1] in ('=', '+', '-', '@') else value
