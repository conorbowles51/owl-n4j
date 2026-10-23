"""Santander Mexico online movement query ("Consulta de Movimientos de la Cuenta de Cheques").

A printout from the bank's online channel, not a monthly statement. Every page
prints the same header: the contract and holder ("Contrato CMC: <n> <holder>"),
the account ("Número de Cuenta"), the queried dates ("Periodo: dd/mm/yyyy al
dd/mm/yyyy"), "Saldo Inicial" and "Saldo Final" with their currency code, the
numbers of credits, debits and movements and the two printed totals. Below it a
ruled table lists every movement (account, date ddmmyyyy, time, branch,
description, debit, credit, running balance, reference, concept), oldest first.

The bank prints "Saldo Inicial" as the balance AFTER the first listed movement
(on every one of the 13 such printouts in the real collection). Neil's ruling
(2026-10-23): the opening of the queried period is the first printed running
balance less the first movement. It is admitted only when the printouts' own
figures prove it, all of them exactly:

* the first movement's printed running balance equals the printed Saldo Inicial
  (what makes the derivation the bank's own figure, not an assumption);
* derived opening + every movement = printed Saldo Final, and every printed
  running balance follows from the one before it (the shared review checks);
* the printed credit and debit totals equal the movements read
  (``statement_total`` rows, the shared review checks);
* the printed numbers of credits, debits and movements equal the rows read,
  every movement row prints the queried account, every date lies in the
  printed period, and every page "Página i de N" of the printout is present and
  repeats the same header (checked here; any failure holds the period with a
  named reason).

The derived opening is cited to the printed Saldo Inicial cell with its basis
(``balance_basis``) and the figures it rests on (``balance_derivation``), never
recorded as the value that cell prints. Switch: ``MOVEMENT_QUERY``.
"""
import re
from datetime import date

from services.financial.pdf_candidates import _digest
from services.financial.statement_import_bbva import box, norm, text
from services.financial.statement_import_proposal import exact_amount

# Neil, 2026-10-23: read the online movement query, deriving its opening. Reverse: False (the printouts are
# then left to the general engine, which holds them, as before).
MOVEMENT_QUERY = True
FORM = 'movement_query'
OPENING_BASIS = 'printed_opening_after_first_movement'
TITLE = 'CONSULTA DE MOVIMIENTOS DE LA CUENTA DE CHEQUES'
ISSUER = re.compile(r'(BANCO SANTANDER MEXICO),? S\.?A\.?')
COLUMNS = {'CUENTA': 'account', 'FECHA': 'date', 'HORA': 'time', 'SUCURSAL': 'branch', 'DESCRIPCION': 'description',
           'IMPORTE CARGO': 'debit', 'IMPORTE ABONO': 'credit', 'SALDO': 'balance', 'REFERENCIA': 'reference',
           'CONCEPTO': 'concept'}
_MONEY = r'(-?\$?\s?[\d,]+\.\d{2})\s+([A-Z]{3})'
LABELS = (
    ('holder', re.compile(r'CONTRATO CMC:\s*(\d+)\s+(\S.*)')),
    ('account', re.compile(r'NUMERO DE CUENTA:\s*(\d{6,20})')),
    ('period', re.compile(r'PERIODO:\s*(\d{2})/(\d{2})/(\d{4})\s+AL\s+(\d{2})/(\d{2})/(\d{4})')),
    ('opening', re.compile(r'SALDO INICIAL:\s*' + _MONEY)),
    ('closing', re.compile(r'SALDO FINAL:\s*' + _MONEY)),
    ('credits_count', re.compile(r'NUMERO DE ABONOS:\s*(\d+)')),
    ('debits_count', re.compile(r'NUMERO DE CARGOS:\s*(\d+)')),
    ('rows_count', re.compile(r'TOTAL DE MOVIMIENTOS:\s*(\d+)')),
    ('credits_total', re.compile(r'IMPORTE TOTAL ABONOS:\s*' + _MONEY)),
    ('debits_total', re.compile(r'IMPORTE TOTAL CARGOS:\s*' + _MONEY)),
)
PAGE = re.compile(r'PAGINA\s+(\d+)\s+DE\s+(\d+)')


def _iso(day, month, year):
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return None


def _page_labels(items):
    """``{name: (match, source, row, cell)}`` for the header labels printed on one page (each once), or None."""
    found = {}
    for s in items:
        for row in s['rows']:
            for cell in row['cells']:
                value = norm(cell['expected_text'])
                for name, pattern in LABELS:
                    m = pattern.fullmatch(value)
                    if m:
                        if name in found:
                            return None
                        found[name] = (m, s, row, cell)
    return found


def _header_row(s):
    """``{role: column_index}`` when a row of this table is the movement column heading, else None."""
    for row in s['rows']:
        names = {norm(c['expected_text']): c['column_index'] for c in row['cells']}
        if set(COLUMNS) <= set(names):
            return row['row_index'], {role: names[label] for label, role in COLUMNS.items()}
    return None


