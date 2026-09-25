"""Reconcile saved corrections and the current ledger before adding legacy rows."""
from copy import deepcopy
from sqlalchemy import select
from postgres.models.financial import FinancialTransaction
from services.financial.statement_details import saved_details
from services.financial.statement_import import StatementImportRequest
from services.financial.statement_admission import assess_admission, explain_blockers, POLICY


def assess_saved_additions(session, document, period, metadata, currency, *, no_activity_confirmed=False, transactions=None):
    proposal = deepcopy(metadata['statement_import_original'])
    raw = {**deepcopy(metadata['statement_import_request']), **saved_details(document), 'currency':currency}
    from services.financial.currency_correction import rescale_minor
    original_currency = metadata['statement_import_request'].get('currency')
    if original_currency and original_currency != currency:
        for row in raw['rows']:
            for key in ('amount_minor', 'balance_minor'):
                value = row.get(key)
                if value is None or (isinstance(value, str) and value.lstrip('-').isdigit()):
                    row[key] = rescale_minor(value, original_currency, currency)
    corrections = {r['id']:r.get('correction') or r['fields'] for r in metadata.get('statement_incomplete_records', [])}
    # Investigator additions are retained alongside the sealed reading, not
    # written into the original extraction or its original import request.
    ids = {r['id'] for r in raw['rows']}
    for item in metadata.get('statement_incomplete_records', []):
        if item['id'] not in ids and item['original'].get('kind') == 'manual_entry':
            raw['rows'].append(deepcopy(item.get('correction') or item['fields']))
    rows = list(transactions) if transactions is not None else list(session.scalars(select(FinancialTransaction).where(FinancialTransaction.case_id == document.case_id,
        FinancialTransaction.source_document_id == document.id, FinancialTransaction.superseded_by_id.is_(None))))
    current = {(t.provenance or {}).get('statement_import_original', {}).get('id'):t for t in rows}
    originals = {r['id']:r for r in proposal['rows']}
    sign = -1 if proposal['metadata'].get('balance_convention') == 'liability_owed' else 1
    controls = metadata.get('statement_details_review', {}).get('balances', {})
    for i, row in enumerate(raw['rows']):
        row = deepcopy(corrections.get(row['id'],row)); raw['rows'][i]=row
        tx=current.get(row['id'])
        if tx:
            day=tx.transaction_date or tx.posted_date or tx.value_date or tx.effective_date
            row.update(excluded=tx.ledger_status!='admitted', amount_minor=str(tx.amount_minor), direction=tx.direction,
                description=tx.description, balance_minor=str(sign*tx.running_balance_minor) if tx.running_balance_minor is not None else None,
                reason='Current saved transaction values.')
            if not row.get('date_unprinted'): row['date']=day.isoformat() if day else ''
        original=originals.get(row['id'],{})
        if period and original.get('kind')=='balance':
            role=original.get('fields',{}).get('description','').strip().lower()
            value=period.opening_balance_minor if role=='opening balance' else period.closing_balance_minor if role=='closing balance' else None
            if role in ('opening balance','closing balance'):
                # A page-cited saved correction chooses one authoritative
                # control, even when the retained reading has several competing
                # balances. Do not turn every old candidate into that control.
                row['balance_minor'] = None if role.removesuffix(' balance') in controls else str(sign*value) if value is not None else None
    pages = proposal.get('statement_page_numbers') or sorted({source['page_number'] for source in proposal.get('sources', [])}) or proposal.get('page_numbers', [])
    for role, balance in controls.items():
        if role not in ('opening', 'closing'):
            continue
        # An explicit clear must also clear an earlier manual control. Original
        # source rows and the original import request remain sealed and intact.
        raw['rows'] = [row for row in raw['rows'] if row['id'] != 'manual:' + role + '-balance']
        if balance.get('amount_minor') is None or balance.get('page') not in pages:
            continue
        raw['rows'].append(dict(id='manual:' + role + '-balance', excluded=True, manual_page=balance['page'],
            date='', description=role + ' balance', amount_minor='0', direction=None,
            balance_minor=balance['amount_minor'], reason='Saved statement balance correction.'))
    request=StatementImportRequest.model_validate(raw)
    result=assess_admission(proposal,request)
    if no_activity_confirmed:
        request = request.model_copy(update=dict(no_activity_confirmed=True, no_activity_revision=result['revision']))
        result = assess_admission(proposal, request)
    # Rows not represented in the old statement request cannot be silently
    # ignored when deciding whether newly repaired readings may enter totals.
    ids={r['id'] for r in raw['rows']}
    if any((t.provenance or {}).get('statement_import_original',{}).get('id') not in ids for t in rows):
        result.update(can_import=False,status='needs_review',no_activity_confirmed=False)
        result['blockers'].append(dict(kind='saved_rows',row_id=None,message='Compare the saved transactions with this statement; some have no matching row in its earlier reading.'))
    if len(current) != len(rows):
        result.update(can_import=False,status='needs_review',no_activity_confirmed=False)
        result['blockers'].append(dict(kind='saved_rows',row_id=None,message='More than one current saved payment refers to the same source reading. Compare those payments before confirming reconciliation.'))
    if any(t.case_id != document.case_id or t.source_document_id != document.id or
           t.statement_period_id != period.id or t.account_id != period.account_id or t.currency != currency for t in rows):
        result.update(can_import=False,status='needs_review',no_activity_confirmed=False)
        result['blockers'].append(dict(kind='saved_rows',row_id=None,message='The saved payments do not all belong to this account, currency and statement period. Review their assignments before confirming reconciliation.'))
    result['blockers'] = explain_blockers(result['blockers'], proposal, raw)
    return result


