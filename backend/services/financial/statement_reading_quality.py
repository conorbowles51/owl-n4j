"""Decide when a recognised statement's embedded text merits an image reread.

This assesses parsing, not evidential accuracy. A reread must retain the same
printed identity, number of payments and balance controls before fewer unreadable
fields can make it preferable. Arithmetic is never used to manufacture values.
"""
import re


def sources_from_tables(tables):
    sources = []
    for index, item in enumerate(tables):
        table = item.get('table') or {}
        rows = {}
        for cell in table.get('values', []):
            if cell.get('text'):
                rows.setdefault(cell['row'], []).append(dict(column_index=cell['column'],
                    expected_text=cell['text'], locator=cell.get('locator')))
        if rows:
            sources.append(dict(page_number=table['page'], table_index=index,
                source_revision='reading-quality', table_source=item.get('table_source'), rows=[dict(row_index=i,
                    cells=sorted(cells, key=lambda c: c['column_index'])) for i, cells in sorted(rows.items())]))
    return sources


_LABELLED_IDENTITY = (('institution', ('Bank', 'Institution')), ('holder', ('Account Name', 'Account Holder')),
    ('account', ('Account Number', 'Account No', 'IBAN')), ('currency', ('Currency',)),
    ('period', ('Statement Period', 'Period')))


def labelled_statement(sources):
    """The printed header of a generic labelled statement page, or None.

    These are the facts the statement review reads from labelled lines, so an
    image reading must reproduce every one of them. OCR can split one printed
    line into several cells; a row is read as its whole printed line and the
    period is compared as dates. A page without its own account number and
    period, or without a labelled payments table, is not assessed.
    """
    from services.financial.money import MoneyError, get_currency
    from services.financial.statement_import_proposal import has_transaction_header, printed_label, printed_period
    if not any(has_transaction_header(source) for source in sources):
        return None
    text = '\n'.join(' '.join(' '.join(cell['expected_text'] for cell in row['cells']).split())
        for source in sources for row in source['rows'])
    printed = {key: printed_label(text, labels) for key, labels in _LABELLED_IDENTITY}
    start, end = printed_period(printed['period'])
    if not printed['account'] or not start:
        return None
    try:
        currency = get_currency(printed['currency'].upper()).code if printed['currency'] else 'USD'
    except MoneyError:
        currency = 'USD'
    return dict(identity=['generic-labelled', printed['institution'], printed['holder'], printed['account'],
        printed['currency'], start, end], currency=currency)


def propose_labelled_rows(sources, statement):
    from services.financial.statement_import_proposal import has_transaction_header, propose_table
    header_pages = {s['page_number'] for s in sources if has_transaction_header(s)}
    return [row for source in sources for row in propose_table({**source, 'case_id': '', 'evidence_file_id': ''},
        statement['currency'], page_has_transaction_table=source['page_number'] in header_pages)['rows']]


def _page_statement_rows(sources):
    """``(identity, rows)`` for one recognised page reading, or ``None``.

    The layout is chosen exactly as the reading check chooses it; ``None``
    means no supported layout claims the page.
    """
    from services.financial.statement_import_credit_one import credit_one_catalog, propose_credit_one_table
    from services.financial.statement_import_andrews import andrews_page, propose_andrews_statement
    from services.financial.statement_import_merrick import merrick_statement, propose_merrick_table
    if not sources:
        return None
    cards, _ = credit_one_catalog(sources)
    merrick = merrick_statement(sources[0]) if len(sources) == 1 else None
    if len(cards) == 1:
        card = cards[0]
        identity = [card[key] for key in ('layout_id', 'account_reference', 'period_start', 'period_end')]
        rows = [r for s in sources for r in propose_credit_one_table(s, 'USD', card)['rows']]
    elif merrick:
        # A missing identity needs explicit identity recovery, not a payment
        # reread whose candidate happens to have the same empty identifier.
        if not merrick['account_reference'] or not merrick['statement_date'] or merrick.get('date_conflict'):
            return None
        identity = [merrick['layout_id'], merrick['account_reference'], merrick['statement_date']]
        rows = propose_merrick_table(sources[0], 'USD', merrick)['rows']
    elif (labelled := None if any(andrews_page(s, allow_unbranded=True) for s in sources)
            else labelled_statement(sources)):
        identity = labelled['identity']
        rows = propose_labelled_rows(sources, labelled)
    else:
        pages = [andrews_page(s, allow_unbranded=True) for s in sources]
        if len(pages) != 1 or not pages[0]:
            return None
        page = pages[0]
        identity = ['andrews-share-statement', page['account'], page['start'], page['end'], page['printed_page']]
        scope = dict(page_number=sources[0]['page_number'], table_index=0,
            heading_rows=page['heading_rows'], row_indices=[r['row_index'] for r in sources[0]['rows']
                if r['row_index'] >= page['body_start']])
        statement = dict(period_start=page['start'], period_end=page['end'], sources=[scope])
        rows = propose_andrews_statement(sources, 'USD', statement)['rows']
    return identity, rows


