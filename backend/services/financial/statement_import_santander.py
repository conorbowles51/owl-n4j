"""Santander Mexico account-scoped movement tables, native or positioned OCR.

Printed account/period headings define scope. Amount columns supply direction;
summary totals, advertisements and fiscal lines never create payments.
"""
import re
from datetime import date
from services.financial.pdf_candidates import _digest
from services.financial.statement_import_bbva import box as _printed_box, norm, text, MONTHS
from services.financial.statement_import_proposal import exact_amount

import os

LAYOUT = 'santander-mexico-movements'


def _switch(name):
    return os.environ.get(name, '1').strip().lower() not in ('0', 'false', 'off', 'no')


# Reader gaps (2026-10-24), each default on and reversible in one place:
# * LOUPE_FINANCIAL_SANTANDER_RULE_APOSTROPHE: a column rule between the date, folio and description
#   read as an apostrophe (scanned pages) separates them like '|' does.
# * LOUPE_FINANCIAL_SANTANDER_COVER_SPACED_ACCOUNT: the cover's balance summary names the section's
#   account when the OCR split the number with a space (the whole cell, spaces removed, is the number).
# * LOUPE_FINANCIAL_SANTANDER_QUIET_COVER_CLOSING: a quiet section (no movement read, printed zero
#   TOTAL lines) whose SALDO FINAL line was not read takes its closing from the cover summary when the
#   cover prints the section's opening as both last month's and this month's balance.
RULE_APOSTROPHE = _switch('LOUPE_FINANCIAL_SANTANDER_RULE_APOSTROPHE')
COVER_SPACED_ACCOUNT = _switch('LOUPE_FINANCIAL_SANTANDER_COVER_SPACED_ACCOUNT')
QUIET_COVER_CLOSING = _switch('LOUPE_FINANCIAL_SANTANDER_QUIET_COVER_CLOSING')
# * LOUPE_FINANCIAL_SANTANDER_CURRENCY_RULE_MARKS: the cover's MONEDA value read with the box rule in front of it
#   ('—- MONEDA NACIONAL', scans) is that value; only marks that are not letters or digits are dropped, and the
#   rest must still be one of the printed currency names exactly.
CURRENCY_RULE_MARKS = _switch('LOUPE_FINANCIAL_SANTANDER_CURRENCY_RULE_MARKS')
# * LOUPE_FINANCIAL_SANTANDER_CURRENCY_ONE_CELL (fin-queue3, 05 MONETA SANTANDER MXN MAY 26): the scan read the label,
#   the box rule and the value as one cell ('MONEDA — MONEDA NACIONAL'). A cell that is the label, then at least one
#   mark that is not a letter or digit, then one of the printed currency names exactly, is that value.
CURRENCY_ONE_CELL = _switch('LOUPE_FINANCIAL_SANTANDER_CURRENCY_ONE_CELL')
_CURRENCY_NAMES = {'MONEDA NACIONAL':'MXN','PESOS':'MXN','DOLARES':'USD','DOLARES AMERICANOS':'USD','USD':'USD','MXN':'MXN'}
# * LOUPE_FINANCIAL_SANTANDER_UNPLACED_TABLE: a movement table the PDF reading kept as ruled cells but could not
#   position on the page (no rectangle on any cell; 09 NOVAC SANTANDER SEP 25 page 6, the start of 'Detalles de
#   movimientos Dinero Creciente') is read in its own row order directly under the one movement heading of its page
#   that has no positioned table under it, its columns taken from the table's own FECHA/DEPOSITO/RETIRO/SALDO
#   heading cells (column_index). A SALDO cell holding several stacked balances gives its row only its first line.
#   The order is kept in 'table_order_rect' beside the cell; the printed locator is never invented.
UNPLACED_TABLE = _switch('LOUPE_FINANCIAL_SANTANDER_UNPLACED_TABLE')
# * LOUPE_FINANCIAL_SANTANDER_CONTINUED_UNPLACED_TABLE: such a table on a page with no open movement heading (06-JUN25
#   SANTANDER MPA MXP page 3: the rest of the CUENTA SANTANDER PYME movements, ending with its SALDO FINAL DEL PERIODO)
#   continues the movement section of the page before. It is read directly under the page's header (the one row
#   printing PERIODO DEL), only when the next positioned row is a movement heading, the page footer or nothing, so
#   nothing printed lies between them. Whether it joins a section is still decided by the page before: an open
#   section of the same customer and period, as for any continuation page.
CONTINUED_UNPLACED_TABLE = _switch('LOUPE_FINANCIAL_SANTANDER_CONTINUED_UNPLACED_TABLE')
# * LOUPE_FINANCIAL_SANTANDER_QUIET_HEADING (fin-queue3, 05 MONETA SANTANDER MXN MAY 26 INVERSION CRECIENTE): a movement
#   heading read without its SALDO word ('FECHA FOLIO DESCRIPCION DEPOSITO RETIRO'; 4 of 71 Dinero Creciente headings
#   of all cases, each directly over a TOTAL line) gives its DEPOSITO and RETIRO columns to the TOTAL line printed
#   directly under it, and to nothing else; that pair is the section's column heading for the quiet-section check.
QUIET_HEADING = _switch('LOUPE_FINANCIAL_SANTANDER_QUIET_HEADING')
# * LOUPE_FINANCIAL_SANTANDER_COVER_OPENING: a section whose SALDO FINAL DEL PERIODO ANTERIOR value the scan lost
#   takes its opening from the cover's balance summary (_cover_opening), the mirror of _cover_closing.
COVER_OPENING = _switch('LOUPE_FINANCIAL_SANTANDER_COVER_OPENING')
ACCOUNT = re.compile(r'(?P<product>CUENTA SANTANDER [A-Z ]+?|INVERSION CRECIENTE|SUPER CUENTA [A-Z ]+?)\s*(?P<number>\d{2}-\d{8}-\d)\b')
DATE = r'\d{2}-[A-Z]{3}-\d{4}'
# Marks a printed column rule between the date and folio columns is read as: '|' and '/', and on
# vector-text and scanned pages also ')', '(', ']' and '['. Never a digit or a letter. Reverse: r'[\s|/]*'.
RULE = r"[\s|/()\[\]'\u2018\u2019]*" if RULE_APOSTROPHE else r'[\s|/()\[\]]*'


