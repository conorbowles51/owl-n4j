"""Recognise Scotiabank Mexico's complete, zero-activity summary statements.

The printed activity chart is independent evidence when OCR misses the shaded
summary amount column. All five chart amounts must explicitly read zero. Missing
pages, conflicting accounts, movement tables and nonzero activity fail closed to
the ordinary review. No missing amount is filled with an assumed zero.
"""
import re
from datetime import date

from services.financial.pdf_candidates import _digest
from services.financial.statement_import_bbva import norm, text, box, MONTHS
from services.financial.statement_import_proposal import exact_amount

LAYOUT = 'scotiabank-mexico-zero-activity'
# Scaffold, off by default (statement_movement_scaffold): the movement table
# below was modelled by the benchmark corpus, not taken from a real statement.
MOVEMENTS_LAYOUT = 'scotiabank-mexico-movements'
MONEY = r'-?\s*\$\s*[\d,.]+'


def _date(value):
    match = re.fullmatch(r'(\d{2})-([A-Z]{3})-(\d{2}|\d{4})', norm(value))
    if not match or match[2] not in MONTHS:
        return None
    year = int(match[3]) + (2000 if len(match[3]) == 2 else 0)
    try:
        return date(year, MONTHS[match[2]], int(match[1]))
    except ValueError:
        return None


def _values(items, label):
    values = set()
    for source in items:
        for row in source['rows']:
            cells = row['cells']
            for i, cell in enumerate(cells):
                if norm(cell['expected_text']) == label and i + 1 < len(cells):
                    values.add(cells[i + 1]['expected_text'].strip())
            for value in [text(row), *(c['expected_text'] for c in cells)]:
                match = re.fullmatch(re.escape(label) + r'\s+(\S+)', norm(value))
                if match:
                    values.add(match[1])
    return values


def _controls(items):
    cells = [c for s in items for row in s['rows'] for c in row['cells']]
    # Both labels and amounts may share one OCR line above the chart.
    controls = {}
    for cell in cells:
        value = norm(cell['expected_text'])
        for role, label in (('opening', 'INICIAL'), ('closing', 'FINAL')):
            match = re.fullmatch(r'SALDO\s*[—–-]?\s*' + label + r'\s*=\s*(-?\s*\$\s*[\d,.]+)', value)
            if match:
                controls.setdefault(role, []).append(cell)
    if any(len(controls.get(role, [])) != 1 for role in ('opening', 'closing')):
        return None
    if any(not box(c) for cells in controls.values() for c in cells):
        return None
    try:
        balances = [_balance_value(controls[role][0], 'MXN') for role in ('opening', 'closing')]
    except ValueError:
        return None
    if balances[0] != balances[1]:
        return None
    headings = {}
    for cell in cells:
        value = re.sub(r'[_.]+$', '', norm(cell['expected_text'])).strip()
        label = next((role for role, pattern in (
            ('deposits', r'DEP[OE]SITOS'), ('interest', r'INTERESES'),
            ('withdrawals', r'RETIROS\s*\.?\s*EN EFECTIVO\s*\.?'),
            ('other', r'OTROS CARGOS\*?'), ('fees', r'COMISIONES'),
        ) if re.fullmatch(pattern, value)), None)
        if label and box(cell):
            headings.setdefault(label, []).append(cell)
    if set(headings) != {'deposits', 'interest', 'withdrawals', 'other', 'fees'} or any(len(v) != 1 for v in headings.values()):
        return None
    chart_top = max(box(c)[3] for v in controls.values() for c in v if box(c))
    evidence = []
    for heading in (v[0] for v in headings.values()):
        rect = box(heading)
        amounts = [c for c in cells if box(c) and chart_top < box(c)[1] < rect[1]
            and rect[0] <= (box(c)[0] + box(c)[2]) / 2 <= rect[2]
            and re.fullmatch(r'\$\s*[\d,.]+', c['expected_text'].strip())]
        try:
            zero = len(amounts) == 1 and exact_amount(amounts[0]['expected_text'], 'MXN') == '0'
        except ValueError:
            zero = False
        if not zero:
            return None
        evidence.append(amounts[0])
    # A readable nonzero summary must not be overridden by an empty chart.
    for source in items:
        for row in source['rows']:
            label = norm(text(row))
            if re.match(r'^(?:\([+=-]\)\s*)?(?:DEP[OE]SITOS|RETIROS|INTERESES RECIBIDOS|COMISIONES COBRADAS|IMPUESTOS)\b', label):
                for cell in row['cells']:
                    if re.fullmatch(r'\$\s*[\d,.]+', cell['expected_text'].strip()):
                        try:
                            if exact_amount(cell['expected_text'], 'MXN') != '0':
                                return None
                        except ValueError:
                            return None
            role = next((role for role, pattern in (
                ('opening', r'^(?:\([=]\)\s*)?SALDO INICIAL\b'),
                ('closing', r'^(?:\([=]\)\s*)?SALDO FINAL DE LA CUENTA\b'),
            ) if re.match(pattern, label)), None)
            if role:
                # The summary amount sits left of the activity chart; chart
                # zeros on the same OCR row are not closing balances.
                for cell in row['cells']:
                    rect, size = box(cell), (cell.get('locator') or {}).get('page_size')
                    if rect and size and rect[2] < size[0] / 2 and re.fullmatch(r'\$\s*[\d,.]+', cell['expected_text'].strip()):
                        try:
                            if exact_amount(cell['expected_text'], 'MXN') != _balance_value(controls[role][0], 'MXN'):
                                return None
                        except ValueError:
                            return None
    return controls, evidence


