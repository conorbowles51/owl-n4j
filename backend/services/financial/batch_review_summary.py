"""Explain existing review checks without changing import admission or evidence.

This is a read-only projection over current batch items, before pagination.
Legacy messages get a display category; their underlying checks remain intact.
"""

REASONS = {
    'currency': ('Choose statement currency', 'Choose the currency printed on the source. Currency is required before import.'),
    'holder': ('Missing account holder', 'Add the person or company shown on the statement. Use Edit account details to fill several statements together.'),
    'account': ('Missing account number', 'Add the printed account number. Use Edit account details to fill several statements together.'),
    'dates': ('Check statement dates', 'Compare the period with the source. Use Edit account details when several statements need dates.'),
    'incomplete': ('Incomplete payment values', 'Open the indicated row to correct its missing value. Incomplete records are kept outside calculated totals.'),
    'balance': ('Balances or totals differ', 'Compare the printed balance or total with the selected payments. The statement review shows the calculation and source.'),
    'count': ('Possible missing payments', 'The selected payments do not match the printed count, or possible payments were left out. Compare the source rows.'),
    'overlap': ('Overlapping statement dates', 'Compare the statements for duplicate payments. Overlapping dates alone do not establish a duplicate.'),
    'duplicate': ('Possible duplicate statements', 'A separate file has matching bank, account, holder, currency and statement dates. Compare the original, then leave the copy unimported or record why both are needed.'),
    'saved_review': ('Earlier corrections need comparison', 'Compare and keep the investigator’s saved corrections before confirming the new reading.'),
    'assignment': ('Payments need an account', 'Open the review to assign these payments to the correct account and period.'),
    'import_failed': ('Import needs recovery', 'Open the statement to check the saved import result and retry without duplicating payments.'),
    'balance_unavailable': ('Balance comparison unavailable', 'An automatic comparison could not be made. This does not establish a balance difference; inspect the printed controls if needed.'),
    'reading': ('Check a source reading', 'The reason is shown on each matching statement. Open the indicated row or statement to compare it with the original.'),
    'additional': ('Additional checks in statement review', 'More checks are retained than fit in the batch preview. Open these statements to see the remaining reasons.'),
}


def reason(problem):
    kind, field, check = (problem.get(key) for key in ('kind', 'field', 'check'))
    message = problem.get('message', '').lower()
    if kind == 'statement_detail':
        return {'holder': 'holder', 'account_number': 'account', 'period': 'dates'}.get(field, 'reading')
    if kind == 'coverage_load':
        return 'reading'
    if kind == 'coverage' and problem.get('matching_statement'):
        return 'duplicate'
    if kind == 'coverage' or 'another statement covers' in message:
        return 'overlap'
    if kind in ('transaction_count', 'omitted_transactions'):
        return 'count'
    if kind == 'missing_field':
        return 'currency' if field == 'currency' else 'incomplete'
    if check or kind == 'arithmetic' or any(text in message for text in ('do not add up', 'does not agree with the printed total')):
        return 'balance'
    if 'earlier saved reviews' in message or 'saved corrections' in message:
        return 'saved_review'
    if 'assign payments to a statement' in message:
        return 'assignment'
    if 'currency' in message and any(text in message for text in ('choose', 'enter', 'missing', 'required')):
        return 'currency'
    if 'account holder' in message and any(text in message for text in ('missing', 'not been identified', 'enter', 'could not')):
        return 'holder'
    if 'account number' in message and any(text in message for text in ('missing', 'not been identified', 'enter', 'could not')):
        return 'account'
    if 'statement period' in message and ('not been identified' in message or 'complete' in message):
        return 'dates'
    if any(text in message for text in ('not enough readable balances', 'not enough readable running balances', 'balance check could not', 'balance comparison unavailable')):
        return 'balance_unavailable'
    return 'reading'


