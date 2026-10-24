"""Santander Mexico account-scoped movement tables, native or positioned OCR.

Printed account/period headings define scope. Amount columns supply direction;
summary totals, advertisements and fiscal lines never create payments.
"""
import re
from datetime import date
from services.financial.pdf_candidates import _digest
from services.financial.statement_import_bbva import box, norm, text, MONTHS
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


def located_rows(items):
    return sorted([(s, r) for s in items for r in s['rows'] if any(box(c) for c in r['cells'])],
        key=lambda pair: (min(box(c)[1] for c in pair[1]['cells'] if box(c)), pair[0]['table_index'], pair[1]['row_index']))


POSITIONLESS_TABLES = _switch('LOUPE_FINANCIAL_SANTANDER_POSITIONLESS_TABLES')


def _positionless(source):
    """A table whose extraction kept only its outline (no cell positions): the rows of a native page's
    ruled table, in printed order, with each cell's column number. Its outline must be located."""
    rect = (source.get('locator') or {}).get('rect')
    return (source.get('geometry_source') == 'table_rectangle_only' and isinstance(rect, list) and len(rect) == 4
            and all(type(v) is int for v in rect) and not any(box(c) for r in source['rows'] for c in r['cells']))


def section_rows(items):
    """``located_rows`` plus (POSITIONLESS_TABLES) the rows of positionless tables, placed at their table's
    top in their stored order. Used only by this reader (other families keep ``located_rows``)."""
    rows = located_rows(items)
    if not POSITIONLESS_TABLES:
        return rows
    extra = [(s, r) for s in items if _positionless(s) for r in s['rows']]
    if not extra:
        return rows
    def key(pair):
        source, row = pair
        if any(box(c) for c in row['cells']):
            return (min(box(c)[1] for c in row['cells'] if box(c)), 0, source['table_index'], row['row_index'])
        return (source['locator']['rect'][1], 1, source['table_index'], row['row_index'])
    return sorted(rows + extra, key=key)


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
                        code = {'MONEDA NACIONAL':'MXN','PESOS':'MXN','DOLARES':'USD','DOLARES AMERICANOS':'USD','USD':'USD','MXN':'MXN'}.get(value)
                        if code:meta['currencies'].add(code)
                    if 'CODIGO DE CLIENTE NO' in norm(c['expected_text']) and i > 0:
                        holder = cells[i-1]['expected_text'].strip()
                        if holder and len(holder) < 200:meta['holders'].add(holder)
    groups, handled = {}, set()
    active = None
    previous_page = None

    def attach(group, section, page, meta):
        for source in pages[page]:
            indices = [row['row_index'] for origin, row in section if origin is source]
            if indices:
                group['section_sources'].append(dict(page_number=page,
                    table_index=source['table_index'], row_indices=indices))
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
        meta = known[key]; located = section_rows(items)
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
    result=[];columns=None;last=None;active_page=None;indexed=None
    for page in sorted({s['page_number'] for s in sources}):
        for s,raw in section_rows([s for s in sources if s['page_number']==page]):
            cells=raw['cells'];joined=norm(text(raw))
            item=dict(id=f"{page}:{s['table_index']}:{raw['row_index']}",page_number=page,table_index=s['table_index'],row_index=raw['row_index'],source_revision=s['source_revision'],source_cells=cells,fields={},issues=[],excluded=True,kind='header')
            result.append(item)
            if page!=active_page:columns=None;last=None;active_page=page;indexed=None
            if raw['row_index'] not in scopes.get((page,s['table_index']),set()):continue
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
                columns={n:labels[n] for n in money_names};last=None;indexed=None;continue
            if (POSITIONLESS_TABLES and 'FECHA' in joined and _positionless(s) and all(n in labels for n in money_names)
                    and len({labels[n]['column_index'] for n in money_names}) == 3):
                # A positionless table: its own column heading numbers the money columns.
                columns={n:labels[n] for n in money_names};last=None
                indexed=(s['page_number'],s['table_index'],{labels[n]['column_index']:n for n in money_names});continue
            if columns is not None and indexed is not None and (page,s['table_index'])!=indexed[:2]:
                # Column numbers belong to their own table only.
                columns=None;last=None;indexed=None
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
            if indexed is not None:
                unreadable=False
                for c in cells:
                    name=indexed[2].get(c['column_index'])
                    if name is None:
                        other.append(c)
                    elif re.fullmatch(r'\$?\s*[\d,.]+\.\d{2}-?',c['expected_text'].strip()):
                        money[name].append(c)
                    elif name!='SALDO' or not all(re.fullmatch(r'\$?\s*[\d,.]+\.\d{2}-?',line.strip()) for line in c['expected_text'].split('\n')):
                        unreadable=True
                    # A running balance cell that took the following lines' balances too is left unread.
                if unreadable:
                    item.update(kind='unresolved',excluded=False)
                    item['fields']['description']=text(raw)
                    item['issues'].append('Check the printed amount for this payment beside the PDF.')
                    continue
                cells=[c for c in cells if c in other or any(c in v for v in money.values())]
            for c in ([] if indexed is not None else cells):
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
    if COVER_CLOSING:
        _cover_closing(result, choice, currency)
    return dict(rows=result,issues=[])


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
                   for s, raw in section_rows([s for s in sources if s['page_number'] == page])
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
