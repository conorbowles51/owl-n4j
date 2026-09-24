"""Reconcile saved corrections and the current ledger before adding legacy rows."""
from copy import deepcopy
from sqlalchemy import select
from postgres.models.financial import FinancialTransaction
from services.financial.statement_details import saved_details
from services.financial.statement_import import StatementImportRequest
from services.financial.statement_admission import assess_admission


def assess_saved_additions(session, document, period, metadata, currency, *, no_activity_confirmed=False):
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
    rows = list(session.scalars(select(FinancialTransaction).where(FinancialTransaction.case_id == document.case_id,
        FinancialTransaction.source_document_id == document.id, FinancialTransaction.superseded_by_id.is_(None))))
    current = {(t.provenance or {}).get('statement_import_original', {}).get('id'):t for t in rows}
    originals = {r['id']:r for r in proposal['rows']}
    sign = -1 if proposal['metadata'].get('balance_convention') == 'liability_owed' else 1
    # Balances entered after an older import have explicit page provenance;
    # include those controls even when the original reader missed them entirely.
    for role, balance in metadata.get('statement_details_review', {}).get('balances', {}).items():
        if role not in ('opening', 'closing') or balance.get('amount_minor') is None:
            continue
        if any(r.get('kind') == 'balance' and r.get('fields', {}).get('description', '').strip().lower() == role + ' balance' for r in proposal['rows']):
            continue
        if balance.get('page') not in proposal.get('page_numbers', []):
            continue
        raw['rows'] = [row for row in raw['rows'] if row['id'] != 'manual:' + role + '-balance']
        raw['rows'].append(dict(id='manual:' + role + '-balance', excluded=True, manual_page=balance['page'],
            date='', description=role + ' balance', amount_minor='0', direction=None, balance_minor=balance['amount_minor'], reason='Saved statement balance correction.'))
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
            if role in ('opening balance','closing balance'):row['balance_minor']=str(sign*value) if value is not None else None
    request=StatementImportRequest.model_validate(raw)
    result=assess_admission(proposal,request)
    if no_activity_confirmed:
        request = request.model_copy(update=dict(no_activity_confirmed=True, no_activity_revision=result['revision']))
        result = assess_admission(proposal, request)
    # Rows not represented in the old statement request cannot be silently
    # ignored when deciding whether newly repaired readings may enter totals.
    ids={r['id'] for r in raw['rows']}
    if any((t.provenance or {}).get('statement_import_original',{}).get('id') not in ids for t in rows):
        result.update(can_import=False,status='needs_review')
        result['blockers'].append(dict(kind='saved_rows',row_id=None,message='Compare the saved transactions with this statement; some have no matching row in its earlier reading.'))
    return result