def current_saved_assessment(session, document, period, *, transactions=None):
    """Project current saved checks without certifying an old or changed import.

    ``transactions`` may be the caller's preloaded, nonsuperseded ORM rows for
    this source and period. No metadata, ledger row or original is written.
    """
    from services.financial.account_history import snapshot
    from services.financial.pdf_candidates import _digest, PdfMappingError
    from pydantic import ValidationError
    metadata = document.metadata_ or {}
    prior = metadata.get('statement_admission') or {}
    rows = list(transactions) if transactions is not None else list(session.scalars(select(FinancialTransaction).where(
        FinancialTransaction.case_id == document.case_id, FinancialTransaction.source_document_id == document.id,
        FinancialTransaction.superseded_by_id.is_(None))))
    current_snapshot = snapshot(period, rows) if period else None
    current = bool(current_snapshot and prior.get('ledger_snapshot') == current_snapshot)
    try:
        if not period or any(_digest(metadata.get(name)) != metadata.get(name + '_sha256')
                for name in ('statement_import_original', 'statement_import_request')):
            raise ValueError('Saved source review is unavailable or changed.')
        review = metadata.get('statement_details_review')
        if review and _digest(review) != metadata.get('statement_details_review_sha256'):
            raise ValueError('Saved detail review is changed.')
        result = assess_saved_additions(session, document, period, metadata, period.currency,
            no_activity_confirmed=current and bool(prior.get('no_activity_confirmed')), transactions=rows)
        current = current and prior.get('policy') == POLICY and prior.get('revision') == result['revision']
    except (KeyError, TypeError, ValueError, ValidationError, PdfMappingError):
        result = dict(policy=POLICY, revision=_digest(dict(source=str(document.id), ledger=current_snapshot)),
            can_import=False, status='needs_review', no_activity_confirmed=False, checks=[], calculation=None,
            assessment_current=False, blockers=explain_blockers([dict(kind='saved_source', row_id=None,
                message='The saved reading or its corrections cannot be verified. Open the saved review and compare its source before confirming reconciliation.')]))
        return result
    # Freshly calculated failures are useful immediately. A successful current
    # calculation alone must not silently certify an unreviewed historical import.
    if result['can_import'] and (not current or not prior.get('can_import')):
        kind = 'assessment_stale' if prior else 'assessment_missing'
        result.update(can_import=False, status='needs_review', no_activity_confirmed=False, assessment_current=False)
        result['blockers'].extend(explain_blockers([dict(kind=kind, row_id=None,
            message=('Saved values changed after the last reconciliation. Review the current statement and save its checks again.' if prior else
                     'This older import has no current reconciliation confirmation. Review the saved statement before confirming its checks.'))]))
    else:
        result['assessment_current'] = True
    return result


def refresh_saved_assessment(session, document, period, *, no_activity_confirmed=False):
    """Record current checks after an explicit saved correction, in its commit."""
    from services.financial.account_history import snapshot
    metadata = deepcopy(document.metadata_ or {})
    rows = list(session.scalars(select(FinancialTransaction).where(
        FinancialTransaction.case_id == document.case_id, FinancialTransaction.source_document_id == document.id,
        FinancialTransaction.superseded_by_id.is_(None))))
    prior = metadata.get('statement_admission') or {}
    current_snapshot = snapshot(period, rows)
    admission = assess_saved_additions(session, document, period, metadata, period.currency,
        no_activity_confirmed=no_activity_confirmed, transactions=rows)
    if (not no_activity_confirmed and prior.get('no_activity_confirmed') and
            prior.get('ledger_snapshot') == current_snapshot and prior.get('policy') == POLICY and
            prior.get('revision') == admission['revision']):
        admission = assess_saved_additions(session, document, period, metadata, period.currency,
            no_activity_confirmed=True, transactions=rows)
    admission['ledger_snapshot'] = current_snapshot
    metadata['statement_admission'] = admission
    metadata['statement_import_issues'] = admission['blockers'] + [
        issue for issue in metadata.get('statement_import_issues', []) if issue.get('kind') == 'coverage']
    document.metadata_ = metadata
    return admission
