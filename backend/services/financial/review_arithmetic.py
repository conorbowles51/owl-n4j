"""Exact, read-only comparisons of a proposed statement with its printed controls.

All callers pass rows from one account and period in source order. A missing
control is not a zero balance. No comparison establishes complete extraction.
"""
import re
from datetime import date


def integer(value):
    return int(value) if isinstance(value, str) and re.fullmatch(r'-?\d{1,20}', value) else None


def control(rows, role):
    matches = [r for r in rows if r['kind'] == 'balance' and r['excluded']
               and r['fields'].get('description', '').strip().lower() == role + ' balance'
               and r['fields'].get('balance') not in (None, '')]
    return matches[0] if len(matches) == 1 and integer(matches[0]['fields']['balance']) is not None else None


def movement(row, liability):
    fields = row['fields']
    amount = integer(fields.get('amount_minor'))
    if amount is None or amount <= 0 or fields.get('direction') not in ('credit', 'debit'):
        return None
    return amount * (1 if fields['direction'] == 'credit' else -1) * (-1 if liability else 1)


def comparison(kind, expected, printed, row, **extra):
    difference = expected - printed
    return dict(kind=kind, status='difference' if difference else 'matches',
                expected_minor=str(expected), printed_minor=str(printed), difference_minor=str(difference),
                row_id=row.get('id'), page=row.get('page_number'), **extra)


def arithmetic_checks(rows, *, liability=False):
    included = [r for r in rows if not r['excluded']]
    moves = [movement(r, liability) for r in included]
    opening, closing = control(rows, 'opening'), control(rows, 'closing')
    opening_value = integer(opening['fields']['balance']) if opening else None
    usable = all(m is not None for m in moves)
    checks = []
    if usable and opening is not None and closing is not None:
        checks.append(comparison('closing_balance', opening_value + sum(moves), integer(closing['fields']['balance']), closing))
    else:
        checks.append(dict(kind='closing_balance', status='unavailable',
                           reason='An opening balance, closing balance or transaction amount is missing or unreadable.'))

    # Dated source order determines which direction to inspect. Same-day rows
    # can be printed either way, so retain both interpretations in that case.
    dates = [r['fields'].get('date') or r['fields'].get('booking_date') or r['fields'].get('value_date') or '' for r in included]
    valid_dates = bool(dates)
    try:
        valid_dates = valid_dates and all(date.fromisoformat(d).isoformat() == d for d in dates)
    except ValueError:
        valid_dates = False
    ascending = valid_dates and all(a <= b for a, b in zip(dates, dates[1:]))
    descending = valid_dates and all(a >= b for a, b in zip(dates, dates[1:]))
    ordered = []
    if ascending:
        ordered.append(('source_order', included))
    if descending and len(included) > 1:
        ordered.append(('reverse_source_order', list(reversed(included))))
    manual = any(r.get('kind') == 'manual_entry' for r in included)
    interpretations = []
    if usable and not manual:
        for order, sequence in ordered:
            previous, pending, compared, mismatches, findings = opening_value, 0, 0, 0, []
            for row in sequence:
                pending += movement(row, liability)
                printed = integer(row['fields'].get('balance'))
                if printed is None:
                    continue
                if previous is not None:
                    compared += 1
                    result = comparison('running_balance', previous + pending, printed, row)
                    if result['status'] == 'difference':
                        mismatches += 1
                        if len(findings) < 100:
                            findings.append(result)
                previous, pending = printed, 0
            interpretations.append(dict(order=order, compared_intervals=compared,
                mismatch_count=mismatches, findings=findings, findings_truncated=mismatches > len(findings)))
    available = [i for i in interpretations if i['compared_intervals']]
    if available:
        best = min(available, key=lambda i: i['mismatch_count'])
        checks.append(dict(kind='running_balance', status='difference' if best['mismatch_count'] else 'matches',
                           **best, interpretations=interpretations))
    else:
        checks.append(dict(kind='running_balance', status='unavailable',
            reason=('A manually added transaction has no position in the printed sequence.' if manual else
                    'There are not enough readable running balances in a known date order.')))

    # Explicit totals are supplied by extraction only when their account,
    # period and credit/debit meaning are known. Never treat a subtotal as the
    # total for the whole statement.
    for direction in ('credit', 'debit'):
        controls = [r for r in rows if r.get('kind') == 'statement_total' and r['excluded']
                    and r['fields'].get('total_direction') == direction]
        if len(controls) == 1 and usable and integer(controls[0]['fields'].get('balance')) is not None:
            expected = sum(integer(r['fields']['amount_minor']) for r in included if r['fields']['direction'] == direction)
            checks.append(comparison(direction + '_total', expected, integer(controls[0]['fields']['balance']), controls[0]))
        else:
            checks.append(dict(kind=direction + '_total', status='unavailable',
                               reason='No separate, readable statement total was identified.'))
    return checks


