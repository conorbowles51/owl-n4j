"""Locate separately printed statements inside a PDF without creating readings.

A collection is grouped only by a printed account reference and complete billing
period. Page numbers remain the original PDF numbers. Unclassified pages are
retained separately so detection cannot silently turn a whole file into a
complete statement.
"""
import re
from services.financial.pdf_candidates import _digest
from services.financial.statement_layout_context import _cycle

_CARD = re.compile(r'(?:Platinum MasterCard Account Ending in|Platinum Mastercard ending in|Platinum Card ending in|Platinum Card \| Platinum Mastercard ending in) (\d{4})')


def statement_catalog(sources):
    groups = {}
    unclassified = []
    information = []
    from services.financial.statement_import_merrick import merrick_statement
    for source in sources:
        merrick = merrick_statement(source)
        if merrick is not None:
            existing = groups.get(merrick["id"])
            if existing is None:
                groups[merrick["id"]] = merrick
            else:
                existing['sources'].extend(merrick['sources'])
                existing['page_numbers'] = sorted(set(existing['page_numbers'] + merrick['page_numbers']))
            continue
        cells = [c for r in source['rows'] for c in r['cells']]
        content = ' '.join(c['expected_text'] for c in cells)
        if ('How can I Avoid Paying Interest Charges?' in content and
            'How can I Close My Account?' in content and
            'Billing Rights Summary' in content and
            not any(c['expected_text'].strip() in ('Trans Date', 'Transaction Date', 'Date') for c in cells)):
            information.append(dict(page_number=source['page_number'], table_index=source['table_index'], kind='card_terms'))
            continue
        cycles = set()
        for row in source['rows']:
            for index, cell in enumerate(row['cells']):
                value = _cycle(cell['expected_text'].strip())
                if value is None and index + 1 < len(row['cells']):
                    following = row['cells'][index + 1]
                    if following['column_index'] == cell['column_index'] + 1:
                        value = _cycle(cell['expected_text'].strip() + ' ' + following['expected_text'].strip())
                if value:
                    cycles.add(tuple(day.isoformat() for day in value))
        cards = {m[1] for c in cells if (m := _CARD.fullmatch(c['expected_text'].strip()))}
        institution = any('capitalone.com' in c['expected_text'].lower() or c['expected_text'].strip() == 'Capital One' for c in cells)
        key = (source['page_number'], source['table_index'])
        if len(cycles) != 1 or len(cards) != 1 or not institution:
            unclassified.append(dict(page_number=key[0], table_index=key[1]))
            continue
        start, end = next(iter(cycles))
        card = next(iter(cards))
        identity = dict(layout_id='capital-one-card', institution='Capital One', account_reference='****' + card,
                        period_start=start, period_end=end)
        identifier = _digest(identity)
        group = groups.setdefault(identifier, dict(id=identifier, **identity, sources=[], page_numbers=[]))
        group['sources'].append(dict(page_number=key[0], table_index=key[1], source_revision=source['source_revision']))
        if key[0] not in group['page_numbers']:
            group['page_numbers'].append(key[0])
    return dict(statements=list(groups.values()), unclassified_sources=unclassified, information_sources=information,
                complete_coverage=not unclassified)
