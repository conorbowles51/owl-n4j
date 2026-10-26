"""BBVA Mexico cash-management statements, with source-bound Spanish columns.

Only pages with the bank, product, account and printed page sequence are grouped.
Summary amounts are controls, never additional payments. All source rows survive.
"""
import os
import re
import unicodedata
from datetime import date
from functools import lru_cache

from services.financial.pdf_candidates import _digest
from services.financial.statement_import_proposal import exact_amount

LAYOUT = 'bbva-mexico-cash-management'
# Scans of this layout can set a space before a thousands comma ('1,031 ,472.00') or read one stray mark where
# the amount cell meets the table rule ('591,276.11?'). A cell that is a whole amount but for that space, or for
# exactly one such trailing mark, is that amount: it is placed in its column by its right edge like any amount, and
# the statement's printed balances and totals still decide. Off: the cell is read as description / left unreadable.
SCAN_AMOUNT_MARKS = os.environ.get('LOUPE_FINANCIAL_BBVA_SCAN_AMOUNT_MARKS', '1').strip().lower() not in ('0', 'false', 'no', 'off')
# BBVA prints two dates on each line, operation (OPER) and liquidation (LIQ). When the scan leaves one unread and the
# other is read, the line is not held for it: an unread liquidation date is left empty (the ledger date is the
# operation date), and an unread operation date takes the printed liquidation date (date_basis records it) only when
# it sits between the operation dates of the lines before and after it (the period's first/last day at its ends),
# the order the bank prints them in.
# Off: either unread date holds the line for a person.
ONE_DATE_PRINTED = os.environ.get('LOUPE_FINANCIAL_BBVA_ONE_DATE_PRINTED', '1').strip().lower() not in ('0', 'false', 'no', 'off')
LIQUIDATION_FOR_OPERATION = 'liquidation_date_operation_unread'
# The same order check for a line whose liquidation date is unread: its read operation date must also sit between the
# operation dates of the lines before and after it (07 ARRENDO BBVA USD JUL 2025 page 2: '14/JUL' read for the
# printed 11/JUL, the liquidation date read '41\JUL', between lines of 07/JUL and 11/JUL). Out of order, the line is
# held for its liquidation date as before ONE_DATE_PRINTED. Off: an unread liquidation date is never checked.
ONE_DATE_BRACKET = os.environ.get('LOUPE_FINANCIAL_BBVA_ONE_DATE_BRACKET', '1').strip().lower() not in ('0', 'false', 'no', 'off')
# On scanned pages OCR reads the zero of a two-digit day as the letter O (O7/ENE). In the day of a short printed date
# (DD/MMM) a letter O is that zero: no BBVA day is written with a letter, and the date still has to be a real day of
# the statement's own period. Off: the date is left unreadable and the line is held.
SCAN_DAY_ZERO = os.environ.get('LOUPE_FINANCIAL_BBVA_SCAN_DAY_ZERO', '1').strip().lower() not in ('0', 'false', 'no', 'off')
_WHOLE_AMOUNT = re.compile(r'(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\.[0-9]{2}')


def scan_amount_text(value):
    """The amount a scanned amount cell prints, or the text unchanged when it is not one."""
    value = value.strip()
    if not SCAN_AMOUNT_MARKS:
        return value
    folded = re.sub(r'(?<=[0-9])\s+,(?=[0-9]{3}(?:[,.]|$))', ',', value)
    if _WHOLE_AMOUNT.fullmatch(folded):
        return folded
    if len(folded) > 1 and folded[-1] in '),;?|' and _WHOLE_AMOUNT.fullmatch(folded[:-1]):
        return folded[:-1]
    return value
MONTHS = {name: i for i, name in enumerate(
    ('ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC'), 1)}


@lru_cache(maxsize=65536)
def norm(text):
    # Pure function of the text, called for every cell by every Mexican
    # layout detector on each reading. ASCII text has no compatibility forms
    # or combining marks, so its result is the upper-cased, space-collapsed
    # text; other text takes the full decomposition path.
    upper = text.upper()
    if upper.isascii():
        return ' '.join(upper.split())
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', upper)
                           if not unicodedata.combining(c)).split())


