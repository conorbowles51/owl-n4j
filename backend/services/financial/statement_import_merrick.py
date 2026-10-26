"""Source-bound recognition of Merrick card statement pages and entries."""
import re
from difflib import SequenceMatcher
from datetime import date
from services.financial.pdf_candidates import _digest
from services.financial.statement_import_proposal import exact_amount
from services.financial.statement_import_card_balances import merrick_summary_balances, balance_control, _rectangle


def _printed_date(text):
    match = re.fullmatch(r'(\d{2})/(\d{2})/(\d{2}|20\d{2})', text)
    if match:
        try:
            return date(2000 + int(match[3]) if len(match[3]) == 2 else int(match[3]),
                        int(match[1]), int(match[2]))
        except ValueError:
            pass
    return None


def _coupon_holder(source):
    """Read the recipient above the right-hand payment-coupon address.

    OCR can split a name into adjacent cells on different extracted rows. The
    street, city/state/ZIP and separate bank address establish this layout;
    neither a nearby account number nor a name on another page can supply it.
    """
    measured = [(row, cell, _rectangle(cell, source['page_number']))
                for row in source['rows'] for cell in row['cells']]
    headings = [box for _, cell, box in measured
                if cell['expected_text'].strip() == 'MERRICK ACCOUNT SUMMARY' and box]
    if len(headings) != 1:
        return '', []
    heading = headings[0]
    if any(box is None or (box.page_width, box.page_height) != (heading.page_width, heading.page_height)
           for _, _, box in measured):
        return '', []
    coupon = [(row, cell, box) for row, cell, box in measured if box
              and (box.page_width, box.page_height) == (heading.page_width, heading.page_height)
              and box.y1 < heading.y0 and box.y0 < box.page_height // 3]
    banks = [box for _, cell, box in coupon
             if cell['expected_text'].strip() == 'MERRICK BANK' and box.x1 < box.page_width // 2]
    candidates = []
    for _, city, city_box in coupon:
        if (city_box.x0 < city_box.page_width // 2
                or not re.fullmatch(r"[A-Z][A-Z .'-]+ [A-Z]{2} \d{5}(?:-\d{4})?", city['expected_text'].strip())):
            continue
        tolerance = city_box.page_width // 60
        streets = [(row, cell, box) for row, cell, box in coupon
                   if abs(box.x0 - city_box.x0) <= tolerance
                   and 0 <= city_box.y0 - box.y1 <= city_box.page_height // 50
                   and re.match(r'\d+\s+[A-Z0-9]', cell['expected_text'].strip())]
        if len(streets) != 1:
            continue
        street = streets[0][2]
        # The bank's postal block must be separate from the recipient block.
        if not any(abs(bank.y0 - street.y0) <= city_box.page_height // 25 for bank in banks):
            continue
        names = [(row, cell, box) for row, cell, box in coupon
                 if city_box.x0 - tolerance <= box.x0 and box.x1 <= city_box.x1 + tolerance
                 and 0 <= street.y0 - box.y1 <= city_box.page_height // 60]
        names.sort(key=lambda item: item[2].x0)
        # Image OCR can set a middle initial a little above the name and
        # report neighbouring words with boxes that touch or overlap slightly
        # (by up to an eighth of the usual gap). A word ending in a point
        # after three or more letters is a speck read as part of the name,
        # not a printed initial or suffix: the name stays unread.
        if (not names or len(names) > 4 or abs(names[0][2].x0 - street.x0) > tolerance
                or any(not re.fullmatch(r"[A-Z][A-Z .'-]*", cell['expected_text'].strip())
                       or re.search(r"[A-Z]{3,}\.$", cell['expected_text'].strip()) for _, cell, _ in names)
                or any(not -(tolerance // 8) <= right[2].x0 - left[2].x1 <= tolerance
                       for left, right in zip(names, names[1:]))):
            continue
        name = ' '.join(cell['expected_text'].strip() for _, cell, _ in names)
        if not 2 <= len(name.split()) <= 12 or len(name) > 128:
            continue
        candidates.append((name, [dict(page_number=source['page_number'], table_index=source['table_index'],
                                      row_index=row['row_index'], source_cell=cell) for row, cell, _ in names]))
    return candidates[0] if len(candidates) == 1 else ('', [])


# The most days one printed billing cycle may cover (the general engine's bound
# for a closing-only period, ``statement_engine.MAX_PERIOD_DAYS``).
MAX_CYCLE_DAYS = 95


def _printed_cycle_days(source):
    """``(days, cell address)`` printed beside ``Days in Billing Cycle`` in the activity summary box, or ``None``.

    The label is the one cell of the box beginning with ``Days`` (OCR damages
    the rest of it); its value is the one whole number on the label's printed
    line, set in the right half of the box. OCR can report the label's words
    and the value on adjacent extracted lines, so the line is the label's
    height widened by one more height above and below. Nothing is repaired:
    any other count of labels or values reads nothing.
    """
    measured = [(row['row_index'], cell, _rectangle(cell, source['page_number']))
                for row in source['rows'] for cell in row['cells']]
    headings = {name: [box for _, cell, box in measured if cell['expected_text'].strip(' |[]') == name]
                for name in ('Summary of Account Activity', 'Payment Information')}
    if any(len(boxes) != 1 or boxes[0] is None for boxes in headings.values()):
        return None
    left, right = headings['Summary of Account Activity'][0], headings['Payment Information'][0]
    size = (left.page_width, left.page_height)
    if (right.page_width, right.page_height) != size or right.x0 <= left.x1:
        return None
    inside = [(index, cell, box) for index, cell, box in measured
              if box and (box.page_width, box.page_height) == size
              and left.x0 - left.page_width // 50 <= box.x0 and box.x1 < right.x0 and box.y0 >= left.y1]
    labels = [box for _, cell, box in inside if re.match(r'Days\b', cell['expected_text'].strip())]
    if len(labels) != 1:
        return None
    label = labels[0]
    height = label.y1 - label.y0
    values = [(index, cell) for index, cell, box in inside
              if re.fullmatch(r'\d{1,2}', cell['expected_text'].strip())
              and box.x0 > max(label.x1, (left.x0 + right.x0) // 2)
              and box.y1 > label.y0 - height and box.y0 < label.y1 + height]
    if len(values) != 1 or not 1 <= int(values[0][1]['expected_text']) <= MAX_CYCLE_DAYS:
        return None
    index, cell = values[0]
    return int(cell['expected_text']), dict(page_number=source['page_number'], table_index=source['table_index'],
                                            row_index=index, column_index=cell['column_index'],
                                            expected_text=cell['expected_text'])


# A damaged scan of this layout loses the summary box's headings and labels
# while its values stay in their printed column and order. Reverse in one
# place: False (the box is then read by its labels only).
SUMMARY_BY_POSITION = True
SUMMARY_POSITION_BASIS = 'merrick_summary_box_values_in_printed_order'
# The box prints, top to bottom: previous balance, payments (-), other credits
# (-), purchases (+), cash advances (+), fees (+), interest (+), new balance,
# past due amount, then credit limit and available credit on one line.
_BOX_LINES = ('previous', 'payments', 'other_credits', 'purchases', 'cash_advances', 'fees', 'interest', 'new',
              'past_due', 'limit_available')


def _box_amount(text):
    """Minor units of a summary box value, or ``None``.

    Every value prints a dollar sign, which OCR reads as ``$`` or ``S``. A
    thousands comma read as a point is unambiguous (three digits per group,
    two after the last point). Without the dollar glyph the sign may have
    become a digit, so the value is unread; no other glyph is read.
    """
    match = re.fullmatch(r'[$Ss](\d{1,3}(?:[,.]\d{3})*)\.(\d{2})', text.strip())
    return int(re.sub(r'[,.]', '', match[1]) + match[2]) if match else None


def summary_by_position(source):
    """The summary box values read in printed order, or ``None``.

    The box is bounded by the ``MERRICK ACCOUNT SUMMARY`` heading above, the
    ``Days`` line below (its label set in the box's label column) and the
    ``Minimum Payment Due`` label of the box beside. Its values are the cells
    right-aligned with the printed days in the billing cycle, one per line:
    exactly the ten lines of ``_BOX_LINES``. The first eight must read and
    must add up (previous - payments - other credits + purchases + cash
    advances + fees + interest = new); anything else reads nothing.
    Returns ``dict(amounts, cells, days)``: ``cells`` maps a line to
    ``(row, value cell)``, ``days`` is ``(days, cell address)``.
    """
    page = source['page_number']
    measured = [(row, cell, _rectangle(cell, page)) for row in source['rows'] for cell in row['cells']]
    headings = [box for _, cell, box in measured if box and cell['expected_text'].strip().startswith('MERRICK ACCOUNT SUMMARY')]
    bounds = [box for _, cell, box in measured if box and cell['expected_text'].strip() == 'Minimum Payment Due']
    if len(headings) != 1 or len(bounds) != 1:
        return None
    heading, bound = headings[0], bounds[0]
    size = (heading.page_width, heading.page_height)
    located = [(row, cell, box) for row, cell, box in measured if box and (box.page_width, box.page_height) == size]
    tolerance = heading.page_width // 50
    if (bound.page_width, bound.page_height) != size or bound.x0 <= heading.x0 + tolerance:
        return None
    labels = [(row, box) for row, cell, box in located if box.y0 > heading.y1 and abs(box.x0 - heading.x0) <= tolerance
              and re.match(r'Days\b', cell['expected_text'].strip())]
    if len(labels) != 1:
        return None
    days_row, days_label = labels[0]
    days = [(cell, box) for row, cell, box in located
            if row is days_row and box.x0 > days_label.x1 and box.x1 < bound.x0]
    if len(days) != 1 or not re.fullmatch(r'\d{1,2}', days[0][0]['expected_text'].strip()):
        return None
    days_cell, days_box = days[0]
    if not 1 <= int(days_cell['expected_text']) <= MAX_CYCLE_DAYS:
        return None
    values = sorted(((row, cell, box) for row, cell, box in located
                     if heading.y1 <= box.y0 < days_label.y0 and box.x1 < bound.x0
                     and abs(box.x1 - days_box.x1) <= tolerance), key=lambda item: item[2].y0)
    if (len(values) != len(_BOX_LINES) or len({id(row) for row, _, _ in values}) != len(values)
            or any(upper[2].y1 > lower[2].y0 for upper, lower in zip(values, values[1:]))):
        return None
    amounts = {name: _box_amount(cell['expected_text']) for name, (_, cell, _) in zip(_BOX_LINES[:8], values)}
    if any(value is None for value in amounts.values()):
        return None
    if (amounts['previous'] - amounts['payments'] - amounts['other_credits'] + amounts['purchases']
            + amounts['cash_advances'] + amounts['fees'] + amounts['interest'] != amounts['new']):
        return None
    days_address = dict(page_number=page, table_index=source['table_index'], row_index=days_row['row_index'],
                        column_index=days_cell['column_index'], expected_text=days_cell['expected_text'])
    return dict(amounts=amounts, cells={name: (row, cell) for name, (row, cell, _) in zip(_BOX_LINES, values)},
                days=(int(days_cell['expected_text']), days_address))


def position_balances(source, currency):
    """Opening and closing controls from ``summary_by_position``, keyed by row index (``{}`` when unread)."""
    box = summary_by_position(source) if SUMMARY_BY_POSITION else None
    if box is None:
        return {}
    controls = {}
    for role, name in (('opening', 'previous'), ('closing', 'new')):
        row, cell = box['cells'][name]
        control = balance_control(role, row['cells'][0], cell, currency)
        control['fields'].update(balance=str(box['amounts'][name]), balance_basis=SUMMARY_POSITION_BASIS)
        control['issues'] = []
        controls[row['row_index']] = control
    return controls


# The statement date's second separator read as a one (``08/26121``) is the
# printed date when the full year-to-date heading gives its year and the
# separately labelled closing date reads the same digits. Applied after the
# statement id is computed, so saved reviews keep their statement. Reverse in
# one place: False.
DATE_SEPARATOR_READ_AS_ONE = True
DATE_SEPARATOR_BASIS = 'statement_date_separator_read_as_one'


def _separator_read_date(printed, closing_values, year):
    match = re.fullmatch(r'(\d{2})/(\d{2})[1lI|](\d{2})', printed)
    if not match or year is None or int(match[3]) != year % 100 or not closing_values:
        return None
    for value in closing_values:
        other = re.fullmatch(r'(\d{2})[/1lI|](\d{2})[/1lI|](\d{2})', value)
        if not other or other.groups() != match.groups():
            return None
    try:
        return date(year, int(match[1]), int(match[2])).isoformat()
    except ValueError:
        return None


# When the engine replaced a damaged Merrick text layer by the page image and
# the image reading lost the holder, use the holder the layer printed on its
# labelled ``Send Payments to:`` line, only for the same account number.
# Reverse in one place: False.
CARRY_LAYER_HOLDER = True


def merrick_statement(source):
    texts = [c['expected_text'].strip() for r in source['rows'] for c in r['cells']]
    if 'MERRICK BANK' not in texts or 'Transactions, Payments and Credits' not in texts:
        return None
    accounts = set()
    for row in source['rows']:
        cells = row['cells']
        for i, cell in enumerate(cells):
            text = cell['expected_text'].strip()
            # OCR may split the printed account into four groups. Only join
            # digits following this label on the same row, without repairing
            # letters or using an unlabelled number elsewhere on the page.
            if text.startswith('Account Number'):
                labelled = ' '.join(c['expected_text'].strip() for c in cells[i:])
                account = re.fullmatch(r'Account Number:?\s+([0-9 ]{13,24})', labelled)
                if account and 13 <= len(account[1].replace(' ', '')) <= 19:
                    accounts.add(account[1].strip())
            match = re.fullmatch(r'Account Number:\s*([0-9 ]{13,24})', text)
            if match and 13 <= len(match[1].replace(' ', '')) <= 19:
                accounts.add(match[1].strip())
    years = {int(m[1]) for text in texts if (m := re.fullmatch(r'(20\d{2}) Totals Year-to-Date', text))}
    dates = {m[1].strip() for text in texts if (m := re.fullmatch(r'Statement Date:\s*(.+)', text))}
    raw_date = next(iter(dates)) if len(dates) == 1 else ''
    # A second printed closing date is a cross-check, not a source of guessed
    # digit corrections when OCR disagrees with the statement-date heading.
    closing_dates = set()
    for row in source['rows']:
        values = [c['expected_text'].strip() for c in row['cells']]
        for i, text in enumerate(values):
            if text == 'Billing Cycle Closing Date' and i + 1 < len(values):
                closing_dates.add(values[i + 1])
    printed_statement_date = raw_date
    year = next(iter(years)) if len(years) == 1 else None
    closing_fallback = ''
    # A missing statement-date label does not erase a separately labelled
    # closing date. Use it only when unique and corroborated by the full YTD
    # year. A present but damaged or conflicting heading still needs review.
    if not dates and len(closing_dates) == 1 and year is not None:
        candidate = next(iter(closing_dates))
        parsed_closing = _printed_date(candidate)
        if parsed_closing is not None and parsed_closing.year == year:
            closing_fallback = raw_date = candidate
    date_conflict = bool(raw_date and closing_dates and
                         any(_printed_date(value) is None or _printed_date(value) != _printed_date(raw_date)
                             for value in closing_dates))
    if year is not None and (not raw_date.endswith(str(year)[-2:]) or date_conflict):
        year = None
    closing = None
    matched = re.fullmatch(r'(\d{2})/(\d{2})/(\d{2}|\d{4})', raw_date)
    if matched and year and int(matched[3]) in (year, year % 100):
        try:
            closing = date(year, int(matched[1]), int(matched[2])).isoformat()
        except ValueError:
            pass
    # A damaged day separator is not repaired. A clearly printed month plus
    # the explicit full YTD year can still constrain transaction-year proposals.
    month = re.match(r'^(0[1-9]|1[0-2])/', raw_date)
    holder = ''
    for row in source['rows']:
        values = [c['expected_text'].strip() for c in row['cells']]
        if values and values[0] == 'Send Payments to:' and len(values) > 1 and re.fullmatch(r'[A-Z][A-Z .\'-]{2,127}', values[1]):
            holder = values[1]
    identity = dict(layout_id='merrick-card', institution='Merrick Bank',
                    account_reference=next(iter(accounts)) if len(accounts) == 1 else '',
                    statement_date=closing or '', printed_statement_date=printed_statement_date,
                    period_start='', period_end='', holder=holder,
                    date_year=year, date_month=int(month[1]) if month else None)
    if closing_fallback:
        identity.update(printed_closing_date=closing_fallback, statement_date_basis='billing_cycle_closing_date')
    identity['id'] = _digest(dict(**identity, source_page=source['page_number']))
    if not closing and DATE_SEPARATOR_READ_AS_ONE and not date_conflict:
        # OCR can damage the label's first word too (``BIiiing``); its value
        # is the next cell on the label's line.
        labelled = [row_values[i + 1] for row_values in ([c['expected_text'].strip() for c in r['cells']]
                                                         for r in source['rows'])
                    for i, text in enumerate(row_values[:-1]) if text.endswith('Cycle Closing Date')]
        separated = _separator_read_date(printed_statement_date, labelled, year)
        if separated:
            identity.update(statement_date=separated, statement_date_basis=DATE_SEPARATOR_BASIS,
                            printed_closing_date=labelled[0])
    # Preserve existing statement IDs and their imported/review records when
    # filling a previously missed coupon name. Proposal versioning still makes
    # changed metadata go through the normal saved-review recovery check.
    if not holder:
        coupon_holder, holder_sources = _coupon_holder(source)
        if coupon_holder:
            identity.update(holder=coupon_holder, holder_sources=holder_sources)
    carried = source.get('original_layer_holder') or {}
    if (not identity['holder'] and CARRY_LAYER_HOLDER and carried.get('holder') and identity['account_reference']
            and re.sub(r'\s+', '', carried.get('account') or '') == re.sub(r'\s+', '', identity['account_reference'])
            and re.fullmatch(r'[A-Z][A-Z .\'-]{2,127}', carried['holder'])):
        # The image reading lost the holder; the page's own embedded text
        # layer printed it on its labelled line, for the same account number.
        identity.update(holder=carried['holder'], holder_basis='original_text_layer_labelled_line')
    # Outside the statement id, like the holder above: the printed days in the
    # billing cycle establish the start with the closing date (closing_only_period).
    cycle_days = _printed_cycle_days(source)
    if not cycle_days and SUMMARY_BY_POSITION:
        # The box's values add up in printed order (``summary_by_position``),
        # so its days line is the one below them.
        box = summary_by_position(source)
        cycle_days = box['days'] if box else None
    if cycle_days:
        identity.update(printed_cycle_days=cycle_days[0], printed_cycle_days_cell=cycle_days[1])
    return dict(**identity, date_conflict=date_conflict,
                sources=[dict(page_number=source['page_number'],table_index=source['table_index'],source_revision=source['source_revision'])],page_numbers=[source['page_number']])


def _transaction_amount(cells, source, currency):
    """Read this layout's printed cents and optional trailing credit marker.

    A separate minus must be beside the amount on the same measured line.
    Missing decimal punctuation is a review exception, never an integer amount
    or a reason to insert an assumed decimal point.
    """
    value = cells[-1]['expected_text'].strip()
    amount_index = len(cells) - 1
    if value == '-' and len(cells) >= 4:
        amount_index -= 1
        amount_box = _rectangle(cells[amount_index], source['page_number'])
        sign_box = _rectangle(cells[-1], source['page_number'])
        if (amount_box is None or sign_box is None
                or (amount_box.page_width, amount_box.page_height) != (sign_box.page_width, sign_box.page_height)
                or not 0 <= sign_box.x0 - amount_box.x1 <= amount_box.page_width // 40
                or min(amount_box.y1, sign_box.y1) <= max(amount_box.y0, sign_box.y0)):
            raise ValueError('Check the amount and minus sign in the PDF. Their positions could not be matched.')
        value = cells[amount_index]['expected_text'].strip() + ' -'
    match = re.fullmatch(
        r'(?P<before>[+-]?)\s*(?P<currency>\$|USD)?\s*(?P<after>[+-]?)'
        r'(?P<amount>(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2})\s*(?P<trailing>-?)', value)
    if not match:
        raise ValueError('Check this amount in the PDF, including the decimal point and both digits after it.')
    signs = [match[name] for name in ('before', 'after', 'trailing') if match[name]]
    if len(signs) > 1:
        raise ValueError('Check this amount in the PDF. More than one sign was read.')
    signed = (match['currency'] or '') + ('-' if signs == ['-'] else '') + match['amount']
    return int(exact_amount(signed, currency)), amount_index


def _transaction_header(cells, page, following=()):
    """Require printed columns and extra row evidence for a damaged heading."""
    names = ('Trans Date', 'Item Description', 'Amount')
    matches = [[cell for cell in cells if cell['expected_text'].strip() == name] for name in names]
    damaged_heading = not matches[0]
    if damaged_heading and len(cells) == 3 and all(len(values) == 1 for values in matches[1:]):
        label = re.sub(r'[^a-z]', '', cells[0]['expected_text'].lower())
        if (not re.search(r'\d', cells[0]['expected_text']) and label.startswith('trans')
                and SequenceMatcher(None, label, 'transdate').ratio() >= .72):
            matches[0] = [cells[0]]
    if any(len(values) != 1 for values in matches):
        return None
    boxes = [_rectangle(values[0], page) for values in matches]
    if (any(box is None for box in boxes)
            or len({(box.page_width, box.page_height) for box in boxes}) != 1
            or not boxes[0].x1 < boxes[1].x0 < boxes[1].x1 < boxes[2].x0
            or min(box.y1 for box in boxes) <= max(box.y0 for box in boxes)):
        return None
    if damaged_heading:
        # Two other readable, positioned payment dates establish this column.
        # Similar heading text alone cannot fill a damaged payment's fields.
        supporters = 0
        for row in following:
            values = [c['expected_text'].strip() for c in row['cells']]
            if values and (values[0] in ('Fees', 'Interest Charged', 'Interest Charge Calculation')
                           or values[0].upper().startswith('TOTAL ')):
                break
            if (values and _printed_date(values[0] + '/2000')
                    and _matches_transaction_columns(row['cells'], boxes, page)):
                supporters += 1
        if supporters < 2:
            return None
    return boxes


def _matches_transaction_columns(cells, header, page):
    """Keep other fields only when date, description and amount positions agree.

    This recognises a row's layout, not the damaged date characters. No month,
    day or year is supplied by this check.
    """
    if header is None or len(cells) < 3:
        return False
    boxes = [_rectangle(cell, page) for cell in cells]
    if (any(box is None for box in boxes)
            or any((box.page_width, box.page_height) != (header[0].page_width, header[0].page_height) for box in boxes)):
        return False
    tolerance = header[0].page_width // 60
    amount_index = len(cells) - (2 if cells[-1]['expected_text'].strip() == '-' else 1)
    amount = boxes[amount_index]
    if (amount_index < 2 or boxes[0].y0 <= max(box.y1 for box in header)
            or abs(boxes[0].x0 - header[0].x0) > tolerance
            or boxes[0].x1 >= header[1].x0
            or amount.x0 < header[1].x1
            or abs(amount.x1 - header[2].x1) > tolerance
            or min(box.y1 for box in boxes) <= max(box.y0 for box in boxes)
            or any(left.x1 > right.x0 for left, right in zip(boxes, boxes[1:]))):
        return False
    return any(abs(box.x0 - header[1].x0) <= tolerance
               and box.x1 < amount.x0 for box in boxes[1:amount_index])


def _section_heading(row, following):
    """A damaged standalone heading needs its nearby, explicit section total.

    Never repair transaction characters or suppress a dated/amount-bearing row.
    This only keeps short heading text out of the payment correction queue.
    """
    cells = row['cells']
    if len(cells) != 1 or re.search(r'\d', cells[0]['expected_text']):
        return False
    label = re.sub(r'[^a-z]', '', cells[0]['expected_text'].lower())
    for heading, total in (('fees', 'TOTAL FEES FOR THIS PERIOD'),
                           ('interestcharged', 'TOTAL INTEREST FOR THIS PERIOD')):
        if SequenceMatcher(None, label, heading).ratio() < 0.72:
            continue
        if any(r['cells'] and r['cells'][0]['expected_text'].strip() == total for r in following[:4]):
            return True
    return False


def _charge_controls(rows, source, currency):
    """Keep printed fee/interest subtotals bound to their own charge sections."""
    scope, members = None, []
    headings = {'Fees': 'fee', 'Interest Charged': 'interest'}
    totals = {'TOTAL FEES FOR THIS PERIOD': 'fee', 'TOTAL INTEREST FOR THIS PERIOD': 'interest'}
    for row in rows:
        cells = row['source_cells']
        texts = [cell['expected_text'].strip() for cell in cells]
        if len(texts) == 1 and texts[0] in headings:
            scope, members = headings[texts[0]], []
            continue
        if any(text in headings or re.fullmatch(r'20\d{2} Totals Year-to-Date', text)
               or text == 'Interest Charge Calculation' for text in texts):
            scope, members = None, []
        if not scope:
            continue
        if texts and texts[0] in totals:
            label = _rectangle(cells[0], source['page_number'])
            value = _rectangle(cells[-1], source['page_number'])
            if (totals[texts[0]] == scope and len(cells) == 2 and label and value
                    and (label.page_width, label.page_height) == (value.page_width, value.page_height)
                    and label.x1 < value.x0 and min(label.y1, value.y1) > max(label.y0, value.y0)):
                fields = dict(description='Printed ' + scope + ' total', total_scope=scope,
                              balance_column=str(cells[-1]['column_index']))
                try:
                    amount, _ = _transaction_amount(cells, source, currency)
                    fields['balance'] = str(amount)
                except ValueError:
                    pass  # An unreadable control makes this check unavailable.
                row.update(kind='statement_total', excluded=True, fields=fields, issues=[])
                for member in members:
                    member['fields']['charge_group'] = scope
            scope, members = None, []
        elif not row['excluded'] or row['kind'] == 'zero_charge':
            members.append(row)


# This layout prints its interest lines on the closing date (the reader holds
# one dated otherwise). OCR can lose that date cell: a line labelled
# ``Interest Charge on ...`` under the Interest Charged heading then takes the
# printed closing date when the lines add up to the printed interest total.
# Reverse in one place: False.
INTEREST_ON_CLOSING_DATE = True
INTEREST_DATE_BASIS = 'merrick_interest_printed_on_closing_date'
# A damaged transaction date (``07rJO``, ``0&'03``) is the one date of the
# printed billing cycle that its readable glyphs allow, when it also lies
# between the readable dates printed before and after it. Reverse in one
# place: False.
DAMAGED_DATE_IN_CYCLE = True
DAMAGED_DATE_BASIS = 'readable_glyphs_within_printed_billing_cycle'
_UNREAD_DATE = 'Check the full date in the PDF. Its characters could not be read. The other recognised fields have been kept.'
_ROW_UNREAD = 'Check this row in the transaction section. Its date or layout could not be read.'


def _glyph_date(text, start, end):
    """The one date in ``start..end`` a printed ``MM/DD`` cell allows, or ``None``.

    The cell must be five glyphs with the separator in the middle (any glyph:
    OCR reads it as ``1``, ``r`` or ``'``). A digit glyph is that digit, an
    ``O``-like glyph a zero; any other glyph is unread. At least three of the
    four digits must be read, and exactly one date of the cycle may fit.
    """
    text = text.strip()
    if len(text) != 5:
        return None
    glyphs = [ch if ch.isdigit() else '0' if ch in 'OoDQ' else None for ch in text[:2] + text[3:]]
    if sum(g is not None for g in glyphs) < 3:
        return None
    from datetime import timedelta
    fits = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
    fits = [day for day in fits if all(g is None or g == ch for g, ch in zip(glyphs, day.strftime('%m%d')))]
    return fits[0] if len(fits) == 1 else None


def _pin_damaged_dates(result, statement):
    try:
        end = date.fromisoformat(statement.get('statement_date') or '')
        days = int(statement.get('printed_cycle_days') or 0)
    except ValueError:
        return
    if not 1 <= days <= MAX_CYCLE_DAYS:
        return
    from datetime import timedelta
    start = end - timedelta(days=days - 1)
    lines = [r for r in result if not r['excluded'] and r['kind'] in ('transaction', 'unresolved')]
    for position, row in enumerate(lines):
        if row['kind'] != 'unresolved' or _UNREAD_DATE not in row['issues'] or not row['fields'].get('amount_minor'):
            continue
        pinned = _glyph_date(row['source_cells'][0]['expected_text'], start, end)
        if pinned is None:
            continue
        before = [date.fromisoformat(r['fields']['date']) for r in lines[:position] if r['fields'].get('date')]
        after = [date.fromisoformat(r['fields']['date']) for r in lines[position + 1:] if r['fields'].get('date')]
        if (before and pinned < before[-1]) or (after and pinned > after[0]):
            continue
        row['fields'].update(date=pinned.isoformat(), date_basis=DAMAGED_DATE_BASIS)
        row['issues'] = [issue for issue in row['issues'] if issue != _UNREAD_DATE]
        row['kind'] = 'transaction'


def _pin_interest_dates(pending, total, statement, source, currency):
    if not pending or total is None or not statement.get('statement_date'):
        return
    readings = []
    for row in pending:
        try:
            value, amount_index = _transaction_amount(row['source_cells'], source, currency)
        except ValueError:
            return
        if value < 0:
            return
        readings.append((row, value, amount_index))
    if sum(value for _, value, _ in readings) != total:
        return
    for row, value, amount_index in readings:
        cells = row['source_cells']
        row.update(issues=[], kind='zero_charge' if value == 0 else 'transaction', excluded=value == 0,
                   fields=dict(description=cells[0]['expected_text'].strip(), counterparty='',
                               amount_minor=str(value), amount_column=str(cells[amount_index]['column_index']),
                               direction='debit', date=statement['statement_date'], date_basis=INTEREST_DATE_BASIS))


def propose_merrick_table(source, currency, statement):
    active = False
    header = None
    result = []
    balances, issues = merrick_summary_balances(source, currency)
    if not balances:
        balances = position_balances(source, currency)
        if balances:
            issues = []
    interest_section, interest_lines, interest_total = False, [], None
    for index, row in enumerate(source['rows']):
        cells = row['cells']
        texts = [c['expected_text'].strip() for c in cells]
        item = dict(id=f"{source['page_number']}:{source['table_index']}:{row['row_index']}",
                    page_number=source['page_number'],table_index=source['table_index'],row_index=row['row_index'],
                    source_revision=source['source_revision'],source_cells=cells,fields={},issues=[],excluded=True,kind='statement_information')
        if 'Transactions, Payments and Credits' in texts:
            active = True
            header = None
        if active and 'Item Description' in texts and 'Amount' in texts:
            header = _transaction_header(cells, source['page_number'], source['rows'][index + 1:])
        if any(re.fullmatch(r'20\d{2} Totals Year-to-Date', text) or text == 'Interest Charge Calculation' for text in texts):
            active = False
        if active and _section_heading(row, source['rows'][index+1:index+5]):
            # The Interest Charged heading opens the lines ``_pin_interest_dates`` may date.
            interest_section = INTEREST_ON_CLOSING_DATE and SequenceMatcher(
                None, re.sub(r'[^a-z]', '', texts[0].lower()), 'interestcharged').ratio() >= .72
            interest_lines = []
            result.append(item)
            continue
        match = re.fullmatch(r'(\d{1,2})/(\d{1,2})', texts[0]) if texts else None
        if active and len(texts) >= 3 and (match or _matches_transaction_columns(cells, header, source['page_number'])):
            item.update(excluded=False,kind='transaction' if match else 'unresolved')
            fields=item['fields']
            # Keep a detached printed minus out of the description even when
            # its geometry is unclear and the amount requires correction.
            middle=texts[1:-2] if texts[-1] == '-' else texts[1:-1]
            if (len(middle) > 1 and re.fullmatch(r'[A-Z0-9 ]{12,30}', middle[0])
                    and re.search(r'\d', middle[0]) and 12 <= len(middle[0].replace(' ', '')) <= 24):
                fields['bank_reference']=middle.pop(0)
            fields.update(description=' '.join(middle),counterparty='')
            year, closing_month=statement['date_year'],statement['date_month']
            month, day = (int(match[1]), int(match[2])) if match else (None, None)
            if match and year and closing_month and month in (closing_month, (closing_month-2)%12+1):
                try:
                    fields['date']=date(year-1 if closing_month==1 and month==12 else year,month,day).isoformat()
                    fields['date_context']=('Year constrained by printed billing cycle closing date and full year-to-date heading.'
                        if statement.get('statement_date_basis') == 'billing_cycle_closing_date'
                        else 'Year constrained by printed statement month and full year-to-date heading.')
                except ValueError:
                    pass
            if (fields.get('date') and statement.get('statement_date')
                    and re.match(r'^Interest Charge\b', fields['description'], re.IGNORECASE)
                    and fields['date'] != statement['statement_date']):
                item['issues'].append('The interest-charge date differs from the printed closing date. Check both dates in the PDF.')
            if 'date' not in fields:
                calendar_year = year - 1 if year and closing_month == 1 and month == 12 else year or 2000
                if match is None:
                    date_issue = 'Check the full date in the PDF. Its characters could not be read. The other recognised fields have been kept.'
                elif _printed_date(f'{month:02}/{day:02}/{calendar_year}') is None:
                    date_issue = 'This date has an invalid month or day. Check the date in the PDF.'
                elif year and closing_month and month not in (closing_month, (closing_month-2)%12+1):
                    date_issue = 'This date is outside the closing month and previous month. Check the date and the selected statement.'
                else:
                    date_issue = 'Check the full date. The printed statement context could not resolve its year.'
                item['issues'].append(date_issue)
            try:
                value, amount_index = _transaction_amount(cells, source, currency)
                fields.update(amount_minor=str(abs(value)), amount_column=str(cells[amount_index]['column_index']))
                if value > 0 and re.search(r'\b(?:MOBILE\s+)?PAYMENT\s*-\s*THANK\s+YOU\b', fields['description'], re.IGNORECASE):
                    item['issues'].append('This row describes a card payment, but no minus sign was read. Check its date and original amount in the PDF, then enter the amount under Credit or Debit.')
                    # The period's printed controls may fix it (card_summary).
                    fields['payment_sign_unread'] = True
                else:
                    fields['direction'] = 'credit' if value < 0 else 'debit'
                # A clearly labelled, positioned zero-interest line records
                # no charge. Its damaged date need not become an import task.
                # Unfamiliar zero-value rows still require their normal review.
                zero_interest = (
                    re.fullmatch(r'Interest Charge on (?:Purchases|Cash Advances):?',
                                 fields['description'], re.IGNORECASE)
                    and _matches_transaction_columns(cells, header, source['page_number'])
                )
                if value == 0 and (match or zero_interest):
                    item.update(excluded=True,kind='zero_charge')
                    item['issues']=[]
            except ValueError as exc:
                # Retain a measured target for automatic crop rereading. A
                # damaged amount is not permission to guess its column.
                if _matches_transaction_columns(cells, header, source['page_number']):
                    amount_index = len(cells) - (2 if texts[-1] == '-' else 1)
                    fields['amount_column'] = str(cells[amount_index]['column_index'])
                item['issues'].append(str(exc))
        elif active and texts and not (texts[0] in ('Transactions, Payments and Credits','Fees','Interest Charged') or texts[0].upper().startswith('TOTAL ') or any('Description' in text for text in texts)):
            item.update(excluded=False,kind='unresolved')
            item['issues'].append(_ROW_UNREAD)
            if interest_section and len(texts) == 2 and re.match(r'Interest Charge on \S', texts[0]):
                interest_lines.append(item)
        if interest_section and texts and texts[0].upper().startswith('TOTAL '):
            if texts[0] == 'TOTAL INTEREST FOR THIS PERIOD' and len(texts) == 2:
                try:
                    interest_total = _transaction_amount(cells, source, currency)[0]
                except ValueError:
                    interest_total = None
                _pin_interest_dates(interest_lines, interest_total, statement, source, currency)
            interest_section, interest_lines = False, []
        if row['row_index'] in balances:
            item.update(balances[row['row_index']])
        result.append(item)
    if DAMAGED_DATE_IN_CYCLE:
        _pin_damaged_dates(result, statement)
    _charge_controls(result, source, currency)
    return dict(rows=result, issues=issues)
