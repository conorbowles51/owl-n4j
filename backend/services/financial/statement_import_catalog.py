"""Locate separately printed statements inside a PDF without creating readings.

A collection is grouped only by a printed account reference and complete billing
period. Page numbers remain the original PDF numbers. Unclassified pages are
retained separately so detection cannot silently turn a whole file into a
complete statement.
"""
from services.financial.pdf_candidates import _digest
from services.financial.statement_layout_context import _cycle, CAPITAL_ONE_CARD_HEADING
from services.financial.statement_information_pages import capital_information_kind, andrews_information_kind, merrick_information_kind, bbva_information_kind


def _capital_page_contexts(sources):
    """Read account/period context across tables on the same physical page.

    A continuation without a readable bank mark can use an exact account and
    period already established by a branded page. Conflicting page headers are
    never assigned by their position beside another statement.
    """
    pages = {}
    for source in sources:
        pages.setdefault(source['page_number'], []).extend(source['rows'])
    candidates, established, information = {}, set(), {}
    for page, rows in pages.items():
        cells = [c for row in rows for c in row['cells']]
        kind = capital_information_kind(rows) or andrews_information_kind(rows) or merrick_information_kind(rows) or bbva_information_kind(rows)
        if kind:
            information[page] = kind
        cycles = set()
        for row in rows:
            for index, cell in enumerate(row['cells']):
                value = _cycle(cell['expected_text'].strip())
                if value is None and index + 1 < len(row['cells']):
                    following = row['cells'][index + 1]
                    if following['column_index'] == cell['column_index'] + 1:
                        value = _cycle(cell['expected_text'].strip() + ' ' + following['expected_text'].strip())
                if value:
                    cycles.add(tuple(day.isoformat() for day in value))
        cards = {m[1] for c in cells if (m := CAPITAL_ONE_CARD_HEADING.fullmatch(c['expected_text'].strip()))}
        if len(cycles) != 1 or len(cards) != 1:
            continue
        start, end = next(iter(cycles))
        key = (next(iter(cards)), start, end)
        candidates[page] = key
        if any('capitalone.com' in c['expected_text'].lower() or c['expected_text'].strip() == 'Capital One' for c in cells):
            established.add(key)
    return {page: key for page, key in candidates.items() if key in established}, information


def statement_catalog(sources):
    from services.financial.statement_import_andrews import andrews_catalog, is_andrews_fee_summary, unassigned_andrews_groups
    andrews, handled, incomplete = andrews_catalog(sources)
    groups = {statement['id']: statement for statement in andrews}
    from services.financial.statement_import_credit_one import credit_one_catalog
    credit_one, credit_one_handled = credit_one_catalog(sources)
    groups.update({statement['id']: statement for statement in credit_one})
    from services.financial.statement_import_bbva import bbva_catalog
    bbva, bbva_handled = bbva_catalog(sources)
    groups.update({statement['id']: statement for statement in bbva})
    from services.financial.statement_import_scotiabank import scotiabank_catalog
    scotiabank, scotiabank_handled = scotiabank_catalog(sources)
    groups.update({statement['id']: statement for statement in scotiabank})
    from services.financial.statement_import_monex import monex_catalog
    monex, monex_handled = monex_catalog(sources)
    groups.update({statement['id']: statement for statement in monex})
    from services.financial.statement_import_kapital import kapital_catalog, kapital_information_kind, INTERCAM_PRODUCT
    kapital, kapital_handled = kapital_catalog(sources)
    groups.update({statement['id']: statement for statement in kapital})
    intercam, intercam_handled = kapital_catalog(sources, institution='Intercam', product=INTERCAM_PRODUCT, layout='intercam-mexico-product-statement')
    groups.update({statement['id']: statement for statement in intercam})
    from services.financial.statement_import_santander import santander_catalog
    santander, santander_handled = santander_catalog(sources)
    groups.update({statement['id']: statement for statement in santander})
    groups.update({statement['id']: statement for statement in unassigned_andrews_groups(sources, handled)})
    unclassified = []
    information = []
    from services.financial.statement_import_merrick import merrick_statement
    capital_pages, information_pages = _capital_page_contexts(sources)
    for source in sources:
        address = (source['page_number'], source['table_index'])
        if address in credit_one_handled or address in bbva_handled or address in scotiabank_handled or address in monex_handled or address in kapital_handled or address in intercam_handled or address in santander_handled:
            continue
        if address in handled:
            if address in incomplete:
                unclassified.append(dict(page_number=address[0], table_index=address[1]))
            continue
        if kind := kapital_information_kind(source):
            information.append(dict(page_number=address[0], table_index=address[1], kind=kind))
            continue
        if is_andrews_fee_summary(source):
            information.append(dict(page_number=address[0], table_index=address[1], kind='fee_summary'))
            continue
        merrick = merrick_statement(source)
        if merrick is not None:
            existing = groups.get(merrick["id"])
            if existing is None:
                groups[merrick["id"]] = merrick
            else:
                existing['sources'].extend(merrick['sources'])
                existing['page_numbers'] = sorted(set(existing['page_numbers'] + merrick['page_numbers']))
            continue
        if source['page_number'] in information_pages:
            information.append(dict(page_number=source['page_number'], table_index=source['table_index'], kind=information_pages[source['page_number']]))
            continue
        key = (source['page_number'], source['table_index'])
        identity = capital_pages.get(source['page_number'])
        if identity is None:
            unclassified.append(dict(page_number=key[0], table_index=key[1]))
            continue
        card, start, end = identity
        identity = dict(layout_id='capital-one-card', institution='Capital One', account_reference='****' + card,
                        period_start=start, period_end=end)
        identifier = _digest(identity)
        group = groups.setdefault(identifier, dict(id=identifier, **identity, sources=[], page_numbers=[]))
        group['sources'].append(dict(page_number=key[0], table_index=key[1], source_revision=source['source_revision']))
        if key[0] not in group['page_numbers']:
            group['page_numbers'].append(key[0])
    return dict(statements=list(groups.values()), unclassified_sources=unclassified, information_sources=information,
                complete_coverage=not unclassified)