def printed_date(value):
    m = re.fullmatch(r'(\d{2})-([A-Z]{3})-(\d{4})', norm(value))
    if not m or m[2] not in MONTHS:
        return None
    try:
        return date(int(m[3]), MONTHS[m[2]], int(m[1])).isoformat()
    except ValueError:
        return None


def box(cell):
    return _printed_box(cell) or cell.get('table_order_rect')


_COLUMN_STEP, _COLUMN_WIDTH = 60000, 50000
_STACKED_MONEY = re.compile(r'\$?\s*\d{1,3}(?:,\d{3})*\.\d{2}')


def _unplaced_tables(items):
    """``items`` with each wholly unpositioned movement table placed under its page's open movement heading."""
    unplaced = [s for s in items if s['rows'] and not any(_printed_box(c) for r in s['rows'] for c in r['cells'])]
    if not unplaced:
        return items
    tables = []
    for s in unplaced:
        heading = next((r for r in s['rows'] if all(n in {norm(c['expected_text']) for c in r['cells']}
                        for n in ('FECHA', 'DEPOSITO', 'RETIRO', 'SALDO'))), None)
        if heading is not None:
            tables.append((s, {norm(c['expected_text']): c['column_index'] for c in heading['cells']}))
    placed = sorted([(s, r) for s in items for r in s['rows'] if any(_printed_box(c) for c in r['cells'])],
                    key=lambda pair: min(_printed_box(c)[1] for c in pair[1]['cells'] if _printed_box(c)))
    top = lambda r: min(_printed_box(c)[1] for c in r['cells'] if _printed_box(c))
    open_headings = []
    for i, (_, r) in enumerate(placed):
        if not re.search(r'DETALLES? DE MOVIMIENTOS', norm(text(r))):
            continue
        after = []
        for _, later in placed[i+1:]:
            if re.search(r'DETALLES? DE MOVIMIENTOS', norm(text(later))):
                break
            after.append(later)
        if not any('FECHA' in norm(text(x)) and 'SALDO' in norm(text(x)) for x in after):
            bottom = max(_printed_box(c)[3] for c in r['cells'] if _printed_box(c))
            open_headings.append((bottom, top(after[0]) if after else None))
    if CONTINUED_UNPLACED_TABLE and len(tables) == 1 and not open_headings:
        headers = [i for i, (_, r) in enumerate(placed) if re.search(r'PERIODO DEL', norm(text(r)))]
        if len(headers) == 1:
            header = placed[headers[0]][1]
            following = placed[headers[0]+1][1] if headers[0]+1 < len(placed) else None
            if following is None or re.search(r'DETALLES? DE MOVIMIENTOS|^PAGINA \d', norm(text(following))):
                open_headings.append((max(_printed_box(c)[3] for c in header['cells'] if _printed_box(c)),
                                      top(following) if following is not None else None))
    if len(tables) != 1 or len(open_headings) != 1:
        return items
    (table, columns), (bottom, limit) = tables[0], open_headings[0]
    if limit is not None and bottom + 2 * len(table['rows']) + 2 >= limit:
        return items
    saldo = columns['SALDO']
    rows = []
    for r in table['rows']:
        y = bottom + 1 + 2 * r['row_index']
        cells = []
        for c in r['cells']:
            c = dict(c, table_order_rect=[100000 + c['column_index'] * _COLUMN_STEP, y,
                                          100000 + c['column_index'] * _COLUMN_STEP + _COLUMN_WIDTH, y + 1])
            lines = [line.strip() for line in c['expected_text'].split('\n')]
            if c['column_index'] == saldo and len(lines) > 1 and all(_STACKED_MONEY.fullmatch(line) for line in lines):
                c['expected_text'] = lines[0]
            cells.append(c)
        rows.append(dict(r, cells=cells))
    return [dict(s, rows=rows) if s is table else s for s in items]


