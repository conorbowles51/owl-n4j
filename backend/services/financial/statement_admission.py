"""One admission rule for individual, batch and recovery statement payments.

This verifies the reviewed ledger against available printed controls. It does
not turn a missing control, equal balances, or an exception note into evidence
that extraction was complete.
"""
from services.financial.pdf_candidates import _digest, PdfMappingError
from services.financial.review_arithmetic import check_proposed_rows, arithmetic_problems
from services.financial.import_issues import retained_issues, calendar_date

POLICY = 'reconciled-statement-v1'


def explain_blockers(blockers, proposal=None, raw=None):
    """Keep stable navigation and exact values with each human explanation."""
    originals = {row['id']: row for row in (proposal or {}).get('rows', [])}
    edits = {row['id']: row for row in (raw or {}).get('rows', [])}
    result = []
    for problem in blockers:
        problem = dict(problem)
        kind, field, check = (problem.get(key) for key in ('kind', 'field', 'check'))
        row_id = problem.get('row_id')
        original = originals.get(row_id, {})
        page = problem.get('page') or original.get('page_number') or edits.get(row_id, {}).get('manual_page')
        if page is not None:
            problem['page'] = page
        if kind == 'no_activity':
            target = dict(kind='no_activity')
        elif kind == 'statement_detail':
            target = dict(kind='statement_field', field='period_start' if field == 'period' else field)
        elif kind in ('assessment_stale', 'assessment_missing', 'saved_rows', 'saved_source'):
            target = dict(kind='saved_review')
        elif kind == 'reading' and not row_id:
            target = dict(kind='assignment' if (proposal or {}).get('assignment_only') else 'source')
        elif check == 'closing_balance' and not row_id:
            target = dict(kind='balance', field='opening_closing')
        elif row_id:
            target = dict(kind='balance' if original.get('kind') in ('balance', 'statement_total') else 'transaction_field',
                row_id=row_id, field=field or ('balance' if check else 'review'))
        else:
            target = dict(kind='source')
        if page is not None:
            target['page'] = page
        problem['target'] = target
        problem['code'] = ':'.join(str(value) for value in (kind or 'reading', field or check or 'review'))
        problem['reason_id'] = _digest(dict(code=problem['code'], row_id=row_id, page=page))
        if field in ('amount', 'balance', 'date', 'direction', 'description', 'counterparty'):
            problem['expected_format'] = {
                'amount': 'A positive amount in the statement currency.',
                'balance': 'A signed printed balance, or blank when none is printed.',
                'date': 'A valid calendar date in YYYY-MM-DD format.',
                'direction': 'Credit (money in) or debit (money out).',
                'description': 'The transaction description printed on the source.',
                'counterparty': 'A name of at most 512 characters.',
            }[field]
            key = {'amount': 'amount_minor', 'balance': 'balance_minor'}.get(field, field)
            value = edits.get(row_id, {}).get(key)
            if field in ('amount', 'balance', 'date', 'direction') and isinstance(value, str):
                problem['observed_value'] = value[:64]
                if field in ('amount', 'balance'):
                    problem['invalid_characters'] = sorted({f'U+{ord(char):04X}' for char in value if char not in '-0123456789'})
        result.append(problem)
    return result


