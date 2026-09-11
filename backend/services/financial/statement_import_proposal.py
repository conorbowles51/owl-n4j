"""Automatic statement-table proposals with explicit, actionable exceptions.

This stage does not admit transactions or assert complete document coverage.
Every row retains its source cells, including excluded headings and controls.
"""
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from services.financial.money import get_currency
from services.financial.pdf_candidates import _digest
from services.financial.source_dates import assess_date_text

VERSION = 'statement-review-v1'
_HEADERS = {
    'date': 'date', 'transaction date': 'date', 'trans date': 'date',
    'booking date': 'booking_date', 'posting date': 'booking_date',
    'value date': 'value_date', 'description': 'description',
    'details': 'description', 'transaction details': 'description',
    'credit': 'credit', 'credits': 'credit', 'money in': 'credit',
    'deposits': 'credit', 'paid in': 'credit',
    'debit': 'debit', 'debits': 'debit', 'money out': 'debit',
    'withdrawals': 'debit', 'paid out': 'debit',
    'balance': 'balance', 'running balance': 'balance', 'amount': 'amount',
}
_CONTROLS = {'opening balance', 'balance brought forward', 'brought forward',
             'closing balance', 'balance carried forward', 'carried forward'}


def exact_amount(text, currency):
    """Read a printed decimal amount without floating point or lost digits.

    Comma decimal conventions and ambiguous separators remain review exceptions.
    No guessed amount is returned when the complete text does not match.
    """
    value = text.strip().replace('\u00a0', ' ')
    code = get_currency(currency)
    symbols = {'EUR': '€', 'GBP': '£', 'USD': '$', 'CAD': '$', 'AUD': '$', 'NZD': '$'}
    prefix = re.escape(currency)
    if currency in symbols:
        prefix += '|' + re.escape(symbols[currency])
    value = re.sub(r'^(?:' + prefix + r')\s*', '', value)
    negative = value.startswith('(') and value.endswith(')')
    if negative:
        value = value[1:-1]
    if not re.fullmatch(r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?', value):
        raise ValueError('Check this amount against the statement.')
    if negative and value.startswith(('-', '+')):
        raise ValueError('The amount has conflicting signs.')
    try:
        number = Decimal(value.replace(',', '')) * (10 ** code.exponent)
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError('Check the currency and decimal places.') from exc
    if number != number.to_integral_value():
        raise ValueError('The amount has more decimal places than this currency supports.')
    result = int(number) * (-1 if negative else 1)
    if not -9223372036854775808 <= result <= 9223372036854775807:
        raise ValueError('The amount exceeds the supported range.')
    return str(result)


def _date(text):
    options = {p['iso_date'] for p in assess_date_text(text, 'unknown')['proposals'] if 'iso_date' in p}
    if len(options) != 1:
        raise ValueError('Check this date; its full date is missing or ambiguous.')
    value = options.pop()
    date.fromisoformat(value)
    return value


def propose_table(source, currency):
    """Interpret labelled columns automatically; preserve every unexplained row."""
    get_currency(currency)
    roles = None
    result = []
    previous_balance = None
    for row in source['rows']:
        cells = {c['column_index']: c for c in row['cells']}
        labels = [(c['column_index'], _HEADERS.get(' '.join(c['expected_text'].lower().split()))) for c in row['cells']]
        known = [(column, role) for column, role in labels if role]
        possible = dict(known)
        is_header = any(r in ('date', 'booking_date', 'value_date') for r in possible.values()) and any(r in ('credit', 'debit', 'amount') for r in possible.values())
        item = dict(id=f"{source['page_number']}:{source['table_index']}:{row['row_index']}",
                    page_number=source['page_number'], table_index=source['table_index'],
                    row_index=row['row_index'], source_revision=source['source_revision'],
                    source_cells=row['cells'], fields={}, issues=[], excluded=False, kind='transaction')
        if is_header:
            if len(set(possible.values())) != len(possible):
                roles = None
                item.update(kind='unresolved', issues=['Several columns have the same meaning. Check the table layout.'])
            else:
                roles = possible
                item.update(kind='header', excluded=True)
            result.append(item)
            continue
        if roles is None:
            item.update(kind='unresolved', issues=['The system could not identify this row from a transaction header.'])
            result.append(item)
            continue
        texts = {role: cells[col]['expected_text'] for col, role in roles.items() if col in cells}
        fields = item['fields']
        fields['description'] = texts.get('description', '')
        party = re.fullmatch(r'(?:wire|transfer|payment)\s+(?:from|to)\s+(.+)', fields['description'], re.I)
        fields['counterparty'] = party.group(1).strip() if party else ''
        control = fields['description'].strip().lower() in _CONTROLS
        amounts = []
        for role in ('credit', 'debit', 'amount', 'balance'):
            text = texts.get(role, '').strip()
            if not text or text in ('-', '—'):
                continue
            try:
                fields[role] = exact_amount(text, currency)
                if role != 'balance' and int(fields[role]) != 0:
                    amounts.append(role)
            except ValueError as exc:
                item['issues'].append(f'{role}: {exc}')
        for role in ('date', 'booking_date', 'value_date'):
            if texts.get(role):
                try:
                    fields[role] = _date(texts[role])
                except ValueError as exc:
                    item['issues'].append(str(exc))
        if control and not amounts and not any(texts.get(r, '').strip() not in ('', '-', '—') for r in ('credit', 'debit', 'amount')):
            item.update(kind='balance', excluded=True)
            if 'balance' in fields:
                previous_balance = int(fields['balance'])
        else:
            if len(amounts) != 1:
                item['issues'].append('Choose the transaction amount and whether money entered or left the account.')
            else:
                role = amounts[0]
                amount = int(fields[role])
                fields['amount_minor'] = str(abs(amount))
                if role in ('credit', 'debit') and amount > 0:
                    fields['direction'] = role
                else:
                    item['issues'].append('Confirm whether this amount is money in or money out.')
            if not any(fields.get(r) for r in ('date', 'booking_date', 'value_date')):
                item['issues'].append('A transaction date needs attention.')
            if not fields['description'].strip():
                item['issues'].append('The transaction description is missing.')
            if previous_balance is not None and 'balance' in fields and fields.get('direction'):
                movement = int(fields['amount_minor']) * (1 if fields['direction'] == 'credit' else -1)
                delta = int(fields['balance']) - previous_balance - movement
                fields['balance_difference_minor'] = str(delta)
                if delta:
                    item['issues'].append('The running balance does not match this payment. Check the amount, direction or a missing row.')
            previous_balance = int(fields['balance']) if 'balance' in fields and not item['issues'] else None
        result.append(item)
    return dict(version=VERSION, case_id=source['case_id'], evidence_file_id=source['evidence_file_id'],
                currency=currency, rows=result,
                transaction_count=sum(not r['excluded'] for r in result),
                needs_attention=sum(bool(r['issues']) for r in result),
                revision=_digest(dict(version=VERSION, source=source, currency=currency)), applied=False)
