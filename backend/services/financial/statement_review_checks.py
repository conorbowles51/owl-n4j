"""Read-only checks for each recognised period in a statement collection."""
from datetime import date


def check_statement_rows(rows, *, liability=False):
    included = [row for row in rows if not row['excluded']]
    flagged = 0
    for row in rows:
        fields = row['fields']
        invalid = bool(row.get('issues'))
        if not row['excluded']:
            value = fields.get('date') or fields.get('booking_date') or fields.get('value_date') or ''
            if value or fields.get('date_basis') != 'statement_end_ordering_only':
                try:
                    invalid |= date.fromisoformat(value).isoformat() != value
                except ValueError:
                    invalid = True
            invalid |= not fields.get('description', '').strip()
            invalid |= fields.get('direction') not in ('credit', 'debit')
            amount = fields.get('amount_minor', '')
            invalid |= not amount.isdigit() or not 0 < int(amount or '0') <= 9223372036854775807
        flagged += bool(invalid)
    result = dict(transaction_count=len(included), flagged_rows=flagged, balance_status='unavailable')
    from services.financial.review_arithmetic import arithmetic_checks
    checks = arithmetic_checks(rows, liability=liability)
    result['checks'] = checks
    result['has_difference'] = any(check['status'] == 'difference' for check in checks)
    closing = checks[0]
    result['balance_status'] = closing['status']
    if 'difference_minor' in closing:
        result['difference_minor'] = closing['difference_minor']
    return result


def add_period_checks(choices, sources, currency):
    """Check all periods from the same saved extraction, without database writes.

    A balance match is arithmetic only. Missing controls and unreadable amounts
    never receive a successful reconciliation status.
    """
    from services.financial.money import get_currency, MoneyError
    by_address = {(s['page_number'], s['table_index']): s for s in sources}
    result = []
    for choice in choices:
        if choice.get('document_kind'):
            result.append(choice)
            continue
        chosen_currency = currency or choice.get('currency')
        if not chosen_currency:
            result.append(choice)
            continue
        try:
            get_currency(chosen_currency)
        except MoneyError:
            result.append(choice)
            continue
        selected = [by_address[(s['page_number'], s['table_index'])] for s in choice['sources']]
        layout = choice.get('layout_id')
        try:
            if layout == 'andrews-share-statement':
                from services.financial.statement_import_andrews import propose_andrews_statement
                rows = propose_andrews_statement(selected, chosen_currency, choice)['rows']
            elif layout == 'bbva-mexico-cash-management':
                from services.financial.statement_import_bbva import propose_bbva_statement
                rows = propose_bbva_statement(selected, chosen_currency, choice)['rows']
            elif layout == 'monex-mexico-currency-summary':
                from services.financial.statement_import_monex import propose_monex_statement
                rows = propose_monex_statement(selected, chosen_currency, choice)['rows']
            elif layout in ('kapital-mexico-product-statement', 'intercam-mexico-product-statement'):
                from services.financial.statement_import_kapital import propose_kapital_statement
                rows = propose_kapital_statement(selected, chosen_currency, choice)['rows']
            elif layout == 'santander-mexico-movements':
                from services.financial.statement_import_santander import propose_santander_statement
                rows = propose_santander_statement(selected, chosen_currency, choice)['rows']
            elif layout in ('capital-one-card', 'merrick-card', 'credit-one-card'):
                from services.financial.statement_import_card import propose_card_table
                from services.financial.statement_import_merrick import propose_merrick_table
                from services.financial.statement_import_credit_one import propose_credit_one_table
                propose = {'capital-one-card': propose_card_table, 'merrick-card': propose_merrick_table,
                    'credit-one-card': propose_credit_one_table}[layout]
                rows = [row for source in selected for row in propose(source, chosen_currency, choice)['rows']]
            else:
                result.append(choice)
                continue
            checks = check_statement_rows(rows, liability=layout in ('capital-one-card', 'merrick-card', 'credit-one-card'))
        except ValueError:
            # One unreadable period must not hide the remaining periods.
            checks = dict(balance_status='unavailable', flagged_rows=1)
        result.append({**choice, 'checks': checks})
    return result
