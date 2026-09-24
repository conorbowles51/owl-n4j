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
                source_revision='reading-quality', rows=[dict(row_index=i,
                    cells=sorted(cells, key=lambda c: c['column_index'])) for i, cells in sorted(rows.items())]))
    return sources


def assess_statement_reading(tables):
    from services.financial.statement_import_credit_one import credit_one_catalog, propose_credit_one_table
    from services.financial.statement_import_andrews import andrews_page, propose_andrews_statement
    sources = sources_from_tables(tables)
    if not sources:
        return None
    cards, _ = credit_one_catalog(sources)
    if len(cards) == 1:
        card = cards[0]
        identity = [card[key] for key in ('layout_id', 'account_reference', 'period_start', 'period_end')]
        rows = [r for s in sources for r in propose_credit_one_table(s, 'USD', card)['rows']]
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
    payments = [r for r in rows if not r['excluded'] and (r['kind'] == 'transaction'
        or 'date_column' in r['fields'] or 'amount_column' in r['fields'])]
    balances = [r for r in rows if r['kind'] == 'balance']
    # Valid but different balances require review, not another guess at digits.
    unreadable = sum(1 for r in payments for field in ('date', 'amount_minor', 'direction')
        if not r['fields'].get(field))
    unreadable += sum('booking_date_column' in r['fields'] and not r['fields'].get('booking_date') for r in payments)
    unreadable += sum('balance_column' in r['fields'] and 'balance' not in r['fields'] for r in payments)
    unreadable += sum('balance' not in r['fields'] for r in balances)
    return dict(identity=identity, payments=len(payments), balances=len(balances), unreadable=unreadable)


def prefer_image_reading(original, image):
    return bool(original and image and original['identity'] == image['identity']
        and original['payments'] == image['payments'] and original['balances'] == image['balances']
        and image['unreadable'] < original['unreadable'])