def located_rows(items):
    if UNPLACED_TABLE:
        items = _unplaced_tables(items)
    return sorted([(s, r) for s in items for r in s['rows'] if any(box(c) for c in r['cells'])],
        key=lambda pair: (min(box(c)[1] for c in pair[1]['cells'] if box(c)), pair[0]['table_index'], pair[1]['row_index']))


def santander_catalog(sources):
    from services.financial.statement_import_santander_query import santander_query_catalog
    query, query_handled = santander_query_catalog(sources)
    if query:
        # An online movement query printout ("Consulta de Movimientos"): every page is the query's.
        return query, query_handled
    pages = {}
    for s in sources:
        pages.setdefault(s['page_number'], []).append(s)
    contexts, known = {}, {}
    for p, items in pages.items():
        content = '\n'.join(norm(text(r)) for s in items for r in s['rows'])
        if not re.search(r'BANCO SANTANDER MEXICO,? S\.?A\.?', content):
            continue
        periods = set(re.findall(r'PERIODO\s+DEL ('+DATE+r') AL ('+DATE+r')', content))
        clients = set(re.findall(r'CODIGO DE CLIENTE NO\.?\s*(\d+)', content))
        if len(periods) != 1 or len(clients) != 1:
            continue
        start, end = map(printed_date, next(iter(periods)))
        if not start or not end or not 0 <= (date.fromisoformat(end)-date.fromisoformat(start)).days <= 62:
            continue
        key = (next(iter(clients)), start, end)
        contexts[p] = key
        meta = known.setdefault(key, dict(products=set(), currencies=set(), holders=set(), pages=[]))
        meta['pages'].append(p)
        meta['products'].update((m['product'].strip(), m['number']) for m in ACCOUNT.finditer(content))
        for s in items:
            for r in s['rows']:
                cells = r['cells']
                for i,c in enumerate(cells):
                    if norm(c['expected_text']) == 'MONEDA' and i+1 < len(cells):
                        value = norm(cells[i+1]['expected_text'])
                        if CURRENCY_RULE_MARKS:
                            value = re.sub(r'^[^A-Z0-9]+|[^A-Z0-9]+$', '', value).strip()
                        code = _CURRENCY_NAMES.get(value)
                        if code:meta['currencies'].add(code)
                    elif CURRENCY_ONE_CELL and (one := re.fullmatch(r'MONEDA\s*[^A-Z0-9\s]+\s*(.+?)\s*', norm(c['expected_text']))):
                        code = _CURRENCY_NAMES.get(one[1])
                        if code:meta['currencies'].add(code)
                    if 'CODIGO DE CLIENTE NO' in norm(c['expected_text']) and i > 0:
                        holder = cells[i-1]['expected_text'].strip()
                        if holder and len(holder) < 200:meta['holders'].add(holder)
    groups, handled = {}, set()
    active = None
    previous_page = None

    def attach(group, section, page, meta):
        for source in pages[page]:
            # By table address: a placed unpositioned table (_unplaced_tables) is a copy of its source.
            indices = [row['row_index'] for origin, row in section if origin['table_index'] == source['table_index']]
            if indices:
                group['section_sources'].append(dict(page_number=page,
                    table_index=source['table_index'], row_indices=indices))
                if any(origin['table_index'] == source['table_index'] and 'table_order_rect' in row['cells'][0]
                       for origin, row in section if row['cells']):
                    # No printed position to compare with another reading's sections (source regions).
                    group.setdefault('unplaced_tables', []).append([page, source['table_index']])
        # Cover supplies identity and currency. Only the bounded movement
        # sections above participate in this account's payments.
        for number in sorted({page, meta['pages'][0]}):
            if number not in group['page_numbers']:
                group['page_numbers'].append(number)
                group['sources'].extend(dict(page_number=number, table_index=s['table_index'],
                    source_revision=s['source_revision']) for s in pages[number])
                handled.update((number, s['table_index']) for s in pages[number])

    def movements(section):
        return any(all(label in norm(text(row)) for label in
            ('FECHA', 'DEPOSITO', 'RETIRO', 'SALDO')) for _, row in section)

    def ended(section):
        return any('SALDO FINAL DEL PERIODO' in norm(text(row)) and
            'ANTERIOR' not in norm(text(row)) for _, row in section)

    for p, items in sorted(pages.items()):
        key = contexts.get(p)
        if not key or previous_page is None or p != previous_page + 1 or (active and active[0] != key):
            active = None
        previous_page = p
        if not key:continue
        meta = known[key]; located = located_rows(items)
        anchors = [(i,s,r) for i,(s,r) in enumerate(located) if re.search(r'DETALLES? DE MOVIMIENTOS', norm(text(r)))]
        # Continuations repeat the customer/period and movement columns, not
        # the account heading. Carry only the immediately preceding open
        # account section; never bridge a missing or differently scoped page.
        prefix = located[:anchors[0][0]] if anchors else located
        if active and movements(prefix):
            attach(active[1], prefix, p, meta)
            if ended(prefix):
                active = None
        elif prefix:
            active = None
        for n,(index,_,heading) in enumerate(anchors):
            active = None
            end = anchors[n+1][0] if n+1 < len(anchors) else len(located)
            section = located[index:end]
            cutoff = next((i for i,(_,r) in enumerate(section) if 'INFORMACION FISCAL' in norm(text(r))), len(section))
            section = section[:cutoff]
            prefix = []
            for _,r in section:
                if 'FECHA' in norm(text(r)) and 'SALDO' in norm(text(r)):break
                prefix.append(norm(text(r)))
            matches = {(m['product'].strip(),m['number']) for m in ACCOUNT.finditer('\n'.join(prefix))}
            if not matches and 'DINERO CRECIENTE SANTANDER' in norm(text(heading)):
                matches = {entry for entry in meta['products'] if entry[0] == 'INVERSION CRECIENTE'}
            if len(matches) != 1:continue
            product, account = next(iter(matches))
            identity = dict(layout_id=LAYOUT,institution='Santander',account_reference=account,period_start=key[1],period_end=key[2])
            group = groups.setdefault(_digest(identity),dict(id=_digest(identity),**identity,account_type='savings' if product=='INVERSION CRECIENTE' else 'checking',
                holder=next(iter(meta['holders'])) if len(meta['holders'])==1 else '',
                currency=next(iter(meta['currencies'])) if len(meta['currencies'])==1 else '',currency_source='printed_account_section',
                customer_reference=key[0], sources=[],page_numbers=[],section_sources=[]))
            attach(group, section, p, meta)
            if movements(section) and not ended(section):
                active = (key, group)
    return list(groups.values()), handled


