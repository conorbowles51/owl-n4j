"""Citi credit-card statements: many billing cycles in one PDF.

Fitted to Citi card productions (one cycle = a summary page followed by pages
headed "Page n of N"). A cycle is established only by its own summary page:
the issuer's site, one printed billing period, one card ending and an Account
Summary with Previous balance and New balance. Every following page of the
cycle must print its number, so a missing page refuses the cycle.

Balances are amounts owed (``liability_owed``): purchases, fees and interest
raise them, payments and credits lower them. The direction of each line is its
printed sign. Transactions are read only from the left-hand column, below the
Trans./Post date heading and above the year-to-date totals; the right-hand
column carries rewards and notices. Lines without an amount below a
transaction (references, travel details) belong to it.

Every printed Account Summary component (payments and credits, purchases and
cash advances, fees, interest) and the printed fee and interest totals must
equal what was read; a difference is proposed as an unresolved line, so the
cycle stays held for a person and is never admitted.
"""
import re
from datetime import date

from services.financial.pdf_candidates import _digest
from services.financial.statement_import_card_balances import balance_control
from services.financial.statement_import_proposal import exact_amount
from datetime import timedelta

LAYOUT = 'citi-card'
INSTITUTION = 'Citibank'
CYCLE = re.compile(r'(\d{2})/(\d{2})/(\d{2})\s*-\s*(\d{2})/(\d{2})/(\d{2})')
ENDING = re.compile(r'Account\s*number ending in:?\s*(\d{4})\b', re.I)
PAGE = re.compile(r'Page (\d+) of (\d+)')
MONEY = re.compile(r'([+-]?)\$(\d{1,3}(?:,\d{3})*\.\d{2}|\d+\.\d{2})')
SUMMARY = {'Previous balance': 'opening', 'Payments': 'payments', 'Credits': 'credits', 'Purchases': 'purchases',
           'Cash advances': 'advances', 'Fees': 'fees', 'Interest': 'interest', 'New balance': 'closing'}
SECTIONS = {'Payments, Credits and Adjustments': 'payments', 'Standard Purchases': 'purchases', 'Purchases': 'purchases',
            'Cash Advances': 'advances', 'Fees charged': 'fees', 'Interest charged': 'interest'}
ROW_DATE = re.compile(r'\d{2}/\d{2}')


def _box(cell):
    rect = (cell.get('locator') or {}).get('rect')
    return rect if isinstance(rect, list) and len(rect) == 4 and all(type(v) is int for v in rect) and rect[0] < rect[2] else None


def _lines(items):
    lines = []
    for s in items:
        for r in s['rows']:
            cells = [c for c in r['cells'] if c['expected_text'].strip() and _box(c)]
            if cells:
                cells.sort(key=lambda c: _box(c)[0])
                lines.append(dict(source=s, row=r, cells=cells, top=min(_box(c)[1] for c in cells),
                                  texts=[c['expected_text'].strip() for c in cells]))
    lines.sort(key=lambda l: (l['top'], l['source']['table_index'], l['row']['row_index']))
    return lines


def _cycle(text):
    m = CYCLE.fullmatch(text)
    if not m:
        return None
    try:
        start = date(2000 + int(m[3]), int(m[1]), int(m[2]))
        end = date(2000 + int(m[6]), int(m[4]), int(m[5]))
    except ValueError:
        return None
    return (start.isoformat(), end.isoformat()) if 0 <= (end - start).days <= 62 else None


def _summary_cells(lines):
    """Account Summary label cells and the value printed to the right of each."""
    headings = [(l, c) for l in lines for c in l['cells'] if c['expected_text'].strip() == 'Account Summary']
    found = {}
    for line, heading in headings:
        x = _box(heading)[0]
        for other in lines:
            if other['top'] <= line['top']:
                continue
            for i, cell in enumerate(other['cells']):
                role = SUMMARY.get(cell['expected_text'].strip())
                if role is None or abs(_box(cell)[0] - x) > 3000 or i + 1 >= len(other['cells']):
                    continue
                value = other['cells'][i + 1]
                if MONEY.fullmatch(value['expected_text'].strip()):
                    found.setdefault(role, []).append((other, cell, value))
    return {role: entries[0] for role, entries in found.items() if len(entries) == 1}


