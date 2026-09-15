"""Read Andrews savings/checking sections without mixing their account shares.

Recognition uses the measured account/period heading and each printed share
heading. Continuations use adjacent source pages or a complete block ordered by
unique printed page numbers. They require the same account and period, a prior
continuation notice and no conflicting page number.
Original cells are retained, including joined or damaged OCR money fields.
"""
import re
from datetime import date

from services.financial.pdf_candidates import _digest
from services.financial.statement_import_proposal import exact_amount

_LAYOUT = 'andrews-share-statement'
_DATE = r'\d{2}/\d{2}'
_SPACED_MONEY = r'[+-]?\s*(?:\d{1,3}(?:,\d{3})+|\d+)\s*\.\s*\d{2}'
_FULL_DATE = r'\d\s*\d\s*/\s*\d\s*\d\s*/\s*(?:2\s*0\s*)?\d\s*\d'
_TYPES = {'BASE SHARE SAVINGS': 'savings', 'FREE CHECKING': 'checking', 'VISA PAYMENT': 'other'}
# OCR may insert spaces inside a fixed printed label. Match its letters exactly;
# this does not repair account numbers, dates, amounts or substituted glyphs.
_PREVIOUS = re.compile(r'(?<![A-Za-z])' + r'\s*'.join('PreviousBalance') + r'(?![A-Za-z])')
_SHARE = re.compile(r'^(\d{2}/\d{2}) ID (\d{4}) (BASE SHARE SAVINGS|FREE CHECKING|VISA PAYMENT) ' + _PREVIOUS.pattern + r'(?: |$)')
_SHARE_LABEL = re.compile(r'^\d{2}/\d{2} ID \S+ (BASE SHARE SAVINGS|FREE CHECKING|VISA PAYMENT)(?: |$)')

_CLOSED = re.compile(r'^(\d{2}/\d{2}) ID (\d{4}) (BASE SHARE SAVINGS|FREE CHECKING|VISA PAYMENT) Closed$')

def _text(row):
    return ' '.join(c['expected_text'].strip() for c in row['cells']).strip()


def _box(cell):
    value = cell.get('locator', {})
    rect = value.get('rect')
    if (not isinstance(rect, list) or len(rect) != 4 or
            not all(type(v) is int for v in rect) or not rect[0] < rect[2] or not rect[1] < rect[3]):
        return None
    return rect


def _full_date(value):
    m = re.fullmatch(r'(\d{2})/(\d{2})/(20\d{2}|\d{2})', re.sub(r'\s+', '', value))
    if not m:
        return None
    try:
        return date(int(m[3]) + (2000 if len(m[3]) == 2 else 0), int(m[1]), int(m[2]))
    except ValueError:
        return None


def andrews_page(source, *, allow_unbranded=False):
    """Identify the heading, never a number from the body or an application."""
    rows = source['rows']
    cells = [c for r in rows for c in r['cells']]
    marks = [c for c in cells if re.fullmatch(r'\.?Andrews', c['expected_text'].strip()) and _box(c)]
    titles = [c for c in cells if re.fullmatch(r'Account[-·]?Statement', re.sub(r'\s+', '', c['expected_text'])) and _box(c)]
    if len(titles) != 1 or len(marks) > 1 or (not marks and not allow_unbranded):
        return None
    size = titles[0]['locator'].get('page_size', [])
    if not isinstance(size, list) or len(size) != 2:
        return None
    width, height = size
    if (type(width) is not int or type(height) is not int or
            not width * .4 < _box(titles[0])[0] or _box(titles[0])[3] > height * .15 or
            any(_box(c)[0] >= width * .4 or _box(c)[3] > height * .15 for c in marks)):
        return None
    top = [r for r in rows if r['cells'] and all(_box(c) and _box(c)[3] < height * .2 for c in r['cells'])]
    accounts = [(r, c) for r in top for c in r['cells'] if re.fullmatch(r'\d{9}', c['expected_text'].strip())
                and _box(c)[0] > width * .4]
    cycles = []
    for row in top:
        m = re.fullmatch(r'(' + _FULL_DATE + r')\s+(' + _FULL_DATE + r')', _text(row))
        if m:
            a, b = _full_date(m[1]), _full_date(m[2])
            if a and b and 0 <= (b-a).days <= 62:
                cycles.append((row, a, b))
    if len(accounts) != 1 or len(cycles) != 1:
        return None
    account_row, account = accounts[0]
    cycle_row, start, end = cycles[0]
    if account_row['row_index'] >= cycle_row['row_index']:
        return None
    following = next((r for r in rows if r['row_index'] > cycle_row['row_index']), None)
    page_number = None
    if following and re.fullmatch(r'\d{1,3}', _text(following)):
        page_number = int(_text(following))
    body = following['row_index'] + 1 if page_number is not None else cycle_row['row_index'] + 1
    return dict(account=account['expected_text'].strip(), start=start.isoformat(), end=end.isoformat(),
                branded=bool(marks),
                printed_page=page_number, body_start=body, width=width,
                heading_rows=[r['row_index'] for r in rows if r['row_index'] < body])


