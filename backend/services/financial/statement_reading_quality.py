"""Decide when a recognised statement's embedded text merits an image reread.

This assesses parsing, not evidential accuracy. A reread must retain the same
printed identity, number of payments and balance controls before fewer unreadable
fields can make it preferable. Arithmetic is never used to manufacture values.
"""


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


def bbva_page_statement(sources):
    """``(identity, rows)`` for a BBVA page that prints its own period, or ``None``.

    Only a page the BBVA catalog groups on its own printed bank, product,
    account, page sequence and period is assessed; a continuation page
    without its period is not. Its dollar product reads as USD, the national
    one as MXN; both have two decimal places.
    """
    from services.financial.statement_import_bbva import bbva_catalog, propose_bbva_statement
    groups, _ = bbva_catalog(sources)
    if len(groups) != 1:
        return None
    group = groups[0]
    pages = set(group['page_numbers'])
    scoped = [s for s in sources if s['page_number'] in pages]
    texts = {cell['expected_text'].upper() for s in scoped for r in s['rows'] for cell in r['cells']}
    currency = 'USD' if any('DOLARES' in t for t in texts) else 'MXN'
    identity = [group[key] for key in ('layout_id', 'account_reference', 'period_start', 'period_end')]
    return identity, propose_bbva_statement(scoped, currency, group)['rows']


def capital_one_page_statement(sources):
    """``(identity, rows)`` for a branded Capital One card page, or ``None``.

    The page must establish exactly one printed card ending and billing cycle
    with the issuer's own name or address, as the statement catalog requires.
    """
    from services.financial.statement_import_catalog import _capital_page_contexts
    from services.financial.statement_import_card import propose_card_table
    from services.financial.statement_layout_context import statement_layout_context
    contexts, _ = _capital_page_contexts(sources)
    if len(set(contexts.values())) != 1:
        return None
    card, start, end = next(iter(contexts.values()))
    statement = dict(layout_id='capital-one-card', institution='Capital One', account_reference='****' + card,
                     period_start=start, period_end=end)
    # The same layout context the stored source and the statement review bind.
    scoped = [{**s, 'layout_context': statement_layout_context(s['rows'])
               or statement_layout_context(s['rows'], continuation_statement=statement)}
              for s in sources if s['page_number'] in contexts]
    identity = [statement[key] for key in ('layout_id', 'account_reference', 'period_start', 'period_end')]
    return identity, [r for s in scoped for r in propose_card_table(s, 'USD', statement)['rows']]


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
    elif (bbva := bbva_page_statement(sources)) is not None:
        identity, rows = bbva
    elif (capital := capital_one_page_statement(sources)) is not None:
        identity, rows = capital
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
    # A card interest charge prints no date of its own; the statement end
    # only orders it. That absence is the printed fact, not an unreadable date.
    missing = {field: sum(not r['fields'].get(field) and not (field == 'date'
        and r['fields'].get('date_basis') == 'statement_end_ordering_only') for r in payments)
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
