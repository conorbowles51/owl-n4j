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
_DATE = r'\d\s*\d\s*/\s*\d\s*\d'
_SPACED_MONEY = r'[+-]?\s*(?:\d{1,3}(?:,\d{3})+|\d+)\s*\.\s*\d{2}'
_FULL_DATE = r'\d\s*\d\s*/\s*\d\s*\d\s*/\s*(?:2\s*0\s*)?\d\s*\d'
_TYPES = {'BASE SHARE SAVINGS': 'savings', 'FREE CHECKING': 'checking', 'VISA PAYMENT': 'other'}
# OCR may insert spaces inside a fixed printed label. Match its letters exactly;
# this does not repair account numbers, dates, amounts or substituted glyphs.
_PREVIOUS = re.compile(r'(?<![A-Za-z])' + r'\s*'.join('PreviousBalance') + r'(?![A-Za-z])')
_SHARE = re.compile(r'^(\d{2}/\d{2}) ID (\d{4}) (BASE SHARE SAVINGS|FREE CHECKING|VISA PAYMENT) ' + _PREVIOUS.pattern + r'(?: |$)')
_SHARE_LABEL = re.compile(r'^\d{2}/\d{2} ID \S+ (BASE SHARE SAVINGS|FREE CHECKING|VISA PAYMENT)(?: |$)')

_CLOSED = re.compile(r'^(\d{2}/\d{2}) ID (\d{4}) (BASE SHARE SAVINGS|FREE CHECKING|VISA PAYMENT) Closed$')
_WITHDRAWAL = r'\s*'.join('Withdrawal')
_DEPOSIT = r'\s*'.join('Deposit')
_RECURRING = r'\s*'.join('Recurring')
_PAYMENT = re.compile(r'^(' + _DATE + r'|\S+)(?: (' + _DATE + r'))? ((?:' + _RECURRING +
                      r'\s+)?(' + _WITHDRAWAL + '|' + _DEPOSIT + r')\b.*)$')
_DAMAGED_DATE_PAYMENT = re.compile(r'^(.{1,12}?) ((?:' + _RECURRING +
                                 r'\s+)?(' + _WITHDRAWAL + '|' + _DEPOSIT + r')\b.*)$')

def _text(row):
    return ' '.join(c['expected_text'].strip() for c in row['cells']).strip()


def _ending_balance(row, width):
    """Recognise the label without substituting characters in its date."""
    cells = row['cells']
    if len(cells) < 2 or cells[1]['expected_text'].strip() != 'Ending Balance':
        return None
    box = _box(cells[0])
    return (re.fullmatch(r'\S{4,7}', cells[0]['expected_text'].strip())
            if box and box[0] < width * .08 else None)


def is_andrews_fee_summary(source):
    page = andrews_page(source, allow_unbranded=True)
    if not page:
        return False
    body = [row for row in source['rows'] if row['row_index'] >= page['body_start']]
    labels = {_text(row) for row in body}
    def first(row):
        return row['cells'][0]['expected_text'].strip(' |[]') if row['cells'] else ''
    firsts = {first(row) for row in body}
    summary_labels = {'Total Returned Item Fees', 'Total Overdraft Fees',
                      'Dividends Paid Year to Date', 'Total Dividends Paid Year to Date'}
    def divider(row):
        text = _text(row)
        return (re.match(r'^[|\[]\s*-{3,}', text) and text.endswith('|')
                and not re.search(r'\d[,.]\d{2}\b|\d{1,2}/\d{1,2}|Withdrawal|Deposit|Recurring', text))
    if any(row['cells'] and first(row) not in summary_labels
           and re.search(r'\d', _text(row))
           and not divider(row)
           and not (len(row['cells']) == 1 and re.fullmatch(r'[\d,. ]+', _text(row))) for row in body):
        return False
    return (({'Total Returned Item Fees', 'Total Overdraft Fees'} <= firsts
             or bool({'Dividends Paid Year to Date', 'Total Dividends Paid Year to Date'} & firsts))
            and not any(re.match(r'^\S{4,7}\s+(?:ID|Withdrawal|Deposit|Recurring)\b', text)
                        or re.match(r'^\d{2}/\d{2}\b', text) for text in labels))


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
    relaxed_marker = False
    for index, row in enumerate(rows):
        text = _text(row)
        if re.fullmatch(r'>\d{8,12}<', text):
            active = True
        elif re.fullmatch(r'>\s*(?:\d\s*){8,12}«?<', text):
            # Spacing inside the mailing code and a doubled closing bracket
            # are not part of the holder's name. Require the complete postal
            # block below before accepting this less exact marker.
            active = relaxed_marker = True
        elif active:
            if re.fullmatch(r'[A-Z][A-Z .\'-]{3,95}', text):
                names.append(text)
            else:
                if relaxed_marker:
                    city = _text(rows[index + 1]) if index + 1 < len(rows) else ''
                    if (not 1 <= len(names) <= 3 or not re.fullmatch(r'\d+ [A-Z0-9 .#\'-]+', text)
                            or not re.fullmatch(r"[A-Z][A-Z .'-]+ [A-Z]{2} \d{5}(?:-\d{4})?", city)):
                        return ''
                    relaxed_marker = False
                break
    value = ' / '.join(names)
    return value if len(value) <= 128 and not relaxed_marker else ''


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