def _balance_value(cell, currency):
    value = cell['expected_text'].split('=', 1)[1].strip()
    negative = value.startswith('-')
    amount = exact_amount(value.lstrip('-').strip(), currency)
    return str(-int(amount)) if negative else amount


def scotiabank_catalog(sources):
    pages = {}
    for source in sources:
        pages.setdefault(source['page_number'], []).append(source)
    groups, handled = [], set()
    for first, items in pages.items():
        joined = '\n'.join(norm(text(r)) for s in items for r in s['rows'])
        if not all(marker in joined for marker in ('SCOTIABANK', 'ESTADO DE CUENTA', 'SCOTIA INV DISP', 'RESUMEN DE SALDOS', 'PAGINA 1 DE 3')):
            continue
        if not all(p in pages for p in range(first, first + 3)):
            continue
        following = ['\n'.join(norm(text(r)) for s in pages[p] for r in s['rows']) for p in (first + 1, first + 2)]
        if not all(marker in following[0] for marker in ('PAGINA 2 DE 3', 'ADVERTENCIAS', 'DATOS SON INFORMATIVOS')):
            continue
        if not all(marker in following[1] for marker in ('PAGINA 3 DE 3', 'ABREVIATURAS', 'SCOTIABANK INVERLAT')):
            continue
        group = [s for p in range(first, first + 3) for s in pages[p]]
        all_text = '\n'.join(norm(text(r)) for s in group for r in s['rows'])
        table = None
        if re.search(r'(?m)^\s*(?:DETALLE DE (?:TUS )?MOVIMIENTOS|FECHA\b.*(?:DESCRIPCION|CONCEPTO|RETIROS|DEPOSITOS))', all_text):
            from services.financial.statement_movement_scaffold import movement_scaffold_enabled
            table = _movement_table(items) if movement_scaffold_enabled() else None
            if table is None:
                continue
            # Every movement-like line must belong to the one parsed table.
            all_text = '\n'.join(norm(text(r)) for s in group for r in s['rows']
                if (s['page_number'], s['table_index'], r['row_index']) not in table['addresses'])
            if re.search(r'(?m)^\s*(?:DETALLE DE (?:TUS )?MOVIMIENTOS|FECHA\b.*(?:DESCRIPCION|CONCEPTO|RETIROS|DEPOSITOS))', all_text):
                continue
        # A dated payment line cannot be suppressed by a zero summary, nor
        # sit outside the movement table.
        if re.search(r'(?m)^\s*\d{1,2}[-/]\w{2,4}(?:[-/]\d{2,4})?\s+\S+', all_text):
            continue
        accounts = {v for v in _values(group, 'CUENTA') if re.fullmatch(r'\d{8,20}', v)}
        periods = _values(items, 'PERIODO')
        if len(accounts) != 1 or len(periods) != 1 or _values(items, 'MONEDA') != {'NACIONAL'}:
            continue
        parts = next(iter(periods)).split('/')
        if len(parts) != 2:
            continue
        start, end = map(_date, parts)
        if not start or not end or not start <= end or (end - start).days > 62:
            continue
        controls = _controls(items) if table is None else _movement_controls(items)
        if controls is None:
            continue
        names = set()
        for s in items:
            for row in s['rows']:
                for c in row['cells']:
                    rect, size = box(c), (c.get('locator') or {}).get('page_size')
                    if rect and size and rect[2] < size[0] / 2 and rect[1] < size[1] / 5:
                        value = re.sub(r'^[^A-ZÁÉÍÓÚÑ]+', '', c['expected_text'].strip())
                        if re.fullmatch(r'[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ &.,]+ S\.?A\.? DE C\.?V\.?', value):
                            names.add(value)
        identity = dict(layout_id=LAYOUT if table is None else MOVEMENTS_LAYOUT, institution='Scotiabank Mexico',
            account_reference=next(iter(accounts)), period_start=start.isoformat(), period_end=end.isoformat())
        groups.append(dict(id=_digest(identity), **identity, account_type='checking',
            holder=next(iter(names)) if len(names) == 1 else '',
            sources=[dict(page_number=s['page_number'], table_index=s['table_index'], source_revision=s['source_revision']) for s in group],
            page_numbers=list(range(first, first + 3)),
            **(dict(zero_activity_evidence=controls[1]) if table is None else {})))
        handled.update((s['page_number'], s['table_index']) for s in group)
    return groups, handled


