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


def assess_statement_reading(tables):
    from services.financial.statement_import_credit_one import credit_one_catalog, propose_credit_one_table
    from services.financial.statement_import_andrews import andrews_page, propose_andrews_statement
    from services.financial.statement_import_merrick import merrick_statement, propose_merrick_table
    sources = sources_from_tables(tables)
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