def _cover(lines):
    """(card ending, start, end, holder) from a cycle's summary page, else None."""
    texts = [t for l in lines for t in l['texts']]
    joined = '\n'.join(texts)
    if 'citicards.com' not in joined.lower() or 'Billing Period:' not in texts:
        return None
    if any(PAGE.fullmatch(t) for t in texts):
        return None
    cycles = {c for t in texts if (c := _cycle(t))}
    endings = {m[1] for t in texts for m in ENDING.finditer(t)}
    summary = _summary_cells(lines)
    if len(cycles) != 1 or len(endings) != 1 or not {'opening', 'closing'} <= set(summary):
        return None
    start, end = next(iter(cycles))
    holder = ''
    marker = next((l for l in lines if any(ENDING.search(t) for t in l['texts'])), None)
    if marker is not None:
        x = _box(marker['cells'][0])[0]
        above = [l for l in lines if l['top'] < marker['top'] and marker['top'] - l['top'] < 15000
                 and abs(_box(l['cells'][0])[0] - x) < 3000]
        if above and re.fullmatch(r"[A-Z][A-Z .,'&-]{2,80}", above[-1]['texts'][0]):
            holder = above[-1]['texts'][0]
    return next(iter(endings)), start, end, holder


def _page_number(lines):
    numbers = {(int(m[1]), int(m[2])) for l in lines for t in l['texts'] if (m := PAGE.fullmatch(t))}
    return next(iter(numbers)) if len(numbers) == 1 else None


def _cycles(sources):
    pages = {}
    for source in sources:
        pages.setdefault(source['page_number'], []).append(source)
    lines = {p: _lines(items) for p, items in pages.items()}
    found = []
    for first in sorted(pages):
        cover = _cover(lines[first])
        if cover is None:
            continue
        count, page = None, first + 1
        while count is None or page < first + count:
            number = _page_number(lines.get(page, [])) if page in pages else None
            texts = [t for l in lines.get(page, []) for t in l['texts']]
            if (number is None or number[0] != page - first + 1 or (count is not None and number[1] != count)
                    or not any('citicards.com' in t.lower() for t in texts)):
                count = None
                break
            count = number[1]
            page += 1
        if count and 2 <= count <= 20:
            found.append((first, count, cover, pages, lines))
    return found


def citi_catalog(sources):
    groups, handled = [], set()
    for first, count, (ending, start, end, holder), pages, _ in _cycles(sources):
        identity = dict(layout_id=LAYOUT, institution=INSTITUTION, account_reference='****' + ending,
                        period_start=start, period_end=end)
        items = [s for p in range(first, first + count) for s in pages[p]]
        groups.append(dict(id=_digest(identity), **identity, account_type='credit_card', holder=holder,
            sources=[dict(page_number=s['page_number'], table_index=s['table_index'], source_revision=s['source_revision'])
                     for s in items],
            page_numbers=list(range(first, first + count))))
        handled.update((s['page_number'], s['table_index']) for s in items)
    return groups, handled


def _month_day(text, first, last):
    """A printed MM/DD (this US layout prints its billing period month first)
    resolved to the one date between ``first`` and ``last``."""
    m = re.fullmatch(r'(\d{2})/(\d{2})', text)
    found = []
    for year in range(first.year, last.year + 1) if m else ():
        try:
            value = date(year, int(m[1]), int(m[2]))
        except ValueError:
            continue
        if first <= value <= last:
            found.append(value.isoformat())
    return found[0] if len(found) == 1 else None


def _signed(text, currency):
    m = MONEY.fullmatch(text.strip())
    if not m:
        raise ValueError(f'Loupe could not read "{text.strip()[:40]}" as an amount. Compare it with the PDF.')
    amount = int(exact_amount(m[2], currency))
    return -amount if m[1] == '-' else amount


def _split_dates(cells, description_x):
    """A date merged with the text after it in one cell ('08/18 CHICK-FIL-A ...')
    is split when the cell starts in a date column; the date keeps its share of
    the cell's box."""
    result = []
    for index, cell in enumerate(cells):
        value = cell['expected_text'].strip()
        m = re.fullmatch(r'(\d{2}/\d{2})\s+(\S.*)', value)
        if index > 1 or not m or _box(cell)[0] >= description_x - 5000:
            result.append(cell)
            continue
        x0, y0, x1, y1 = _box(cell)
        cut = x0 + (x1 - x0) * m.end(1) // len(value)
        part = lambda text, a, b: {**cell, 'expected_text': text, 'locator': {**cell['locator'], 'rect': [a, y0, b, y1]}}
        result += [part(m[1], x0, cut), part(m[2], cut + 1, x1)]
    return result


