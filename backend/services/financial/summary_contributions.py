"""Totals and their contributing readings captured together, without extra queries."""
from services.financial.ledger_summary import ledger_summary, LedgerSummaryError
from services.financial.working_totals import working_totals_from_readings


def summary_contributions(session, *, case_id, account_id=None, start_date=None, end_date=None, population='verified'):
    if population not in ('verified', 'working'):
        raise LedgerSummaryError('Choose working or verified readings.')
    captured = ledger_summary(session, case_id=case_id, account_id=account_id,
        start_date=start_date, end_date=end_date, capture_readings=True)
    result = (working_totals_from_readings(captured) if population == 'working'
              else {k: v for k, v in captured.items() if k not in ('readings', 'history_captured')})
    result['contributions'] = []
    result['has_credit_card_readings'] = False
    if not result['available']:
        return result
    for reading in captured['readings']:
        included = (reading['exclusion_reason'] in (None, 'proof_class_not_included')
                    if population == 'working' else reading['included'])
        if not included:
            continue
        row = reading['row']
        if reading.get('account', {}).get('account_type') == 'credit_card':
            result['has_credit_card_readings'] = True
        result['contributions'].append(dict(
            transaction_id=row['key'], ref_id=row['ref_id'], currency=row['currency'],
            amount_minor=row['amount_minor'], direction=row['direction'],
            ordering_date=row['ordering_date'], proof_class=row['proof_class'],
            source_proof_class=reading['source']['proof_class'],
            source_document_id=reading['source']['id']))
    return result