def propose_santander_statement(sources,currency,choice):
    from services.financial.statement_import_santander_query import FORM, propose_santander_query
    if choice.get('form') == FORM:
        return propose_santander_query(sources, currency, choice)
    scopes={(s['page_number'],s['table_index']):set(s['row_indices']) for s in choice['section_sources']}
    result=[];columns=None;last=None;active_page=None;previous_balance=None;quiet_heading=None
    for page in sorted({s['page_number'] for s in sources}):
        for s,raw in located_rows([s for s in sources if s['page_number']==page]):
            cells=raw['cells'];joined=norm(text(raw))
            item=dict(id=f"{page}:{s['table_index']}:{raw['row_index']}",page_number=page,table_index=s['table_index'],row_index=raw['row_index'],source_revision=s['source_revision'],source_cells=cells,fields={},issues=[],excluded=True,kind='header')
            result.append(item)
            if page!=active_page:columns=None;last=None;active_page=page
            if raw['row_index'] not in scopes.get((page,s['table_index']),set()):continue
            # A heading read without SALDO serves only the very next line of its section (QUIET_HEADING).
            heading_before,quiet_heading=(quiet_heading if quiet_heading and quiet_heading[0]==page else None),None
            labels={norm(c['expected_text']):c for c in cells}
            if 'SALDO FINAL DEL PERIODO' in joined:
                opening='ANTERIOR' in joined
                item['kind']='balance';item['fields']['description']='Opening Balance' if opening else 'Closing Balance'
                amount=cells[-1];value=amount['expected_text'].strip()
                if len(cells)==1:value=re.sub(r'^.*?:\s*','',value)
                item['fields']['balance_column']=str(amount['column_index'])
                try:item['fields']['balance']=exact_amount(value.replace('$','').strip(),currency)
                except ValueError as exc:item['issues'].append(str(exc))
                if not opening:columns=None;last=None
                continue
            money_names=('DEPOSITO','RETIRO','SALDO')
            if 'FECHA' in joined and all(n in labels and box(labels[n]) for n in money_names):
                columns={n:labels[n] for n in money_names};last=None;continue
            if (QUIET_HEADING and columns is None and 'FECHA' in joined and 'SALDO' not in joined
                    and all(n in labels and box(labels[n]) for n in ('DEPOSITO','RETIRO'))):
                quiet_heading=(page,{n:labels[n] for n in ('DEPOSITO','RETIRO')});continue
            if columns is None and heading_before and joined.startswith('TOTAL'):
                _quiet_totals(item,cells,heading_before[1],result,currency)
                continue
            if columns is None:
                # A recognizable payment under an unreadable column heading
                # is an incomplete reading, never evidence of no activity.
                if re.match(r'^'+DATE+RULE+r'\d{7}\b', joined):
                    item.update(kind='unresolved', excluded=False)
                    item['fields']['description'] = text(raw)
                    item['issues'].append('The movement columns could not be read. Check the date, deposit or withdrawal and balance beside the PDF.')
                continue
            if MERGED_TOTAL and _merges_total(cells):
                split=_split_merged_total(cells,columns,last,currency)
                if split is None:
                    # Never take the TOTAL line's figures as this payment's.
                    item.update(kind='unresolved',excluded=False)
                    item['fields']['description']=text(raw)
                    item['issues'].append('This line prints a payment and the TOTAL line together. Check the payment amount and balance beside the PDF.')
                    continue
                cells,totals=split
                for direction,cell in totals:
                    total=dict(item,id=item['id']+':'+direction,fields={},issues=[],kind='statement_total',excluded=True)
                    total['fields'].update(description='Total '+direction,total_direction=direction,balance_column=str(cell['column_index']),
                        balance=exact_amount(cell['expected_text'],currency),merged_with_row=item['id'])
                    result.append(total)
            money={n:[] for n in money_names};other=[]
            for c in cells:
                rect=box(c)
                if rect and rect[0] >= box(columns['DEPOSITO'])[0] and re.fullmatch(r'\$?\s*[\d,.]+\.\d{2}-?',c['expected_text'].strip()):
                    # Both ruled cells and OCR words stay in their printed
                    # monetary columns; absent cells are not shifted left.
                    name=min(money_names,key=lambda n:abs(rect[2]-box(columns[n])[2]))
                    money[name].append(c)
                else:other.append(c)
            if joined.startswith('TOTAL'):
                for name,direction in [('DEPOSITO','credit'),('RETIRO','debit')]:
                    if len(money[name])!=1:continue
                    total=item if not item['fields'] else dict(item,id=item['id']+':'+direction,fields={},issues=[])
                    if total is not item:result.append(total)
                    total['kind']='statement_total';total['fields'].update(description='Total '+direction,total_direction=direction,balance_column=str(money[name][0]['column_index']))
                    try:total['fields']['balance']=exact_amount(money[name][0]['expected_text'],currency)
                    except ValueError as exc:total['issues'].append(str(exc))
                continue
            # Native date/folio cells and scanned merged fields use the same
            # explicit printed date + folio prefix. No date from a description.
            prefix=' '.join(c['expected_text'].strip() for c in other)
            m=re.match(r'^('+DATE+r')'+RULE+r'(\d{7})(?:'+RULE+r')(.*)$',prefix,re.S)
            if not m:
                if last and not any(money.values()) and prefix and not re.match(r'P[ÁA]GINA|BANCO SANTANDER|ESTADO DE CUENTA',norm(prefix)):
                    last['fields']['description']+=' '+prefix
                    last.setdefault('continuation_sources',[]).append(dict(page_number=page,table_index=s['table_index'],row_index=raw['row_index'],source_cells=cells))
                    item['fields']['parent_transaction_id']=last['id']
                elif any(money.values()):
                    item.update(kind='unresolved',excluded=False)
                    item['fields']['description']=prefix
                    item['issues'].append('Check the printed date and reference for this payment beside the PDF.')
                continue
            # The previous payment's printed running balance, when it is the line just before this one.
            moved=[r for r in result if not r['excluded'] and r['kind'] in ('transaction','unresolved')]
            previous_balance=(last['fields'].get('balance') if last and moved and moved[-1] is last and not last['issues']
                              and 'amount_minor' in last['fields'] else None)
            item.update(kind='transaction',excluded=False);last=item;fields=item['fields']
            fields.update(description=m[3].strip(),bank_reference=m[2],date_column=str(other[0]['column_index']),description_column=str(other[-1]['column_index']))
            day=printed_date(m[1])
            if day and choice['period_start']<=day<=choice['period_end']:fields['date']=day
            else:item['issues'].append('Check this payment date against the printed statement period.')
            directions=[(name,d) for name,d in [('DEPOSITO','credit'),('RETIRO','debit')] if money[name]]
            if len(directions)!=1:item['issues'].append('Choose the printed deposit or withdrawal amount for this payment.')
            else:
                name,direction=directions[0];fields['direction']=direction
                if len(money[name])==1:
                    c=money[name][0];fields[direction+'_column']=str(c['column_index'])
                    try:
                        amount=exact_amount(c['expected_text'],currency)
                        if int(amount)<=0:raise ValueError('The payment amount must be positive; the column supplies direction.')
                        fields['amount_minor']=amount
                    except ValueError as exc:item['issues'].append(str(exc))
                else:item['issues'].append('Check the printed amount for this payment.')
            if len(money['SALDO'])==1:
                c=money['SALDO'][0];fields['balance_column']=str(c['column_index'])
                try:fields['balance']=exact_amount(c['expected_text'],currency)
                except ValueError as exc:item['issues'].append(str(exc))
            if BALANCE_STEP_AMOUNT and 'amount_minor' not in fields and fields.get('direction'):
                _balance_step_amount(item, previous_balance, money, currency)
    if COVER_OPENING:
        _cover_opening(result, choice, currency)
    if COVER_CLOSING:
        _cover_closing(result, choice, currency)
    return dict(rows=result,issues=[])