# Tesseract's English model has no accented ó. On scanned pages it reads the
# ó of Operación, Liquidación and Depósitos as one or two other glyphs (é,
# d, 6, do). Only that position is tolerated: every other letter, the
# words Saldo de, Inicial and Final, and the Abonos (+) suffix must be read
# exactly, so one balance label can never be taken for another.
_ACCENTED_CONTROLS = (
    (re.compile(r'SALDO DE OPERACI[^\sN]{1,2}N INICIAL'), 'SALDO DE OPERACION INICIAL'),
    (re.compile(r'SALDO DE OPERACI[^\sN]{1,2}N FINAL'), 'SALDO DE OPERACION FINAL'),
    (re.compile(r'SALDO DE LIQUIDACI[^\sN]{1,2}N INICIAL'), 'SALDO DE LIQUIDACION INICIAL'),
    (re.compile(r'DEP[^\sS]{1,2}SITOS / ABONOS \(\+\)'), 'DEPOSITOS / ABONOS (+)'))


def control_norm(value):
    # These are label readings, never edits to a printed date or amount.
    value = norm(value).strip(" '_~|\"")
    return next((label for pattern, label in _ACCENTED_CONTROLS if pattern.fullmatch(value)), value)


def text(row):
    return ' '.join(c['expected_text'].strip() for c in row['cells']).strip()


def full_date(value):
    try:
        d, m, y = map(int, value.split('/'))
        return date(y, m, d) if 2000 <= y < 2100 else None
    except (ValueError, TypeError):
        return None


def labelled_values(sources):
    values = {}
    for source in sources:
        for row in source['rows']:
            cells = row['cells']
            if not cells:
                continue
            labels = cells[0]['expected_text'].splitlines()
            if len(labels) > 1:
                # Some ruled PDFs merge the left label column vertically.
                following = [r for r in source['rows'] if r['row_index'] >= row['row_index']]
                right = [c['expected_text'].strip() for r in following for c in r['cells']
                         if c['column_index'] > cells[0]['column_index']]
                if len(labels) == len(right):
                    for label, value in zip(labels, right):
                        values.setdefault(norm(label), set()).add(value)
            elif len(cells) == 2:
                values.setdefault(norm(cells[0]['expected_text']), set()).add(cells[1]['expected_text'].strip())
            # OCR can place the address block and account/period block on one
            # row. Read the explicit label and its neighbour, not the first
            # two cells of that combined row.
            for index, cell in enumerate(cells[:-1]):
                label = norm(cell['expected_text'])
                if label in ('PERIODO', 'NO. DE CUENTA', 'NO. CUENTA'):
                    values.setdefault(label, set()).add(cells[index + 1]['expected_text'].strip())
            match = re.fullmatch(r'NO\.? (?:DE )?CUENTA\s*:?\s+(\d{8,20})', norm(text(row)))
            if match:
                values.setdefault('NO. CUENTA', set()).add(match[1])
    return values


