"""Kapital product sections, scoped by CLABE, currency and printed period.

The changing header Numero is a statement reference. Each product's CLABE is
the account reference. Summary totals and tax/information pages are not payments.
"""
import re
from datetime import date
from services.financial.pdf_candidates import _digest
from services.financial.statement_import_bbva import box, norm, text
from services.financial.statement_import_proposal import exact_amount

LAYOUT = 'kapital-mexico-product-statement'
PRODUCT = re.compile(r'SERVICIO EMPRESARIAL FX(?: USD)? KAPITAL\b')
INTERCAM_PRODUCT = re.compile(r'SERVICIO EMPRESARIAL FX(?: USD)?\s+\d{3}-\d+-\d{3}-\d\b')


def kapital_information_kind(source, *, institution='Kapital', product=PRODUCT):
    joined='\n'.join(norm(text(r)) for r in source['rows'])
    if institution.upper() not in joined or product.search(joined):return None
    if all(label in joined for label in ('CONCEPTO','DEPOSITOS','RETIROS','SALDO')):return None
    if 'ABREVIATURAS CHEQUES' in joined and 'INSTRUMENTOS MONETARIOS' in joined:return 'glossary'
    if 'FOLIO DEL CFDI:' in joined and 'CADENA ORIGINAL DEL COMPLEMENTO DE CERTIFICACION DIGITAL' in joined:return 'tax_certificate'
    if 'INFORMACION RELEVANTE DE TU ESTADO DE CUENTA' in joined:return 'statement_information'
    return None


def _context(items, *, institution='Kapital'):
    rows = [r for s in items for r in s['rows']]
    joined = '\n'.join(norm(text(r)) for r in rows)
    if institution == 'Kapital' and 'KAPITAL' not in joined:
        return None
    cycles = set(re.findall(r'PERIODO DEL (\d{4}-\d{2}-\d{2}) AL (\d{4}-\d{2}-\d{2})', joined))
    numbers, clients, rfcs = set(), set(), set()
    for row in rows:
        for i,c in enumerate(row['cells'][:-1]):
            value=row['cells'][i+1]['expected_text'].strip()
            label=norm(c['expected_text'])
            if label == 'NUMERO' and value.isdigit(): numbers.add(value)
            if label == 'CLIENTE' and value.isdigit(): clients.add(value)
            if re.sub(r'[^A-Z]','',label) == 'RFC' and re.fullmatch(r'[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}',value): rfcs.add(value)
    if len(cycles)!=1 or len(numbers)!=1 or len(clients)!=1 or len(rfcs)!=1:
        return None
    start,end=next(iter(cycles))
    try:
        if not 0 <= (date.fromisoformat(end)-date.fromisoformat(start)).days <= 62: return None
    except ValueError: return None
    return (next(iter(numbers)),next(iter(clients)),next(iter(rfcs)),start,end)