def propose_scotiabank_statement(sources, currency, choice):
    controls, _ = _controls([s for s in sources if s['page_number'] == choice['page_numbers'][0]])
    result = []
    for source in sources:
        for raw in source['rows']:
            item = dict(id=f"{source['page_number']}:{source['table_index']}:{raw['row_index']}",
                page_number=source['page_number'], table_index=source['table_index'], row_index=raw['row_index'],
                source_revision=source['source_revision'], source_cells=raw['cells'], fields={}, issues=[], excluded=True, kind='header')
            # The two chart labels can occupy the same row. Keep each balance
            # source separately addressable without manufacturing a payment.
            matches = [(role, cell) for role, cells in controls.items() for cell in cells if cell in raw['cells']]
            if not matches:
                result.append(item)
            for index, (role, cell) in enumerate(matches):
                fields = dict(description=role.title() + ' Balance',
                    balance_column=str(cell['column_index']), standalone_balance='true')
                issues = []
                try:
                    fields['balance'] = _balance_value(cell, currency)
                except ValueError as exc:
                    issues.append(str(exc))
                result.append({**item, 'id': item['id'] + (f':{role}' if index else ''), 'kind': 'balance',
                    'fields': fields, 'issues': issues})
    return dict(rows=result, issues=[])


def scotiabank_no_activity_evidence(sources, choice, rows, currency):
    """The printed activity chart's five zero amounts prove the period quiet.

    The catalog accepts this layout only for the complete three-page statement
    with equal printed Saldo inicial / Saldo final, five chart amounts each
    read exactly as zero, no movement table, no dated payment line and no
    readable nonzero summary amount. The chart cells are re-read from the
    same page here and cited; nothing is assumed zero.
    """
    from services.financial.statement_printed_no_activity import zero_totals_evidence, held
    found = _controls([s for s in sources if s['page_number'] == choice['page_numbers'][0]])
    if found is None:
        return held('scotiabank-mexico', 'chart_unreadable', 'The activity chart amounts were not all read as zero. Check the page before confirming that it contains no transactions.',
            page_number=choice['page_numbers'][0])
    return zero_totals_evidence(rows, choice, currency, family='scotiabank-mexico', zero_cells=found[1],
        printed_currency='MXN')  # the catalog requires Moneda NACIONAL


def _chart_balances(cells):
    """The one printed Saldo inicial = / Saldo final= pair above the chart."""
    controls = {}
    for cell in cells:
        value = norm(cell['expected_text'])
        for role, label in (('opening', 'INICIAL'), ('closing', 'FINAL')):
            if re.fullmatch(r'SALDO\s*[—–-]?\s*' + label + r'\s*=\s*(-?\s*\$\s*[\d,.]+)', value):
                controls.setdefault(role, []).append(cell)
    if any(len(controls.get(role, [])) != 1 for role in ('opening', 'closing')):
        return None
    if any(not box(c) for cells in controls.values() for c in cells):
        return None
    return controls


