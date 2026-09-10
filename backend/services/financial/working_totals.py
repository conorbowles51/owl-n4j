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
                  outside_verified_rows=None)
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