def _facts(labels):
    """Printed header facts of one page as comparable values (the same on every page of one printout)."""
    period = labels['period'][0]
    start, end = _iso(*period.groups()[:3]), _iso(*period.groups()[3:])
    facts = dict(contract=labels['holder'][0][1], holder=labels['holder'][0][2].strip(), account=labels['account'][0][1],
                 period_start=start, period_end=end)
    for name in ('opening', 'closing', 'credits_total', 'debits_total'):
        facts[name] = labels[name][0].groups()
    for name in ('credits_count', 'debits_count', 'rows_count'):
        facts[name] = int(labels[name][0][1])
    return facts


def santander_query_catalog(sources):
    """One period per printout: every page titled, headed and numbered alike, the issuer printed."""
    if not MOVEMENT_QUERY:
        return [], set()
    pages = {}
    for s in sources:
        pages.setdefault(s['page_number'], []).append(s)
    titled = {p for p, items in pages.items() if any(norm(text(r)) == TITLE for s in items for r in s['rows'])}
    if not titled:
        return [], set()
    if titled != set(pages):
        # A page of something else in the same file: not this layout's to claim.
        return [], set()
    issuers = {m[1] for items in pages.values() for s in items for r in s['rows'] if (m := ISSUER.search(norm(text(r))))}
    if len(issuers) != 1:
        return [], set()
    # The bank's name as its legal line prints it: the same ledger account as the monthly statements the
    # general engine reads from the same legal line (an account's identity includes its bank).
    institution = next(iter(issuers))
    facts, numbers = None, {}
    for p, items in sorted(pages.items()):
        labels = _page_labels(items)
        if not labels or len(labels) != len(LABELS):
            return [], set()
        here = _facts(labels)
        if not here['period_start'] or not here['period_end'] or here['period_start'] > here['period_end']:
            return [], set()
        if facts is not None and here != facts:
            return [], set()
        facts = here
        printed = {PAGE.fullmatch(norm(text(r))) for s in items for r in s['rows']} - {None}
        if len(printed) != 1:
            return [], set()
        m = next(iter(printed))
        numbers[p] = (int(m[1]), int(m[2]))
        if sum(1 for s in items if _header_row(s)) != 1:
            return [], set()
    currencies = {facts[name][1] for name in ('opening', 'closing', 'credits_total', 'debits_total')}
    totals = {total for _, total in numbers.values()}
    group = dict(layout_id='santander-mexico-movements', form=FORM, institution=institution,
                 account_reference=facts['account'], period_start=facts['period_start'],
                 period_end=facts['period_end'])
    group = dict(id=_digest(group), **group, account_type='checking', holder=facts['holder'],
                 # Every printed money figure of the header names one currency, or none is taken.
                 currency=next(iter(currencies)) if len(currencies) == 1 else '',
                 currency_source='printed_account_section', customer_reference=facts['contract'],
                 # Printed page numbering: every page of the printout present once, in order.
                 pages_complete=(len(totals) == 1 and sorted(n for n, _ in numbers.values())
                                 == list(range(1, next(iter(totals)) + 1))),
                 sources=[dict(page_number=p, table_index=s['table_index'], source_revision=s['source_revision'])
                          for p, items in sorted(pages.items()) for s in items],
                 page_numbers=sorted(pages),
                 section_sources=[dict(page_number=p, table_index=s['table_index'],
                                       row_indices=[r['row_index'] for r in s['rows']])
                                  for p, items in sorted(pages.items()) for s in items])
    return [group], {(s['page_number'], s['table_index']) for s in sources}


def _amount(value, currency):
    return exact_amount(value.replace('$', '').strip(), currency)


def _summary_amount(match, currency):
    value, code = match.groups()
    if code != currency:
        raise ValueError(f'The printed amount is {code}, but this review uses {currency}. Check the statement currency.')
    return _amount(value, currency)


