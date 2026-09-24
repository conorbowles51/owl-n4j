"""One admission rule for individual, batch and recovery statement payments.

This verifies the reviewed ledger against available printed controls. It does
not turn a missing control, equal balances, or an exception note into evidence
that extraction was complete.
"""
from services.financial.pdf_candidates import _digest, PdfMappingError
from services.financial.review_arithmetic import check_proposed_rows, arithmetic_problems
from services.financial.import_issues import retained_issues, calendar_date

POLICY = 'reconciled-statement-v1'


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
    return dict(policy=POLICY, revision=revision, can_import=not unique,
        status=('needs_review' if unique else 'confirmed_no_activity' if no_payments else 'reconciled'),
        no_activity_confirmed=no_payments and not unique, blockers=unique)


def require_admission(proposal, request, arithmetic=None):
    result = assess_admission(proposal, request, arithmetic)
    if not result['can_import']:
        messages = ' '.join(p['message'] for p in result['blockers'][:4])
        raise PdfMappingError('Statement remains in review; no payments were imported. ' + messages, 422)
    return result