def assess_statement_reading(tables):
    found = _page_statement_rows(sources_from_tables(tables))
    if found is None:
        return None
    identity, rows = found
    # Merrick and generic rows that fit no printed column are still payments
    # whose fields are unreadable; a reread that adds or drops one is refused.
    payments = [r for r in rows if not r['excluded'] and (r['kind'] == 'transaction'
        or (identity[0] in ('merrick-card', 'generic-labelled') and r['kind'] == 'unresolved')
        or 'date_column' in r['fields'] or 'amount_column' in r['fields'])]
    balances = [r for r in rows if r['kind'] == 'balance']
    # Valid but different balances require review, not another guess at digits.
    missing = {field: sum(not r['fields'].get(field) for r in payments)
        for field in ('date', 'amount_minor', 'direction')}
    missing['booking_date'] = sum('booking_date_column' in r['fields'] and not r['fields'].get('booking_date') for r in payments)
    # Andrews prints a running balance on every payment. Its parser can only
    # identify balance_column after separating readable money; relying on that
    # successful parse concealed damaged balances from the image-reread check.
    missing['balance'] = sum(('balance_column' in r['fields']
        or r['fields'].get('statement_layout') == 'andrews-share-statement')
        and 'balance' not in r['fields'] for r in payments)
    missing['statement_balance'] = sum('balance' not in r['fields'] for r in balances)
    zero_charges = sum(r['kind'] == 'zero_charge' for r in rows)
    result = dict(identity=identity, payments=len(payments), payment_rows=len(payments) + zero_charges,
        zero_charge_rows=zero_charges, balances=len(balances), missing_fields=missing, unreadable=sum(missing.values()))
    # Preserve readable facts across every supported family, not just counts.
    # One repaired cell must not silently alter another payment or control.
    result['known_rows'] = [{key: r['fields'][key] for key in
        ('date', 'booking_date', 'value_date', 'amount_minor', 'direction',
         'description', 'bank_reference', 'balance', 'additional_printed_date')
        if key in r['fields']} for r in rows
        if r in payments or r['kind'] in ('zero_charge', 'balance', 'statement_total')]
    return result


def prefer_image_reading(original, image):
    def preserves_known_rows():
        if 'known_rows' not in original:
            return True
        before, after = original['known_rows'], image.get('known_rows', [])
        return len(before) == len(after) and all(
            all(candidate.get(key) == value for key, value in row.items())
            for row, candidate in zip(before, after))
    def physical_rows(reading):
        if 'payment_rows' not in reading:
            return reading['payments']
        count = reading['payments'] + reading.get('zero_charge_rows', 0)
        return count if count == reading['payment_rows'] else None
    return bool(original and image and original['identity'] == image['identity']
        and preserves_known_rows()
        and physical_rows(original) is not None and physical_rows(original) == physical_rows(image)
        and original['balances'] == image['balances']
        and (not original.get('missing_fields') or not image.get('missing_fields') or
            all(image['missing_fields'].get(field, 0) <= count for field, count in original['missing_fields'].items()))
        and image['unreadable'] < original['unreadable'])