def _quiet_totals(item, cells, heading, result, currency):
    """The TOTAL line under a heading read without SALDO: one printed amount under each of DEPOSITO and RETIRO
    (nearest right edge, never left of the DEPOSITO heading), or nothing."""
    money = {n: [] for n in heading}
    for c in cells:
        rect = box(c)
        if rect and rect[0] >= box(heading['DEPOSITO'])[0] and re.fullmatch(r'\$?\s*[\d,.]+\.\d{2}-?', c['expected_text'].strip()):
            money[min(heading, key=lambda n: abs(rect[2] - box(heading[n])[2]))].append(c)
    if any(len(found) != 1 for found in money.values()):
        return
    for name, direction in (('DEPOSITO', 'credit'), ('RETIRO', 'debit')):
        total = item if not item['fields'] else dict(item, id=item['id'] + ':' + direction, fields={}, issues=[])
        if total is not item:
            result.append(total)
        total['kind'] = 'statement_total'
        total['fields'].update(description='Total ' + direction, total_direction=direction,
                               balance_column=str(money[name][0]['column_index']))
        try:
            total['fields']['balance'] = exact_amount(money[name][0]['expected_text'], currency)
        except ValueError as exc:
            total['issues'].append(str(exc))


# LOUPE_FINANCIAL_SANTANDER_BALANCE_STEP_AMOUNT: a payment amount printed with a misread separator
# ("2.571,151.00") is read digit for digit when it equals, exactly and in its column's direction, the step
# between the previous payment's printed running balance and its own (_balance_step_amount).
BALANCE_STEP_AMOUNT = _switch('LOUPE_FINANCIAL_SANTANDER_BALANCE_STEP_AMOUNT')
_SEPARATED_AMOUNT = re.compile(r'\$?\s*\d{1,3}(?:[.,]\d{3})*[.,]\d{2}')


