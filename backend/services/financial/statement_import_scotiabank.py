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
        if re.search(r'(?m)^\s*(?:DETALLE DE (?:TUS )?MOVIMIENTOS|FECHA\b.*(?:DESCRIPCION|CONCEPTO|RETIROS|DEPOSITOS))', all_text):
            continue
        # A dated payment line cannot be suppressed by a zero summary.
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
        controls = _controls(items)
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
        identity = dict(layout_id=LAYOUT, institution='Scotiabank Mexico', account_reference=next(iter(accounts)),
            period_start=start.isoformat(), period_end=end.isoformat())
        groups.append(dict(id=_digest(identity), **identity, account_type='checking',
            holder=next(iter(names)) if len(names) == 1 else '',
            sources=[dict(page_number=s['page_number'], table_index=s['table_index'], source_revision=s['source_revision']) for s in group],
            page_numbers=list(range(first, first + 3)),
            zero_activity_evidence=controls[1]))
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
