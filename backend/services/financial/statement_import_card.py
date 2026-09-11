"""Prepare the recognised Capital One statement sections for one review.

Printed card references remain masked. Purchase debits increase card debt;
payment credits reduce it. No bank-to-card transfer or counterparty identity is
inferred. Undated interest charges remain explicit review exceptions.
"""
import re
from services.financial.statement_import_proposal import exact_amount
from services.financial.statement_layout_context import _dates_within
from datetime import date


def propose_card_table(source, currency, statement):
    context = source.get('layout_context')
    observed = {item['row_index']: item for item in (context or {}).get('rows', [])}
    result = []
    fees = False
    fee_columns = None
    for row in source['rows']:
        item = dict(id=f"{source['page_number']}:{source['table_index']}:{row['row_index']}",
                    page_number=source['page_number'], table_index=source['table_index'], row_index=row['row_index'],
                    source_revision=source['source_revision'], source_cells=row['cells'], fields={},
                    issues=[], excluded=True, kind='statement_information')
        texts = [cell['expected_text'].strip() for cell in row['cells']]
        candidate = observed.get(row['row_index'])
        if 'Fees' in texts:
            fees = True
            fee_columns = None
        elif any(text in ('Interest Charged', 'Totals Year-to-Date', 'Interest Charge Calculation') or text.startswith('Total Fees') for text in texts):
            fees = False
        if fees and all(label in texts for label in ('Date', 'Description', 'Amount')):
            fee_columns = {cell['expected_text'].strip(): cell['column_index'] for cell in row['cells']}
        elif fees and fee_columns:
            columns = {c['column_index']: c for c in row['cells']}
            if all(fee_columns[key] in columns for key in ('Date', 'Description', 'Amount')):
                dates = _dates_within(columns[fee_columns['Date']]['expected_text'],
                                     date.fromisoformat(statement['period_start']), date.fromisoformat(statement['period_end']))[1]
                candidate = dict(date_proposals=dates, posting_date_proposals=[],
                    description_source=columns[fee_columns['Description']], amount_source=columns[fee_columns['Amount']],
                    printed_section='Fees', card_ending=statement['account_reference'][-4:])
        if candidate:
            item.update(excluded=False, kind='transaction')
            fields = item['fields']
            fields.update(description=candidate['description_source']['expected_text'], counterparty='',
                          card_ending=candidate['card_ending'], printed_section=candidate['printed_section'])
            if len(candidate['date_proposals']) == 1:
                fields['date'] = candidate['date_proposals'][0]
            else:
                item['issues'].append('Check the transaction date against this billing period.')
            if len(candidate.get('posting_date_proposals', [])) == 1:
                fields['booking_date'] = candidate['posting_date_proposals'][0]
            try:
                raw = candidate['amount_source']['expected_text'].strip()
                # The issuer prints a separated minus before the currency symbol.
                sign = -1 if raw.startswith('-') else 1
                raw = re.sub(r'^[+-]\s*', '', raw)
                amount = int(exact_amount(raw, currency)) * sign
                fields.update(amount_minor=str(abs(amount)), direction='credit' if amount < 0 else 'debit')
                if not amount:
                    item['issues'].append('Check whether this zero-value entry belongs in the transaction list.')
            except ValueError as exc:
                item['issues'].append(str(exc))
            item['layout_context'] = candidate
        elif context and texts and re.fullmatch(r'Interest Charge on (?:Purchases|Cash Advances|Other Balances)', texts[0]):
            item.update(kind='transaction', excluded=False)
            item['fields'].update(description=texts[0], direction='debit', counterparty='')
            try:
                amount = exact_amount(texts[-1], currency)
                item['fields']['amount_minor'] = amount
                if int(amount) == 0:
                    item.update(kind='zero_charge', excluded=True)
                else:
                    item['issues'].append('This interest charge has no printed transaction date. Check and record its date before importing.')
            except ValueError as exc:
                item['issues'].append(str(exc))
        elif context and any(re.match(r'^(?:\d{1,2}[/-]\d{1,2}|[A-Za-z]{3,9}\.?\s+\d{1,2})$', text) for text in texts):
            item.update(kind='unresolved', excluded=False)
            item['issues'].append('This dated row was not recognised in a transaction section. Check it against the PDF.')
        result.append(item)
    return dict(rows=result)
