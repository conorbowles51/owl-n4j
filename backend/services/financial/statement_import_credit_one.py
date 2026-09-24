"""Read Credit One card cycles from their own headings and measured tables.

One PDF may contain unrelated banks, cards, accounts and cycles. Only an exact
issuer heading, account number and complete cycle establish this reader. The
original cells are retained; ambiguous OCR digits are never guessed from totals.
"""
import re
from datetime import datetime, date

from services.financial.pdf_candidates import _digest
from services.financial.statement_import_proposal import exact_amount
from services.financial.statement_import_card_balances import balance_control
from services.financial.statement_layout_context import card_row_dates

LAYOUT = 'credit-one-card'
HEADING = 'CREDIT ONE BANK CREDIT CARD STATEMENT'


def _text(row):
    return ' '.join(c['expected_text'].strip() for c in row['cells'])


def _box(cell):
    locator = cell.get('locator') or {}
    box = locator.get('rect')
    return box if (locator.get('kind') == 'page_rectangle' and isinstance(box, list)
        and len(box) == 4 and all(type(v) is int for v in box)
        and box[0] < box[2] and box[1] < box[3]) else None


def _cycle(text):
    # The separator is a word, never a repair to a date or account digit.
    match = re.fullmatch(r'([A-Za-z]+ \d{2}, 20\d{2}) (?:to|lo|t\s+io) ([A-Za-z]+ \d{2}, 20\d{2})', text)
    if not match:
        return None
    try:
        start, end = (datetime.strptime(v, '%B %d, %Y').date() for v in match.groups())
    except ValueError:
        return None
    return (start.isoformat(), end.isoformat()) if 0 <= (end-start).days <= 62 else None


def _holder(rows):
    """Coupon addressee above a street and US city/ZIP, beside the bank address."""
    cells = [c for r in rows for c in r['cells'] if _box(c)]
    names = set()
    for city in cells:
        box = _box(city)
        width, height = city['locator']['page_size']
        if (box[0] < width / 2 or box[1] < height / 2
                or not re.fullmatch(r"[A-Z][A-Z .'-]+ [A-Z]{2} \d{5}(?:-\d{4})?", city['expected_text'].strip())):
            continue
        streets = [c for c in cells if abs(_box(c)[0]-box[0]) < width/50
            and 0 <= box[1]-_box(c)[3] < height/50
            and re.match(r'\d+ [A-Z0-9]', c['expected_text'].strip())]
        if len(streets) != 1:
            continue
        street = _box(streets[0])
        above = [c for c in cells if abs(_box(c)[0]-box[0]) < width/50
            and 0 <= street[1]-_box(c)[3] < height/50
            and re.fullmatch(r"[A-Z][A-Z .'-]{3,100}", c['expected_text'].strip())]
        if len(above) == 1:
            names.add(above[0]['expected_text'].strip())
    return next(iter(names)) if len(names) == 1 else ''


def credit_one_catalog(sources):
    pages = {}
    for source in sources:
        pages.setdefault(source['page_number'], []).append(source)
    groups, handled = {}, set()
    for number, page_sources in pages.items():
        rows = [r for s in page_sources for r in s['rows']]
        top = [r for r in rows if r['cells'] and all(_box(c)
            and _box(c)[3] < c['locator']['page_size'][1] * .15 for c in r['cells'])]
        if sum(_text(r) == HEADING for r in top) != 1:
            continue
        if sum(_text(r).startswith('Account Number') for r in top) != 1:
            continue
        accounts = {re.sub(r'\s', '', m[1]) for r in top
            if (m := re.fullmatch(r'Account Number:? ([\d ]{13,24})', _text(r)))
            and 13 <= len(re.sub(r'\s', '', m[1])) <= 19}
        periods = {p for r in top if (p := _cycle(_text(r)))}
        if len(accounts) != 1 or len(periods) != 1:
            continue
        start, end = next(iter(periods))
        identity = dict(layout_id=LAYOUT, institution='Credit One Bank',
            account_reference=next(iter(accounts)), period_start=start, period_end=end)
        identifier = _digest(identity)
        group = groups.setdefault(identifier, dict(id=identifier, **identity,
            account_type='credit_card', sources=[], page_numbers=[], holder=''))
        holder = _holder(rows)
        group.setdefault('_holders', set()).update([holder] if holder else [])
        group['page_numbers'].append(number)
        for source in page_sources:
            group['sources'].append(dict(page_number=number, table_index=source['table_index'],
                source_revision=source['source_revision']))
            handled.add((number, source['table_index']))
    for group in groups.values():
        holders = group.pop('_holders')
        group['holder'] = next(iter(holders)) if len(holders) == 1 else ''
    return list(groups.values()), handled


