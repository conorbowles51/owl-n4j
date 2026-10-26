"""Whole-period pinned reading of held Andrews money cells (printed controls across pages).

The evidence engine verifies every recognised money cell of a scanned Andrews
page against crops of the page image and holds each cell the crops do not
confirm. On each page it then accepts, for a held cell, the one printed reading
(page or crop) that the page's own agreed controls pin
(``statement_reading_quality.pinned_andrews_values``). A page cannot see the
controls printed on its neighbours: the first payment on a page has its
previous balance on the page before, the last one its next payment on the page
after, and the opening and ending balances may be pages apart.

This pass applies the same rule to the whole period, at review time, using
only what the engine stored: for each held cell the readings a recogniser
produced from the print (``printed_readings``), and which cells (or parts of a
joined amount and balance cell) the crops confirmed. A reading is accepted
only when it is pinned: one printed control of the period (previous balance +
signed payment = running balance; last balance = ending balance) holds with
it and contains it as its only unagreed cell, every other cell of that control
being confirmed, repaired by the engine, or pinned earlier in this pass. A
joined cell needs a control per unconfirmed part (both kinds when neither part
is confirmed), exactly as on a page. Exactly one reading of a cell may be
pinned. Arithmetic never supplies a value: only a printed reading can be
accepted.

All or nothing per period: the readings are used only when every held money
cell of the period's payments and balances is pinned and, with them in place,
every control of the period holds, from the opening to the ending balance.
Otherwise the proposal is returned unchanged. Each accepted cell is listed on
its row (``value_repairs``) with the page reading, the held text, the accepted
reading and the cells that pin it, so the machine reading stays visible beside
the accepted one. A reading made before the engine stored printed readings
offers no candidate and is left as it is.

``PERIOD_PINNING = False`` turns the pass off in one place.

``NATIVE_TEXT_GLYPHS``: a scan the producer already recognised (a native text
layer, e.g. Adobe Paper Capture) has no engine crop records, so its damaged
money cells had no candidate and every period with one waited for a person.
On such pages (every page of the period ``extraction_method == 'native'`` and
no engine verification record) the cells the reader could not parse are the
held cells, every money cell it did parse is the agreed page reading the
reader uses anyway, and each held cell offers the readings of its own printed
glyphs (``glyph_readings``: look-alike letters read as the digits they stand
for, a speck (or a dash/slash between digits) read as nothing, a point or a
minus, a comma before the cents read as the decimal point, one of several
points kept, spaces between digits ignored; each amount must print two
decimals). They are accepted exactly as above: pinned by a printed
control, exactly one reading per cell, all or nothing for the period, which
must then reconcile from its opening to its ending balance. Measured on the
five Andrews files of the Erica Hopper case (headless/FIN-ERICA-LESSONS.md).

Three wider sources of readings, each a fact the engine stored and each still
accepted only as above (switches in one place each):

* ``RECOGNISED_READINGS``: a held cell also offers every amount a recogniser
  stated for it (``recognised_readings``: the page reading or its glyph
  interpretation even when no crop repeats it, and each distinct crop
  amount). Measured on real Andrews scans: crops joined a dash between the
  amount and the balance, or read the minus as a point, while the page
  reading was the printed value; or two of six crops gave the printed value.
* ``DAMAGED_CELLS``: money cells whose page reading is not an amount at all
  (``2468:13``), which the engine now crops on Andrews pages
  (``damaged_cells``), are held cells like any other and offer their
  recognised readings.
* ``GLYPH_AGREEMENT``: a held cell whose page reading, its look-alike glyphs
  read as the digits they stand for, states exactly the amount at least four
  crop readings at both resolutions state (``page_glyphs_agree_with_crops``)
  is agreed with that reading: two recognisers state the same amount, which
  is what confirms any other cell. It still has to reconcile with the period.
"""
import itertools
import os
import re
from copy import deepcopy