def _balance_step_amount(item, previous_balance, money, currency):
    fields = item['fields']
    direction = fields['direction']
    cells = money['DEPOSITO' if direction == 'credit' else 'RETIRO']
    if previous_balance is None or fields.get('balance') is None or len(cells) != 1:
        return
    printed = cells[0]['expected_text'].strip()
    if not _SEPARATED_AMOUNT.fullmatch(printed):
        return
    amount = int(re.sub(r'\D', '', printed))
    step = int(fields['balance']) - int(previous_balance)
    if amount <= 0 or step != (amount if direction == 'credit' else -amount):
        return
    unreadable = [issue for issue in item['issues'] if 'as an amount' in issue]
    if len(unreadable) != len(item['issues']) or len(unreadable) != 1:
        return
    item['issues'] = []
    fields.update(amount_minor=str(amount), amount_basis='printed_balance_step')


# Whether a ruled row that prints the section's last payment and its TOTAL line
# together is split (``_split_merged_total``). Reverse in one place.
MERGED_TOTAL = True
_MONEY_LINE = re.compile(r'\$?\s*[\d,]+\.\d{2}')


def _merges_total(cells):
    """A dated row whose description cell ends in a line reading exactly TOTAL."""
    return bool(cells and re.match(DATE, norm(cells[0]['expected_text'].strip())) and any(
        len(lines) >= 2 and norm(lines[-1].strip()) == 'TOTAL'
        for lines in (c['expected_text'].split('\n') for c in cells)))


def _split_merged_total(cells, columns, last, currency):
    """``(payment cells, [(direction, total cell)])`` for a ruled row merging a payment with the TOTAL line, or None.

    The ruling stored both printed lines in one row of cells. A money cell of
    two lines gives its first line to the payment and its second to the TOTAL
    line. The payment's amount must come from such a two-line cell (exactly
    one of deposit or withdrawal); a one-line cell in the other amount column
    is then the TOTAL line's. A one-line balance cell is the payment's only
    when the previous payment's printed balance plus or minus this amount
    equals it exactly (the TOTAL line prints no balance). The description
    keeps every line but the last. Anything else is None (the row is held).
    """
    names = ('DEPOSITO', 'RETIRO', 'SALDO')
    payment, single, double = [], {n: [] for n in names}, {n: [] for n in names}
    for c in cells:
        lines = [line.strip() for line in c['expected_text'].split('\n')]
        rect = box(c)
        if rect and rect[0] >= box(columns['DEPOSITO'])[0] and all(_MONEY_LINE.fullmatch(line) for line in lines):
            name = min(names, key=lambda n: abs(rect[2] - box(columns[n])[2]))
            if len(lines) == 1:
                single[name].append(c)
            elif len(lines) == 2:
                double[name].append((dict(c, expected_text=lines[0]), dict(c, expected_text=lines[1])))
            else:
                return None
        elif len(lines) >= 2 and norm(lines[-1]) == 'TOTAL':
            payment.append(dict(c, expected_text='\n'.join(lines[:-1])))
        elif len(lines) == 1:
            payment.append(c)
        else:
            return None
    if any(len(single[n]) + len(double[n]) > 1 for n in names) or double['SALDO']:
        return None
    paid = [(n, d) for n, d in (('DEPOSITO', 'credit'), ('RETIRO', 'debit')) if double[n]]
    if len(paid) != 1 or len(single['SALDO']) != 1 or not last or last['fields'].get('balance') is None:
        return None
    name, direction = paid[0]
    try:
        amount = int(exact_amount(double[name][0][0]['expected_text'], currency))
        balance = int(exact_amount(single['SALDO'][0]['expected_text'], currency))
        previous = int(last['fields']['balance'])
    except ValueError:
        return None
    if previous + (amount if direction == 'credit' else -amount) != balance:
        return None
    totals = []
    for n, d in (('DEPOSITO', 'credit'), ('RETIRO', 'debit')):
        cell = double[n][0][1] if double[n] else single[n][0] if single[n] else None
        if cell is not None:
            totals.append((d, cell))
    return payment + [double[name][0][0], single['SALDO'][0]], totals


