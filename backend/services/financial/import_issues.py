"""Keep import availability separate from checks and incomplete readings.

Incomplete records belong to the imported source, not to the numeric ledger.
Their original fields survive unchanged until a correction supplies a usable
reading. In particular, a missing amount is never manufactured as zero.
"""
from datetime import date
from pydantic import ValidationError
from services.financial.money import get_currency, MoneyError


def calendar_date(value):
    try:
        parsed = date.fromisoformat(value)
        return parsed if parsed.isoformat() == value else None
    except (TypeError, ValueError):
        return None


def usable_currency(value):
    try:
        return get_currency(value).code
    except (TypeError, ValueError, KeyError, MoneyError):
        return None


def usable_balance(value, convention=None):
    if not isinstance(value, str) or not value.lstrip('-').isdigit():
        return False
    minimum = -9223372036854775807 if convention == 'liability_owed' else -9223372036854775808
    return minimum <= int(value) <= 9223372036854775807


def incomplete_fields(row, request):
    from services.financial.statement_import import ImportRow
    problems = []
    if not usable_currency(request.currency):
        problems.append('currency')
    try:
        ImportRow.model_validate(row.model_dump())
    except ValidationError as error:
        for issue in error.errors(include_url=False, include_input=False):
            field = str(issue['loc'][-1]) if issue['loc'] else ''
            if field in ('amount_minor', 'balance_minor'):
                problems.append('amount' if field == 'amount_minor' else 'balance')
            else:
                # After validators report the record rather than a field.
                message = issue['msg'].lower()
                problems.append('direction' if 'credit or debit' in message else
                    'description' if 'description' in message else
                    'amount' if 'amount' in message else 'date')
    if row.date_unprinted and not calendar_date(request.period_end):
        problems.append('date')
    if len(row.counterparty) > 512:
        problems.append('counterparty')
    return sorted(set(problems))


def retained_issues(proposal, request, *, arithmetic=None, coverage=None):
    from services.financial.review_arithmetic import arithmetic_problems
    originals = {r['id']: r for r in proposal['rows']}
    issues = []
    if not any(not row.excluded for row in request.rows):
        omitted = sum(row['kind'] == 'transaction' and not row['excluded'] for row in proposal['rows'])
        if omitted:
            issues.append(dict(kind='omitted_transactions', row_id=None,
                message=f'Balances saved without transactions. {omitted} possible payments were left out; their original readings are retained.'))
    for row in request.rows:
        if row.excluded:
            if row.balance_minor is not None and not usable_balance(row.balance_minor, proposal['metadata'].get('balance_convention')):
                issues.append(dict(kind='missing_field', field='balance', row_id=row.id,
                    message='The printed balance could not be read. It is retained with the statement but is not used in the balance check.'))
            continue
        original = originals.get(row.id, {})
        for field in incomplete_fields(row, request):
            issues.append(dict(kind='missing_field', field=field, row_id=row.id,
                page=original.get('page_number', row.manual_page),
                message=('The party name is too long to save as a transaction. Correct the name against the original.' if field == 'counterparty' else
                    f'The {field} is missing or unreadable. The record is retained outside calculated totals.')))
        if not row.reason.strip():
            for message in original.get('issues', []):
                issues.append(dict(kind='reading', row_id=row.id, page=original.get('page_number'), message=message))
    for field, label in [('holder', 'account holder'), ('account_number', 'account number')]:
        if not getattr(request, field).strip():
            issues.append(dict(kind='statement_detail', field=field, row_id=None,
                message=f'The {label} has not been identified.'))
    start, end = calendar_date(request.period_start), calendar_date(request.period_end)
    if (request.period_start or request.period_end) and (not start or not end or start > end):
        issues.append(dict(kind='statement_detail', field='period', row_id=None,
            message='The complete statement period has not been identified.'))
    if arithmetic:
        issues.extend(dict(kind='arithmetic', **problem) for problem in arithmetic_problems(arithmetic))
    if coverage and coverage.get('requires_review'):
        issues.append(dict(kind='coverage', row_id=None,
            message='Another supplied statement covers some of these dates. Compare their payments if needed.'))
    return issues


def incomplete_records(proposal, request):
    originals = {r['id']: r for r in proposal['rows']}
    return [dict(id=row.id, fields=row.model_dump(mode='json'),
        missing_fields=missing, original=originals.get(row.id, dict(page_number=row.manual_page)),
        resolved_transaction_id=None, version=0)
        for row in request.rows if not row.excluded
        if (missing := incomplete_fields(row, request))]