PERIOD_PINNING = True
RECOGNISED_READINGS = True
DAMAGED_CELLS = True
GLYPH_AGREEMENT = True
# ``JOINT_GLYPHS``: damaged cells printed next to one another (a payment's amount and its balance, or two
# payments in a row) can never be pinned one at a time, since every control holding one holds another
# unagreed cell. When the cells left unpinned each offer exactly one reading of their own glyphs, they are
# taken together only if, with all of them in place, every printed control they stand in holds; the period
# must then reconcile from its opening to its ending balance as for any pinned reading. Off: such a period
# waits for a person, as before.
JOINT_GLYPHS = os.environ.get('LOUPE_FINANCIAL_ANDREWS_JOINT_GLYPHS', '1') != '0'
JOINT_BASIS = 'single_glyph_readings_jointly_pinned_by_printed_balances'
METHOD = 'andrews_period_pinned_reading'
VERIFICATION = 'tesseract_money_cell_verification'
NATIVE_TEXT_GLYPHS = os.environ.get('LOUPE_FINANCIAL_ANDREWS_NATIVE_GLYPHS', '1') != '0'
NATIVE_BASIS = 'native_text_glyphs_pinned_by_printed_balances'
# ``ONE_GLYPH``: on a native text layer, a damaged money cell none of whose glyph readings is pinned (a speck,
# '?' or a letter printed where a digit stands: '~293.42' for 2293.42, '20?2. 82' for 2072.82, '-43.0'Z' for
# -43.07) offers its readings with that one glyph read as each digit (``one_glyph_readings``); every other glyph
# stays as printed, so arithmetic fixes one digit and never a whole value. Exactly one such reading may be
# accepted, only when every printed control holding the cell holds with it and every other cell of those
# controls is agreed, and only when it is fixed twice: a balance by the payment before it and the payment
# after it; an amount by its own control, both of whose balances hold in another control. The period must then
# reconcile from its opening to its ending balance as for any pinned reading. Off: such a period waits for a
# person, as before.
ONE_GLYPH = os.environ.get('LOUPE_FINANCIAL_ANDREWS_ONE_GLYPH', '1') != '0'
ONE_GLYPH_BASIS = 'one_unread_glyph_fixed_by_printed_balances'
REPAIRS = ('statement_money_pinned_reading', 'statement_money_pinned_repair', 'statement_money_second_reader_repair')


def _key(page, cell):
    return (page, cell['table_index'], cell['row_index'], cell['column_index'])


def stored_cells(source_locations, pages):
    """``(held, agreed, parts)`` from the engine's records of ``pages``.

    ``held`` maps each still-held cell to its record entry; ``agreed`` is every
    cell the crops confirmed or a recorded repair accepted; ``parts`` the
    confirmed parts of held joined cells, as ``cell + (part,)``.
    """
    held, agreed, parts = {}, set(), set()
    for location in source_locations or []:
        if not isinstance(location, dict) or location.get('page_number') not in pages:
            continue
        page = location['page_number']
        records = [r for r in location.get('ocr_refinements') or [] if isinstance(r, dict)]
        verification = [r for r in records if r.get('method') == VERIFICATION]
        if len(verification) != 1 or verification[0].get('error'):
            continue
        repaired = {_key(page, c) for r in records if r.get('method') in REPAIRS and r.get('decision') == 'repaired'
                    for c in r.get('cells') or []}
        cells = list(verification[0].get('cells') or [])
        if DAMAGED_CELLS:
            cells += [c for c in verification[0].get('damaged_cells') or [] if isinstance(c, dict) and not c.get('error')]
        for cell in cells:
            key = _key(page, cell)
            if cell.get('status') == 'confirmed' or key in repaired:
                agreed.add(key)
            else:
                held[key] = cell
                parts.update(key + (name,) for name in cell.get('confirmed_parts') or ())
    return held, agreed, parts


# Glyphs a recogniser prints for a digit, and specks it prints for nothing,
# a decimal point or a minus sign. Only money cells are read this way.
_DIGIT_LOOKALIKES = str.maketrans({'O': '0', 'o': '0', 'D': '0', 'l': '1', 'I': '1', '|': '1', 'i': '1', '!': '1',
                                   'B': '8', 'S': '5', 's': '5', 'Z': '2', 'z': '2'})
_SPECKS = '·•_\'’‘`"“”~^*°' + (':;' if os.environ.get('LOUPE_FINANCIAL_ANDREWS_COLON_POINT', '1') != '0' else '')
_MAX_MARKS = 4
_PRINTED_AMOUNT = re.compile(r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}')
_MONEY_ISSUES = ('Check the transaction amount in the PDF. Its digits, sign or decimal point could not be read.',
                 'Check the running balance in the PDF. It could not be read separately from the transaction amount.',
                 'Check this balance in the PDF. Its digits or decimal point could not be read.')