def kapital_catalog(sources, *, institution='Kapital', product=PRODUCT, layout=LAYOUT):
    pages={}
    for s in sources: pages.setdefault(s['page_number'],[]).append(s)
    contexts={p:_context(items, institution=institution) for p,items in pages.items()}
    if institution == 'Intercam':
        # Only a printed Intercam product/CLABE establishes issuer identity.
        # Counterparty mentions of a bank cannot identify the statement bank.
        established={contexts[p] for p,items in pages.items() if contexts[p] and any(
            product.search(norm(text(r))) and re.search(r'\bCLABE\s*136\d{15}\b', norm(text(r)))
            for s in items for r in s['rows'])}
        contexts={p:c if c in established else None for p,c in contexts.items()}
    holders={}
    for p,items in pages.items():
        context=contexts[p]
        if not context: continue
        joined='\n'.join(norm(text(r)) for s in items for r in s['rows'])
        if not any(label in joined for label in ('PERSONA MORAL','PERSONA FISICA')):continue
        # First text in the left address block; the header is on the right.
        names=[c for s in items for r in s['rows'] for c in r['cells'] if box(c)
            and (size:=(c.get('locator') or {}).get('page_size'))
            and box(c)[0]<size[0]*.2 and size[1]*.12<=box(c)[1]<size[1]*.25
            and re.fullmatch(r'[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ &.,]{2,180}',c['expected_text'].strip())
            and not product.match(norm(c['expected_text']))]
        if names: holders.setdefault(context,set()).add(min(names,key=lambda c:box(c)[1])['expected_text'].strip())
    groups,handled=[],set()
    previous=None
    for page,items in sorted(pages.items()):
        context=contexts[page]
        if not context: previous=None; continue
        located=[(s,r) for s in items for r in s['rows'] if any(box(c) for c in r['cells'])]
        headings=[]
        for s,r in located:
            if product.search(norm(text(r))) and (m:=re.search(r'\bCLABE\s*(\d{18})\b',norm(text(r)))):
                headings.append((min(box(c)[1] for c in r['cells'] if box(c)),m[1],s,r))
        headings.sort(key=lambda v:v[0])
        # A continued payment table can precede the next product on a page.
        if previous and previous[0]==context and previous[1]==page-1:
            cutoff=headings[0][0] if headings else float('inf')
            pre=[(s,r) for s,r in located if max(box(c)[3] for c in r['cells'] if box(c))<cutoff]
            if any(all(k in norm(text(r)) for k in ('CONCEPTO','DEPOSITOS','RETIROS','SALDO')) for _,r in pre):
                target=previous[2]
                for s in items:
                    indices=[r['row_index'] for a,r in pre if a is s]
                    if indices: target['section_sources'].append(dict(page_number=page,table_index=s['table_index'],row_indices=indices))
                target['sources'].extend(dict(page_number=page,table_index=s['table_index'],source_revision=s['source_revision']) for s in items)
                target['page_numbers'].append(page)
                previous=(context,page,target)
                handled.update((page,s['table_index']) for s in items)
        recognised = 0
        for index,(top,clabe,_,_) in enumerate(headings):
            bottom=headings[index+1][0] if index+1<len(headings) else float('inf')
            scoped=[(s,r) for s,r in located if top<=min(box(c)[1] for c in r['cells'] if box(c))<bottom]
            currencies=set()
            for _,r in scoped:
                for i,c in enumerate(r['cells'][:-1]):
                    if norm(c['expected_text'])=='MONEDA':
                        value=norm(r['cells'][i+1]['expected_text'])
                        if value in ('MN','M.N.','MXN','USD'): currencies.add('MXN' if value in ('MN','M.N.') else value)
            if len(currencies)!=1: continue
            recognised += 1
            currency=next(iter(currencies))
            identity=dict(layout_id=layout,institution=institution,account_reference=clabe,currency=currency,
                period_start=context[3],period_end=context[4])
            group=dict(id=_digest(identity),**identity,account_type='checking',
                holder=next(iter(holders[context])) if len(holders.get(context,set()))==1 else '',
                statement_reference=context[0],customer_reference=context[1],currency_source='printed_account_section',
                sources=[dict(page_number=page,table_index=s['table_index'],source_revision=s['source_revision']) for s in items],
                page_numbers=[page],section_sources=[dict(page_number=page,table_index=s['table_index'],
                    row_indices=[r['row_index'] for a,r in scoped if a is s]) for s in items if any(a is s for a,_ in scoped)])
            groups.append(group)
            previous=(context,page,group)
            handled.update((page,s['table_index']) for s in items)
        if recognised != len(headings):
            # Another unreadable product on this page remains unassigned;
            # recognising its neighbour must not conceal that missing scope.
            handled.difference_update((page,s['table_index']) for s in items)
            previous = None
    # Retain cover header cells in each currency review, without expanding the
    # account-section overlap boundary to the common header or other products.
    by_context={}
    for p,c in contexts.items():
        if c and c in holders: by_context.setdefault(c,p)
    for group in groups:
        c=contexts[group['page_numbers'][0]];first=by_context.get(c)
        if first and first not in group['page_numbers']:
            group['sources']=[dict(page_number=first,table_index=s['table_index'],source_revision=s['source_revision']) for s in pages[first]]+group['sources']
            group['page_numbers']=sorted(set([first]+group['page_numbers']))
    return groups,handled


