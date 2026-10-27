"""Kapital product sections, scoped by CLABE, currency and printed period.

The changing header Numero is a statement reference. Each product's CLABE is
the account reference. Summary totals and tax/information pages are not payments.
"""
import os
import re
from datetime import date
from services.financial.pdf_candidates import _digest
from services.financial.statement_import_bbva import box, norm, text
from services.financial.statement_import_proposal import exact_amount
from services.financial.statement_engine import addressee_name

LAYOUT = 'kapital-mexico-product-statement'
# OCR can drop the final letter where the heading meets its account number ("KAPITA 123-...").
PRODUCT = re.compile(r'SERVICIO EMPRESARIAL FX(?: USD)? KAPITAL?\b')
INTERCAM_PRODUCT = re.compile(r'SERVICIO EMPRESARIAL FX(?: USD)?\s+\d{3}-\d+-\d{3}-\d\b')


def _switch(name):
    return os.environ.get(name, '1').strip().lower() not in ('0', 'false', 'no', 'off')


# The scan reads one stray mark after a printed amount where the cell meets the table's vertical rule
# ('6,300,000.00)', '6,616,985.42,', '61,268,306.15?'). An amount printed whole (thousands groups, two decimals,
# an optional trailing minus) followed by exactly one such mark is that amount; the reconciliation still decides.
# Off: such a value is unreadable and the period waits for a person.
AMOUNT_NOISE = _switch('LOUPE_FINANCIAL_KAPITAL_AMOUNT_NOISE')
_NOISE_TAIL = re.compile(r'^(\d{1,3}(?:,\d{3})*\.\d{2}-?)[),;?|]$')
# The scan can also set a space before a thousands comma ('2,506 ,338.78)', '7,531 ,506.44)', '2,921 ,063.67;').
# A space between a digit and a comma that three digits follow is that comma; the whole amount pattern above must
# still match. Off: such a value is unreadable and the period waits for a person.
AMOUNT_GROUP_SPACE = _switch('LOUPE_FINANCIAL_KAPITAL_AMOUNT_GROUP_SPACE')
_GROUP_SPACE = re.compile(r'(?<=\d)\s+,(?=\d{3}(?:[,.]|$))')
# A movement heading read only in part on one page (the scan lost some of its words at the foot of the cover
# page: 'CONCEPTO DEPOSITOS' alone) takes the missing columns from the complete heading the same product section
# prints on its other pages, when every heading word read on this page sits where that complete heading prints
# it (the layout's columns do not move between pages). Off: the page's payments wait for a person.
HEADING_FROM_SECTION = _switch('LOUPE_FINANCIAL_KAPITAL_HEADING_FROM_SECTION')
# Millipoints a heading word may sit from the complete heading's printed position (3 points).
_HEADING_TOLERANCE = 3000
_HEADING_NAMES = ('CONCEPTO', 'DEPOSITOS', 'RETIROS', 'SALDO')
# A movement line whose DIA cell the scan did not read (fin-queue lesson 15, 05 ECOTERRA KAPITAL MAY 24; 01 MONETA
# KAPITAL ENE 26) has its folio, or its concepto, in the day's place: the folio became the day and the concepto's
# first line the bank reference, so the concepto kept only its wrapped lines. Each slot now takes only a cell of
# its own shape (day: 1-2 digits, folio: 4+ digits, the rest the concepto); the day stays unread and the line still
# waits for it. Off: cells are taken by position.
MISSING_DAY_CELL = _switch('LOUPE_FINANCIAL_KAPITAL_MISSING_DAY_CELL')
# (fin-queue3 K3, 06 ARRENDO KAPITAL JUN 26 USD) A section's only movement heading read with a word cut short or
# carrying a mark ('CONCEPTO DEPOSITOS RETIRO. SALDO') is that heading when all four words are read on the line,
# located, in the printed order (CONCEPTO, DEPOSITOS, RETIROS, SALDO left to right). Off: the section's lines wait
# for a person as payments whose headings were not read.
HEADING_WORD_MARKS = _switch('LOUPE_FINANCIAL_KAPITAL_HEADING_WORD_MARKS')
# (fin-queue3 K6, 06 MONETA KAPITAL MXN JUN 25) The scan read the client number '49499208' as '19499208' on Hoja
# 2-3, so those pages printed another statement's header and the movement table on them was assigned to no
# statement. Pages printing the same statement number (Numero), R.F.C. and period are one statement's pages when
# their client numbers differ in exactly one digit (same length); they take the first such page's header. Off:
# the pages stay unassigned and the period waits for a person.
CLIENT_ONE_DIGIT = _switch('LOUPE_FINANCIAL_KAPITAL_CLIENT_ONE_DIGIT')


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


def _one_digit_apart(a, b):
    return len(a) == len(b) and sum(x != y for x, y in zip(a, b)) == 1