def propose_citi_statement(sources, currency, statement):
    by_address, items = {}, []
    for source in sources:
        for raw in source['rows']:
            address = (source['page_number'], source['table_index'], raw['row_index'])
            item = dict(id=':'.join(map(str, address)), page_number=address[0], table_index=address[1], row_index=address[2],
                source_revision=source['source_revision'], source_cells=raw['cells'], fields={}, issues=[], excluded=True,
                kind='statement_information')
            items.append(item)
            by_address[address] = item

    def item_of(line):
        return by_address[(line['source']['page_number'], line['source']['table_index'], line['row']['row_index'])]

    pages = {}
    for source in sources:
        pages.setdefault(source['page_number'], []).append(source)
    numbers = sorted(pages)
    summary = _summary_cells(_lines(pages[numbers[0]]))
    printed = {}
    for role, (line, label, value) in summary.items():
        try:
            printed[role] = _signed(value['expected_text'], currency)
        except ValueError:
            printed[role] = None
        if role in ('opening', 'closing'):
            item_of(line).update(balance_control(role, label, value, currency))
    period = (date.fromisoformat(statement['period_start']), date.fromisoformat(statement['period_end']))
    state = dict(read=[], totals={}, previous=None, section=None, lone=None, pending_total=None, pending=None)

    def unresolved(item, message):
        item.update(kind='unresolved', excluded=False)
        item['issues'].append(message)

    def flush():
        """Lines waiting for a partner that never came are held for a person."""
        if state['lone'] is not None:
            unresolved(item_of(state['lone'][0]), 'An amount was read on a line without a date or description. Compare it with the PDF.')
        if state['pending'] is not None:
            unresolved(item_of(state['pending'][0]), 'Check the dates, description and amount of this card line against the PDF.')
        state.update(lone=None, pending=None, pending_total=None)

    active, columns = False, None
    for number in numbers[1:]:
        for line in _lines(pages[number]):
            cells, texts = line['cells'], line['texts']
            if texts[0] == 'Trans.' or (len(texts) >= 4 and texts[:2] == ['date', 'date'] and 'Amount' in texts):
                if 'Amount' in texts:
                    columns = dict(post=_box(cells[1])[0], description=_box(cells[texts.index('Description')])[0],
                                   amount=_box(cells[texts.index('Amount')])[2])
                active, state['previous'] = True, None
                continue
            if not active or columns is None:
                continue
            left = [c for c in cells if _box(c)[0] < columns['amount'] + 15000]
            if not left:
                continue
            left = _split_dates(left, columns['description'])
            words = [c['expected_text'].strip() for c in left]
            first = words[0]
            if re.fullmatch(r'20\d{2} totals year-to-date', first) or first.startswith('Interest charge calculation'):
                flush()
                active, state['previous'] = False, None
                continue
            heading = SECTIONS.get(re.sub(r", cont'd$", '', first))
            if heading and len(left) == 1:
                flush()
                state.update(section=heading, previous=None)
                continue
            if words == ['Date', 'Description', 'Amount']:
                flush()
                state['previous'] = None
                continue
            total = re.fullmatch(r'Total (fees|interest) charged in this billing period', first)
            top = _box(left[0])[1]
            lone = len(left) == 1 and MONEY.fullmatch(first) is not None
            if total and len(left) == 1:
                # The text layer can put the amount on its own row just above
                # or just below its label.
                if state['lone'] is not None and top - _box(state['lone'][1])[1] <= 6000:
                    _total(item_of(state['lone'][0]), total, state['lone'][1], currency, state['totals'])
                    state['lone'] = None
                    flush()
                else:
                    flush()
                    state['pending_total'] = (total, top)
                state['previous'] = None
                continue
            if lone and state['pending_total'] is not None and top - state['pending_total'][1] <= 6000:
                _total(item_of(line), state['pending_total'][0], left[0], currency, state['totals'])
                state.update(pending_total=None, previous=None)
                continue
            state['pending_total'] = None
            if total and len(left) == 2:
                flush()
                _total(item_of(line), total, left[1], currency, state['totals'])
                state['previous'] = None
                continue
            amounts = [c for c in left if MONEY.fullmatch(c['expected_text'].strip())
                       and abs(_box(c)[2] - columns['amount']) <= 15000]
            dates = []
            for cell in left:
                if ROW_DATE.fullmatch(cell['expected_text'].strip()) and len(dates) < 2:
                    dates.append(cell)
                else:
                    break
            item = item_of(line)
            if lone:
                flush()
                state.update(lone=(line, left[0]), previous=None)
                continue
            if dates and not amounts:
                # A two-line entry prints its amount on the next line.
                flush()
                state.update(pending=(line, left, dates), previous=None)
                continue
            if not dates and not amounts:
                target = state['pending'] or None
                if target is not None:
                    target[1].extend(left)  # wraps before the amount line
                    item.update(kind='continuation', fields=dict(parent_transaction_id=item_of(target[0])['id']))
                    continue
                _continue(state['previous'], item, line, number, words)
                continue
            if state['pending'] is not None and not dates and len(amounts) == 1 and left[-1] is amounts[0]:
                first_line, first_left, dates = state['pending']
                state['pending'] = None
                item.update(kind='continuation', fields=dict(parent_transaction_id=item_of(first_line)['id']))
                owner = item_of(first_line)
                owner.setdefault('continuation_sources', []).append(dict(page_number=number,
                    row_index=line['row']['row_index'], source_cells=line['row']['cells']))
                description = [c for c in first_left if c not in dates] + left[:-1]
                _card_line(owner, dates, description, amounts[0], columns, period, state, currency, statement)
                continue
            flush()
            if len(amounts) != 1 or left[-1] is not amounts[0] or len(dates) > 2 or (
                    not dates and not (state['section'] == 'interest' and len(left) >= 2)):
                unresolved(item, 'Check the dates, description and amount of this card line against the PDF.')
                state['previous'] = None
                continue
            description = [c for c in left if c not in dates and c is not amounts[0]]
            _card_line(item, dates, description, amounts[0], columns, period, state, currency, statement)
    flush()
    _check_summary(state['read'], printed, state['totals'], summary, item_of)
    return dict(rows=items, issues=[])


