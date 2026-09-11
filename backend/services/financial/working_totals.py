"""Explicit working totals, separate from classification-qualified ledger totals."""
import re
from services.financial.ledger_summary import ledger_summary, LedgerSummaryError
from services.financial.money import get_currency

LIMITATION = ('Working totals include current admitted readings from admitted sources, including P3 readings '
    'outside verified totals. They do not establish completeness or change classification. '
    'Currencies remain separate; internal transfers are not matched or netted. Net postings are not an account balance.')


def working_totals_from_readings(summary):
    """Use the same captured population as an export; perform no additional reads."""
    result = {key: value for key, value in summary.items() if key not in ('readings', 'history_captured', 'points', 'grouping', 'date_basis')}
    result.update(population='working', included_classes=['p0', 'p1', 'p2', 'p3'], limitation=LIMITATION,
                  outside_verified_rows=None, has_credit_card_readings=False)
    if not summary['available']:
        return result
    if 'readings' not in summary or len(summary['readings']) != summary['considered_rows']:
        raise LedgerSummaryError('Working totals require the complete captured reading population.')
    groups, exclusions, outside = {}, dict(summary['exclusions']), 0
    exclusions['proof_class_not_included'] = 0
    for reading in summary['readings']:
        reason = reading['exclusion_reason']
        if reason not in (None, 'proof_class_not_included'):
            continue
        row = reading['row']
        if (reading.get('account') or {}).get('account_type') == 'credit_card':
            result['has_credit_card_readings'] = True
        if row['ledger_status'] != 'admitted' or row['superseded_by_id'] is not None or reading['source']['status'] != 'admitted':
            raise LedgerSummaryError('Working total membership is inconsistent.')
        amount = row['amount_minor']
        if not isinstance(amount, str) or not re.fullmatch(r'0|[1-9][0-9]{0,18}', amount) or int(amount) > 9223372036854775807 or row['direction'] not in ('credit', 'debit'):
            raise LedgerSummaryError('A working-total reading has an invalid amount or direction.')
        try:
            currency = get_currency(row['currency']).code
        except Exception as exc:
            raise LedgerSummaryError('A working-total reading has an unsupported currency.') from exc
        group = groups.setdefault(currency, dict(currency=currency, rows=0, credits_minor=0, debits_minor=0))
        group['rows'] += 1
        group[row['direction'] + 's_minor'] += int(amount)
        outside += reason == 'proof_class_not_included'
    for group in groups.values():
        group['net_minor'] = str(group['credits_minor'] - group['debits_minor'])
        group['credits_minor'], group['debits_minor'] = str(group['credits_minor']), str(group['debits_minor'])
    excluded = sum(exclusions.values())
    result.update(exclusions=exclusions, excluded_rows=excluded,
        included_rows=summary['considered_rows']-excluded, outside_verified_rows=outside,
        currencies=[groups[key] for key in sorted(groups)])
    return result


def working_ledger_summary(session, *, case_id, account_id=None, start_date=None, end_date=None):
    return working_totals_from_readings(ledger_summary(session, case_id=case_id, account_id=account_id,
        start_date=start_date, end_date=end_date, capture_readings=True))


def working_ledger_analysis(session, *, case_id, account_id=None, start_date=None, end_date=None, grouping='monthly'):
    """Analysis and contributing sources use exactly the working-total population."""
    if grouping not in ('daily', 'monthly', 'counterparty'):
        raise LedgerSummaryError('Unsupported working analysis grouping.')
    captured = ledger_summary(session, case_id=case_id, account_id=account_id,
        start_date=start_date, end_date=end_date, capture_readings=True)
    result = working_totals_from_readings(captured)
    counterparty = grouping == 'counterparty'
    output = 'counterparties' if counterparty else 'points'
    result[output] = []
    if counterparty:
        result.update(label_basis='counterparty_raw_exact',
            counterparty_limitation='Equal source labels are grouped verbatim within each currency. Missing and blank labels remain separate; this does not resolve identity or match transfers.')
    else:
        result.update(grouping=grouping, date_basis='ordering_date')
    if not result['available']:
        return result
    groups = {}
    for reading in captured['readings']:
        if reading['exclusion_reason'] not in (None, 'proof_class_not_included'):
            continue
        row = reading['row']
        label = row['counterparty_raw'] if counterparty else row['ordering_date']
        if counterparty:
            if label is not None and not isinstance(label, str):
                raise LedgerSummaryError('A working counterparty label is invalid.')
        else:
            from datetime import date
            try:
                parsed = date.fromisoformat(label)
                if parsed.isoformat() != label: raise ValueError('Noncanonical date')
            except (ValueError, TypeError) as exc:
                raise LedgerSummaryError('A working ordering date is invalid.') from exc
            if grouping == 'monthly': label = parsed.replace(day=1).isoformat()
        currency = get_currency(row['currency']).code
        group = groups.setdefault((label, currency), dict(currency=currency, rows=0,
            credits_minor=0, debits_minor=0, transaction_ids=[], source_document_ids=set(),
            **{'label' if counterparty else 'date': label}))
        group['rows'] += 1
        group[row['direction'] + 's_minor'] += int(row['amount_minor'])
        group['transaction_ids'].append(row['key'])
        group['source_document_ids'].add(reading['source']['id'])
    for key in sorted(groups, key=lambda k: (k[0] is not None, k[0] or '', k[1])):
        group = groups[key]
        group['net_minor'] = str(group['credits_minor'] - group['debits_minor'])
        group['credits_minor'], group['debits_minor'] = str(group['credits_minor']), str(group['debits_minor'])
        group['source_document_ids'] = sorted(group['source_document_ids'])
        result[output].append(group)
    return result