def bbva_catalog(sources):
    pages = {}
    for source in sources:
        pages.setdefault(source['page_number'], []).append(source)
    contexts = {}
    for page, items in pages.items():
        texts = [norm(c['expected_text']) for s in items for r in s['rows'] for c in r['cells']]
        if ('ESTADO DE CUENTA' not in texts
                or not any(re.search(r'BBVA (?:MEXICO|BANCOMER),? S\.?A\.?', t) for t in texts)):
            continue
        products = {t for t in texts if t.startswith('CASH MANAGEMENT ') or re.fullmatch(r'MAESTRA (?:DOLARES )?PYME(?: BBVA)?', t)}
        numbered = {tuple(map(int, m.groups())) for t in texts
                    if (m := re.fullmatch(r'PAGINA\s+(\d+)\s*/\s*(\d+)', t))}
        values = labelled_values(items)
        accounts = {value for label, entries in values.items()
                    if label in ('NO. DE CUENTA', 'NO. CUENTA') for value in entries
                    if re.fullmatch(r'\d{8,20}', value)}
        if len(products) != 1 or len(numbered) != 1 or len(accounts) != 1:
            continue
        number, count = next(iter(numbered))
        if not 1 <= number <= count <= 500:
            continue
        cycles = set()
        for value in values.get('PERIODO', set()):
            m = re.fullmatch(r'DEL (\d{2}/\d{2}/\d{4}) AL (\d{2}/\d{2}/\d{4})', norm(value))
            if m:
                start, end = full_date(m[1]), full_date(m[2])
                if start and end and start <= end and (end-start).days <= 370:
                    cycles.add((start.isoformat(), end.isoformat()))
        contexts[page] = dict(account=next(iter(accounts)), product=next(iter(products)),
                              number=number, count=count, cycles=cycles)
    groups, handled = [], set()
    anchors = [(page, c) for page, c in contexts.items() if len(c['cycles']) == 1]
    for page, anchor in anchors:
        start, end = next(iter(anchor['cycles']))
        first = page - anchor['number'] + 1
        matched = [p for p, c in contexts.items() if c['account'] == anchor['account']
                   and c['product'] == anchor['product'] and c['count'] == anchor['count']
                   and p-c['number']+1 == first and (not c['cycles'] or c['cycles'] == {(start, end)})]
        # Conflicting cycles within the same printed sequence cannot borrow context.
        if any(c['cycles'] and c['cycles'] != {(start, end)} for p, c in contexts.items()
               if c['account'] == anchor['account'] and p-c['number']+1 == first):
            continue
        items = [s for s in sources if s['page_number'] in matched]
        names = {m[1].strip() for s in items for r in s['rows']
                 if (m := re.fullmatch(r'Nombre del Receptor\s*:\s*(.+)', text(r), re.I))}
        addressed = set()
        # A company name in the address block above Información Financiera
        # is explicit holder evidence (older statements lack the fiscal
        # recipient footer); address lines and bank legal footers must not
        # be used as names.
        for page in matched:
            cells = [cell for source in items if source['page_number'] == page
                for row in source['rows'] for cell in row['cells']]
            cutoffs = [box(cell)[1] for cell in cells if norm(cell['expected_text']) == 'INFORMACION FINANCIERA' and box(cell)]
            if not cutoffs:
                continue
            for cell in cells:
                rect = box(cell)
                size = (cell.get('locator') or {}).get('page_size')
                name = cell['expected_text'].strip()
                if (rect and size and rect[0] < size[0] / 2 and rect[1] < min(cutoffs)
                        and re.fullmatch(r'.{3,180}\s(?:S\.?\s*A\.?\s*(?:P\.?\s*I\.?)?|S\.?\s*DE\s*R\.?\s*L\.?)\s*DE\s*C\.?\s*V\.?', norm(name))):
                    addressed.add(name)
        if not names:
            names = addressed
        elif len(names) == 1 and len(addressed) == 1:
            # The fiscal footer prints the company without its legal form (the tax
            # receipt's recipient name); the address block prints the same name
            # with it. The holder is the name as printed with its legal form.
            receptor, full = norm(next(iter(names))), next(iter(addressed))
            rest = norm(full)[len(receptor):] if norm(full).startswith(receptor + ' ') else ''
            if rest and re.fullmatch(r'\s*,?\s*(?:S\.?\s*A\.?\s*(?:P\.?\s*I\.?)?|S\.?\s*DE\s*R\.?\s*L\.?)\s*DE\s*C\.?\s*V\.?', rest):
                names = {full}
        identity = dict(layout_id=LAYOUT, institution='BBVA Mexico', account_reference=anchor['account'],
                        period_start=start, period_end=end)
        identifier = _digest(identity)
        if any(g['id'] == identifier for g in groups):
            continue
        groups.append(dict(id=identifier, **identity, account_type='checking',
                           holder=next(iter(names)) if len(names) == 1 else '',
                           sources=[dict(page_number=s['page_number'], table_index=s['table_index'],
                                         source_revision=s['source_revision']) for s in items],
                           page_numbers=sorted(matched)))
        handled.update((s['page_number'], s['table_index']) for s in items)
    return groups, handled


