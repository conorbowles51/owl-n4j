"""Santander Mexico account-scoped movement tables, native or positioned OCR.

Printed account/period headings define scope. Amount columns supply direction;
summary totals, advertisements and fiscal lines never create payments.
"""
import re
from datetime import date
from services.financial.pdf_candidates import _digest
from services.financial.statement_import_bbva import box, norm, text, MONTHS
from services.financial.statement_import_proposal import exact_amount

LAYOUT = 'santander-mexico-movements'
ACCOUNT = re.compile(r'(?P<product>CUENTA SANTANDER [A-Z ]+?|INVERSION CRECIENTE|SUPER CUENTA [A-Z ]+?)\s*(?P<number>\d{2}-\d{8}-\d)\b')
DATE = r'\d{2}-[A-Z]{3}-\d{4}'


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


def santander_catalog(sources):
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
    for p, items in sorted(pages.items()):
        key = contexts.get(p)
        if not key:continue
        meta = known[key]; located = located_rows(items)
        anchors = [(i,s,r) for i,(s,r) in enumerate(located) if re.search(r'DETALLES? DE MOVIMIENTOS', norm(text(r)))]
        for n,(index,_,heading) in enumerate(anchors):
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
            for s in items:
                indices=[r['row_index'] for a,r in section if a is s]
                if indices:group['section_sources'].append(dict(page_number=p,table_index=s['table_index'],row_indices=indices))
            # Cover supplies holder, currency and RFC evidence; only movement
            # section addresses below participate in this account's payments.
            for page in sorted(set([p,meta['pages'][0]])):
                if page not in group['page_numbers']:
                    group['page_numbers'].append(page)
                    group['sources'].extend(dict(page_number=page,table_index=s['table_index'],source_revision=s['source_revision']) for s in pages[page])
                    handled.update((page,s['table_index']) for s in pages[page])
    return list(groups.values()), handled


def propose_santander_statement(sources,currency,choice):
    scopes={(s['page_number'],s['table_index']):set(s['row_indices']) for s in choice['section_sources']}
    result=[];columns=None;last=None;active_page=None
    for page in sorted({s['page_number'] for s in sources}):
        for s,raw in located_rows([s for s in sources if s['page_number']==page]):
            cells=raw['cells'];joined=norm(text(raw))
            item=dict(id=f"{page}:{s['table_index']}:{raw['row_index']}",page_number=page,table_index=s['table_index'],row_index=raw['row_index'],source_revision=s['source_revision'],source_cells=cells,fields={},issues=[],excluded=True,kind='header')
            result.append(item)
            if page!=active_page:columns=None;last=None;active_page=page
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
                columns={n:labels[n] for n in money_names};last=None;continue
            if columns is None:continue
            money={n:[] for n in money_names};other=[]
            for c in cells:
                rect=box(c)
                if rect and rect[2] >= box(columns['DEPOSITO'])[0] and re.fullmatch(r'\$?\s*[\d,]+\.\d{2}-?',c['expected_text'].strip()):
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
            m=re.match(r'^('+DATE+r')[\s|]*(\d{7})(?:[\s|/]*)(.*)$',prefix,re.S)
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
    return dict(rows=result,issues=[])