def _opening_corroborated_by_next_page(source, page, following):
    """An unreadable logo needs the next branded, matching printed page 2."""
    if (following is None or page['printed_page'] not in (None, 1)
            or following['page_number'] != source['page_number'] + 1
            or following['table_index'] != source['table_index']
            or not any(_SHARE.match(_text(r)) for r in source['rows'] if r['row_index'] >= page['body_start'])
            or not any('Continued on following page' in _text(r) for r in source['rows'])):
        return False
    next_page = andrews_page(following)
    return (next_page is not None and next_page['printed_page'] == 2
            and all(next_page[k] == page[k] for k in ('account', 'start', 'end')))


def andrews_catalog(sources):
    groups = {}
    handled = set()
    incomplete = set()
    previous = None
    active = None
    ordered = list(_reading_order(sources))
    for index, (source, order_group) in enumerate(ordered):
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
        following = ordered[index + 1][0] if index + 1 < len(ordered) else None
        # Exact printed account/period details and a branded next page can
        # establish an opening whose logo OCR missed. Never infer its dates.
        if not page['branded'] and not continues and not _opening_corroborated_by_next_page(source, page, following):
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
            if re.match(r'^\d{2}/\d{2} Ending Balance(?: |$)', text) or _ending_balance(row, page['width']):
                active = None
        if addressed:
            handled.add(key)
        if unknown:
            incomplete.add(key)
        previous = dict(**page, pdf_page=key[0], table_index=key[1], order_group=order_group,
                        continues=any('Continued on following page' in _text(r) for r in source['rows']))
    return list(groups.values()), handled, incomplete


def unassigned_andrews_groups(sources, handled):
    """Expose orphan payment pages for an explicit account assignment.

    A readable main account and period do not establish which share owns a
    continuation after a missing page. Keep its payments available for the
    existing reviewed row move, without allowing this group to be imported.
    """
    groups = []
    for source in sources:
        key = (source['page_number'], source['table_index'])
        if key in handled:
            continue
        page = andrews_page(source)
        if not page:
            continue
        body = [r for r in source['rows'] if r['row_index'] >= page['body_start']]
        if any(_SHARE_LABEL.match(_text(r)) or _PREVIOUS.search(_text(r)) for r in body):
            continue
        first = next((r for r in body if r['cells'] and _box(r['cells'][0])
                      and _box(r['cells'][0])[0] < page['width'] * .08
                      and (_PAYMENT.match(_text(r)) or _DAMAGED_DATE_PAYMENT.match(_text(r)))), None)
        if first is None:
            continue
        indices = []
        for row in body:
            if row['row_index'] < first['row_index']:
                continue
            if 'Continued on following page' in _text(row):
                break
            indices.append(row['row_index'])
            if _ending_balance(row, page['width']):
                break
        identity = dict(layout_id=_LAYOUT, main_account_reference=page['account'],
                        period_start=page['start'], period_end=page['end'],
                        unassigned_source=list(key))
        groups.append(dict(id=_digest(identity), **identity,
            institution='Andrews Federal Credit Union', account_reference='',
            account_label=f"Unassigned payments on PDF page {source['page_number']}",
            account_type='other', share_reference='', holder='', assignment_only=True,
            page_numbers=[source['page_number']],
            sources=[dict(page_number=key[0], table_index=key[1], source_revision=source['source_revision'],
                          row_indices=indices, heading_rows=page['heading_rows'])]))
    return groups


def _period_date(text, statement):
    text = re.sub(r'\s+', '', text)
    if not re.fullmatch(_DATE, text):
        return None
    start, end = date.fromisoformat(statement['period_start']), date.fromisoformat(statement['period_end'])
    options = set()
    for year in range(start.year, end.year+1):
        value = _full_date(text + '/' + str(year))
        if value and start <= value <= end:
            options.add(value.isoformat())
    return next(iter(options)) if len(options) == 1 else None