def _holder(rows):
    """The addressee lines immediately following the printed mailing marker."""
    names = []
    active = False
    for row in rows:
        text = _text(row)
        if re.fullmatch(r'>\d{8,12}<', text):
            active = True
        elif active:
            if re.fullmatch(r'[A-Z][A-Z .\'-]{3,95}', text):
                names.append(text)
            else:
                break
    value = ' / '.join(names)
    return value if len(value) <= 128 else ''


def _reading_order(sources):
    """Order a complete, uniquely numbered block by its printed page numbers.

    The physical pages must be contiguous and print the same account/period.
    Missing or repeated numbers keep their original order. No number is inferred
    for an unreadable heading. Original page addresses are never changed.
    """
    ordered = sorted(sources, key=lambda s: (s['page_number'], s['table_index']))
    block = []

    def emit():
        numbers = [page['printed_page'] for _, page in block]
        if (len(numbers) > 1 and sorted(numbers) == list(range(1, len(numbers)+1))
                and next(page for _, page in block if page['printed_page'] == 1)['branded']
                and numbers != sorted(numbers)):
            group = (block[0][0]['page_number'], block[0][0]['table_index'])
            return [(source, group) for source, _ in sorted(block, key=lambda item: item[1]['printed_page'])]
        return [(source, None) for source, _ in block]

    for source in ordered:
        page = andrews_page(source, allow_unbranded=True)
        if page is None or page['printed_page'] is None:
            yield from emit()
            block = []
            yield source, None
            continue
        if block:
            previous_source, previous = block[-1]
            if (source['page_number'] != previous_source['page_number'] + 1 or
                    source['table_index'] != previous_source['table_index'] or
                    any(page[k] != previous[k] for k in ('account', 'start', 'end'))):
                yield from emit()
                block = []
        block.append((source, page))
    yield from emit()


def andrews_catalog(sources):
    groups = {}
    handled = set()
    incomplete = set()
    previous = None
    active = None
    for source, order_group in _reading_order(sources):
        page = andrews_page(source, allow_unbranded=True)
        key = (source['page_number'], source['table_index'])
        if page is None:
            active = None
            previous = None
            continue
        follows = (previous and (key == (previous['pdf_page'] + 1, previous['table_index']) or
                   order_group is not None and order_group == previous['order_group']))
        continues = (follows and active
                     and previous['continues'] and page['account'] == previous['account']
                     and (page['start'], page['end']) == (previous['start'], previous['end'])
                     and (page['printed_page'] is None or previous['printed_page'] is None
                          or page['printed_page'] == previous['printed_page'] + 1)
                     and page['printed_page'] != 1)
        # A missing logo can be tolerated only within an already identified
        # statement, never as the start of an otherwise anonymous document.
        if not page['branded'] and not continues:
            active = None
            previous = None
            continue
        if not continues:
            active = None
        addressed = set()
        unknown = False
        for row in source['rows']:
            if row['row_index'] < page['body_start']:
                continue
            text = _text(row)
            if 'Continued on following page' in text:
                break
            match = _SHARE.match(text)
            if _PREVIOUS.search(text) or (_SHARE_LABEL.match(text) and not _CLOSED.fullmatch(text)):
                active = None
                if match:
                    identity = dict(layout_id=_LAYOUT, institution='Andrews Federal Credit Union',
                        account_reference=page['account'] + ' / Share ' + match[2],
                        main_account_reference=page['account'], share_reference=match[2],
                        account_label=match[3], account_type=_TYPES[match[3]],
                        period_start=page['start'], period_end=page['end'])
                    # Another opening heading is another statement occurrence,
                    # even when account and dates match an earlier copy.
                    identifier = _digest(dict(**identity, opening_source=[*key, row['row_index']]))
                    active = groups.setdefault(identifier, dict(id=identifier, **identity,
                        holder=_holder(source['rows']), sources=[], page_numbers=[]))
                else:
                    unknown = True
            if active is not None:
                if order_group is not None:
                    active['uses_printed_page_order'] = True
                scope = next((s for s in active['sources'] if (s['page_number'], s['table_index']) == key), None)
                if scope is None:
                    scope = dict(page_number=key[0], table_index=key[1], source_revision=source['source_revision'],
                                 row_indices=[], heading_rows=page['heading_rows'])
                    active['sources'].append(scope)
                    active['page_numbers'].append(key[0])
                scope['row_indices'].append(row['row_index'])
                addressed.add(active['id'])
            elif re.match(r'^\d{2}/\d{2}(?: |$)', text):
                unknown = True
            closure = _CLOSED.fullmatch(text)
            if closure and active:
                closed_on = _period_date(closure[1], active)
                if closure[2] == active['share_reference'] and closure[3] == active['account_label'] and closed_on:
                    active['account_closure'] = dict(date=closed_on, page_number=source['page_number'], table_index=source['table_index'],
                        row_index=row['row_index'], source_cells=row['cells'])
                else:
                    unknown = True
                active = None
            if re.match(r'^\d{2}/\d{2} Ending Balance(?: |$)', text):
                active = None
        if addressed:
            handled.add(key)
        if unknown:
            incomplete.add(key)
        previous = dict(**page, pdf_page=key[0], table_index=key[1], order_group=order_group,
                        continues=any('Continued on following page' in _text(r) for r in source['rows']))
    return list(groups.values()), handled, incomplete


