"""Keep import availability separate from checks and incomplete readings.

Incomplete records belong to the imported source, not to the numeric ledger.
Their original fields survive unchanged until a correction supplies a usable
reading. In particular, a missing amount is never manufactured as zero.
"""
import os
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


def row_reviewed(original, row):
    """A saved value correction is a review even when its optional note is blank."""
    value = row if isinstance(row, dict) else row.model_dump()
    if value.get('reason', '').strip():
        return True
    fields = original.get('fields', {})
    baseline = dict(date=fields.get('date') or fields.get('booking_date') or fields.get('value_date') or '',
        description=fields.get('description', ''), counterparty=fields.get('counterparty', ''),
        amount_minor=fields.get('amount_minor') or ('0' if original.get('excluded') else ''),
        direction=fields.get('direction'), balance_minor=fields.get('balance'))
    return any(key in value and value[key] != expected for key, expected in baseline.items())


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


# 2026-10-25 (fin-queue, Neil: build the queue's lessons in): a file holding only
# some printed pages of a statement is still complete for the period when a page
# it does hold carries the bank's own count of the period's movements as zero
# deposits and zero withdrawals, with one opening and one closing balance, equal:
# the missing pages cannot hold a movement the bank counted as none (BNB2 08 and
# 09 BBVA 23 USD: one "PAGINA n/6" page printing TOTAL MOVIMIENTOS 0 / 0). Only
# counts and balances the reader took from the page count; a person's entered
# balance still needs their note. The same zero counts already prove no activity
# at admission (statement_admission). Off: missing pages always hold.
PAGES_MISSING_PRINTED_QUIET = os.environ.get('LOUPE_FINANCIAL_PAGES_MISSING_PRINTED_QUIET', '1') != '0'


def printed_quiet(proposal, request):
    """The pages held print the bank's own zero movement counts for this period and no payment is selected."""
    if not PAGES_MISSING_PRINTED_QUIET or any(not row.excluded for row in request.rows):
        return False
    rows = proposal.get('rows') or []
    counted = {row['fields'].get('total_direction') for row in rows if row['kind'] == 'statement_total'
               and not row['fields'].get('total_scope') and row['fields'].get('printed_transaction_count') == '0'}
    balances = [row['fields'].get('balance') for row in rows if row['kind'] == 'balance'
                and row['fields'].get('description') in ('Opening Balance', 'Closing Balance')]
    if (counted >= {'credit', 'debit'} and len(balances) == 2 and balances[0] not in (None, '')
            and str(balances[0]) == str(balances[1])):
        return True
    # The same counts printed on the page images (a proved quiet image reading: its source proof names the balances).
    evidence = proposal.get('no_activity_evidence') or {}
    if evidence.get('basis') != 'page_image_zero_counts':
        return False
    from services.financial.statement_admission import source_proves_no_activity
    return source_proves_no_activity(evidence, request.model_dump(mode='json'))


# 2026-10-26 (fin-queue3 L7, Neil: every lesson into the processor): the same for a period with movements. A file
# holding some printed pages of a statement is complete for the period when a page it holds prints the bank's own
# count and total of the period's deposits and of its withdrawals, and the payments selected match all four: one more
# movement on a missing page would change a count the bank printed (BNB2 ECO 2023 MN and 06/09 BBVA 23 MXN: one
# "PAGINA n/N" production of the movement pages only). Only counts and totals read from the page count; a payment
# entered by a person does not settle it (the image reading's rows do: they are proved against the same counts).
# Off: missing pages with movements always hold.
PAGES_MISSING_PRINTED_COUNTS = os.environ.get('LOUPE_FINANCIAL_PAGES_MISSING_PRINTED_COUNTS', '1') != '0'


def printed_complete(proposal, request):
    """The pages held print the period's deposit and withdrawal counts and totals, and the payments selected match them."""
    from services.financial.review_arithmetic import integer
    if not PAGES_MISSING_PRINTED_COUNTS:
        return False
    selected = [row for row in request.rows if not row.excluded]
    if not selected:
        return False
    rows = proposal.get('rows') or []
    printed = {direction: {(row['fields'].get('printed_transaction_count'), row['fields'].get('balance')) for row in rows
                           if row['kind'] == 'statement_total' and not row['fields'].get('total_scope')
                           and row['fields'].get('total_direction') == direction} for direction in ('credit', 'debit')}
    image = proposal.get('image_printed_controls') or {}
    if any(len(found) != 1 for found in printed.values()) and image \
            and all(str(row.id).startswith('manual:vision-') for row in selected):
        # Counts and totals the page images print (vision_reader.printed_controls), for the payments read from them.
        printed = {direction: {(str(image['count_%ss' % direction]), str(image['total_%ss_minor' % direction]))}
                   for direction in ('credit', 'debit')}
    for direction in ('credit', 'debit'):
        if len(printed[direction]) != 1:
            return False
        count, total = next(iter(printed[direction]))
        if not (isinstance(count, str) and count.isdigit()) or integer(total) is None:
            return False
        mine = [row for row in selected if row.direction == direction]
        if len(mine) != int(count) or sum(integer(row.amount_minor) or 0 for row in mine) != integer(total):
            return False
    return True


def retained_issues(proposal, request, *, arithmetic=None, coverage=None):
    from services.financial.review_arithmetic import arithmetic_problems
    originals = {r['id']: r for r in proposal['rows']}
    issues = []
    gap = proposal.get('printed_pages_missing')
    if gap and not (getattr(request, 'coverage_review_reason', None) or '').strip() and not printed_quiet(proposal, request) \
            and not printed_complete(proposal, request):
        from services.financial.printed_page_count import message
        issues.append(dict(kind='printed_pages_missing', row_id=None, pages=gap['missing'], message=message(gap)))
    for original in proposal['rows']:
        count = original['fields'].get('printed_transaction_count')
        direction = original['fields'].get('total_direction')
        if original['kind'] == 'statement_total' and isinstance(count, str) and count.isdigit() and direction in ('credit', 'debit'):
            actual = sum(not row.excluded and row.direction == direction for row in request.rows)
            if actual != int(count):
                issues.append(dict(kind='transaction_count', row_id=original['id'], page=original.get('page_number'),
                    message=f'The statement lists {count} {"charges" if direction == "debit" else "credits"}; {actual} are selected. Check for missing transactions.'))
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
        if not row_reviewed(original, row):
            for message in original.get('issues', []):
                issues.append(dict(kind='reading', row_id=row.id, page=original.get('page_number'), message=message))
    for field, label in [('holder', 'account holder'), ('account_number', 'account number')]:
        if not getattr(request, field).strip():
            issues.append(dict(kind='statement_detail', field=field, row_id=None,
                message=f'The {label} has not been identified.'))
    start, end = calendar_date(request.period_start), calendar_date(request.period_end)
    start_unprinted = request.period_start_unprinted and not request.period_start and bool(end)
    if (request.period_start or request.period_end) and not start_unprinted and (not start or not end or start > end):
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