def _movement_controls(items):
    """Printed balances and activity totals of a statement with movements.

    Scaffold (see statement_movement_scaffold). Every summary line must carry
    exactly one readable amount left of the activity chart; the summary
    opening/closing must equal the chart-line balances; interest, fees and
    taxes must print exactly zero, so the printed Depositos and Retiros are
    the whole credit and debit totals. Anything else returns None.
    """
    cells = [c for s in items for row in s['rows'] for c in row['cells']]
    balances = _chart_balances(cells)
    if balances is None:
        return None
    try:
        printed = {role: _balance_value(balances[role][0], 'MXN') for role in ('opening', 'closing')}
    except ValueError:
        return None
    labels = (('opening', r'SALDO INICIAL'), ('credit', r'\(\+\)\s*DEP[OE]SITOS'),
              ('interest', r'\(\+\)\s*INTERESES RECIBIDOS\b.*'), ('debit', r'\(-\)\s*RETIROS'),
              ('fees', r'\(-\)\s*COMISIONES COBRADAS'), ('taxes', r'\(-\)\s*IMPUESTOS'),
              ('closing', r'\(=\)\s*SALDO FINAL DE LA CUENTA'))
    found = {}
    for source in items:
        for row in source['rows']:
            if not row['cells']:
                continue
            role = next((role for role, pattern in labels if re.fullmatch(pattern, norm(row['cells'][0]['expected_text']))), None)
            if role is None:
                continue
            amounts = []
            for cell in row['cells'][1:]:
                rect, size = box(cell), (cell.get('locator') or {}).get('page_size')
                if rect and size and rect[2] < size[0] / 2 and re.fullmatch(MONEY, cell['expected_text'].strip()):
                    amounts.append(cell)
            found.setdefault(role, []).append((source, row, amounts))
    if set(found) != {role for role, _ in labels} or any(len(v) != 1 or len(v[0][2]) != 1 for v in found.values()):
        return None
    try:
        values = {role: exact_amount(v[0][2][0]['expected_text'].strip(), 'MXN')
                  for role, v in found.items() if role not in ('opening', 'closing')
                  and not v[0][2][0]['expected_text'].strip().startswith('-')}
        values.update({role: _balance_value(dict(expected_text='=' + found[role][0][2][0]['expected_text']), 'MXN')
                       for role in ('opening', 'closing')})
    except ValueError:
        return None
    if len(values) != 7 or any(values[role] != '0' for role in ('interest', 'fees', 'taxes')):
        return None
    if values['opening'] != printed['opening'] or values['closing'] != printed['closing']:
        return None
    return balances, {role: (found[role][0][0], found[role][0][1], found[role][0][2][0]) for role in ('credit', 'debit')}


def _movement_table(items):
    """The one Detalle de tus movimientos table on the first page.

    Scaffold (see statement_movement_scaffold). The heading must be followed
    directly by the six printed column headings, in order. Body rows run
    until the first line with neither a printed date nor an amount. Returns
    the header cells, the body rows and every address the table occupies.
    """
    located = [(s, r) for s in items for r in s['rows'] if r['cells']]
    if any(not box(c) for _, r in located for c in r['cells']):
        return None  # an unplaced line could be a payment; never skip it
    located.sort(key=lambda pair: (min(box(c)[1] for c in pair[1]['cells']), pair[0]['table_index'], pair[1]['row_index']))
    headings = [i for i, (_, r) in enumerate(located) if re.fullmatch(r'DETALLE DE (?:TUS )?MOVIMIENTOS', norm(text(r)))]
    if len(headings) != 1 or headings[0] + 1 >= len(located):
        return None
    names = ('FECHA', 'CONCEPTO', 'REFERENCIA', 'DEPOSITO', 'RETIRO', 'SALDO')
    source, header = located[headings[0] + 1]
    if tuple(norm(c['expected_text']) for c in header['cells']) != names:
        return None
    columns = dict(zip(names, header['cells']))
    addresses = {(s['page_number'], s['table_index'], r['row_index']) for s, r in located[headings[0]:headings[0] + 2]}
    body = []
    for s, r in located[headings[0] + 2:]:
        cells = r['cells']
        money = [c for c in cells if re.fullmatch(MONEY, c['expected_text'].strip())
                 and box(c)[2] > box(columns['REFERENCIA'])[2]]
        if not money and not _date(cells[0]['expected_text']):
            break
        body.append((s, r))
        addresses.add((s['page_number'], s['table_index'], r['row_index']))
    if not body:
        return None
    return dict(columns=columns, body=body, addresses=addresses)