def pinned_running_balance_values(tables, disputed):
    """Crop readings that a generic running-balance statement fixes on its own.

    ``disputed`` maps ``(table_index, row, column)`` to the value every crop
    reading of that money cell gave, where it contradicts the page reading.
    Arithmetic alone cannot choose between two readings that both reconcile,
    which is exactly what compensating misreads do. So a crop value is only
    accepted when it is pinned: one printed control equation (previous
    balance, payment, running balance; or last balance and closing balance)
    contains it as its only disputed cell, every other cell of that equation
    was read the same by the page and the crops, and the equation holds with
    the crop value. The page reading then contradicts both the image and the
    agreed controls. Every disputed cell must be pinned and the whole chain
    must reconcile, or nothing is accepted and the page stays held.

    Returns ``{cell: dict(text=..., pinned_by=[cells])}`` or ``{}``.
    """
    if not disputed:
        return {}
    candidate = []
    for index, item in enumerate(tables):
        table = item.get('table') or {}
        values = [{**cell, 'text': disputed.get((index, cell['row'], cell['column']), cell.get('text'))}
                  for cell in table.get('values', [])]
        candidate.append({**item, 'table': {**table, 'values': values}})
    sources = sources_from_tables(candidate)
    if len(sources) != 1:
        return {}
    statement = labelled_statement(sources)
    if not statement:
        return {}
    source = sources[0]
    rows = propose_labelled_rows(sources, statement)
    from services.financial.statement_import_proposal import has_transaction_header
    header = next((i for i, r in enumerate(rows) if r['kind'] == 'header'
                   and has_transaction_header(dict(rows=[dict(cells=r['source_cells'])]))), None)
    if header is None:
        return {}
    body = [r for r in rows[header + 1:] if not (r['kind'] == 'header' and r['excluded'])]

    def cell(row, column_key):
        return (source['table_index'], row['row_index'], int(row['fields'][column_key]))

    opening = closing = None
    steps, totals = [], []
    for row in body:
        fields = row['fields']
        if row['issues'] or row['kind'] not in ('balance', 'transaction', 'statement_total'):
            return {}
        if row['kind'] == 'balance':
            if 'balance' not in fields or fields.get('normalized_balance_label'):
                return {}
            if fields['description'] == 'Opening Balance' and opening is None and not steps:
                opening = (cell(row, 'balance_column'), int(fields['balance']))
            elif fields['description'] == 'Closing Balance' and closing is None and opening is not None:
                closing = (cell(row, 'balance_column'), int(fields['balance']))
            else:
                return {}
        elif row['kind'] == 'statement_total':
            totals.append(row)
        else:
            if closing is not None or opening is None or row['excluded']:
                return {}
            role = fields.get('direction')
            if role not in ('credit', 'debit') or role not in fields or 'balance' not in fields:
                return {}
            movement = int(fields['amount_minor']) * (1 if role == 'credit' else -1)
            steps.append(((cell(row, role + '_column'), movement), (cell(row, 'balance_column'), int(fields['balance']))))
    if opening is None or closing is None:
        return {}
    equations, previous = [], opening
    for (amount_cell, movement), balance in steps:
        equations.append(([previous[0], amount_cell, balance[0]], previous[1] + movement == balance[1]))
        previous = balance
    equations.append(([previous[0], closing[0]], previous[1] == closing[1]))
    for row in totals:
        direction = row['fields']['total_direction']
        printed = int(row['fields']['balance'])
        members = [amount for amount, movement in (s[0] for s in steps) if (movement > 0) == (direction == 'credit')]
        total = sum(abs(movement) for _, movement in (s[0] for s in steps) if (movement > 0) == (direction == 'credit'))
        equations.append(([cell(row, 'balance_column'), *members], printed == total))
    if not all(holds for _, holds in equations):
        return {}
    accepted = {}
    for key, text in disputed.items():
        pinning = next((cells for cells, _ in equations if key in cells
                        and not any(other in disputed for other in cells if other != key)), None)
        if pinning is None:
            return {}
        accepted[key] = dict(text=text, pinned_by=[list(other) for other in pinning if other != key])
    return accepted


_LIABILITY_LAYOUTS = ('merrick-card', 'credit-one-card')


def page_controls_reconcile(tables):
    """Whether every printed control on one recognised page reconciles.

    Used before a disputed money cell may take a second reader's value: two
    compensating misreads reconcile too, so this never chooses a value, it
    only refuses one that the page's own controls contradict. Each statement
    on the page is checked as the review checks it (an Andrews page can carry
    several share statements). Every statement must be complete on this page:
    its closing balance must be printed here and match, no check may show a
    difference and no row may be flagged. A control printed on another page
    cannot be confirmed here, so such a page never reconciles.

    Returns ``dict(reconciles=bool, statements=[...])`` or ``None`` when no
    supported layout claims the page.
    """
    from services.financial.statement_review_checks import check_statement_rows
    sources = sources_from_tables(tables)
    found = _page_statement_rows(sources)
    if found is None:
        return None
    identity, rows = found
    statements = [(identity, rows)]
    if identity[0] == 'andrews-share-statement':
        from services.financial.statement_import_andrews import andrews_catalog, propose_andrews_statement
        groups, _, incomplete = andrews_catalog(sources)
        if not groups or incomplete:
            return dict(reconciles=False, statements=[], reason='andrews_statements_not_separable')
        statements = [([group['layout_id'], group['account_reference'], group['period_start'], group['period_end']],
                       propose_andrews_statement(sources, 'USD', group)['rows']) for group in groups]
    summaries = []
    for statement_identity, statement_rows in statements:
        result = check_statement_rows(statement_rows, liability=statement_identity[0] in _LIABILITY_LAYOUTS)
        summaries.append(dict(identity=statement_identity, flagged_rows=result['flagged_rows'],
            checks=[dict(kind=c['kind'], status=c['status']) for c in result['checks']],
            reconciles=(result['flagged_rows'] == 0 and result['balance_status'] == 'matches'
                        and not result['has_difference'])))
    return dict(reconciles=bool(summaries) and all(s['reconciles'] for s in summaries), statements=summaries)