def _period_date(text, statement):
    if not re.fullmatch(_DATE, text):
        return None
    start, end = date.fromisoformat(statement['period_start']), date.fromisoformat(statement['period_end'])
    options = set()
    for year in range(start.year, end.year+1):
        value = _full_date(text + '/' + str(year))
        if value and start <= value <= end:
            options.add(value.isoformat())
    return next(iter(options)) if len(options) == 1 else None


def andrews_source_regions(sources, statement):
    """Physical account sections remain comparable when OCR renumbers rows."""
    lookup = {(s['page_number'], s['table_index']): s for s in sources}
    result = []
    for scope in statement['sources']:
        source = lookup[(scope['page_number'], scope['table_index'])]
        cells = [c for r in source['rows'] if r['row_index'] in scope['row_indices'] for c in r['cells']]
        if not cells or any(_box(c) is None for c in cells):
            return None
        locator = cells[0]['locator']
        if any((c['locator'].get('page_size'), c['locator'].get('space')) !=
               (locator.get('page_size'), locator.get('space')) for c in cells):
            return None
        result.append(dict(page_number=scope['page_number'], table_index=scope['table_index'],
            page_size=locator['page_size'], space=locator['space'],
            top=min(_box(c)[1] for c in cells), bottom=max(_box(c)[3] for c in cells)))
    return result


def source_regions_overlap(current, previous):
    """None means incomparable coordinate spaces, requiring a broader check."""
    if not current or not previous:
        return None
    overlapping = False
    for a in current:
        for b in previous:
            if a['page_number'] != b['page_number']:
                continue
            if (a['page_size'], a['space']) != (b['page_size'], b['space']):
                return None
            overlapping |= min(a['bottom'], b['bottom']) > max(a['top'], b['top'])
    return overlapping


def _amount(text, currency):
    if not re.fullmatch(_SPACED_MONEY, text):
        raise ValueError('Check the amount in the PDF, including its sign and decimal point.')
    return int(exact_amount(re.sub(r'\s+', '', text), currency))


def _money_cells(row, width):
    return [c for c in row['cells'] if _box(c) and _box(c)[0] >= width * .46]