def _balances(source, currency):
    """Only the activity summary; exclude repeated balances in payment/coupon boxes."""
    cells = [(r['row_index'], c) for r in source['rows'] for c in r['cells'] if _box(c)]
    headings = [c for _, c in cells if c['expected_text'].strip() == 'SUMMARY OF ACCOUNT ACTIVITY']
    right = [c for _, c in cells if c['expected_text'].strip() == 'PAYMENT INFORMATION']
    if not headings:
        return {}
    if len(headings) != 1 or len(right) != 1:
        return {}
    left_box, right_box = _box(headings[0]), _box(right[0])
    if left_box[2] >= right_box[0] or max(left_box[1], right_box[1]) >= min(left_box[3], right_box[3]):
        return {}
    height = headings[0]['locator']['page_size'][1]
    opening_labels = [c for _, c in cells if c['expected_text'].strip() == 'Previous Balance'
        and _box(c)[2] < right_box[0] and left_box[3] <= _box(c)[1] < left_box[3] + height/10]
    if len(opening_labels) != 1:
        return {}
    opening_x = _box(opening_labels[0])[0]
    tolerance = headings[0]['locator']['page_size'][0] / 50
    result = {}
    for role, name in [('opening', 'Previous Balance'), ('closing', 'New Balance')]:
        labels = [(i, c) for i, c in cells if c['expected_text'].strip() == name
            and abs(_box(c)[0] - opening_x) < tolerance
            and _box(c)[2] < right_box[0] and left_box[3] <= _box(c)[1] < left_box[3] + height/5]
        if len(labels) != 1:
            continue
        index, label = labels[0]
        values = sorted([c for i, c in cells if i == index and _box(label)[2] <= _box(c)[0]
            and _box(c)[2] < right_box[0]], key=lambda c: _box(c)[0])
        if values:
            value = values[0]
            raw = value['expected_text'].strip(' |[]')
            # A trailing minus is this layout's printed credit-balance sign.
            # No letters or digits are changed; keep the original source cell.
            if re.fullmatch(r'\$?\d[\d,]*\.\d{2}-', raw):
                raw = '-' + raw[:-1]
            result[index] = balance_control(role, label, {**value, 'expected_text': raw}, currency)
    return result