def _amount(value,currency):
    value=value.strip()
    # MN is an explicit peso marker in this recognised Mexican product.
    if re.search(r'\s+(?:MN|M\.N\.)$',value):
        value=re.sub(r'\s+(?:MN|M\.N\.)$',' MXN',value)
    suffix=re.fullmatch(r'(.+)\s+(MXN|USD)',value)
    if suffix:
        if suffix[2]!=currency:
            raise ValueError(f'The printed amount is {suffix[2]}, but this review uses {currency}. Check the currency for this account section.')
        value=suffix[1]
    negative=value.endswith('-')
    if negative: value=value[:-1].strip()
    amount=exact_amount(value,currency)
    return str(-int(amount)) if negative else amount


def _day(value,choice):
    if not re.fullmatch(r'\d{1,2}',value): return None
    start,end=map(date.fromisoformat,(choice['period_start'],choice['period_end']))
    found=[]
    for year in range(start.year,end.year+1):
        for month in range(1,13):
            try: candidate=date(year,month,int(value))
            except ValueError: continue
            if start<=candidate<=end: found.append(candidate.isoformat())
    return found[0] if len(found)==1 else None


def propose_kapital_statement(sources,currency,choice):
    product = INTERCAM_PRODUCT if choice.get('layout_id') == 'intercam-mexico-product-statement' else PRODUCT
    scopes={(s['page_number'],s['table_index']):set(s['row_indices']) for s in choice['section_sources']}
    result=[];columns=None;last=None;active_page=None
    # Drawn tables and outside text have separate indexes. Read their rows in
    # visual order so a table is not followed by the header above it.
    from services.financial.statement_import_santander import located_rows
    ordered=[(s,raw) for page in sorted({s['page_number'] for s in sources})
             for s,raw in located_rows([s for s in sources if s['page_number']==page])]
    for s,raw in ordered:
        if s['page_number']!=active_page: columns=None;last=None;active_page=s['page_number']
        cells=raw['cells'];item=dict(id=f"{s['page_number']}:{s['table_index']}:{raw['row_index']}",
            page_number=s['page_number'],table_index=s['table_index'],row_index=raw['row_index'],
            source_revision=s['source_revision'],source_cells=cells,fields={},issues=[],excluded=True,kind='header')
        result.append(item)
        if raw['row_index'] not in scopes.get((s['page_number'],s['table_index']),set()):continue
        labels={norm(c['expected_text']):c for c in cells}
        joined=norm(text(raw))
        if product.search(joined):columns=None;last=None
        names=('CONCEPTO','DEPOSITOS','RETIROS','SALDO')
        if all(n in labels and box(labels[n]) for n in names):
            columns={n:labels[n] for n in names};last=None;continue
        if columns is None:
            role=next((role for label,role in [('SALDO INICIAL','opening'),('SALDO FINAL','closing'),('+ DEPOSITOS','credit'),('- RETIROS','debit')] if label in labels),None)
            if role:
                label=next(c for c in cells if norm(c['expected_text']) in ('SALDO INICIAL','SALDO FINAL','+ DEPOSITOS','- RETIROS'))
                i=cells.index(label);following=cells[i+1:i+2]
                if not following or not box(label) or box(label)[0]>(label['locator']['page_size'][0]*.4):continue
                amount=following[0]
                item['kind']='balance' if role in ('opening','closing') else 'statement_total'
                item['fields']=dict(description=role.title()+' Balance' if item['kind']=='balance' else 'Total '+role,balance_column=str(amount['column_index']))
                if item['kind']=='statement_total':item['fields']['total_direction']=role
                try:item['fields']['balance']=_amount(amount['expected_text'],currency)
                except ValueError as exc:item['issues'].append(str(exc))
            elif (len(cells)>=3 and re.fullmatch(r'\d{1,2}',cells[0]['expected_text'].strip())
                and re.fullmatch(r'\d{4,}',cells[1]['expected_text'].strip())
                and any(re.fullmatch(r'[\d,]+\.\d{2}-?',c['expected_text'].strip()) for c in cells[2:])):
                # A missed header must not hide an otherwise visible
                # payment or turn it into a balances-only statement.
                item.update(kind='unresolved',excluded=False)
                item['fields'].update(description=' '.join(c['expected_text'].strip() for c in cells[2:]),
                    bank_reference=cells[1]['expected_text'].strip())
                parsed=_day(cells[0]['expected_text'].strip(),choice)
                if parsed:item['fields']['date']=parsed
                item['issues'].append('This looks like a payment, but its deposit and withdrawal headings were not read. Compare the row with the PDF and choose the amount and direction.')
            continue
        if joined.startswith(('TOTAL','HOJA ','ESTE DOCUMENTO')):
            columns=None;last=None;continue
        # Located right-aligned amounts are assigned to the nearest money
        # column. The day and folio are never interpreted as amounts.
        money={n:[] for n in names[1:]};other=[]
        for cell in cells:
            rect=box(cell)
            if rect and (rect[0]>=box(columns['DEPOSITOS'])[0]-20000 or
                (rect[2]>=box(columns['DEPOSITOS'])[0] and re.fullmatch(r'[\d,]+\.\d{2}-?',cell['expected_text'].strip()))):
                near=min(names[1:],key=lambda n:abs(rect[2]-box(columns[n])[2]))
                money[near].append(cell)
            else:other.append(cell)
        day=other[0]['expected_text'].strip() if other else ''
        dated=bool(re.fullmatch(r'\d{1,2}',day))
        if not dated and not any(money.values()):
            if last and other:
                last['fields']['description']+=' '+text(raw)
                last.setdefault('continuation_sources',[]).append(dict(page_number=s['page_number'],table_index=s['table_index'],row_index=raw['row_index'],source_cells=cells))
                item['fields']['parent_transaction_id']=last['id']
            continue
        item.update(kind='transaction',excluded=False);fields=item['fields'];last=item
        fields['description']=' '.join(c['expected_text'].strip() for c in other[2:])
        if other:fields['date_column']=str(other[0]['column_index'])
        if len(other)>1:fields['bank_reference']=other[1]['expected_text'].strip()
        if len(other)>2:fields['description_column']=str(other[2]['column_index'])
        parsed=_day(day,choice)
        if parsed:fields['date']=parsed
        else:item['issues'].append('Check the printed day against this statement period.')
        directions=[(n,d) for n,d in [('DEPOSITOS','credit'),('RETIROS','debit')] if money[n]]
        if len(directions)!=1:item['issues'].append('Check which deposit or withdrawal column contains this payment.')
        else:
            n,direction=directions[0];fields['direction']=direction
            if len(money[n])!=1:item['issues'].append('Check the payment amount in the PDF.')
            else:
                amount=money[n][0];fields[direction+'_column']=str(amount['column_index'])
                try:
                    value=_amount(amount['expected_text'],currency)
                    if int(value)<=0:raise ValueError('A payment amount must be positive; its column supplies the direction.')
                    fields['amount_minor']=value
                except ValueError as exc:item['issues'].append(str(exc))
        if len(money['SALDO'])==1:
            balance=money['SALDO'][0];fields['balance_column']=str(balance['column_index'])
            try:fields['balance']=_amount(balance['expected_text'],currency)
            except ValueError as exc:item['issues'].append(str(exc))
        if not fields['description']:item['issues'].append('Check the payment description.')
    return dict(rows=result,issues=[])