# Whether a section whose own closing line was not read takes its closing from
# the cover's balance summary (``_cover_closing``). Reverse in one place.
COVER_CLOSING = True
_MONEY_CELL = re.compile(r'\$?\s*\d{1,3}(?:,\d{3})*\.\d{2}')
_PERCENT_CELL = re.compile(r'-?\d{1,3}\.\d{2}\s*%')


def _cover_closing(rows, choice, currency):
    """The section's closing from the cover's balance summary when its SALDO FINAL line was not read.

    The cover prints one summary line per account: product, account number,
    the previous month's balance and share, and this month's balance and share.
    That line is taken only when it names this section's account number
    exactly, prints exactly two money values and two percentages, its previous
    month's balance equals the section's printed opening (SALDO FINAL DEL
    PERIODO ANTERIOR) and its current month's balance equals the printed running
    balance of the section's last movement: three printed facts agree. The
    value is printed on the statement and cited to its own cell. Anything else
    leaves the closing unread.
    """
    balances = [row for row in rows if row['kind'] == 'balance']
    openings = [row for row in balances if row['fields'].get('description') == 'Opening Balance']
    if any(row['fields'].get('description') == 'Closing Balance' for row in balances) or len(openings) != 1:
        return
    opening = openings[0]['fields'].get('balance')
    moves = [row for row in rows if row['kind'] in ('transaction', 'unresolved') and not row['excluded']]
    if opening is None:
        return
    if not moves and QUIET_COVER_CLOSING:
        # A quiet section: its printed TOTAL line reads zero deposits and zero withdrawals, exactly once
        # each, so the cover's current balance must equal its previous one and the section's opening.
        totals = [row for row in rows if row['kind'] == 'statement_total']
        directions = sorted(row['fields'].get('total_direction') or '' for row in totals)
        if directions != ['credit', 'debit'] or any(row['issues'] or row['fields'].get('balance') != '0' for row in totals):
            return
        last = opening
    elif not moves or moves[-1]['kind'] != 'transaction' or moves[-1]['fields'].get('balance') is None:
        return
    else:
        last = moves[-1]['fields']['balance']
    account = choice.get('account_reference') or ''
    found = []
    for row in rows:
        if row['kind'] != 'header':
            continue
        cells = row['source_cells']
        if not account or not any(_names_account(c['expected_text'], account) for c in cells):
            continue
        money = [c for c in cells if _MONEY_CELL.fullmatch(c['expected_text'].strip())]
        shares = [c for c in cells if _PERCENT_CELL.fullmatch(c['expected_text'].strip())]
        if len(money) != 2 or len(shares) != 2 or not all(box(c) for c in money):
            continue
        try:
            values = [exact_amount(c['expected_text'].replace('$', '').strip(), currency) for c in money]
        except ValueError:
            continue
        if values == [opening, last]:
            found.append((row, money[1], values[1]))
    if len(found) != 1:
        return
    row, cell, value = found[0]
    row.update(kind='balance', excluded=True)
    row['fields'].update(description='Closing Balance', balance=value, balance_column=str(cell['column_index']),
                         balance_basis='cover_balance_summary')