def _one_point(part):
    """A part printing several points (``1.171.75``, ``3207.6.8``): each way of keeping one of them."""
    if part.count('.') < 2:
        return [part]
    points = [i for i, ch in enumerate(part) if ch == '.']
    return [''.join(ch for i, ch in enumerate(part) if ch != '.' or i == keep) for keep in points]


def glyph_readings(text):
    """The clean readings a damaged text-layer money cell's own glyphs allow (one or two amounts each).

    ``-16,30`` -> ``-16.30``; ``479·_54`` -> ``479.54``; ``·ll . 20`` -> ``11.20`` and
    ``-11.20``; ``-22 .6 8 1351 . 77`` -> ``-22.68 1351.77``; ``BOO.OD`` -> ``800.00``;
    ``819-82`` -> ``819.82``. A reading is only ever a candidate: the period's
    printed controls must pin it, exactly one reading per cell.
    """
    base = re.sub(r'\.(?:\s*\.)+', '.', (text or '').translate(_DIGIT_LOOKALIKES))
    base = re.sub(r'\s*,\s*(\d{2})(?!\d)', r',\1', base)
    # A speck, or a dash or slash printed between two digits (``819-82``, ``6673 /50``).
    marks = [i for i, ch in enumerate(base) if ch in _SPECKS
             or ch in '-/' and re.search(r'\d\s*$', base[:i]) and re.match(r'\s*\d', base[i + 1:])]
    if len(marks) > _MAX_MARKS:
        return []
    found = []
    for choice in itertools.product(('', '.', '-'), repeat=len(marks)):
        chars = list(base)
        for i, value in zip(marks, choice):
            chars[i] = value
        candidate = re.sub(r',(\d{2})(?!\d)', r'.\1', ''.join(chars).strip(' .,'))
        candidate = re.sub(r'(?<=[+-])\s+', '', candidate)
        if re.search(r'\d-', candidate):
            continue
        parts = candidate.split()
        readings = []
        for i in range(0, len(parts)):
            if i == 0 and sum('.' in part for part in parts) > 1:
                continue  # two printed amounts are never one
            sides = [''.join(parts)] if i == 0 else [''.join(parts[:i]), ''.join(parts[i:])]
            for chosen in itertools.product(*[_one_point(side) for side in sides]):
                if all(_PRINTED_AMOUNT.fullmatch(side) for side in chosen):
                    readings.append(' '.join(chosen))
        for reading in readings:
            if reading not in found:
                found.append(reading)
    return found


def one_glyph_readings(text):
    """``[(reading, part)]``: the readings of ``text`` with one glyph that is no digit read as each digit.

    The glyph is a look-alike letter, a speck or ``?`` printed where a digit
    stands (``~293.42``, ``-43.0'Z``, ``20?2. 82``); every other glyph is read
    as ``glyph_readings`` reads it. ``part`` names the value of a joined
    amount-and-balance cell the glyph is in ('amount' or 'balance'), or None
    for a cell of one value. Only candidates: ``pin_period`` accepts one only
    as ONE_GLYPH describes.
    """
    text = text or ''
    found = []
    for i, ch in enumerate(text):
        if not (ch in _SPECKS or ch == '?' or ord(ch) in _DIGIT_LOOKALIKES):
            continue
        by_digit = [glyph_readings(text[:i] + d + text[i + 1:]) for d in '0123456789']
        if len({len(readings) for readings in by_digit}) != 1:
            continue  # the digit changes how the rest of the cell reads
        for position in range(len(by_digit[0])):
            values = [readings[position].split() for readings in by_digit]
            if len({len(v) for v in values}) != 1:
                continue
            changed = {j for j in range(len(values[0])) if len({v[j] for v in values}) > 1}
            if len(changed) != 1:
                continue
            part = None if len(values[0]) == 1 else ('amount', 'balance')[changed.pop()]
            for readings in by_digit:
                if readings[position] not in [r for r, _ in found]:
                    found.append((readings[position], part))
    return found


