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

VERSION = 'statement-review-v10'
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


def _rect(cell, page):
    locator = cell.get('locator') or {}
    rect, size = locator.get('rect'), locator.get('page_size')
    if (locator.get('page') != page or not isinstance(rect, list) or len(rect) != 4
            or not isinstance(size, list) or len(size) != 2
            or not all(type(v) is int for v in rect+size)
            or not 0 <= rect[0] < rect[2] <= size[0]
            or not 0 <= rect[1] < rect[3] <= size[1]):
        return None
    return rect, size


def _printed_roles(source, header, row, roles):
    """Text-alignment grids number present cells, so blank columns need geometry.

    Assign only cells wholly inside a single band between printed headings.
    Keep original cell indices and positions for corrections and citations.
    Uncertain or overlapping positions remain exceptions, never index fallbacks.
    """
    headings = [(c, _rect(c, source['page_number'])) for c in header]
    if not headings or any(p is None for _, p in headings):
        return None
    size = headings[0][1][1]
    headings.sort(key=lambda item: item[1][0][0])
    if any(p[1] != size for _, p in headings):
        return None
    boundaries = [0]
    for (_, left), (_, right) in zip(headings, headings[1:]):
        if left[0][2] >= right[0][0]:
            return None
        boundaries.append((left[0][2]+right[0][0]) / 2)
    boundaries.append(size[0])
    assigned = {}
    for cell in row['cells']:
        pos = _rect(cell, source['page_number'])
        if pos is None or pos[1] != size:
            return None
        slots = [i for i in range(len(headings)) if boundaries[i] <= pos[0][0] and pos[0][2] <= boundaries[i+1]]
        if len(slots) != 1:
            return None
        column = headings[slots[0]][0]['column_index']
        if column in assigned:
            return None
        assigned[column] = cell
    return {role: assigned[col] for col, role in roles.items() if col in assigned}


def _statement_heading(row):
    if len(row['cells']) != 1:
        return False
    text = ' '.join(row['cells'][0]['expected_text'].split())
    return bool(re.fullmatch(r'(?:Account (?:Name|Holder|Number|No)|IBAN|Statement Period|Period|Currency|Bank|Institution): .+', text, re.I)
                or re.fullmatch(r'(?:BANK|BUSINESS ACCOUNT|ACCOUNT) STATEMENT(?: - .+)?', text, re.I)
                or re.fullmatch(r'[A-Z .&]+(?:BANK|CREDIT UNION)(?:,? N[.]?A[.]?)?', text))


def propose_table(source, currency):
    """Interpret labelled columns automatically; preserve every unexplained row."""
    get_currency(currency)
    roles = None
    header = []
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
                header = row['cells']
                # Exclude only explicit statement metadata above a recognised table.
                for earlier in result:
                    if earlier['kind'] == 'unresolved' and _statement_heading({'cells': earlier['source_cells']}):
                        earlier.update(kind='header', excluded=True, issues=[])
                item.update(kind='header', excluded=True)
            result.append(item)
            continue
        if roles is None:
            item.update(kind='unresolved', issues=['The system could not identify this row from a transaction header.'])
            result.append(item)
            continue
        if source.get('table_source') == 'text_alignment':
            role_cells = _printed_roles(source, header, row, roles)
            if role_cells is None:
                item.update(kind='unresolved', issues=['The values do not fit the printed columns. Check the row against the PDF before entering its fields.'])
                result.append(item)
                previous_balance = None
                continue
        else:
            role_cells = {role: cells[col] for col, role in roles.items() if col in cells}
        texts = {role: cell['expected_text'] for role, cell in role_cells.items()}
        fields = item['fields']
        fields.update({role+'_column': str(cell['column_index']) for role, cell in role_cells.items()})
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