def box(cell):
    locator = cell.get('locator') or {}
    rect = locator.get('rect')
    if not isinstance(rect, list) or len(rect) != 4 or not all(type(v) is int for v in rect):
        return None
    return rect if rect[0] < rect[2] and rect[1] < rect[3] else None


def short_date(value, choice):
    match = re.fullmatch(r'([0-9O]{1,2})/([A-Z]{3})' if SCAN_DAY_ZERO else r'(\d{1,2})/([A-Z]{3})', norm(value))
    if not match or match[2] not in MONTHS or not re.search(r'\d', match[1]):
        return None
    start, end = date.fromisoformat(choice['period_start']), date.fromisoformat(choice['period_end'])
    candidates = []
    for year in range(start.year, end.year+1):
        try:
            parsed = date(year, MONTHS[match[2]], int(match[1].replace('O', '0')))
            if start <= parsed <= end:
                candidates.append(parsed.isoformat())
        except ValueError:
            pass
    return candidates[0] if len(candidates) == 1 else None


def propose_bbva_statement(sources, currency, choice):
    result = []
    last_payment = None
    liquidation_unread = set()
    prior_period = False
    prior_period_pages = set()
    printed_labels = {control_norm(c['expected_text']) for s in sources for r in s['rows'] for c in r['cells']}
    operational = bool({'SALDO DE OPERACION INICIAL', 'SALDO DE OPERACION FINAL'} & printed_labels)
    balance_labels = (('SALDO DE OPERACION INICIAL', 'Opening Balance'), ('SALDO DE OPERACION FINAL', 'Closing Balance')) if operational else (
        ('SALDO DE LIQUIDACION INICIAL', 'Opening Balance'), ('SALDO FINAL (+)', 'Closing Balance'))
    running_column = 'OPERACION' if operational else 'LIQUIDACION'
    for source in sorted(sources, key=lambda s: (s['page_number'], s['table_index'])):
        columns = None
        for raw in source['rows']:
            cells = raw['cells']
            item = dict(id=f"{source['page_number']}:{source['table_index']}:{raw['row_index']}",
                        page_number=source['page_number'], table_index=source['table_index'],
                        row_index=raw['row_index'], source_revision=source['source_revision'],
                        source_cells=cells, fields={}, issues=[], excluded=True, kind='header')
            result.append(item)
            labels = {control_norm(c['expected_text']): c for c in cells}
            row_text = norm(text(raw))
            if row_text.startswith('MOVIMIENTOS DE PERIODOS ANTERIORES') and 'LIQUIDACION' in row_text:
                # These are operations already booked in a previous period.
                # BBVA repeats them to explain the settlement balance, outside
                # this period's printed payment counts and totals.
                prior_period = True
                columns = None
                last_payment = None
            if row_text.startswith('TOTAL DE MOVIMIENTOS'):
                prior_period = False
                columns = None
            if prior_period:
                prior_period_pages.add(source['page_number'])
                item.update(kind='prior_period_settlement')
                continue
            # Never mix operational and liquidation balances. Prefer the
            # operational pair, matching the operation-date transaction list.
            role = next((role for label, role in balance_labels
                if label in labels), None)
            total = next((direction for label, direction in (
                ('DEPOSITOS / ABONOS (+)', 'credit'), ('RETIROS / CARGOS (-)', 'debit')) if label in labels), None)
            control_label = next((label for label, _ in balance_labels if label in labels), None) if role else next(
                (label for label in ('DEPOSITOS / ABONOS (+)', 'RETIROS / CARGOS (-)') if label in labels), None)
            control_cells = cells[cells.index(labels[control_label]):] if control_label else []
            if (role and len(control_cells) == 2) or (total and len(control_cells) == 3 and control_cells[1]['expected_text'].strip().isdigit()):
                amount = control_cells[-1]
                item.update(kind='balance' if role else 'statement_total')
                item['fields'].update(description=role or ('Total ' + total), balance_column=str(amount['column_index']))
                if total:
                    item['fields']['total_direction'] = total
                    if len(control_cells) == 3 and control_cells[1]['expected_text'].strip().isdigit():
                        item['fields']['printed_transaction_count'] = control_cells[1]['expected_text'].strip()
                try:
                    item['fields']['balance'] = exact_amount(amount['expected_text'], currency)
                except ValueError as exc:
                    item['issues'].append(str(exc))
                continue
            names = ('OPER', 'LIQ', 'COD. DESCRIPCION', 'REFERENCIA', 'CARGOS', 'ABONOS', 'OPERACION', 'LIQUIDACION')
            # Scanned table rules can attach punctuation to otherwise exact
            # column labels. Normalize only known headings, never cell amounts
            # or descriptions, and still require the complete positioned grid.
            for cell in cells:
                heading = norm(cell['expected_text']).strip(" \"'‘’“”.,:;_-=–—|")
                if heading in (*names, 'OPER LIQ') and heading not in labels:
                    labels[heading] = cell
            date_headings = all(name in labels and box(labels[name]) for name in names[:2]) or (
                'OPER LIQ' in labels and box(labels['OPER LIQ']))
            if date_headings and all(name in labels and box(labels[name]) for name in names[2:]):
                columns = {name: labels[name] for name in names[2:]}
                continue
            if columns is None:
                continue
            if norm(text(raw)).startswith(('TOTAL DE MOVIMIENTOS', 'ESTIMADO CLIENTE', 'BBVA MEXICO,', 'BBVA BANCOMER,', 'LA GAT REAL')):
                columns = None
                continue
            # Match amount cells to the printed debit, credit and two balance
            # columns by their right edges. Do not equate liquidation and operation dates.
            buckets = {name: [] for name in names}
            malformed = False
            for cell in cells:
                rect = box(cell)
                if rect is None:
                    malformed = True
                    continue
                if rect[0] < box(columns['COD. DESCRIPCION'])[0] - 3000:
                    buckets['OPER'].append(cell)
                elif (re.fullmatch(r'(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\.[0-9]{2}', scan_amount_text(cell['expected_text']))
                        and len(aligned := [name for name in names[4:]
                            if abs(rect[2]-box(columns[name])[2]) <= 8000]) == 1):
                    # Large right-aligned amounts extend left of their shorter
                    # column heading. Their right edge, not text width, places
                    # them in Cargos/Abonos rather than the description.
                    buckets[aligned[0]].append(cell)
                elif rect[0] < box(columns['CARGOS'])[0] - 3000:
                    buckets['COD. DESCRIPCION'].append(cell)
                else:
                    matches = [name for name in names[4:]
                               if abs(rect[2]-box(columns[name])[2]) <= 8000]
                    if len(matches) == 1:
                        buckets[matches[0]].append(cell)
                    else:
                        malformed = True
            joined = lambda name: ' '.join((scan_amount_text(c['expected_text']) if name in names[4:] else c['expected_text'].strip())
                                           for c in buckets[name])
            # Preserve the two printed dates even when OCR merges their
            # headings or puts the description in the liquidation-date cell.
            date_parts = joined('OPER').split(maxsplit=2)
            date_text = date_parts[0] if date_parts else ''
            value_text = date_parts[1] if len(date_parts) > 1 else ''
            description = joined('COD. DESCRIPCION')
            if len(date_parts) > 2:
                description = ' '.join(filter(None, (date_parts[2], description)))
            if len(buckets['OPER']) > 1:
                buckets['LIQ'] = buckets['OPER'][1:]
            if not date_text and not value_text and not any(buckets[name] for name in names[4:]) and not malformed:
                if description and last_payment:
                    last_payment['fields']['description'] += ' ' + description
                    last_payment.setdefault('continuation_sources', []).append(dict(page_number=source['page_number'],
                        table_index=source['table_index'], row_index=raw['row_index'], source_cells=cells))
                    item['fields']['parent_transaction_id'] = last_payment['id']
                elif description:
                    item.update(kind='unresolved', excluded=False, issues=['Check this continuation: its preceding transaction was not identified.'])
                continue
            item.update(kind='transaction', excluded=False)
            fields = item['fields']
            fields.update(description=description, date_column=str(buckets['OPER'][0]['column_index']) if buckets['OPER'] else '0')
            description_cells = buckets['COD. DESCRIPCION'] or buckets['LIQ']
            if description_cells:
                fields['description_column'] = str(description_cells[0]['column_index'])
            printed_dates = {role: short_date(value, choice) for role, value in (('date', date_text), ('value_date', value_text))}
            for role in ('date', 'value_date'):
                if printed_dates[role]:
                    fields[role] = printed_dates[role]
                elif ONE_DATE_PRINTED and role == 'value_date' and printed_dates['date']:
                    liquidation_unread.add(item['id'])
                elif ONE_DATE_PRINTED and role == 'date' and printed_dates['value_date']:
                    fields.update(date=printed_dates['value_date'], date_basis=LIQUIDATION_FOR_OPERATION)
                else:
                    item['issues'].append('Check the printed ' + ('operation date.' if role == 'date' else 'liquidation date.'))
            if buckets['LIQ']:
                fields['value_date_column'] = str(buckets['LIQ'][0]['column_index'])
            active = [name for name in ('CARGOS', 'ABONOS') if buckets[name]]
            if len(active) == 1:
                name = active[0]
                fields['direction'] = 'debit' if name == 'CARGOS' else 'credit'
                fields[fields['direction']+'_column'] = str(buckets[name][0]['column_index'])
                try:
                    amount = exact_amount(joined(name), currency)
                    if int(amount) <= 0:
                        raise ValueError('Check the sign of this transaction amount.')
                    fields['amount_minor'] = fields[fields['direction']] = amount
                except ValueError as exc:
                    item['issues'].append(str(exc))
            else:
                item['issues'].append('Check the amount in the Cargos or Abonos column.')
            if buckets[running_column]:
                fields['balance_column'] = str(buckets[running_column][0]['column_index'])
                try:
                    fields['balance'] = exact_amount(joined(running_column), currency)
                except ValueError as exc:
                    item['issues'].append(str(exc))
            if not description or malformed:
                item['issues'].append('Some values could not be placed in the BBVA transaction columns. Compare this row with the PDF.')
            last_payment = item
    payments = [row for row in result if row['kind'] == 'transaction' and not row['excluded']]
    checked = (lambda r: r['fields'].get('date_basis') == LIQUIDATION_FOR_OPERATION
               or (ONE_DATE_BRACKET and r['id'] in liquidation_unread))
    for i, row in enumerate(payments):
        if not checked(row):
            continue
        before = next((r['fields']['date'] for r in reversed(payments[:i]) if r['fields'].get('date')
                       and not checked(r)), choice['period_start'])
        after = next((r['fields']['date'] for r in payments[i+1:] if r['fields'].get('date')
                      and not checked(r)), choice['period_end'])
        if not before or not after or not before <= row['fields']['date'] <= after:
            if row['fields'].get('date_basis') == LIQUIDATION_FOR_OPERATION:
                del row['fields']['date'], row['fields']['date_basis']
                row['issues'].insert(0, 'Check the printed operation date.')
            else:
                row['issues'].append('Check the printed liquidation date.')
    for row in result:
        count = row['fields'].get('printed_transaction_count')
        if count is not None:
            direction = row['fields']['total_direction']
            found = sum(not r['excluded'] and r['fields'].get('direction') == direction for r in result)
            if found != int(count):
                row['issues'].append(f'The statement lists {count} {"charges" if direction == "debit" else "credits"}; Loupe identified {found}. Check for missing transactions.')
    return dict(rows=result, issues=[], balance_basis='operation' if operational else 'liquidation',
                prior_period_settlement_pages=sorted(prior_period_pages))