def item_reasons(item):
    if item.status in ('skipped', 'assigned', 'removed', 'duplicate_ignored', 'superseded_reading'):
        return {}
    summary = item.summary
    result = {}
    problems = summary.get('problems', [])
    for problem in problems:
        key = 'import_failed' if summary.get('import_failed') else reason(problem)
        result[key] = result.get(key, 0) + 1
    remaining = max(0, summary.get('problem_count', 0) - len(problems))
    if remaining:
        result['additional'] = remaining
    return result


def is_blocked(item):
    return item.status in ('ready', 'attention') and not item.summary.get('can_import', item.status == 'ready')


def matches_group(item, group):
    if not group:
        return True
    if group == 'blocked':
        return is_blocked(item)
    return group in item_reasons(item)


def validate_group(group):
    if group and group not in {*REASONS, 'blocked'}:
        from services.financial.pdf_candidates import PdfMappingError
        raise PdfMappingError('Choose a review reason from this batch.', 422)


def group_label(group):
    if group == 'blocked':
        return 'Cannot be imported yet'
    return REASONS[group][0] if group else None


def tagged_problems(summary):
    return [{**problem, 'review_reason': 'import_failed' if summary.get('import_failed') else reason(problem)}
            for problem in summary.get('problems', [])]


def statement_summary(items):
    """Count current prepared reviews once, separately from overlapping reasons.

    A prepared item can also be an unidentified/assignment-only review, so this
    total is not a claim that every item is a fully identified statement period.
    Zero extracted payments alone never proves that a period had no activity.
    """
    result = dict(total=0, available=0, blocked=0, imported=0, pending_import=0,
        skipped=0, duplicate_ignored=0, assigned=0, other=0,
        available_with_payments=0, available_no_activity=0, available_other=0)
    for item in items:
        if item.status in ('removed', 'superseded_reading'):
            continue
        result['total'] += 1
        if item.status in ('ready', 'attention'):
            if is_blocked(item):
                result['blocked'] += 1
                continue
            result['available'] += 1
            payment_count = item.summary.get('transaction_count')
            known_payment_count = type(payment_count) is int and payment_count >= 0
            admission = item.summary.get('admission')
            admission = admission if isinstance(admission, dict) else {}
            if known_payment_count and payment_count > 0:
                result['available_with_payments'] += 1
            elif (known_payment_count and payment_count == 0 and admission.get('can_import') is True
                    and admission.get('assessment_current') is True
                    and admission.get('status') == 'confirmed_no_activity'
                    and admission.get('no_activity_confirmed') is True):
                result['available_no_activity'] += 1
            else:
                result['available_other'] += 1
        elif item.status in ('imported', 'pending_import', 'skipped', 'duplicate_ignored', 'assigned'):
            result[item.status] += 1
        else:
            result['other'] += 1
    return result


def review_summary(items):
    grouped = {}
    result = dict(blocked_statements=0, importable_with_checks=0, imported_with_checks=0,
                  unchecked_balance_statements=0, groups=[])
    for item in items:
        if item.status in ('skipped', 'assigned', 'removed', 'duplicate_ignored', 'superseded_reading'):
            continue
        blocked = is_blocked(item)
        importable = item.status in ('ready', 'attention') and not blocked
        reasons = item_reasons(item)
        result['blocked_statements'] += int(blocked)
        result['importable_with_checks'] += int(importable and bool(reasons))
        result['imported_with_checks'] += int(item.status == 'imported' and bool(reasons))
        result['unchecked_balance_statements'] += int(item.summary.get('balance_status') == 'unavailable')
        for key, count in reasons.items():
            label, explanation = REASONS[key]
            group = grouped.setdefault(key, dict(id=key, label=label, explanation=explanation,
                statement_count=0, check_count=0, blocked_statements=0, importable_statements=0, imported_statements=0))
            group['statement_count'] += 1
            group['check_count'] += count
            group['blocked_statements'] += int(blocked)
            group['importable_statements'] += int(importable)
            group['imported_statements'] += int(item.status == 'imported')
    result['groups'] = sorted(grouped.values(), key=lambda g: (-g['blocked_statements'], -g['statement_count'], g['label']))
    return result