def _movement_row(raw, columns, currency, choice):
    """Fields and issues for one body row; columns come from the printed headings."""
    cells, fields, issues = raw['cells'], {}, []
    money = {name: [] for name in ('DEPOSITO', 'RETIRO', 'SALDO')}
    other = []
    for cell in cells:
        if re.fullmatch(MONEY, cell['expected_text'].strip()) and box(cell)[2] > box(columns['REFERENCIA'])[2]:
            money[min(money, key=lambda n: abs(box(cell)[2] - box(columns[n])[2]))].append(cell)
        else:
            other.append(cell)
    day = _date(other[0]['expected_text']) if other else None
    if day is None:
        return fields, ['Check the printed date and amount for this payment beside the PDF.']
    fields['date_column'] = str(other[0]['column_index'])
    if choice['period_start'] <= day.isoformat() <= choice['period_end']:
        fields['date'] = day.isoformat()
    else:
        issues.append('Check this payment date against the printed statement period.')
    text_cells = {'CONCEPTO': [], 'REFERENCIA': []}
    for cell in other[1:]:
        text_cells[min(text_cells, key=lambda n: abs(box(cell)[0] - box(columns[n])[0]))].append(cell)
    if len(text_cells['CONCEPTO']) != 1 or len(text_cells['REFERENCIA']) > 1:
        issues.append('Check the printed description and reference for this payment beside the PDF.')
    if text_cells['CONCEPTO']:
        fields['description'] = ' '.join(c['expected_text'].strip() for c in text_cells['CONCEPTO'])
        fields['description_column'] = str(text_cells['CONCEPTO'][0]['column_index'])
    if len(text_cells['REFERENCIA']) == 1:
        fields['bank_reference'] = text_cells['REFERENCIA'][0]['expected_text'].strip()
    directions = [(name, d) for name, d in (('DEPOSITO', 'credit'), ('RETIRO', 'debit')) if money[name]]
    if len(directions) != 1 or len(money[directions[0][0]]) != 1:
        issues.append('Choose the printed deposit or withdrawal amount for this payment.')
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
            fields['balance'] = _balance_value(dict(expected_text='=' + cell['expected_text']), currency)
        except ValueError as exc:
            issues.append(str(exc))
    return fields, issues


def propose_scotiabank_movements(sources, currency, choice):
    """Scaffold reader for the movement table (statement_movement_scaffold).

    Payments come only from the parsed table; the chart-line balances and the
    printed Depositos / Retiros totals are retained as controls so admission
    checks the rows against all of them.
    """
    first = [s for s in sources if s['page_number'] == choice['page_numbers'][0]]
    found, table = _movement_controls(first), _movement_table(first)
    if found is None or table is None:
        raise ValueError('The movement table or its printed totals could not be read. Review this statement again.')
    balances, totals = found
    body = {(s['page_number'], s['table_index'], r['row_index']) for s, r in table['body']}
    result = []
    for source in sources:
        for raw in source['rows']:
            address = (source['page_number'], source['table_index'], raw['row_index'])
            item = dict(id=':'.join(map(str, address)), page_number=address[0], table_index=address[1], row_index=address[2],
                source_revision=source['source_revision'], source_cells=raw['cells'], fields={}, issues=[], excluded=True, kind='header')
            total = next((role for role, entry in totals.items() if entry[0] is source and entry[1] is raw), None)
            matches = [(role, cell) for role, cells in balances.items() for cell in cells if cell in raw['cells']]
            if address in body:
                fields, issues = _movement_row(raw, table['columns'], currency, choice)
                item.update(kind='transaction' if not issues else 'unresolved', excluded=False, fields=fields, issues=issues)
                if issues and not fields.get('description'):
                    fields['description'] = text(raw)
                result.append(item)
            elif total:
                cell = totals[total][2]
                item.update(kind='statement_total', fields=dict(description='Total ' + total, total_direction=total,
                    balance_column=str(cell['column_index'])))
                try:
                    item['fields']['balance'] = exact_amount(cell['expected_text'].strip(), currency)
                except ValueError as exc:
                    item['issues'].append(str(exc))
                result.append(item)
            elif matches:
                for index, (role, cell) in enumerate(matches):
                    fields = dict(description=role.title() + ' Balance',
                        balance_column=str(cell['column_index']), standalone_balance='true')
                    issues = []
                    try:
                        fields['balance'] = _balance_value(cell, currency)
                    except ValueError as exc:
                        issues.append(str(exc))
                    result.append({**item, 'id': item['id'] + (f':{role}' if index else ''), 'kind': 'balance',
                        'fields': fields, 'issues': issues})
            else:
                result.append(item)
    return dict(rows=result, issues=[])