def _client_misreads(contexts):
    """Each page's header, a client number read one digit apart from the first page printing the same statement
    number, R.F.C. and period taking that page's header."""
    first = {}
    for page in sorted(p for p, c in contexts.items() if c):
        first.setdefault((contexts[page][0],) + contexts[page][2:], contexts[page])
    out = {}
    for page, context in contexts.items():
        base = first.get((context[0],) + context[2:]) if context else None
        out[page] = base if base and base != context and _one_digit_apart(base[1], context[1]) else context
    return out


def kapital_catalog(sources, *, institution='Kapital', product=PRODUCT, layout=LAYOUT):
    pages={}
    for s in sources: pages.setdefault(s['page_number'],[]).append(s)
    contexts={p:_context(items, institution=institution) for p,items in pages.items()}
    if CLIENT_ONE_DIGIT:
        contexts=_client_misreads(contexts)
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
        # The holder is the first line of the left address block (the header is on the right): the
        # general addressee rule, so a printed name may hold figures and an address line is never taken.
        cells=sorted((c for s in items for r in s['rows'] for c in r['cells'] if box(c)
            and (size:=(c.get('locator') or {}).get('page_size'))
            and box(c)[0]<size[0]*.2 and size[1]*.12<=box(c)[1]<size[1]*.25
            and c['expected_text'].strip() and not product.match(norm(c['expected_text']))),
            key=lambda c:(box(c)[1],box(c)[0]))
        lines=[]
        for c in cells:
            if lines and box(c)[1]-lines[-1][0]<(box(c)[3]-box(c)[1])/2: lines[-1][1].append(c['expected_text'].strip())
            else: lines.append((box(c)[1],[c['expected_text'].strip()]))
        name=addressee_name([' '.join(words) for _,words in lines])
        # A cover page whose first line reads as no name gives none; two cover pages disagreeing give none.
        if lines: holders.setdefault(context,set())
        if name: holders[context].add(name)
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
            # The product's currency is the first Moneda line under its own heading; a later product on
            # the page (an investment line) prints its own Moneda further down.
            printed=[]
            for _,r in sorted(scoped,key=lambda item:min(box(c)[1] for c in item[1]['cells'] if box(c))):
                for i,c in enumerate(r['cells'][:-1]):
                    if norm(c['expected_text'])=='MONEDA':
                        printed.append((norm(r['cells'][i+1]['expected_text']),min(box(c)[1] for c in r['cells'] if box(c))))
            if len(printed)>1:
                # The section ends where the next product prints its own currency line.
                scoped=[(s,r) for s,r in scoped if min(box(c)[1] for c in r['cells'] if box(c))<printed[1][1]]
            printed=[value for value,_ in printed]
            currencies={'MXN' if printed[0] in ('MN','M.N.') else printed[0]} if printed and printed[0] in ('MN','M.N.','MXN','USD') else set()
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
    if AMOUNT_GROUP_SPACE:
        value=_GROUP_SPACE.sub(',',value)
    if AMOUNT_NOISE and (noise:=_NOISE_TAIL.fullmatch(value)):
        value=noise[1]
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


def _section_heading(ordered, scopes):
    """The complete movement heading (all four words, located) printed in this product section, as
    {word: cell}, when every complete heading it prints sits at the same positions; else None."""
    found = []
    for s, raw in ordered:
        if raw['row_index'] not in scopes.get((s['page_number'], s['table_index']), set()):
            continue
        labels = {norm(c['expected_text']): c for c in raw['cells']}
        if all(n in labels and box(labels[n]) for n in _HEADING_NAMES):
            found.append({n: labels[n] for n in _HEADING_NAMES})
    if not found:
        return None
    first = found[0]
    for other in found[1:]:
        if any(abs(box(other[n])[0] - box(first[n])[0]) > _HEADING_TOLERANCE
               or abs(box(other[n])[2] - box(first[n])[2]) > _HEADING_TOLERANCE for n in _HEADING_NAMES):
            return None
    return first


# A heading word read without its final letter ('RETIRO' under the 'RETIROS' column).
_HEADING_SHORT = {'RETIRO': 'RETIROS', 'DEPOSITO': 'DEPOSITOS'}


def _heading_words(cells):
    """{heading word: cell} of a line printing all four movement heading words in order, each read whole, cut
    short by its final letter or followed by one mark; None otherwise."""
    read = {}
    for cell in cells:
        word = norm(cell['expected_text']).rstrip('.,;:')
        name = _HEADING_SHORT.get(word, word)
        if name in _HEADING_NAMES and box(cell):
            if name in read:
                return None
            read[name] = cell
    if len(read) != len(_HEADING_NAMES):
        return None
    lefts = [box(read[n])[0] for n in _HEADING_NAMES]
    return read if lefts == sorted(lefts) and len(set(lefts)) == len(lefts) else None