def _ordinary_additional_date(printed, primary):
    """Recognise nearby date text without assigning it a transaction-date role."""
    printed = re.sub(r'\s+', '', printed)
    if not primary or not re.fullmatch(_DATE, printed):
        return False
    first = date.fromisoformat(primary)
    for year in (first.year - 1, first.year):
        additional = _full_date(printed + '/' + str(year))
        if additional and 0 <= (first - additional).days <= 31:
            return True
    return False


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


def _amount(text, currency, *, separate_cell=False):
    # OCR can insert spaces between digits in one measured money cell. Only
    # join those spaces after geometry separates the amount from its balance.
    # Never join adjacent numbers in a combined amount/balance text cell or
    # replace letters, signs or decimal punctuation.
    value = re.sub(r'\s+', '', text)
    if not re.fullmatch(_SPACED_MONEY, text) and not (
            separate_cell and re.fullmatch(_SPACED_MONEY, value)):
        raise ValueError('Check the amount in the PDF, including its sign and decimal point.')
    return int(exact_amount(value, currency))


def _money_cells(row, width):
    return [c for c in row['cells'] if _box(c) and _box(c)[0] >= width * .46]


def _voucher_money(row, following, width, currency):
    """Read two specific long credit-voucher layouts, retaining their cells.

    A numeric suffix is accepted only after the exact printed payment label.
    A following line must contain only two measured money cells immediately
    beneath that label. No digit, sign, account or balance is inferred.
    """
    cells = row['cells']
    if len(cells) not in (2, 3) or not all(_box(c) for c in cells):
        return None
    date_cell, description_cell = cells[:2]
    if not (_box(date_cell)[0] < width * .08 and
            _box(date_cell)[2] <= _box(description_cell)[0] < width * .46):
        return None
    match = re.fullmatch(r'((?:Recurring )?Withdrawal Adjustment Debit Card Credit Voucher)'
                         r'(?:\s+(' + _SPACED_MONEY + r'))?', description_cell['expected_text'].strip())
    if not match:
        return None
    wrapped = match[2] is None
    if wrapped:
        if len(cells) != 2 or following is None or len(following['cells']) != 2:
            return None
        money_cells = _money_cells(following, width)
        if len(money_cells) != 2:
            return None
        amount_text, balance_text = [c['expected_text'].strip() for c in money_cells]
    else:
        if len(cells) != 3 or _box(cells[2])[0] < width * .46:
            return None
        money_cells = [description_cell, cells[2]]
        amount_text, balance_text = match[2], cells[2]['expected_text'].strip()
    measured = cells + (money_cells if wrapped else [])
    space = tuple(cells[0]['locator'].get(k) for k in ('page', 'page_size', 'space', 'units'))
    if any(tuple(c['locator'].get(k) for k in ('page', 'page_size', 'space', 'units')) != space
           for c in measured):
        return None
    left, right = [_box(c) for c in money_cells]
    if left[2] > right[0] or max(left[1], right[1]) >= min(left[3], right[3]):
        return None
    description_box = _box(description_cell)
    if wrapped:
        height = description_box[3] - description_box[1]
        if not (description_box[2] <= left[2] and
                description_box[3] - height * .25 <= min(left[1], right[1]) <= description_box[3] + height * 1.1):
            return None
    elif max(description_box[1], _box(date_cell)[1]) >= min(description_box[3], _box(date_cell)[3]):
        return None
    try:
        _amount(amount_text, currency, separate_cell=wrapped)
        _amount(balance_text, currency, separate_cell=True)
    except ValueError:
        return None
    return dict(body=date_cell['expected_text'].strip() + ' ' + match[1],
                money_cells=money_cells, amount_text=amount_text, balance_text=balance_text,
                source_row=following if wrapped else row, wrapped=wrapped)