def _cover_opening(rows, choice, currency):
    """(fin-queue3) The section's opening from the cover's balance summary when the value of its SALDO FINAL DEL
    PERIODO ANTERIOR line was not read (05 MONETA SANTANDER MXN MAY 26, INVERSION CRECIENTE 66-50958129-0).

    The mirror of ``_cover_closing``: the cover line naming this section's account number exactly, printing
    exactly two money values and two percentages, whose current month's balance equals the section's printed
    closing and whose previous month's balance equals that closing less the section's printed deposit total plus
    its printed withdrawal total. Three printed facts agree; the value is cited to its own cover cell, and the
    unread label line stays as read (a heading line).
    """
    balances = [row for row in rows if row['kind'] == 'balance']
    openings = [row for row in balances if row['fields'].get('description') == 'Opening Balance']
    closings = [row for row in balances if row['fields'].get('description') == 'Closing Balance']
    if len(openings) != 1 or len(closings) != 1 or openings[0]['fields'].get('balance') is not None:
        return
    if closings[0]['issues'] or closings[0]['fields'].get('balance') is None:
        return
    totals = {d: [row for row in rows if row['kind'] == 'statement_total' and row['fields'].get('total_direction') == d]
              for d in ('credit', 'debit')}
    if any(len(found) != 1 or found[0]['issues'] or found[0]['fields'].get('balance') is None for found in totals.values()):
        return
    closing = int(closings[0]['fields']['balance'])
    previous = str(closing - int(totals['credit'][0]['fields']['balance']) + int(totals['debit'][0]['fields']['balance']))
    account = choice.get('account_reference') or ''
    found = []
    for row in rows:
        if row['kind'] != 'header' or not account:
            continue
        cells = row['source_cells']
        if not any(_names_account(c['expected_text'], account) for c in cells):
            continue
        money = [c for c in cells if _MONEY_CELL.fullmatch(c['expected_text'].strip())]
        shares = [c for c in cells if _PERCENT_CELL.fullmatch(c['expected_text'].strip())]
        if len(money) != 2 or len(shares) != 2 or not all(box(c) for c in money):
            continue
        try:
            values = [exact_amount(c['expected_text'].replace('$', '').strip(), currency) for c in money]
        except ValueError:
            continue
        if values == [previous, str(closing)]:
            found.append((row, money[0]))
    if len(found) != 1:
        return
    row, cell = found[0]
    label = openings[0]
    label.update(kind='header', excluded=True, issues=[])
    label['fields'] = dict(description=label['fields'].get('description'), balance_read_from=row['id'])
    row.update(kind='balance', excluded=True)
    row['fields'].update(description='Opening Balance', balance=previous, balance_column=str(cell['column_index']),
                         balance_basis='cover_balance_summary')


def _names_account(value, account):
    """A cover cell prints this account number: inside its text, or (OCR split it with a space) as the
    whole cell once its spaces are removed. Never a longer number containing it."""
    if re.search(r'(?<![\d-])' + re.escape(account) + r'(?![\d-])', value):
        return True
    return COVER_SPACED_ACCOUNT and re.sub(r'\s+', '', value) == account


def santander_no_activity_evidence(sources, choice, rows, currency):
    """Printed zero TOTAL line and equal SALDO FINAL lines prove a quiet section.

    Beyond the shared printed-control checks, the section's own lines must
    read, in printed order: the previous-period balance, the movement column
    heading, immediately the TOTAL line, then the period's final balance. Any
    dated line inside the section, or any line between the column heading and
    the TOTAL line, could be an unread payment and keeps the period held.
    """
    from services.financial.statement_printed_no_activity import zero_totals_evidence
    scopes = {(s['page_number'], s['table_index']): set(s['row_indices']) for s in choice.get('section_sources') or []}

    def guard():
        ordered = [(page, s, raw) for page in sorted({s['page_number'] for s in sources})
                   for s, raw in located_rows([s for s in sources if s['page_number'] == page])
                   if raw['row_index'] in scopes.get((page, s['table_index']), set())]
        roles = []
        for page, s, raw in ordered:
            joined = norm(text(raw))
            if re.search(DATE, joined):
                return ('dated_line', 'A dated line was read inside this account section. Check it before confirming that the section contains no transactions.')
            if 'SALDO FINAL DEL PERIODO' in joined:
                roles.append(('opening' if 'ANTERIOR' in joined else 'closing', page))
            elif 'FECHA' in joined and all(label in joined for label in ('DEPOSITO', 'RETIRO', 'SALDO')):
                roles.append(('columns', page))
            elif QUIET_HEADING and 'FECHA' in joined and all(label in joined for label in ('DEPOSITO', 'RETIRO')):
                roles.append(('columns', page))  # read without SALDO; only the TOTAL line may follow it
            elif joined.startswith('TOTAL'):
                roles.append(('total', page))
            elif roles and roles[-1][0] == 'columns':
                return ('rows_between_heading_and_total', 'Text was read between the movement column heading and the TOTAL line. Check it before confirming that the section contains no transactions.')
        sequence = [role for role, _ in roles]
        if (QUIET_COVER_CLOSING and sequence == ['opening', 'columns', 'total'] and any(
                row['kind'] == 'balance' and row['fields'].get('balance_basis') == 'cover_balance_summary' for row in rows)):
            # The section's SALDO FINAL line was not read; its closing is the cover summary's, which prints
            # the section's opening as last month's and this month's balance (_cover_closing).
            sequence = sequence + ['closing']
        if sequence != ['opening', 'columns', 'total', 'closing'] or roles[1][1] != roles[2][1]:
            return ('section_lines', 'The balance, column heading and TOTAL lines of this account section were not read in their printed order on one page. Check the page before confirming that it contains no transactions.')
        return None

    return zero_totals_evidence(rows, choice, currency, family='santander-mexico', guard=guard)