def _completed_heading(labels, template):
    """A partly read movement heading completed from the section's complete heading, or None: it must read
    CONCEPTO and at least one amount heading, each at the complete heading's printed position, on a page of
    the same size, and no other word in the amount columns' area."""
    if template is None:
        return None
    read = {}
    for word, cell in labels.items():
        name = _HEADING_SHORT.get(word, word)
        if name in _HEADING_NAMES and box(cell):
            read[name] = cell
        elif box(cell) and box(cell)[0] >= box(template['DEPOSITOS'])[0] - _HEADING_TOLERANCE:
            # Another word read in the amount columns' area: not the heading as printed elsewhere.
            return None
    if 'CONCEPTO' not in read or len(read) < 2:
        return None
    for n, cell in read.items():
        here, there = box(cell), box(template[n])
        # The word's box keeps one printed edge of the complete heading's (a word read short loses the other)
        # and overlaps it.
        if ((cell.get('locator') or {}).get('page_size') != (template[n].get('locator') or {}).get('page_size')
                or min(abs(here[0] - there[0]), abs(here[2] - there[2])) > _HEADING_TOLERANCE
                or min(here[2], there[2]) <= max(here[0], there[0])):
            return None
    return {n: read.get(n) or template[n] for n in _HEADING_NAMES}


def propose_kapital_statement(sources,currency,choice):
    product = INTERCAM_PRODUCT if choice.get('layout_id') == 'intercam-mexico-product-statement' else PRODUCT
    scopes={(s['page_number'],s['table_index']):set(s['row_indices']) for s in choice['section_sources']}
    result=[];columns=None;last=None;active_page=None
    # Drawn tables and outside text have separate indexes. Read their rows in
    # visual order so a table is not followed by the header above it.
    from services.financial.statement_import_santander import located_rows
    ordered=[(s,raw) for page in sorted({s['page_number'] for s in sources})
             for s,raw in located_rows([s for s in sources if s['page_number']==page])]
    template=_section_heading(ordered,scopes) if HEADING_FROM_SECTION else None
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
        if HEADING_WORD_MARKS and (marked:=_heading_words(cells)):
            columns=marked;last=None;continue
        if HEADING_FROM_SECTION and (completed:=_completed_heading(labels,template)):
            columns=completed;last=None;continue
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
        if MISSING_DAY_CELL and other and not dated and (re.fullmatch(r'\d{4,}',day) or re.search(r'[A-Z]{3}',norm(day))):
            rest=list(other)
            folio=rest.pop(0) if re.fullmatch(r'\d{4,}',rest[0]['expected_text'].strip()) else None
            fields['description']=' '.join(c['expected_text'].strip() for c in rest)
            if folio:fields['bank_reference']=folio['expected_text'].strip()
            if rest:fields['description_column']=str(rest[0]['column_index'])
            day=''
        else:
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


def kapital_no_activity_evidence(sources, choice, rows, currency):
    """A product section's printed + Depositos / - Retiros of zero prove it quiet.

    Beyond the shared printed-control checks, the product section must print
    no movement table (CONCEPTO/DEPOSITOS/RETIROS/SALDO heading), no Total
    line other than the table's zero Total (0.00 deposits, 0.00 withdrawals,
    the closing balance), and no line that starts like a payment (day then
    folio). Any of them could carry an unread payment and keeps the period held.
    """
    from services.financial.statement_printed_no_activity import zero_totals_evidence
    scopes = {(s['page_number'], s['table_index']): set(s['row_indices']) for s in choice.get('section_sources') or []}
    closing = {r['fields'].get('balance') for r in rows if r['kind'] == 'balance'
               and r['fields'].get('description') == 'Closing Balance'}

    def zero_total(joined):
        # The movement table's own Total line printing zero deposits, zero withdrawals and the
        # closing balance is a printed zero control, not a payment (real Intercam/Kapital USD
        # sections print it under an empty table).
        amounts = [int(a.replace(',', '').replace('.', '')) for a in re.findall(r'\d{1,3}(?:,\d{3})*\.\d{2}', joined)]
        return (len(amounts) == 3 and amounts[:2] == [0, 0] and len(closing) == 1
                and str(amounts[2]) == next(iter(closing)) and not re.search(r'\d{4,}(?![\d,.])', joined))

    def guard():
        for s in sources:
            for raw in s['rows']:
                if raw['row_index'] not in scopes.get((s['page_number'], s['table_index']), set()):
                    continue
                joined = norm(text(raw))
                if any(label in joined for label in ('CONCEPTO', 'FOLIO')) or re.search(r'\bDEPOSITOS\b.*\bRETIROS\b', joined):
                    return ('movement_table', 'A movement table was read in this product section. Check it before confirming that the section contains no transactions.')
                if (joined.startswith('TOTAL') and not zero_total(joined)) or re.match(r'^\d{1,2}\s+\d{4,}', joined):
                    return ('payment_line', 'A line that may be a payment was read in this product section. Check it before confirming that the section contains no transactions.')
        return None

    family = 'intercam-mexico' if choice.get('layout_id') == 'intercam-mexico-product-statement' else 'kapital-mexico'
    return zero_totals_evidence(rows, choice, currency, family=family, guard=guard)