def propose_santander_query(sources, currency, choice):
    from services.financial.statement_import_santander import located_rows
    result, movements, first_page = [], [], None
    page_labels = {}
    for page in sorted({s['page_number'] for s in sources}):
        items = [s for s in sources if s['page_number'] == page]
        page_labels[page] = _page_labels(items) or {}
        headers = {s['table_index']: _header_row(s) for s in items}
        first_page = page if first_page is None else first_page
        for s, raw in located_rows(items):
            item = dict(id=f"{page}:{s['table_index']}:{raw['row_index']}", page_number=page, table_index=s['table_index'],
                        row_index=raw['row_index'], source_revision=s['source_revision'], source_cells=raw['cells'],
                        fields={}, issues=[], excluded=True, kind='header')
            result.append(item)
            heading = headers.get(s['table_index'])
            if not heading or raw['row_index'] == heading[0]:
                continue
            columns = heading[1]
            cells = {c['column_index']: c for c in raw['cells']}
            value = {role: cells[index]['expected_text'].strip() if index in cells else '' for role, index in columns.items()}
            item.update(kind='transaction', excluded=False)
            fields = item['fields']
            fields.update(description=' '.join(v for v in (value['description'], value['concept']) if v),
                          bank_reference=value['reference'], date_column=str(columns['date']),
                          description_column=str(columns['description']))
            movements.append(item)
            if value['account'] != choice['account_reference']:
                item['issues'].append('This movement line prints another account number. Check it against the PDF.')
            m = re.fullmatch(r'(\d{2})(\d{2})(\d{4})', value['date'])
            day = _iso(m[1], m[2], m[3]) if m else None
            if day and choice['period_start'] <= day <= choice['period_end']:
                fields['date'] = day
            else:
                item['issues'].append('Check this payment date against the printed query period.')
            amounts = {}
            for role in ('debit', 'credit'):
                try:
                    amounts[role] = int(_amount(value[role], currency)) if value[role] else None
                except ValueError as exc:
                    amounts[role] = None
                    item['issues'].append(str(exc))
            nonzero = [role for role in ('debit', 'credit') if amounts[role]]
            if (len(nonzero) != 1 or any(amounts[r] is None for r in ('debit', 'credit'))
                    or amounts[nonzero[0]] <= 0):
                item['issues'].append('Choose the printed debit or credit amount for this payment.')
            else:
                direction = nonzero[0]
                fields.update(direction=direction, amount_minor=str(amounts[direction]))
                fields[direction + '_column'] = str(columns[direction])
            try:
                fields['balance'] = _amount(value['balance'], currency)
                fields['balance_column'] = str(columns['balance'])
            except ValueError as exc:
                item['issues'].append(str(exc))
    labels = page_labels.get(first_page) or {}
    problems = []
    if len(labels) != len(LABELS) or any(_facts(page_labels[p]) != _facts(labels) for p in page_labels
                                         if len(page_labels[p]) == len(LABELS)) or any(
            len(page_labels[p]) != len(LABELS) for p in page_labels):
        problems.append('The printed query header could not be read the same on every page. Check the pages.')
    if not choice.get('pages_complete'):
        problems.append('The printed page numbering shows pages of this query that are not in the file.')

    def underived(opening, message):
        # Not proven: no opening is offered at all (the printed Saldo Inicial is not this period's opening).
        opening['fields'].pop('balance', None)
        opening['issues'].append(message)
        problems.append(message)

    def control(name, kind, **fields):
        m, s, raw, cell = labels[name]
        item = dict(id=f"{first_page}:{s['table_index']}:{raw['row_index']}:{name}", page_number=first_page,
                    table_index=s['table_index'], row_index=raw['row_index'], source_revision=s['source_revision'],
                    source_cells=raw['cells'], fields=dict(fields, balance_column=str(cell['column_index'])),
                    issues=[], excluded=True, kind=kind)
        try:
            item['fields']['balance'] = _summary_amount(m, currency)
        except ValueError as exc:
            item['issues'].append(str(exc))
        result.append(item)
        return item

    if not problems:
        opening = control('opening', 'balance', description='Opening Balance')
        control('closing', 'balance', description='Closing Balance')
        control('credits_total', 'statement_total', description='Total credit', total_direction='credit')
        control('debits_total', 'statement_total', description='Total debit', total_direction='debit')
        facts = _facts(labels)
        read = dict(credits_count=sum(1 for r in movements if r['fields'].get('direction') == 'credit'),
                    debits_count=sum(1 for r in movements if r['fields'].get('direction') == 'debit'),
                    rows_count=len(movements))
        if any(read[k] != facts[k] for k in read):
            problems.append('The printed numbers of credits, debits and movements differ from the movement lines read.')
        dates = [r['fields'].get('date') or '' for r in movements]
        first = movements[0] if movements else None
        if not first or dates != sorted(dates):
            # Oldest first is the printed order the derivation rests on; anything else is held.
            underived(opening, 'The opening balance before the first movement is not printed, and the movement lines '
                               'were not read oldest first, so it cannot be worked out. Enter it from the source.')
        elif 'balance' in opening['fields'] and first['fields'].get('balance') is not None and first['fields'].get(
                'amount_minor') and first['fields'].get('direction') in ('credit', 'debit'):
            printed = int(opening['fields']['balance'])
            after_first = int(first['fields']['balance'])
            moved = int(first['fields']['amount_minor']) * (1 if first['fields']['direction'] == 'credit' else -1)
            if after_first != printed:
                underived(opening, 'The printed Saldo Inicial is not the balance after the first movement, so the '
                                   'opening balance cannot be worked out. Enter it from the source.')
            else:
                opening['fields'].update(balance=str(printed - moved), balance_basis=OPENING_BASIS, balance_derivation=dict(
                    printed_opening_minor=str(printed), first_movement_id=first['id'],
                    first_movement_minor=str(moved), first_balance_minor=str(after_first)))
        else:
            underived(opening, 'The first movement or the printed Saldo Inicial could not be read, so the opening '
                               'balance cannot be worked out. Enter it from the source.')
    if problems:
        # Held on a printed line of the query itself: a person checks it against the PDF.
        anchor = next((r for r in result if r['kind'] == 'header' and r['page_number'] == first_page), None)
        if anchor is None:
            raise ValueError('The movement query has no printed lines to review.')
        anchor.update(kind='unresolved', excluded=False)
        anchor['fields']['description'] = text(dict(cells=anchor['source_cells']))
        anchor['issues'].extend(problems)
    return dict(rows=result, issues=[])