def propose_andrews_statement(sources, currency, statement):
    result = []
    previous_balance = None
    previous_payment = None
    scopes = {(s['page_number'], s['table_index']):s for s in statement['sources']}
    order = {key: index for index, key in enumerate(scopes)}
    for source in sorted(sources, key=lambda s: order[(s['page_number'], s['table_index'])]):
        page = andrews_page(source, allow_unbranded=True)
        scope = scopes[(source['page_number'], source['table_index'])]
        money_continuations = {}
        for position, row in enumerate(source['rows']):
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
            if index in money_continuations:
                parent = money_continuations[index]
                item.update(kind='continuation')
                item['fields']['parent_transaction_id'] = parent['id']
                parent.setdefault('continuation_sources', []).append(dict(
                    page_number=source['page_number'], row_index=index, source_cells=cells))
                continue
            # The period/year-to-date fee summary is not a second set of fee
            # payments, even when it follows an account's continuation page.
            if (cells and cells[0]['expected_text'].strip() in
                    ('Total Returned Item Fees', 'Total Overdraft Fees') and len(cells) == 3):
                continue
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
            damaged_closing = not closing and _ending_balance(row, page['width'])
            if opening or closing or damaged_closing:
                item.update(kind='balance')
                fields = item['fields']
                fields['description'] = 'Opening Balance' if opening else 'Closing Balance'
                fields['date'] = (_period_date((opening or closing)[1], statement) or '') if opening or closing else ''
                if money_cells:
                    fields['balance_column'] = str(money_cells[-1]['column_index'])
                try:
                    fields['balance'] = str(_amount(money, currency, separate_cell=len(money_cells) == 1))
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
            parsed = _PAYMENT.match(body)
            first_box = _box(cells[0]) if cells else None
            damaged_date_payment = (_DAMAGED_DATE_PAYMENT.match(body)
                                    if not parsed and first_box and first_box[0] < page['width'] * .08 else None)
            dated_money = (first_box and first_box[0] < page['width'] * .08 and money_cells
                           and re.match(r'^\S{4,7}(?: |$)', body))
            if parsed or damaged_date_payment or dated_money:
                following = source['rows'][position + 1] if position + 1 < len(source['rows']) else None
                if following is not None and following['row_index'] not in scope['row_indices']:
                    following = None
                voucher = _voucher_money(row, following, page['width'], currency) if parsed else None
                if voucher:
                    body, money_cells = voucher['body'], voucher['money_cells']
                    parsed = _PAYMENT.match(body)
                    item['value_sources'] = {name: dict(page_number=source['page_number'],
                        table_index=source['table_index'], row_index=voucher['source_row']['row_index'], source_cell=cell)
                        for name, cell in zip(('amount', 'balance'), money_cells)}
                    if voucher['wrapped']:
                        money_continuations[voucher['source_row']['row_index']] = item
                item.update(excluded=False, kind='transaction' if parsed else 'unresolved')
                fields = item['fields']
                date_text = parsed[1] if parsed else damaged_date_payment[1] if damaged_date_payment else body.split(' ', 1)[0]
                value = _period_date(date_text, statement)
                if value:
                    fields['date'] = value
                else:
                    item['issues'].append('Check the full date in the PDF. It could not be read within this statement period.')
                fields['date_column'] = str(cells[0]['column_index'])
                fields['description'] = parsed[3] if parsed else damaged_date_payment[2] if damaged_date_payment else body.partition(' ')[2]
                fields['counterparty'] = ''
                if parsed and parsed[2]:
                    fields['additional_printed_date'] = parsed[2]
                    # The first printed date remains the row date, just as on
                    # adjacent rows with secondary date text on a continuation
                    # line. Retain the other text without calling it a posting,
                    # value or transaction date. Unusual dates still need review.
                    if not _ordinary_additional_date(parsed[2], value):
                        item['issues'].append('Check the additional date printed beside this payment. It is unreadable, later than the row date or more than 31 days earlier.')
                pair = re.fullmatch(r'(' + _SPACED_MONEY + r')\s+(.+)', money)
                amount_text, balance_text = (pair[1], pair[2]) if pair else ('', '')
                if pair is None:
                    trailing = re.fullmatch(r'(.+)\s+(' + _SPACED_MONEY + r')', money)
                    if trailing:
                        amount_text, balance_text = trailing[1], trailing[2]
                if len(money_cells) == 2:
                    amount_text, balance_text = [c['expected_text'].strip() for c in money_cells]
                if voucher:
                    amount_text, balance_text = voucher['amount_text'], voucher['balance_text']
                separate_cells = (len(money_cells) == 2 and
                                  _box(money_cells[0])[2] <= _box(money_cells[1])[0])
                try:
                    amount = _amount(amount_text, currency, separate_cell=separate_cells)
                    fields['amount_minor'] = str(abs(amount))
                    if not voucher or not voucher['wrapped']:
                        fields['amount_column'] = str(money_cells[0]['column_index'])
                    description = fields['description']
                    verb = re.sub(r'\s+', '', parsed[4] if parsed else damaged_date_payment[3]) if parsed or damaged_date_payment else None
                    conflict = (amount > 0 and verb == 'Withdrawal' and 'Adjustment' not in description
                                or amount < 0 and verb == 'Deposit')
                    if conflict or verb is None:
                        item['issues'].append('Check the amount and whether money entered or left the account. The number or its minus sign may have been read incorrectly.')
                    else:
                        fields['direction'] = 'credit' if amount >= 0 else 'debit'
                except ValueError:
                    item['issues'].append('Check the transaction amount in the PDF. Its digits, sign or decimal point could not be read.')
                try:
                    fields['balance'] = str(_amount(balance_text, currency, separate_cell=separate_cells))
                    if not voucher or not voucher['wrapped']:
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
