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

VERSION = 'statement-review-v21'
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


def _printed_layouts(source, header, following, roles):
    """Find column boundaries supported by the rows below this printed header.

    Text-alignment cells omit blank columns. Headings may be left, centre or
    right aligned while amounts are right aligned. Compare those three layouts
    across the section rather than assuming the gap midpoint for each value.
    Equal-scoring layouts remain alternatives: a row is mapped only when they
    agree, so a lone ambiguous credit/debit value is not guessed.
    """
    headings = [(c, _rect(c, source['page_number'])) for c in header]
    if not headings or any(p is None for _, p in headings):
        return []
    size = headings[0][1][1]
    headings.sort(key=lambda item: item[1][0][0])
    if any(p[1] != size for _, p in headings):
        return []
    gaps = []
    money_roles = {'credit', 'debit', 'amount', 'balance'}
    for (left_cell, left), (right_cell, right) in zip(headings, headings[1:]):
        if left[0][2] >= right[0][0]:
            return []
        gaps.append((left[0][2], right[0][0],
                     roles.get(left_cell['column_index']) in money_roles
                     and roles.get(right_cell['column_index']) in money_roles))
    layouts = []
    for fraction in (0.0, 0.5, 1.0):
        boundaries = [0, *[start + (end-start)*(fraction if numeric else 0.5)
                           for start, end, numeric in gaps], size[0]]
        score = 0
        for row in following:
            labels = {_HEADERS.get(' '.join(c['expected_text'].lower().split())) for c in row['cells']}
            if labels & {'date', 'booking_date', 'value_date'} and labels & {'credit', 'debit', 'amount'}:
                break
            assigned = _assign_printed_cells(source, headings, boundaries, row, roles)
            if assigned and (assigned.keys() & {'date', 'booking_date', 'value_date'}
                             and assigned.keys() & {'credit', 'debit', 'amount', 'balance'}):
                score += 1
        layouts.append((score, headings, boundaries))
    best = max(layout[0] for layout in layouts)
    return [(headings, boundaries) for score, headings, boundaries in layouts if score == best]


def _assign_printed_cells(source, headings, boundaries, row, roles):
    size = headings[0][1][1]
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


def _printed_roles(source, layouts, row, roles):
    assignments = [_assign_printed_cells(source, headings, boundaries, row, roles)
                   for headings, boundaries in layouts]
    if not assignments or any(assignment is None for assignment in assignments):
        return None
    first = assignments[0]
    if any(assignment != first for assignment in assignments[1:]):
        return None
    return first


def _statement_heading(row):
    if len(row['cells']) != 1:
        return False
    text = ' '.join(row['cells'][0]['expected_text'].split())
    return bool(re.fullmatch(r'(?:Account (?:Name|Holder|Number|No)|IBAN|Statement Period|Period|Currency|Bank|Institution|Reference): .+', text, re.I)
                or re.fullmatch(r'(?:BANK|BUSINESS ACCOUNT|ACCOUNT) STATEMENT(?: - .+)?', text, re.I)
                or text == 'BENEFICIARY FOR OUTGOING TRANSFERS'
                or re.fullmatch(r'[A-Z .&]+(?:BANK|CREDIT UNION)(?:,? N[.]?A[.]?)?', text))


def _statement_page_number(row):
    if len(row['cells']) != 1:
        return False
    text = ' '.join(row['cells'][0]['expected_text'].split())
    return bool(re.fullmatch(r'Page [1-9][0-9]* (?:of|/) [1-9][0-9]*', text, re.I))


def has_transaction_header(source):
    for row in source['rows']:
        roles = {_HEADERS.get(' '.join(c['expected_text'].lower().split())) for c in row['cells']}
        if roles & {'date', 'booking_date', 'value_date'} and roles & {'credit', 'debit', 'amount'}:
            return True
    return False


def propose_table(source, currency, *, page_has_transaction_table=False):
    """Interpret labelled columns automatically; preserve every unexplained row."""
    get_currency(currency)
    roles = None
    header = []
    layouts = []
    result = []
    previous_balance = None
    for index, row in enumerate(source['rows']):
        cells = {c['column_index']: c for c in row['cells']}
        labels = [(c['column_index'], _HEADERS.get(' '.join(c['expected_text'].lower().split()))) for c in row['cells']]
        known = [(column, role) for column, role in labels if role]
        possible = dict(known)
        is_header = any(r in ('date', 'booking_date', 'value_date') for r in possible.values()) and any(r in ('credit', 'debit', 'amount') for r in possible.values())
        item = dict(id=f"{source['page_number']}:{source['table_index']}:{row['row_index']}",
                    page_number=source['page_number'], table_index=source['table_index'],
                    row_index=row['row_index'], source_revision=source['source_revision'],
                    source_cells=row['cells'], fields={}, issues=[], excluded=False, kind='transaction')
        if (page_has_transaction_table or roles is not None) and _statement_page_number(row):
            item.update(kind='header', excluded=True)
            result.append(item)
            continue
        if is_header:
            if len(set(possible.values())) != len(possible):
                roles = None
                item.update(kind='unresolved', issues=['Several columns have the same meaning. Check the table layout.'])
            else:
                roles = possible
                header = row['cells']
                if source.get('table_source') == 'text_alignment':
                    layouts = _printed_layouts(source, header, source['rows'][index+1:], roles)
                # Exclude only explicit statement metadata above a recognised table.
                for earlier in result:
                    if earlier['kind'] == 'unresolved' and _statement_heading({'cells': earlier['source_cells']}):
                        earlier.update(kind='header', excluded=True, issues=[])
                item.update(kind='header', excluded=True)
            result.append(item)
            continue
        if roles is None:
            if page_has_transaction_table and (_statement_heading(row) or
                    len(row['cells']) == 1 and row['cells'][0]['expected_text'].strip() == 'TRANSACTION HISTORY'):
                item.update(kind='header', excluded=True)
            else:
                item.update(kind='unresolved', issues=['The system could not identify this row from a transaction header.'])
            result.append(item)
            continue
        if source.get('table_source') == 'text_alignment':
            role_cells = _printed_roles(source, layouts, row, roles)
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
        total_role = {
            'total credits': 'credit', 'total deposits': 'credit', 'total money in': 'credit',
            'total debits': 'debit', 'total withdrawals': 'debit', 'total money out': 'debit',
        }.get(' '.join(fields['description'].lower().split()))
        if total_role and not any(texts.get(role, '').strip() for role in ('date', 'booking_date', 'value_date')):
            # Only a labelled total in its matching amount column. Retain the
            # printed cells and let the reviewer correct an unreadable total.
            candidates = [role for role in ('credit', 'debit', 'amount', 'balance')
                          if texts.get(role, '').strip() not in ('', '-', '—')]
            if len(candidates) == 1 and candidates[0] in (total_role, 'amount'):
                role = candidates[0]
                fields.update(total_direction=total_role, balance_column=fields[role+'_column'])
                try:
                    fields['balance'] = exact_amount(texts[role], currency)
                except ValueError:
                    item['issues'].append('Check the printed statement total against the PDF.')
                item.update(kind='statement_total', excluded=True)
                result.append(item)
                continue
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