def _with_texts(tables, texts):
    """``tables`` (stored JSON form) with the cell texts in ``texts`` replaced."""
    result = []
    for index, item in enumerate(tables):
        table = item.get('table') or {}
        values = [{**cell, 'text': texts.get((index, cell['row'], cell['column']), cell.get('text'))}
                  for cell in table.get('values', [])]
        result.append({**item, 'table': {**table, 'values': values}})
    return result


def _andrews_equations(rows):
    """``[(cells, holds)]`` for every printed Andrews control whose cells all parse.

    Each payment gives ``previous balance + signed amount = running balance``
    and each section ends with ``last balance = ending balance``. A row that
    does not yield every number, a direction and its measured columns breaks
    the chain there; no equation spans it. A payment whose sign contradicts
    its printed verb has no direction, so it yields no equation.
    """
    equations, previous = [], None
    for row in rows:
        fields = row['fields']
        if row['kind'] == 'balance':
            cell = ((row['table_index'], row['row_index'], int(fields['balance_column']))
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
                    and all(fields.get(k) is not None for k in
                            ('amount_minor', 'direction', 'balance', 'amount_column', 'balance_column'))):
                amount_cell = (row['table_index'], row['row_index'], int(fields['amount_column']))
                point = ((row['table_index'], row['row_index'], int(fields['balance_column'])), int(fields['balance']))
                movement = int(fields['amount_minor']) * (1 if fields['direction'] == 'credit' else -1)
                if previous:
                    equations.append(([previous[0], amount_cell, point[0]], previous[1] + movement == point[1]))
            previous = point
    return equations


def pinned_andrews_values(tables, candidates):
    """The one reading of each disputed Andrews money cell that the page's agreed controls fix.

    ``candidates`` maps ``(table_index, row, column)`` to the readings of that
    cell that a recogniser actually produced from the print (the page reading,
    the crop reading, or for a cell whose sign glyph was unreadable, its agreed
    digits with and without the minus). Arithmetic alone cannot choose between
    readings that both reconcile, which is what compensating misreads do, so a
    reading is accepted only when it is pinned: one printed control equation
    (previous balance, payment, running balance; or last balance and ending
    balance) contains the cell as its only disputed cell, every other cell of
    that equation is one the page and the crops read the same way, and the
    equation holds with that reading. Exactly one candidate of each cell must
    be pinned, every disputed cell must be resolved, and with all of them in
    place every printed control on the page must reconcile. Otherwise nothing
    is accepted and the page stays held.

    Returns ``dict(values={cell: dict(text=..., pinned_by=[cells])}, controls=...)``,
    ``{}`` when nothing is accepted, or ``None`` when no Andrews layout claims the page.
    """
    from services.financial.statement_import_andrews import andrews_catalog, propose_andrews_statement
    from services.financial.statement_import_proposal import exact_amount
    found = _page_statement_rows(sources_from_tables(tables))
    if found is None or found[0][0] != 'andrews-share-statement':
        return None
    if not candidates or not all(candidates.values()):
        return {}
    disputed = set(candidates)

    def pinning(key, text):
        sources = sources_from_tables(_with_texts(tables, {key: text}))
        if len(sources) != 1:
            return None
        groups, _, incomplete = andrews_catalog(sources)
        if not groups or incomplete:
            return None
        for group in groups:
            for cells, holds in _andrews_equations(propose_andrews_statement(sources, 'USD', group)['rows']):
                if holds and key in cells and not any(other in disputed for other in cells if other != key):
                    return [list(other) for other in cells if other != key]
        return None

    accepted = {}
    for key, texts in candidates.items():
        by_value = {}
        for text in texts:
            try:
                by_value.setdefault(exact_amount(re.sub(r'[\s,$]', '', text), 'USD'), text)
            except Exception:
                return {}
        fixed = [(text, cells) for text in by_value.values() if (cells := pinning(key, text)) is not None]
        if len(fixed) != 1:
            return {}
        accepted[key] = dict(text=fixed[0][0], pinned_by=fixed[0][1])
    controls = page_controls_reconcile(_with_texts(tables, {key: value['text'] for key, value in accepted.items()}))
    if not controls or not controls['reconciles']:
        return {}
    return dict(values=accepted, controls=controls)
