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
from copy import deepcopy

PERIOD_PINNING = True
RECOGNISED_READINGS = True
DAMAGED_CELLS = True
GLYPH_AGREEMENT = True
METHOD = 'andrews_period_pinned_reading'
VERIFICATION = 'tesseract_money_cell_verification'
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
    if not all(candidates.values()):
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

    while True:
        found_now = {}
        for key, readings in candidates.items():
            if key in pinned:
                continue
            fixed = [(text, cells) for text in readings.values() if (cells := pinning(key, text)) is not None]
            if len(fixed) == 1:
                found_now[key] = dict(text=fixed[0][0], pinned_by=[list(c) for c in fixed[0][1]])
        pinned.update(found_now)
        if not found_now:
            break
    if pinned.keys() != held.keys():
        return proposal
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
    result['period_pinned'] = dict(method=METHOD, cells=len(pinned), equations=len(equations), reconciles=True)
    return result
