"""Source-proven additions, never replacement, for deployment recovery.

The planner does not write. Ambiguous source matches and manual decisions remain
review work. The writer is called under the case/evidence/document locks, and its
receipt commits with the payments so a restart cannot append the same reading.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from sqlalchemy import select, func
from services.financial.pdf_candidates import PdfMappingError, _digest
from services.financial.import_batches import initial_request
from services.financial.statement_import import StatementImportRequest, check_import_request, _primary_date_role
from services.financial.statement_details import saved_currency
from services.financial.import_issues import incomplete_records
from services.financial.review_arithmetic import check_proposed_rows, arithmetic_problems
from postgres.models.financial import FinancialTransaction


def address(row):
    keys = ('page_number', 'table_index', 'row_index')
    values = tuple(row.get(key) for key in keys)
    return values if all(isinstance(value, int) and value >= 0 for value in values) and values[0] > 0 else None


def value_key(row):
    return (row.get('date') or row.get('booking_date') or row.get('value_date'),
        str(row.get('amount_minor')), row.get('direction'))


def plan_additions(proposal, document, transactions):
    metadata = document.metadata_ or {}
    original = metadata.get('statement_import_original')
    saved = metadata.get('statement_import_request')
    if not original or not saved or _digest(original) != metadata.get('statement_import_original_sha256') or _digest(saved) != metadata.get('statement_import_request_sha256'):
        raise PdfMappingError('The earlier import needs a source comparison. Its saved records are unchanged.', 409)
    if document.status != 'admitted' or proposal.get('recovered_saved_section'):
        raise PdfMappingError('This import has a reviewed disposition or account split. Open its saved records.', 409)
    if proposal.get('saved_review') or proposal.get('previous_saved_review'):
        raise PdfMappingError('An investigator has saved a review. Compare that work with the new reading before adding payments.', 409)
    if proposal.get('currency') != saved_currency(document):
        raise PdfMappingError('The new reading and saved currency differ. Review the currency; saved values were kept.', 409)
    for key in ('account_number', 'institution', 'period_start', 'period_end'):
        before = (original.get('metadata') or {}).get(key)
        after = (proposal.get('metadata') or {}).get(key)
        # Parser improvements may fill a previously missing value, but cannot
        # silently map a changed account/period onto an existing import.
        if before and after and str(before).strip().casefold() != str(after).strip().casefold():
            raise PdfMappingError('The new reading identifies different account or period details. Compare the source sections.', 409)
    raw = initial_request(proposal)
    request = StatementImportRequest.model_validate(raw)
    originals = check_import_request(proposal, request)
    if incomplete_records(proposal, request):
        raise PdfMappingError('The new reading still has incomplete payments. Review them beside the source.', 409)
    checks = check_proposed_rows(proposal, raw['rows'])
    if arithmetic_problems(checks):
        raise PdfMappingError('The new reading does not agree with the printed controls. Review the statement before adding payments.', 409)

    old_edits = {row['id']: row for row in saved['rows']}
    known = defaultdict(list)
    for row in original['rows']:
        if address(row):
            known[address(row)].append(row)
    for entry in metadata.get('statement_recovery_additions', {}).values():
        for row in entry.get('originals', []):
            if address(row):
                known[address(row)].append(row)

    # Include superseded/excluded originals: an investigator's correction or
    # exclusion must never be resurrected as a "missing" payment.
    transaction_addresses = {}
    manual_values = Counter()
    all_values = set()
    for tx in transactions:
        provenance = tx.provenance or {}
        row = provenance.get('statement_import_original', {})
        location = address(row)
        if location:
            transaction_addresses[location] = row
        key = (str(tx.transaction_date or tx.posted_date or tx.value_date or tx.effective_date), str(tx.amount_minor), tx.direction)
        all_values.add(key)
        if not location:
            manual_values[key] += 1
        if row.get('fields'):
            all_values.add(value_key(row['fields']))

    candidates = [row for row in request.rows if not row.excluded]
    additions, matched, reasons = [], 0, []
    resolving = {}
    incompletes = {r['id']: r for r in metadata.get('statement_incomplete_records', [])}
    for row in candidates:
        source = originals[row.id]
        location = address(source)
        if not location or not source.get('source_cells'):
            reasons.append('A recovered payment has no precise printed row location.')
            continue
        prior = known.get(location, [])
        if location in transaction_addresses:
            before = transaction_addresses[location]
            def printed(row):
                return [" ".join(cell.get('expected_text', '').split()) for cell in row.get('source_cells', [])]
            if not printed(before) or printed(before) != printed(source):
                reasons.append('The layout of a saved payment changed. Compare source locations before adding payments.')
            else:
                matched += 1
            continue
        if prior:
            if len(prior) != 1:
                reasons.append('More than one earlier reading matches a recovered row.')
                continue
            old = prior[0]
            edit = old_edits.get(old['id'])
            incomplete = incompletes.get(old['id'])
            baseline = next((r for r in initial_request(original)['rows'] if r['id'] == old['id']), None)
            from services.financial.statement_import import DraftImportRow
            untouched = bool(edit and baseline and DraftImportRow.model_validate(edit) == DraftImportRow.model_validate(baseline))
            if incomplete and not incomplete.get('correction') and not incomplete.get('resolved_transaction_id') and untouched:
                resolving[row.id] = old['id']
            elif old.get('kind') == 'unclassified' and untouched:
                # Earlier readers left unmatched text excluded by default. That
                # default is not an investigator's decision to exclude a payment.
                pass
            else:
                reasons.append('A recovered row overlaps an earlier selection or correction. Compare it first.')
                continue
        key = value_key(row.model_dump())
        if manual_values[key]:
            reasons.append('A recovered payment may duplicate a manually added payment. Compare the occurrences.')
            continue
        if key in all_values:
            reasons.append('A recovered payment has the same date, amount and direction as an existing payment at another source location.')
            continue
        additions.append((row, source))
    if additions and manual_values:
        reasons.append('This statement also contains manually positioned payments. Compare them with the recovered rows before adding payments.')
    if reasons:
        # One atomic statement decision avoids half-recovered ambiguous scopes.
        raise PdfMappingError(' '.join(dict.fromkeys(reasons)), 409)
    if additions and not any(check.get('status') == 'matches' and check.get('kind') in ('closing_balance', 'credit_total', 'debit_total', 'running_balance') for check in checks['checks']):
        raise PdfMappingError('New payments need a source comparison because no printed control verifies this reading.', 409)
    return dict(additions=additions, matched=matched, resolving=resolving, checks=checks,
        revision=_digest(dict(source=str(document.id), reading=proposal['revision'])))


def append_recovered(session, *, document, proposal, plan, run, actor, release):
    """Caller commits this together with the durable per-file outcome."""
    from services.financial.imported_records import transaction_draft
    from services.financial.transactions import record_transactions
    from services.financial.reconcile import reconcile_period
    metadata = deepcopy(document.metadata_)
    receipts = metadata.setdefault('statement_recovery_additions', {})
    if plan['revision'] in receipts:
        return 0
    from services.financial.statement_details import _load
    _, period, account = _load(session, document.case_id, document.id, lock=True)
    account_id = account.id
    position = session.scalar(select(func.max(FinancialTransaction.row_index)).where(
        FinancialTransaction.case_id == document.case_id, FinancialTransaction.source_document_id == document.id))
    sign = -1 if metadata['statement_import_original']['metadata'].get('balance_convention') == 'liability_owed' else 1
    drafts = [transaction_draft(row, original, account_id=account_id, period_id=period.id if period else None,
        currency=saved_currency(document), position=(position if position is not None else -1) + index + 1,
        actor=actor, balance_sign=sign, period_end=metadata['statement_import_request'].get('period_end', ''),
        session=session, case_id=document.case_id) for index, (row, original) in enumerate(plan['additions'])]
    for draft in drafts:
        draft.provenance['automatic_statement_recovery'] = dict(release=release, reading_revision=proposal['revision'])
    written = record_transactions(session, run, document, drafts, retain_prior_versions=True) if drafts else []
    receipts[plan['revision']] = dict(release=release, reading_revision=proposal['revision'],
        transaction_ids=[str(tx.id) for tx in written], originals=[original for _, original in plan['additions']],
        checks=plan['checks'])
    for (row, _), tx in zip(plan['additions'], written):
        incomplete_id = plan['resolving'].get(row.id)
        for incomplete in metadata.get('statement_incomplete_records', []):
            if incomplete['id'] == incomplete_id:
                incomplete.update(resolved_transaction_id=str(tx.id), recovery_release=release)
    if written:
        # Recheck against the actual saved ledger, including corrections and
        # exclusions. Never leave resolved missing-field flags on the old import,
        # or replace a real balance difference with the unedited parser totals.
        from services.financial.statement_details import saved_details
        from services.financial.import_issues import retained_issues
        effective = initial_request(proposal)
        effective.update(saved_details(document))
        effective['currency'] = saved_currency(document)
        current = list(session.scalars(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == document.id,
            FinancialTransaction.case_id == document.case_id,
            FinancialTransaction.superseded_by_id.is_(None),
            FinancialTransaction.ledger_status != 'superseded')))
        by_location = {address((tx.provenance or {}).get('statement_import_original', {})): tx for tx in current}
        source_rows = {row['id']: row for row in proposal['rows']}
        for row in effective['rows']:
            original = source_rows[row['id']]
            tx = by_location.get(address(original)) if address(original) else None
            if row['excluded'] or tx is None:
                continue
            role = _primary_date_role(original.get('fields', {}))
            day = tx.posted_date if role == 'booking_date' else tx.value_date if role == 'value_date' else tx.transaction_date
            day = day or tx.transaction_date or tx.posted_date or tx.value_date or tx.effective_date
            row.update(excluded=tx.ledger_status != 'admitted', amount_minor=str(tx.amount_minor),
                direction=tx.direction, description=tx.description, counterparty=tx.counterparty_raw or '',
                balance_minor=str(tx.running_balance_minor * sign) if tx.running_balance_minor is not None else None)
            if not row.get('date_unprinted'):
                row['date'] = day.isoformat() if day else ''
        checked = StatementImportRequest.model_validate(effective)
        checks = check_proposed_rows(proposal, effective['rows'])
        receipts[plan['revision']]['previous_issues'] = metadata.get('statement_import_issues', [])
        metadata['statement_import_checks'] = checks
        metadata['statement_import_issues'] = retained_issues(proposal, checked, arithmetic=checks) + [
            issue for issue in metadata.get('statement_import_issues', []) if issue.get('kind') == 'coverage']
    document.metadata_ = metadata
    if period:
        reconcile_period(session, period)
    return len(written)