def propose_credit_one_table(source, currency, statement):
    controls = _balances(source, currency)
    result, active, header, previous = [], False, None, None
    section = 'Transactions'
    for row in source['rows']:
        cells = row['cells']
        texts = [c['expected_text'].strip() for c in cells]
        text = ' '.join(texts)
        item = dict(id=f"{source['page_number']}:{source['table_index']}:{row['row_index']}",
            page_number=source['page_number'], table_index=source['table_index'], row_index=row['row_index'],
            source_revision=source['source_revision'], source_cells=cells, fields={},
            issues=[], excluded=True, kind='statement_information')
        result.append(item)
        if row['row_index'] in controls:
            item.update(controls[row['row_index']])
            continue
        if text == 'TRANSACTIONS':
            active, header, previous = True, None, None
            continue
        if not active:
            continue
        if (re.match(r'^20\d{2} Totals Year-to', text) or text == 'INTEREST CHARGE CALCULATION'
                or text.startswith('YOUR ACCOUNT ') or text.startswith('Please return')):
            active, previous = False, None
            continue
        if ('Reference Number' in texts and 'Amount' in texts
                and re.search(r'Trans Date\s+Post Date\s+Description of\s*Transaction or Credit', text)):
            date_cells = [c for c in cells if c['expected_text'].startswith('Trans Date')]
            amount_cells = [c for c in cells if c['expected_text'] == 'Amount']
            if len(date_cells) == len(amount_cells) == 1 and _box(date_cells[0]) and _box(amount_cells[0]):
                header = (_box(date_cells[0])[0], _box(amount_cells[0])[2])
            continue
        if text in ('Fees', 'Interest Charged', 'Payments, Credits, and Adjustments', 'Purchases'):
            section, previous = text, None
            continue
        if text.startswith(('TOTAL FEES FOR THIS ', 'TOTAL INTEREST FOR THIS ')):
            previous = None
            continue
        if not header:
            if re.search(r'\d', text):
                item.update(kind='unresolved', excluded=False,
                    issues=['Check this card payment against the PDF. Its transaction columns could not be located.'])
            continue
        if not all(_box(c) for c in cells):
            item.update(kind='unresolved', excluded=False,
                issues=['Check this payment against the PDF. Its source positions are unavailable.'])
            continue
        width = cells[0]['locator']['page_size'][0] if cells else 0
        values = [c for c in cells if abs(_box(c)[2]-header[1]) <= width/50
            and _box(c)[0] > header[0]]
        body = [c for c in cells if _box(c)[0] >= header[0] - width/100 and c not in values]
        # Preserve wrapped descriptions without treating a reference or a date
        # printed on a continuation line as another transaction.
        if not values and previous and body and body == cells and not re.match(r'\d', text):
            previous['fields']['description'] += ' ' + text
            previous.setdefault('continuation_sources', []).append(dict(page_number=source['page_number'],
                row_index=row['row_index'], source_cells=cells))
            item.update(kind='continuation', fields=dict(parent_transaction_id=previous['id']))
            continue
        item.update(kind='transaction', excluded=False)
        if len(values) != 1 or len(body) < 3:
            item.update(kind='unresolved', issues=['Check the dates, description and amount of this card payment against the PDF.'])
            previous = None
            continue
        trans, post, *description = body
        trans_text, post_text = trans['expected_text'].strip(), post['expected_text'].strip()
        # A printed column may be joined to the description by OCR. Keep its
        # exact suffix in the description and bind both fields to that cell.
        joined_post = re.fullmatch(r'(\d{2}/\d{2})[.,]?\s+(.+)', post_text)
        description_text = ' '.join(c['expected_text'].strip() for c in description)
        if joined_post:
            post_text = joined_post[1]
            description_text = joined_post[2] + ' ' + description_text
        def date_text(value):
            return value.rstrip('.,') if re.fullmatch(r'\d{2}/\d{2}[.,]', value) else value
        fields = item['fields']
        fields.update(description=description_text,
            counterparty='', printed_section=section, card_ending=statement['account_reference'][-4:],
            date_column=str(trans['column_index']), booking_date_column=str(post['column_index']),
            amount_column=str(values[0]['column_index']))
        reference = [c['expected_text'].strip() for c in cells if _box(c)[2] <= header[0]]
        if reference:
            fields['reference'] = ' '.join(reference)
        _, dates, postings, _ = card_row_dates(date_text(trans_text), date_text(post_text),
            date.fromisoformat(statement['period_start']), date.fromisoformat(statement['period_end']))
        if len(dates) == 1:
            fields['date'] = dates[0]
        else:
            item['issues'].append('Check the transaction date against this card billing period.')
        if len(postings) == 1:
            fields['booking_date'] = postings[0]
        else:
            item['issues'].append('Check the posting date against this card billing period.')
        try:
            amount = int(exact_amount(values[0]['expected_text'], currency))
            fields.update(amount_minor=str(abs(amount)), direction='credit' if amount < 0 else 'debit')
            if amount == 0 and section == 'Interest Charged':
                item.update(excluded=True, kind='zero_charge', issues=[])
            elif amount == 0:
                item['issues'].append('Check whether this zero-value entry belongs in the transaction list.')
        except ValueError:
            item['issues'].append('Check this card amount against the PDF. Its sign or digits could not be read.')
        previous = item if not item['excluded'] else None
    return dict(rows=result, issues=[])
