"""Source-bound recognition of Merrick card statement pages and entries."""
import re
from datetime import date
from services.financial.pdf_candidates import _digest
from services.financial.statement_import_proposal import exact_amount


def merrick_statement(source):
    texts = [c['expected_text'].strip() for r in source['rows'] for c in r['cells']]
    if 'MERRICK BANK' not in texts or 'Transactions, Payments and Credits' not in texts:
        return None
    accounts = set()
    for row in source['rows']:
        cells = row['cells']
        for i, cell in enumerate(cells):
            text = cell['expected_text'].strip()
            match = re.fullmatch(r'Account Number:\s*([0-9 ]{13,24})', text)
            if match:
                accounts.add(match[1].strip())
            elif text == 'Account Number' and i + 1 < len(cells) and re.fullmatch(r'[0-9 ]{13,24}', cells[i+1]['expected_text'].strip()):
                accounts.add(cells[i+1]['expected_text'].strip())
    years = {int(m[1]) for text in texts if (m := re.fullmatch(r'(20\d{2}) Totals Year-to-Date', text))}
    dates = {m[1].strip() for text in texts if (m := re.fullmatch(r'Statement Date:\s*(.+)', text))}
    raw_date = next(iter(dates)) if len(dates) == 1 else ''
    year = next(iter(years)) if len(years) == 1 else None
    if year is not None and not raw_date.endswith(str(year)[-2:]):
        year = None
    closing = None
    matched = re.fullmatch(r'(\d{2})/(\d{2})/(\d{2}|\d{4})', raw_date)
    if matched and year and int(matched[3]) in (year, year % 100):
        try:
            closing = date(year, int(matched[1]), int(matched[2])).isoformat()
        except ValueError:
            pass
    # A damaged day separator is not repaired. A clearly printed month plus
    # the explicit full YTD year can still constrain transaction-year proposals.
    month = re.match(r'^(0[1-9]|1[0-2])/', raw_date)
    holder = ''
    for row in source['rows']:
        values = [c['expected_text'].strip() for c in row['cells']]
        if values and values[0] == 'Send Payments to:' and len(values) > 1 and re.fullmatch(r'[A-Z][A-Z .\'-]{2,127}', values[1]):
            holder = values[1]
    identity = dict(layout_id='merrick-card', institution='Merrick Bank',
                    account_reference=next(iter(accounts)) if len(accounts) == 1 else '',
                    statement_date=closing or '', printed_statement_date=raw_date,
                    period_start='', period_end='', holder=holder,
                    date_year=year, date_month=int(month[1]) if month else None)
    identity['id'] = _digest(dict(**identity, source_page=source['page_number']))
    return dict(**identity, sources=[dict(page_number=source['page_number'],table_index=source['table_index'],source_revision=source['source_revision'])],page_numbers=[source['page_number']])


def propose_merrick_table(source, currency, statement):
    active = False
    result = []
    for row in source['rows']:
        cells = row['cells']
        texts = [c['expected_text'].strip() for c in cells]
        item = dict(id=f"{source['page_number']}:{source['table_index']}:{row['row_index']}",
                    page_number=source['page_number'],table_index=source['table_index'],row_index=row['row_index'],
                    source_revision=source['source_revision'],source_cells=cells,fields={},issues=[],excluded=True,kind='statement_information')
        if 'Transactions, Payments and Credits' in texts:
            active = True
        if any(re.fullmatch(r'20\d{2} Totals Year-to-Date', text) for text in texts):
            active = False
        match = re.fullmatch(r'(\d{1,2})/(\d{1,2})', texts[0]) if texts else None
        if active and match and len(texts) >= 3:
            item.update(excluded=False,kind='transaction')
            fields=item['fields']
            middle=texts[1:-1]
            if len(middle)>1 and re.fullmatch(r'[A-Z0-9]{12,24}', middle[0]):
                fields['bank_reference']=middle.pop(0)
            fields.update(description=' '.join(middle),counterparty='')
            year, closing_month=statement['date_year'],statement['date_month']
            month, day=int(match[1]),int(match[2])
            if year and closing_month and month in (closing_month, (closing_month-2)%12+1):
                try:
                    fields['date']=date(year-1 if closing_month==1 and month==12 else year,month,day).isoformat()
                    fields['date_context']='Year constrained by printed statement month and full year-to-date heading.'
                except ValueError:
                    pass
            if 'date' not in fields:
                item['issues'].append('Check the full date. The printed statement context could not resolve its year.')
            try:
                value=int(exact_amount(texts[-1],currency))
                fields.update(amount_minor=str(abs(value)),direction='credit' if value<0 else 'debit')
                if value == 0:
                    item.update(excluded=True,kind='zero_charge')
                    item['issues']=[]
            except ValueError as exc:
                item['issues'].append(str(exc))
        elif active and texts and not (texts[0] in ('Transactions, Payments and Credits','Fees','Interest Charged') or texts[0].upper().startswith('TOTAL ') or any('Description' in text for text in texts)):
            item.update(excluded=False,kind='unresolved')
            item['issues'].append('Check this row in the transaction section. Its date or layout could not be read.')
        result.append(item)
    return dict(rows=result)