def check_proposed_rows(proposal, edits):
    """Overlay editable values without accepting client-supplied source controls."""
    from services.financial.pdf_candidates import PdfMappingError
    from services.financial.statement_review_checks import check_statement_rows
    reviewed = {r['id']: r for r in edits}
    originals = {r['id']: r for r in proposal['rows']}
    if len(reviewed) != len(edits) or not originals.keys() <= reviewed.keys():
        raise PdfMappingError('The review must contain each original row once. Reopen this statement.', 409)
    effective = []
    for original in proposal['rows']:
        edit = reviewed[original['id']]
        fields = original['fields']
        effective.append({**original, 'excluded': edit['excluded'],
            'issues': [] if edit.get('reason', '').strip() else original.get('issues', []),
            'fields': {**fields, **{k: edit[k] for k in ('date', 'description', 'direction', 'amount_minor')
                                  if k in edit and not (k == 'description' and original['kind'] in ('balance', 'statement_total'))},
                       'balance': edit.get('balance_minor', fields.get('balance')),
                       'date_basis': fields.get('date_basis') if edit.get('date_unprinted') else None}})
    for row in edits:
        if row['id'] not in originals:
            if not row['id'].startswith('manual:') or row.get('manual_page') not in proposal.get('page_numbers', []):
                raise PdfMappingError('A manually added transaction needs a page from this PDF.', 422)
            effective.append(dict(id=row['id'], kind='manual_entry', excluded=row['excluded'], issues=[],
                                  page_number=row['manual_page'], fields={**row, 'balance': row.get('balance_minor')}))
    from services.financial.pdf_candidates import _digest
    result = check_statement_rows(effective, liability=proposal['metadata'].get('balance_convention') == 'liability_owed')
    result['checks_revision'] = _digest(dict(version='statement-checks-v1', source_revision=proposal['revision'], rows=[
        dict(id=r['id'], excluded=r['excluded'], fields={k:r['fields'].get(k) for k in
             ('date', 'booking_date', 'value_date', 'date_basis', 'amount_minor', 'direction', 'balance')}) for r in effective]))
    return result


def accepted_difference(result, request):
    return bool(request.get('balance_exception_reason', '').strip()
                and request.get('balance_exception_revision') == result['checks_revision'])


def arithmetic_problems(result):
    problems = []
    for check in result['checks']:
        if check['status'] != 'difference':
            continue
        if check['kind'] == 'running_balance':
            for finding in check['findings']:
                problems.append(dict(message='The payments since the previous printed balance do not add up to this balance.',
                                     row_id=finding.get('row_id'), page=finding.get('page'), check='running_balance'))
        else:
            message = {'closing_balance': 'The payments do not add up to the printed closing balance.',
                       'credit_total': 'The money in does not agree with the printed total.',
                       'debit_total': 'The money out does not agree with the printed total.'}[check['kind']]
            problems.append(dict(message=message, row_id=check.get('row_id'), page=check.get('page'), check=check['kind']))
    return problems
