"""Monex contract statements with separately printed currency summaries.

The supported balance-only layout requires the complete numbered statement,
explicit zero credit/debit controls, and matching opening/closing balances.
Routing instructions are retained as source evidence, never account ownership
or transactions. An unknown page or movement table prevents this shortcut.
"""
import re
from datetime import date

from services.financial.pdf_candidates import _digest
from services.financial.statement_import_bbva import box, norm, text, labelled_values
from services.financial.statement_import_proposal import exact_amount

LAYOUT = 'monex-mexico-currency-summary'
MONTHS = {name: i for i, name in enumerate(('ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO',
    'JUNIO', 'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE'), 1)}
CURRENCIES = {'PESO MEXICANO': 'MXN', 'EURO': 'EUR', 'DOLAR AMERICANO': 'USD',
    'LIBRA ESTERLINA': 'GBP', 'FRANCO SUIZO': 'CHF', 'DOLAR CANADA': 'CAD',
    'DOLAR AUSTRALIANO': 'AUD', 'CORONA SUECA': 'SEK', 'YEN JAPONES': 'JPY'}


def _period(value):
    m = re.fullmatch(r'DEL (\d{1,2}) (\w+) (\d{4}) AL (\d{1,2}) (\w+) (\d{4})', norm(value))
    if not m:
        return None
    try:
        start, end = date(int(m[3]), MONTHS[m[2]], int(m[1])), date(int(m[6]), MONTHS[m[5]], int(m[4]))
        return (start.isoformat(), end.isoformat()) if start <= end and (end-start).days <= 62 else None
    except (KeyError, ValueError):
        return None


def _controls(items):
    """Select the summary's own labels and adjacent values, not averages."""
    roles = {'SALDO INICIAL:': 'opening', 'SALDO VISTA:': 'closing',
        '+ TOTAL ABONOS:': 'credit', '- TOTAL CARGOS:': 'debit'}
    found = {}
    for source in items:
        for row in source['rows']:
            cells = row['cells']
            for i, cell in enumerate(cells[:-1]):
                role = roles.get(norm(cell['expected_text']))
                following = cells[i+1]
                if not role or not box(cell) or not box(following):
                    continue
                # The next physical cell must sit to the right on this line.
                if box(following)[0] < box(cell)[2] or abs(box(following)[1]-box(cell)[1]) > 10000:
                    continue
                found.setdefault(role, []).append((source, row, following))
    return {k: v[0] for k, v in found.items()} if set(found) == set(roles.values()) and all(len(v) == 1 for v in found.values()) else None