def propose_andrews_statement(sources, currency, statement):
    result = []
    previous_balance = None
    previous_payment = None
    scopes = {(s['page_number'], s['table_index']):s for s in statement['sources']}
    order = {key: index for index, key in enumerate(scopes)}
    for source in sorted(sources, key=lambda s: order[(s['page_number'], s['table_index'])]):
        page = andrews_page(source, allow_unbranded=True)
        scope = scopes[(source['page_number'], source['table_index'])]
        for row in source['rows']:
            index = row['row_index']
            if index not in scope['row_indices'] and index not in scope['heading_rows']:
                continue
            cells = row['cells']
            text = _text(row)
            item = dict(id=f"{source['page_number']}:{source['table_index']}:{index}",
                        page_number=source['page_number'], table_index=source['table_index'], row_index=index,
                        source_revision=source['source_revision'], source_cells=cells, fields={},
                        issues=[], excluded=True, kind='statement_information')
            result.append(item)
            if index not in scope['row_indices']:
                continue
            item['fields']['statement_layout'] = _LAYOUT
            if 'Continued on following page' in text:
                continue
            closure = statement.get('account_closure')
            if (closure and source['page_number'] == closure['page_number']
                    and source['table_index'] == closure['table_index'] and index == closure['row_index']):
                item['fields'].update(account_closed_on=closure['date'], description=text)
                continue
            money_cells = _money_cells(row, page['width'])
            money = ' '.join(c['expected_text'].strip() for c in money_cells)
            body = ' '.join(c['expected_text'].strip() for c in cells if c not in money_cells)
            opening = _SHARE.match(body)
            closing = re.fullmatch(r'(\d{2}/\d{2}) Ending Balance', body)
            if opening or closing:
                item.update(kind='balance')
                fields = item['fields']
                fields['description'] = 'Opening Balance' if opening else 'Closing Balance'
                fields['date'] = _period_date((opening or closing)[1], statement) or ''
                if money_cells:
                    fields['balance_column'] = str(money_cells[-1]['column_index'])
                try:
                    fields['balance'] = str(_amount(money, currency))
                except ValueError:
                    item['issues'].append('Check this balance in the PDF. Its digits or decimal point could not be read.')
                if opening:
                    previous_balance = int(fields['balance']) if 'balance' in fields else None
                elif 'balance' in fields and previous_balance is not None and int(fields['balance']) != previous_balance:
                    item['issues'].append('The closing balance differs from the last transaction balance. Check for a missing transaction or a misread balance.')
                previous_payment = None
                continue
            # Continuation references can also begin MM/DD; only a transaction
            # verb or a measured date + money row can begin another payment.
            parsed = re.match(r'^(\S+)(?: (\d{2}/\d{2}))? ((?:Recurring )?(?:Withdrawal|Deposit)\b.*)$', body)
            first_box = _box(cells[0]) if cells else None
            dated_money = (first_box and first_box[0] < page['width'] * .08 and money_cells
                           and re.match(r'^\S{4,7}(?: |$)', body))
            if parsed or dated_money:
                item.update(excluded=False, kind='transaction' if parsed else 'unresolved')
                fields = item['fields']
                date_text = parsed[1] if parsed else body.split(' ', 1)[0]
                value = _period_date(date_text, statement)
                if value:
                    fields['date'] = value
                else:
                    item['issues'].append('Check the full date in the PDF. It could not be read within this statement period.')
                fields['date_column'] = str(cells[0]['column_index'])
                fields['description'] = parsed[3] if parsed else body.partition(' ')[2]
                fields['counterparty'] = ''
                if parsed and parsed[2]:
                    fields['additional_printed_date'] = parsed[2]
                    item['issues'].append('This line prints a second date without a heading. Check which date belongs to the transaction.')
                pair = re.fullmatch(r'(' + _SPACED_MONEY + r')\s+(.+)', money)
                amount_text, balance_text = (pair[1], pair[2]) if pair else ('', '')
                if pair is None:
                    trailing = re.fullmatch(r'(.+)\s+(' + _SPACED_MONEY + r')', money)
                    if trailing:
                        amount_text, balance_text = trailing[1], trailing[2]
                if len(money_cells) == 2:
                    amount_text, balance_text = [c['expected_text'].strip() for c in money_cells]
                try:
                    amount = _amount(amount_text, currency)
                    fields.update(amount_minor=str(abs(amount)), amount_column=str(money_cells[0]['column_index']))
                    description = fields['description']
                    conflict = (amount > 0 and 'Withdrawal' in description and 'Adjustment' not in description
                                or amount < 0 and description.startswith('Deposit'))
                    if conflict or not parsed:
                        item['issues'].append('Check whether money entered or left the account. The description and amount sign need review.')
                    else:
                        fields['direction'] = 'credit' if amount >= 0 else 'debit'
                except ValueError:
                    item['issues'].append('Check the transaction amount in the PDF. Its digits, sign or decimal point could not be read.')
                try:
                    fields['balance'] = str(_amount(balance_text, currency))
                    fields['balance_column'] = str(money_cells[-1]['column_index'])
                except ValueError:
                    item['issues'].append('Check the running balance in the PDF. It could not be read separately from the transaction amount.')
                if previous_balance is not None and all(k in fields for k in ('balance', 'amount_minor', 'direction')):
                    movement = int(fields['amount_minor']) * (1 if fields['direction'] == 'credit' else -1)
                    delta = int(fields['balance']) - previous_balance - movement
                    fields['balance_difference_minor'] = str(delta)
                    if delta:
                        item['issues'].append('The running balance does not match this payment. Check the amount, balance or a missing row.')
                previous_balance = int(fields['balance']) if 'balance' in fields else None
                previous_payment = item
            elif previous_payment is not None:
                item['kind'] = 'continuation'
                previous_payment['fields']['description'] += '\n' + text
                previous_payment.setdefault('continuation_sources', []).append(dict(
                    page_number=source['page_number'], row_index=index, source_cells=cells))
            else:
                item.update(excluded=False, kind='unresolved')
                item['issues'].append('Check this line in the account section. It could not be linked to a transaction.')
    issues = []
    for name in ('Opening Balance', 'Closing Balance'):
        controls = [r for r in result if r['kind'] == 'balance' and r['fields'].get('description') == name]
        if not controls and not (name == 'Closing Balance' and statement.get('account_closure')):
            issues.append(f'The {name.lower()} was not found for this account section. Check the PDF for a missing or unreadable page.')
    return dict(rows=result, issues=issues)