def _continue(previous, item, line, number, words):
    """A line without date or amount below a card line: its network reference,
    or more of its description (travel details)."""
    if previous is None:
        return
    fields = previous['fields']
    joined = ' '.join(words)
    if re.fullmatch(r'[A-Z0-9*#]+(?: [A-Z0-9*#]+)*', joined) and re.search(r'\d', joined):
        fields['reference'] = (fields.get('reference', '') + ' ' + joined).strip()
    else:
        fields['description'] = (fields.get('description', '') + ' ' + joined).strip()
    previous.setdefault('continuation_sources', []).append(dict(page_number=number,
        row_index=line['row']['row_index'], source_cells=line['row']['cells']))
    item.update(kind='continuation', fields=dict(parent_transaction_id=previous['id']))


def _card_line(item, dates, description, amount_cell, columns, period, state, currency, statement):
    start, end = period
    section = state['section']
    item.update(kind='transaction', excluded=False)
    fields = item['fields']
    fields.update(description=' '.join(c['expected_text'].strip() for c in description), counterparty='',
                  printed_section=section or '', card_ending=statement['account_reference'][-4:],
                  amount_column=str(amount_cell['column_index']))
    if section in ('fees', 'interest'):
        fields['charge_group'] = 'fee' if section == 'fees' else 'interest'
    try:
        amount = _signed(amount_cell['expected_text'], currency)
        fields.update(amount_minor=str(abs(amount)), direction='credit' if amount < 0 else 'debit')
        if amount == 0:
            item.update(kind='zero_charge', excluded=True)
            state['previous'] = None
            return
    except ValueError as exc:
        item['issues'].append(str(exc))
    if not dates:
        # An interest line printed without a date: the period end orders it
        # only and never becomes a printed transaction date.
        fields['date_basis'] = 'statement_end_ordering_only'
    else:
        # Payments print only the posting date; purchases print the
        # transaction date and the posting date.
        trans = dates[0] if len(dates) == 2 or _box(dates[0])[0] < columns['post'] - 5000 else None
        post = dates[-1] if len(dates) == 2 or trans is None else None
        fields['date_column'] = str((trans or post)['column_index'])
        if trans is not None and post is not None:
            fields['booking_date_column'] = str(post['column_index'])
            posted = _month_day(post['expected_text'].strip(), start - timedelta(days=31), end)
            if posted:
                fields['booking_date'] = posted
                # A purchase shortly before the cycle can post inside it.
                when = _month_day(trans['expected_text'].strip(), date.fromisoformat(posted) - timedelta(days=31),
                                  date.fromisoformat(posted))
            else:
                when = None
                item['issues'].append('Check the posting date against this card billing period.')
        else:
            # A line posted on the previous cycle's closing day can be printed
            # in this cycle: the printed month and day decide within a month.
            when = _month_day((trans or post)['expected_text'].strip(), start - timedelta(days=31), end)
        if when:
            fields['date'] = when
        else:
            item['issues'].append('Check the transaction date against this card billing period.')
    if not fields['description']:
        item['issues'].append('Check the description of this card line against the PDF.')
    state['read'].append(item)
    state['previous'] = item