def monex_catalog(sources):
    pages = {}
    for source in sources:
        pages.setdefault(source['page_number'], []).append(source)
    groups, handled = [], set()
    for first, items in pages.items():
        joined = '\n'.join(text(r) for s in items for r in s['rows'])
        if not all(word in norm(joined) for word in ('MONEX', 'RFC TITULAR:', 'CTA. CLABE:', 'TIPO DE CONTRATO:')):
            continue
        values = labelled_values(items)
        contracts = {v for v in values.get('CONTRATO:', set()) if re.fullmatch(r'\d{5,20}', v)}
        periods = {p for v in values.get('PERIODO:', set()) if (p := _period(v))}
        if len(contracts) != 1 or len(periods) != 1:
            continue
        contract, (start, end) = next(iter(contracts)), next(iter(periods))
        # The name is in the address block above C.P., on the cover's right.
        cells = [c for s in items for r in s['rows'] for c in r['cells'] if box(c)]
        postal = [c for c in cells if norm(c['expected_text']) == 'C.P.']
        names = {c['expected_text'].strip() for c in cells if len(postal) == 1
            and abs(box(c)[0]-box(postal[0])[0]) < 6000 and box(c)[1] < box(postal[0])[1]
            and re.fullmatch(r'.{3,180}\sS\.?\s*A\.?\s*DE\s*C\.?\s*V\.?', norm(c['expected_text']))}
        numbered = {}
        for page, group in pages.items():
            raw = '\n'.join(norm(text(r)) for s in group for r in s['rows'])
            numbers = {tuple(map(int, m.groups())) for m in re.finditer(r'\bHOJA (\d+) DE (\d+)\b', raw)}
            ids = set(re.findall(r'\bCONTRATO:\s*(\d{5,20})\b', raw))
            if len(numbers) == 1 and ids == {contract} and 'MONEX' in raw:
                n, count = next(iter(numbers))
                if page - n + 1 == first and 2 <= n <= count <= 100:
                    numbered[page] = (count, raw)
        counts = {v[0] for v in numbered.values()}
        if len(counts) != 1:
            continue
        count = next(iter(counts))
        if set(numbered) != set(range(first+1, first+count)):
            continue
        from services.financial.statement_movement_scaffold import movement_scaffold_enabled
        scaffold = movement_scaffold_enabled()
        candidates, understood, awaiting = [], True, None
        for page, (_, raw) in sorted(numbered.items()):
            group = pages[page]
            if awaiting is not None:
                # Scaffold only: the section's movement table must be the very
                # next page, headed with that section's own currency label.
                table = _movement_table(group, awaiting[3]) if page == awaiting[0] + 1 else None
                if table is None:
                    understood = False
                    break
                candidates.append((*awaiting[:3], page))
                awaiting = None
                continue
            if any(marker in raw for marker in ('REFERENCIAS BANCARIAS', 'AVISO DE SEGURIDAD DE LA INFORMACION', 'ESTIMADO CLIENTE:')):
                continue
            if 'RESUMEN CUENTA' not in raw or re.search(r'\b(?:MOVIMIENTOS|FECHA\s+(?:OPERACION|CONCEPTO))\b', raw):
                understood = False
                break
            # A currency heading must precede the summary opening balance.
            controls = _controls(group)
            if not controls:
                understood = False
                break
            opening_cell = controls['opening'][2]
            labels = [c for s in group for r in s['rows'] for c in r['cells']
                if box(c) and norm(c['expected_text']) in CURRENCIES and box(c)[1] < box(opening_cell)[1]]
            if len(labels) != 1:
                understood = False
                break
            currency = CURRENCIES[norm(labels[0]['expected_text'])]
            try:
                amounts = {role: exact_amount(entry[2]['expected_text'], currency) for role, entry in controls.items()}
                if amounts['credit'] != '0' or amounts['debit'] != '0' or amounts['opening'] != amounts['closing']:
                    if scaffold and (amounts['credit'] != '0' or amounts['debit'] != '0'):
                        # Activity: only a following movement table can explain it.
                        awaiting = (page, currency, controls, norm(labels[0]['expected_text']))
                        continue
                    understood = False
                    break
            except ValueError:
                understood = False
                break
            candidates.append((page, currency, controls, None))
        if awaiting is not None or not understood or not candidates or len({c[1] for c in candidates}) != len(candidates):
            continue
        all_items = [s for p in range(first, first+count) for s in pages[p]]
        for page, currency, controls, movement_page in candidates:
            identity = dict(layout_id=LAYOUT, institution='Monex', account_reference=contract,
                currency=currency, period_start=start, period_end=end)
            section_pages = [page] + ([movement_page] if movement_page else [])
            groups.append(dict(id=_digest(identity), **identity, account_type='checking', holder=next(iter(names)) if len(names) == 1 else '',
                summary_page=page, currency_source='printed_account_section',
                account_reference_kind='multi_currency_contract',
                **(dict(movement_page=movement_page) if movement_page else {}),
                section_sources=[dict(page_number=s['page_number'], table_index=s['table_index'],
                    row_indices=[r['row_index'] for r in s['rows']]) for p in section_pages for s in pages[p]],
                sources=[dict(page_number=s['page_number'], table_index=s['table_index'], source_revision=s['source_revision']) for s in all_items],
                page_numbers=list(range(first, first+count))))
        handled.update((s['page_number'], s['table_index']) for s in all_items)
    return groups, handled


