"""Prepare the recognised Capital One statement sections for one review.

Printed card references remain masked. Purchase debits increase card debt;
payment credits reduce it. No bank-to-card transfer or counterparty identity is
inferred. Undated interest charges remain explicit review exceptions.
"""
import re
from services.financial.statement_import_proposal import exact_amount
from services.financial.statement_layout_context import _cycle, card_row_dates
from services.financial.card_table_columns import card_row_columns
from datetime import date
from services.financial.statement_import_card_balances import summary_balances


def propose_card_table(source, currency, statement):
    balances, issues = summary_balances(source, currency)
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
        # A cycle header can span several measured OCR cells. Its dates describe
        # statement coverage, not an unrecognised dated transaction.
        if _cycle(' '.join(texts)) is not None:
            result.append(item)
            continue
        if row['row_index'] in balances:
            item.update(balances[row['row_index']])
            result.append(item)
            continue
        candidate = observed.get(row['row_index'])
        if 'Fees' in texts:
            fees = True
            fee_columns = None
        elif any(text in ('Interest Charged', 'Totals Year-to-Date', 'Interest Charge Calculation') or text.startswith('Total Fees') for text in texts):
            fees = False
        header_options = [('Date', 'Description', 'Amount'), ('Trans Date', 'Post Date', 'Description', 'Amount')]
        matched_headers = [names for names in header_options if all(texts.count(name) == 1 for name in names)]
        if fees and (any(name in texts for name in ('Date', 'Trans Date', 'Post Date')) or all(name in texts for name in ('Description', 'Amount'))):
            fee_columns = ({name: next(c for c in row['cells'] if c['expected_text'].strip() == name)
                            for name in matched_headers[0]} if len(matched_headers) == 1 else None)
        elif fees and fee_columns:
            mapped = card_row_columns(row['cells'], fee_columns)
            date_label = 'Date' if 'Date' in fee_columns else 'Trans Date'
            if mapped:
                columns, descriptions = mapped
                date_source = columns[date_label]
                posting_source = columns.get('Post Date')
                _, dates, postings, basis = card_row_dates(date_source['expected_text'],
                    posting_source['expected_text'] if posting_source else None,
                    date.fromisoformat(statement['period_start']), date.fromisoformat(statement['period_end']))
                candidate = dict(date_proposals=dates, date_source=date_source, posting_date_source=posting_source,
                    posting_date_proposals=postings, date_basis=basis,
                    description_source=columns['Description'], description_sources=descriptions, amount_source=columns['Amount'],
                    printed_section='Fees', card_ending=statement['account_reference'][-4:])
        if candidate:
            item.update(excluded=False, kind='transaction')
            fields = item['fields']
            fields.update(description=' '.join(cell['expected_text'] for cell in candidate.get('description_sources', [candidate['description_source']])), counterparty='',
                          card_ending=candidate['card_ending'], printed_section=candidate['printed_section'])
            fields['date_column'] = str(candidate['date_source']['column_index'])
            if len(candidate['date_proposals']) == 1:
                fields['date'] = candidate['date_proposals'][0]
            else:
                item['issues'].append('Check the transaction date against this billing period.')
            if len(candidate.get('posting_date_proposals', [])) == 1:
                fields['booking_date'] = candidate['posting_date_proposals'][0]
            if candidate.get('posting_date_source'):
                fields['booking_date_column'] = str(candidate['posting_date_source']['column_index'])
                if candidate['posting_date_source']['expected_text'].strip() and 'booking_date' not in fields:
                    item['issues'].append('Check the posting date in the PDF. It could not be read within this billing period.')
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
        elif texts and re.fullmatch(r'Interest Charge on (?:Purchases|Cash Advances|Other Balances)', texts[0]):
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
        elif any(re.fullmatch(r'(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|[A-Za-z]{3,9}\.?\s+\d{1,2}(?:,?\s+\d{4})?)', text) for text in texts):
            item.update(kind='unresolved', excluded=False)
            item['issues'].append('This dated row was not recognised in a transaction section. Check it against the PDF.')
        result.append(item)
    return dict(rows=result, issues=issues)