def native_text_pages(source_locations, pages):
    """Whether every page is a native text layer with no engine verification record."""
    by_page = {l.get('page_number'): l for l in source_locations or [] if isinstance(l, dict)}
    return bool(pages) and all(
        by_page.get(page, {}).get('extraction_method') == 'native'
        and not any(isinstance(r, dict) and r.get('method') == VERIFICATION
                    for r in by_page[page].get('ocr_refinements') or [])
        for page in pages)


def native_cells(rows, sources):
    """``(held, agreed, parts)`` for a native text layer: the money cells the reader could not parse are held."""
    from services.financial.statement_import_andrews import _heading, _money_cells
    widths = {(s['page_number'], s['table_index']): _heading(s)['width'] for s in sources}
    held, money, parts = {}, set(), set()
    for row in rows:
        if not (row['kind'] == 'balance' or (not row['excluded'] and row['kind'] in ('transaction', 'unresolved'))):
            continue
        width = widths.get((row['page_number'], row['table_index']))
        if width is None:
            continue
        cells = _money_cells(dict(cells=row['source_cells']), width)
        keys = [(row['page_number'], row['table_index'], row['row_index'], c['column_index']) for c in cells]
        money.update(keys)
        failed = [m for m in row.get('issues') or [] if m in _MONEY_ISSUES]
        if not failed or row.get('value_sources'):
            continue
        fields = row['fields']
        if len(cells) == 2 and row['kind'] != 'balance':
            targets = [i for i, name in ((0, 'amount_minor'), (1, 'balance')) if name not in fields]
        else:
            targets = list(range(len(cells)))
        for i in targets:
            key = keys[i]
            held[key] = dict(table_index=key[1], row_index=key[2], column_index=key[3],
                             original_text=cells[i]['expected_text'], status='unconfirmed', observations=[],
                             printed_readings=[[t, 'native_text_glyphs'] for t in glyph_readings(cells[i]['expected_text'])])
            if len(cells) == 1 and row['kind'] != 'balance':
                parts.update(key + (name,) for name, field in (('amount', 'amount_minor'), ('balance', 'balance'))
                             if field in fields)
    return held, money - set(held), parts


def _with_texts(sources, texts):
    """``sources`` with the cell texts in ``texts`` (keyed by page, table, row, column) replaced."""
    if not texts:
        return sources
    result = []
    for source in sources:
        page, table = source['page_number'], source['table_index']
        if not any(k[0] == page and k[1] == table for k in texts):
            result.append(source)
            continue
        rows = []
        for row in source['rows']:
            cells = [dict(c, expected_text=texts[(page, table, row['row_index'], c['column_index'])])
                     if (page, table, row['row_index'], c['column_index']) in texts else c for c in row['cells']]
            rows.append(dict(row, cells=cells))
        result.append(dict(source, rows=rows))
    return result


def period_equations(rows):
    """``[(cells, holds)]`` for every printed control of one period whose cells all parse.

    The period form of ``statement_reading_quality._andrews_equations``: cells
    are keyed by page as well, so a payment's previous balance may be on the
    page before, and the ending balance closes the chain wherever it prints.
    """
    equations, previous = [], None
    for row in rows:
        fields = row['fields']
        if row['kind'] == 'balance':
            cell = ((row['page_number'], row['table_index'], row['row_index'], int(fields['balance_column']))
                    if 'balance' in fields and fields.get('balance_column') is not None else None)
            point = (cell, int(fields['balance'])) if cell else None
            if fields.get('description') == 'Opening Balance':
                previous = point
            elif fields.get('description') == 'Closing Balance':
                if previous and point:
                    equations.append(([previous[0], point[0]], previous[1] == point[1]))
                previous = None
        elif row['kind'] == 'continuation' or row['excluded'] and row['kind'] == 'statement_information':
            continue
        else:
            point = None
            if (row['kind'] == 'transaction' and not row.get('value_sources')
                    and all(fields.get(k) is not None for k in ('balance', 'balance_column'))):
                point = ((row['page_number'], row['table_index'], row['row_index'], int(fields['balance_column'])),
                         int(fields['balance']))
                if previous and all(fields.get(k) is not None for k in ('amount_minor', 'direction', 'amount_column')):
                    amount_cell = (row['page_number'], row['table_index'], row['row_index'], int(fields['amount_column']))
                    movement = int(fields['amount_minor']) * (1 if fields['direction'] == 'credit' else -1)
                    equations.append(([previous[0], amount_cell, point[0]], previous[1] + movement == point[1]))
            previous = point
    return equations