def propose_monex_statement(sources, currency, choice):
    controls = _controls([s for s in sources if s['page_number'] == choice['summary_page']])
    if not controls:
        raise ValueError('The currency summary controls could not be read. Review this statement again.')
    addresses = {(s['page_number'], s['table_index'], r['row_index']): (role, cell)
        for role, (s, r, cell) in controls.items()}
    body, columns = set(), None
    if choice.get('movement_page'):
        # Scaffold only (statement_movement_scaffold); the catalog emits a
        # movement page only when the switch is on.
        summary = [s for s in sources if s['page_number'] == choice['summary_page']]
        label = next(norm(c['expected_text']) for s in summary for r in s['rows'] for c in r['cells']
            if norm(c['expected_text']) in CURRENCIES and CURRENCIES[norm(c['expected_text'])] == choice['currency'])
        table = _movement_table([s for s in sources if s['page_number'] == choice['movement_page']], label)
        if table is None:
            raise ValueError('The movement table for this currency could not be read. Review this statement again.')
        columns = table['columns']
        body = {(s['page_number'], s['table_index'], r['row_index']) for s, r in table['body']}
    result = []
    for source in sources:
        for raw in source['rows']:
            address = (source['page_number'], source['table_index'], raw['row_index'])
            item = dict(id=':'.join(map(str, address)), page_number=address[0], table_index=address[1], row_index=address[2],
                source_revision=source['source_revision'], source_cells=raw['cells'], fields={}, issues=[], excluded=True, kind='header')
            result.append(item)
            if address in body:
                fields, issues = _movement_row(raw, columns, currency, choice)
                if issues and not fields.get('description'):
                    fields['description'] = text(raw)
                item.update(kind='unresolved' if issues else 'transaction', excluded=False, fields=fields, issues=issues)
                continue
            if address not in addresses:
                continue
            role, cell = addresses[address]
            balance = role in ('opening', 'closing')
            item.update(kind='balance' if balance else 'statement_total')
            item['fields'].update(description=role.title() + ' Balance' if balance else 'Total ' + role,
                balance_column=str(cell['column_index']))
            if balance:
                item['fields']['standalone_balance'] = 'true'
            if not balance:
                item['fields']['total_direction'] = role
            try:
                item['fields']['balance'] = exact_amount(cell['expected_text'], currency)
            except ValueError as exc:
                item['issues'].append(str(exc))
    return dict(rows=result, issues=[])


def monex_no_activity_evidence(sources, choice, rows, currency):
    """A currency summary's printed zero + Total abonos / - Total cargos prove it quiet.

    The catalog accepts this layout only when every numbered page is
    understood and none carries a movement table. As a further guard the
    currency's summary page must contain no line that starts with a date.
    """
    from services.financial.statement_printed_no_activity import zero_totals_evidence

    def guard():
        for s in sources:
            if s['page_number'] != choice.get('summary_page'):
                continue
            for raw in s['rows']:
                if re.match(r'^\d{1,2}\s*[/-]\s*(?:\d{1,2}|[A-Z]{3})\s*[/-]\s*\d{2,4}\b', norm(text(raw))):
                    return ('dated_line', 'A dated line was read on this currency summary page. Check it before confirming that the section contains no transactions.')
        return None

    return zero_totals_evidence(rows, choice, currency, family='monex-mexico', guard=guard)


AMOUNT = r'-?[\d,]+\.\d{2}'