def assess_admission(proposal, request, arithmetic=None):
    raw = request.model_dump(mode='json')
    arithmetic = arithmetic or check_proposed_rows(proposal, raw['rows'])
    revision = _digest(dict(policy=POLICY, checks=arithmetic['checks_revision'], details={
        key: raw.get(key) for key in ('currency', 'holder', 'account_number', 'institution', 'period_start', 'period_end')}))
    blockers = retained_issues(proposal, request, arithmetic=arithmetic)
    for field, label in [('institution', 'bank'), ('period_start', 'statement start date'), ('period_end', 'statement end date')]:
        if not raw.get(field) or (field.startswith('period_') and not calendar_date(raw[field])):
            blockers.append(dict(kind='statement_detail', field=field, row_id=None, message=f'Enter the {label} printed on this statement.'))
    closing = next(c for c in arithmetic['checks'] if c['kind'] == 'closing_balance')
    if closing['status'] == 'unavailable':
        blockers.append(dict(kind='arithmetic', check='closing_balance', row_id=None,
            message='Enter one opening and one closing balance from the statement, and complete every selected payment, to reconcile this period.'))
    # An optional total absent from the source is not a blocker. An identified
    # but unreadable/ambiguous printed control must be resolved.
    for check in arithmetic['checks']:
        if check['status'] != 'unavailable' or not check['kind'].endswith('_total'):
            continue
        role = check['kind'].removesuffix('_total')
        controls = [r for r in proposal['rows'] if r['kind'] == 'statement_total' and
            ((role in ('credit', 'debit') and not r['fields'].get('total_scope') and r['fields'].get('total_direction') == role)
             or r['fields'].get('total_scope') == role)]
        if controls:
            blockers.append(dict(kind='arithmetic', check=check['kind'], row_id=controls[0]['id'], page=controls[0].get('page_number'),
                message=f'Check the printed {role} total. It could not be compared with the selected payments.'))
    # A missed payment cannot be used to waive known printed running controls.
    # Statements without such controls still reconcile against their endpoints.
    running = next((check for check in arithmetic['checks'] if check['kind'] == 'running_balance'), {})
    if any(not row.get('excluded') and row.get('fields', {}).get('balance') not in (None, '') for row in proposal['rows']):
        for row_id in running.get('unplaced_row_ids', []):
            blockers.append(dict(kind='manual_placement', field='source_order_anchor', row_id=row_id,
                message='Choose where this added payment appears among the printed payments so its running balance interval can be checked.'))
    edits = {r.id:r for r in request.rows}
    for original in proposal['rows']:
        edit = edits.get(original['id'])
        if original['kind'] == 'transaction' and not original['excluded'] and edit and edit.excluded and not edit.reason.strip():
            blockers.append(dict(kind='excluded_payment', row_id=original['id'], page=original.get('page_number'),
                message='A detected payment was excluded. Confirm the reason against the source before reconciling.'))
    no_payments = not any(not r.excluded for r in request.rows)
    zero_directions = {r['fields'].get('total_direction') for r in proposal['rows'] if r['kind'] == 'statement_total' and
        r['fields'].get('printed_transaction_count') == '0'}
    printed_no_activity = zero_directions >= {'credit', 'debit'}
    reviewed_no_activity = bool(raw.get('no_activity_confirmed') and raw.get('no_activity_revision') == revision)
    if no_payments and not printed_no_activity and not reviewed_no_activity:
        blockers.append(dict(kind='no_activity', row_id=None,
            message='Check every page of this period and confirm that it contains no transactions. Equal balances alone do not establish no activity.'))
    if proposal.get('reading_failure') or proposal.get('assignment_only'):
        blockers.append(dict(kind='reading', row_id=None, message=proposal.get('reading_failure') or 'Assign the unallocated statement pages before importing.'))
    unique = []
    for blocker in blockers:
        if blocker not in unique: unique.append(blocker)
    calculation = dict(available=closing['status'] != 'unavailable', currency=raw.get('currency'),
        balance_convention=closing.get('balance_convention', 'asset_balance'),
        opening_minor=closing.get('opening_minor'), credit_minor=closing.get('credit_minor'), debit_minor=closing.get('debit_minor'),
        calculated_closing_minor=closing.get('expected_minor'), printed_closing_minor=closing.get('printed_minor'),
        difference_minor=closing.get('difference_minor'))
    return dict(policy=POLICY, revision=revision, can_import=not unique,
        status=('needs_review' if unique else 'confirmed_no_activity' if no_payments else 'reconciled'),
        no_activity_confirmed=no_payments and not unique, blockers=explain_blockers(unique, proposal, raw),
        checks=arithmetic['checks'], calculation=calculation, assessment_current=True)


def require_admission(proposal, request, arithmetic=None):
    result = assess_admission(proposal, request, arithmetic)
    if not result['can_import']:
        messages = ' '.join(p['message'] for p in result['blockers'][:4])
        raise PdfMappingError('Statement remains in review; no payments were imported. ' + messages, 422)
    return result