def _chain_cells(rows):
    """Every money cell of the period's payments and printed balances (page, table, row, column)."""
    cells = set()
    for row in rows:
        if row['kind'] == 'balance' or (not row['excluded'] and row['kind'] in ('transaction', 'unresolved')):
            for cell in row['source_cells']:
                cells.add((row['page_number'], row['table_index'], row['row_index'], cell['column_index']))
    return cells


def pin_period(proposal, sources, currency, statement, source_locations):
    """``proposal`` with the held money cells the period's agreed controls pin, or unchanged."""
    from services.financial.statement_import_andrews import propose_andrews_statement
    from services.financial.statement_reading_quality import _andrews_reading
    if not PERIOD_PINNING:
        return proposal
    pages = {s['page_number'] for s in sources}
    held, agreed_cells, parts = stored_cells(source_locations, pages)
    chain = _chain_cells(proposal['rows'])
    held = {key: cell for key, cell in held.items() if key in chain}
    native = False
    if not held and NATIVE_TEXT_GLYPHS and native_text_pages(source_locations, pages):
        held, agreed_cells, parts = native_cells(proposal['rows'], sources)
        held = {key: cell for key, cell in held.items() if key in chain}
        native = bool(held)
    if not held:
        return proposal
    candidates, context = {}, {}
    for key, cell in held.items():
        readings = {}
        offered = list(cell.get('printed_readings') or ())
        if RECOGNISED_READINGS:
            offered += list(cell.get('recognised_readings') or ())
        for item in offered:
            text = item[0] if isinstance(item, (list, tuple)) else None
            try:
                readings.setdefault(_andrews_reading(text), text)
            except Exception:
                if not RECOGNISED_READINGS:
                    readings = {}
                    break
                # A reading the statement reader cannot parse (``74.20-``) is
                # no candidate; the cell's other readings still are.
                continue
        candidates[key] = readings
        if cell.get('confirmed_parts') and cell.get('confirmed_parts_text'):
            context[key] = cell['confirmed_parts_text']
    if not all(readings or (native and ONE_GLYPH and one_glyph_readings(held[key].get('original_text')))
               for key, readings in candidates.items()):
        return proposal
    pinned = {}
    if GLYPH_AGREEMENT:
        for key, cell in held.items():
            text = cell.get('page_glyphs_agree_with_crops')
            try:
                value = _andrews_reading(text) if text else None
            except Exception:
                value = None
            if value is not None and value in candidates[key]:
                pinned[key] = dict(text=candidates[key][value], pinned_by=[], basis='page_glyphs_agree_with_crops')

    def agreed(cell, role):
        return cell + (role,) in parts or cell in pinned or (cell in agreed_cells and cell not in held)

    def roles(cells):
        return ('balance', 'amount', 'balance') if len(cells) == 3 else ('balance', 'balance')

    def rows_with(texts):
        return propose_andrews_statement(_with_texts(sources, texts), currency, statement)['rows']

    def pinning(key, text):
        texts = {**context, **{cell: value['text'] for cell, value in pinned.items()}, key: text}
        found = [cells for cells, holds in period_equations(rows_with(texts))
                 if holds and key in cells
                 and all(agreed(other, role) for other, role in zip(cells, roles(cells)) if other != key)]
        if len(_andrews_reading(text)) == 2:
            own = [cells for cells in found if cells.count(key) == 2]
            onward = [cells for cells in found if cells.count(key) == 1 and cells[0] == key]
            amount_ok, balance_ok = (key + (name,) in parts for name in ('amount', 'balance'))
            if amount_ok:
                found = own or onward
            elif balance_ok:
                found = own
            elif own and onward:
                found = [own[0] + onward[0]]
            else:
                found = []
        if not found:
            return None
        return sorted({tuple(other) for other in found[0] if other != key})

    def one_glyph(key):
        """(ONE_GLYPH) The one reading with one unread glyph that the printed controls fix, else None."""
        found = []
        for text, part in one_glyph_readings(held[key].get('original_text')):
            texts = {**context, **{cell: value['text'] for cell, value in pinned.items()}, key: text}
            equations = period_equations(rows_with(texts))
            standing = [cells for cells, _ in equations if key in cells]
            if not standing or not all(holds for cells, holds in equations if key in cells) or not all(
                    agreed(other, role) for cells in standing for other, role in zip(cells, roles(cells)) if other != key):
                continue
            own = [cells for cells in standing if len(cells) == 3 and cells[1] == key]
            if (part or ('amount' if own else 'balance')) == 'balance':
                # Fixed twice: by the payment before it and by the payment after it.
                ok = any(cells[-1] == key for cells in standing) and any(cells[0] == key for cells in standing)
            else:
                # Fixed by its own control, whose two balances each hold in another control.
                ok = len(own) == 1 and all(any(holds and cells != own[0] and cells[end] == own[0][side]
                                               for cells, holds in equations) for side, end in ((0, -1), (2, 0)))
            if ok:
                found.append((text, sorted({tuple(other) for cells in standing for other in cells if other != key})))
        return found[0] if len(found) == 1 else None

    while True:
        found_now = {}
        for key, readings in candidates.items():
            if key in pinned:
                continue
            fixed = [(text, cells) for text in readings.values() if (cells := pinning(key, text)) is not None]
            if len(fixed) == 1:
                found_now[key] = dict(text=fixed[0][0], pinned_by=[list(c) for c in fixed[0][1]])
        if not found_now and native and ONE_GLYPH:
            for key in held:
                if key not in pinned and (fixed := one_glyph(key)) is not None:
                    found_now[key] = dict(text=fixed[0], basis=ONE_GLYPH_BASIS, pinned_by=[list(c) for c in fixed[1]])
                    break
        pinned.update(found_now)
        if not found_now:
            break
    left = [key for key in held if key not in pinned]
    if left and JOINT_GLYPHS and all(len(candidates[key]) == 1 for key in left):
        texts = {**context, **{cell: value['text'] for cell, value in pinned.items()},
                 **{key: next(iter(candidates[key].values())) for key in left}}
        standing = [(cells, holds) for cells, holds in period_equations(rows_with(texts))
                    if any(key in cells for key in left)]
        if (all(holds for _, holds in standing)
                and all(any(key in cells for cells, _ in standing) for key in left)):
            for key in left:
                pinned[key] = dict(text=texts[key], basis=JOINT_BASIS, pinned_by=sorted(
                    {tuple(other) for cells, _ in standing if key in cells for other in cells if other != key}))
                pinned[key]['pinned_by'] = [list(c) for c in pinned[key]['pinned_by']]
    if pinned.keys() != held.keys():
        return proposal
    if native:
        for value in pinned.values():
            value.setdefault('basis', NATIVE_BASIS)
    texts = {key: value['text'] for key, value in pinned.items()}
    repaired = propose_andrews_statement(_with_texts(sources, texts), currency, statement)
    equations = period_equations(repaired['rows'])
    payments = [r for r in repaired['rows'] if not r['excluded'] and r['kind'] in ('transaction', 'unresolved')]
    closings = [r for r in repaired['rows'] if r['kind'] == 'balance' and r['fields'].get('description') == 'Closing Balance']
    if (not equations or not all(holds for _, holds in equations) or not closings
            or any(r['fields'].get(k) is None for r in payments for k in ('amount_minor', 'direction', 'balance'))):
        return proposal
    by_row = {}
    for key, value in sorted(pinned.items()):
        cell = held[key]
        by_row.setdefault(key[:3], []).append(dict(method=METHOD, page_number=key[0], table_index=key[1],
            row_index=key[2], column_index=key[3], page_reading=cell.get('original_text'),
            held_text=cell.get('marked_text') or cell.get('original_text'), text=value['text'],
            accepted_reading=dict([*(cell.get('recognised_readings') or ()),
                                   *(cell.get('printed_readings') or ())]).get(value['text']),
            pinned_by=value['pinned_by'], observations=len(cell.get('observations') or []),
            **({'basis': value['basis']} if value.get('basis') else {})))
    result = deepcopy(repaired)
    for row in result['rows']:
        repairs = by_row.get((row['page_number'], row['table_index'], row['row_index']))
        if repairs:
            row['value_repairs'] = repairs
    result['period_pinned'] = dict(method=METHOD, cells=len(pinned), equations=len(equations), reconciles=True,
                                   **({'basis': NATIVE_BASIS} if native else {}))
    return result