def _movement_table(items, label):
    """One currency section's movement table: scaffold, off by default.

    Modelled by the benchmark corpus, not on a real Monex page (see
    statement_movement_scaffold). The page must hold, in order, only the
    contract line, the heading Movimientos <section currency>, the five
    column headings, dated body rows and the Hoja n de m footer. Anything
    else, or any unplaced cell, returns None and the contract stays refused.
    """
    located = [(s, r) for s in items for r in s['rows'] if r['cells']]
    if not located or any(not box(c) for _, r in located for c in r['cells']):
        return None
    located.sort(key=lambda pair: (min(box(c)[1] for c in pair[1]['cells']), pair[0]['table_index'], pair[1]['row_index']))
    lines = [norm(text(r)) for _, r in located]
    if len(lines) < 5 or not re.fullmatch(r'MONEX CONTRATO: \d{5,20}', lines[0]) or lines[1] != 'MOVIMIENTOS ' + label:
        return None
    names = ('FECHA', 'CONCEPTO', 'ABONOS', 'CARGOS', 'SALDO')
    header = located[2][1]
    if tuple(norm(c['expected_text']) for c in header['cells']) != names:
        return None
    if not re.fullmatch(r'HOJA \d+ DE \d+', lines[-1]):
        return None
    body = located[3:-1]
    if not body or not all(re.match(r'\d{2}/\d{2}/\d{4}\b', line) for line in lines[3:-1]):
        return None
    return dict(columns=dict(zip(names, header['cells'])), body=body)


def _movement_row(raw, columns, currency, choice):
    """Fields and issues for one body row; columns come from the printed headings."""
    fields, issues = {}, []
    money = {name: [] for name in ('ABONOS', 'CARGOS', 'SALDO')}
    other = []
    for cell in raw['cells']:
        if re.fullmatch(AMOUNT, cell['expected_text'].strip()) and box(cell)[0] > box(columns['FECHA'])[2]:
            money[min(money, key=lambda n: abs(box(cell)[2] - box(columns[n])[2]))].append(cell)
        else:
            other.append(cell)
    match = re.fullmatch(r'(\d{2})/(\d{2})/(\d{4})', other[0]['expected_text'].strip()) if other else None
    try:
        day = date(int(match[3]), int(match[2]), int(match[1])).isoformat() if match else None
    except ValueError:
        day = None
    if day is None:
        return fields, ['Check the printed date and amount for this payment beside the PDF.']
    fields['date_column'] = str(other[0]['column_index'])
    if choice['period_start'] <= day <= choice['period_end']:
        fields['date'] = day
    else:
        issues.append('Check this payment date against the printed statement period.')
    if len(other) != 2:
        issues.append('Check the printed description for this payment beside the PDF.')
    if len(other) > 1:
        fields['description'] = ' '.join(c['expected_text'].strip() for c in other[1:])
        fields['description_column'] = str(other[1]['column_index'])
    directions = [(name, d) for name, d in (('ABONOS', 'credit'), ('CARGOS', 'debit')) if money[name]]
    if len(directions) != 1 or len(money[directions[0][0]]) != 1:
        issues.append('Choose the printed credit or debit amount for this payment.')
    else:
        name, direction = directions[0]
        cell = money[name][0]
        fields['direction'] = direction
        fields[direction + '_column'] = str(cell['column_index'])
        try:
            amount = exact_amount(cell['expected_text'].strip(), currency)
            if cell['expected_text'].strip().startswith('-') or int(amount) <= 0:
                raise ValueError('The payment amount must be positive; the column supplies direction.')
            fields['amount_minor'] = amount
        except ValueError as exc:
            issues.append(str(exc))
    if len(money['SALDO']) != 1:
        issues.append('Check the printed balance after this payment.')
    else:
        cell = money['SALDO'][0]
        fields['balance_column'] = str(cell['column_index'])
        try:
            value = cell['expected_text'].strip()
            amount = exact_amount(value.lstrip('-'), currency)
            fields['balance'] = str(-int(amount)) if value.startswith('-') else amount
        except ValueError as exc:
            issues.append(str(exc))
    return fields, issues