def _total(item, match, cell, currency, totals):
    """A printed fee or interest total for this billing period."""
    scope = 'fee' if match[1] == 'fees' else 'interest'
    item.update(kind='statement_total', excluded=True)
    item['fields'].update(description=f'Total {scope} charged', total_scope=scope, balance_column=str(cell['column_index']))
    try:
        totals[scope] = _signed(cell['expected_text'], currency)
        item['fields']['balance'] = str(totals[scope])
    except ValueError as exc:
        item['issues'].append(str(exc))
        totals[scope] = None


def _check_summary(read, printed, totals, summary, item_of):
    """Every printed summary component must equal what was read."""
    def amount(rows, direction, group=None):
        try:
            return sum(int(r['fields']['amount_minor']) for r in rows if not r['excluded'] and r['fields'].get('direction') == direction
                       and (group is None or r['fields'].get('charge_group') == group))
        except (KeyError, ValueError):
            return None

    def total(*roles):
        values = [abs(printed[r]) if printed.get(r) is not None else None for r in roles if r in printed]
        return None if None in values or not values else sum(values)
    checks = [(('payments', 'credits'), amount(read, 'credit'), 'payments and credits'),
              (('purchases', 'advances', 'fees', 'interest'), amount(read, 'debit'), 'purchases, cash advances, fees and interest'),
              (('fees',), amount(read, 'debit', 'fee'), 'fees'),
              (('interest',), amount(read, 'debit', 'interest'), 'interest')]
    for roles, found, label in checks:
        expected = total(*roles)
        if expected is not None and found == expected:
            continue
        anchor = next((summary[r] for r in roles if r in summary), None)
        if anchor is None:
            # Any component line, else the closing balance itself (which then
            # stops being a control, so the cycle cannot reconcile).
            anchor = next((summary[r] for r in SUMMARY.values() if r not in ('opening', 'closing') and r in summary),
                          summary.get('closing'))
        line = anchor[0]
        item = item_of(line)
        item.update(kind='unresolved', excluded=False)
        item['fields'] = dict(description=' '.join(line['texts'])[:300])
        item['issues'].append(f'The printed {label} differ from the card lines read for this cycle. '
                              'Compare the account summary with the transaction pages before importing.')
    for scope, roles in (('fee', ('fees',)), ('interest', ('interest',))):
        if scope in totals and (totals[scope] is None or totals[scope] != total(*roles)):
            anchor = summary.get(roles[0]) or summary.get('closing')
            item = item_of(anchor[0])
            if item['kind'] != 'unresolved':
                item.update(kind='unresolved', excluded=False)
                item['fields'] = dict(description=' '.join(anchor[0]['texts'])[:300])
            item['issues'].append(f'The printed total {scope} charged differs from the account summary. '
                                  'Compare both with the PDF before importing.')


def citi_no_activity_evidence(sources, choice, rows, currency):
    """A cycle whose Account Summary prints every movement as zero is quiet.

    The six printed components (payments, credits, purchases, cash advances,
    fees, interest) are re-read from the summary page and cited; each must be
    printed and read exactly as zero. The shared proof then also requires
    equal printed balances, no proposed card line and the printed period.
    """
    from services.financial.statement_printed_no_activity import zero_totals_evidence, held
    first = min(s['page_number'] for s in sources)
    summary = _summary_cells(_lines([s for s in sources if s['page_number'] == first]))
    cells = []
    for role in ('payments', 'credits', 'purchases', 'advances', 'fees', 'interest'):
        if role not in summary:
            return held('citi-card', 'controls_missing', 'The account summary was not read completely. Check the page before confirming that this cycle has no transactions.',
                        page_number=first)
        value = summary[role][2]
        try:
            zero = _signed(value['expected_text'], currency) == 0
        except ValueError:
            zero = False
        if not zero:
            return held('citi-card', 'totals_not_zero', 'The account summary shows money moved in this cycle. Check the pages for card lines that were not read.',
                        page_number=first)
        cells.append(value)

    def guard():
        if any(r['kind'] == 'statement_total' and r['fields'].get('balance') not in ('0', None) for r in rows):
            return ('totals_not_zero', 'A printed fee or interest total is not zero. Check the pages for card lines that were not read.')
        return None

    return zero_totals_evidence(rows, choice, currency, family='citi-card', guard=guard, zero_cells=cells, printed_currency='USD')
