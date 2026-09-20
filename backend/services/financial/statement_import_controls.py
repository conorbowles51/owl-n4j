"""Retain source-bound balance readings from the normal statement import."""
from services.financial.locators import Locator
from services.financial.pdf_candidates import _digest
from services.financial.import_issues import usable_balance


def _control(role, row, original):
    if original.get('manual_balance'):
        return dict(role=role, row_id=row['id'], original_text='', reviewed_value=row['balance_minor'],
            locator=dict(kind='page_only', page=row['manual_page']), reason=row['reason'])
    column = int(original['fields']['balance_column'])
    cells = [cell for cell in original['source_cells'] if cell['column_index'] == column]
    if len(cells) != 1:
        raise ValueError('The balance source cell is ambiguous.')
    cell = cells[0]
    locator = Locator.from_json(cell['locator'])
    if locator.rectangle is None or locator.page != original['page_number']:
        raise ValueError('The balance source position is missing.')
    return dict(role=role, row_id=row['id'], original_text=cell['expected_text'],
                reviewed_value=row['balance_minor'], locator=locator.to_json(), reason=row['reason'])


def retain_import_controls(document, period, request, originals, openings, closings, *, balance_convention='liability_owed'):
    controls = []
    for role, rows in (('opening', openings), ('closing', closings)):
        if len(rows) == 1:
            row = rows[0]
            controls.append(_control(role, row.model_dump(mode='json'), originals[row.id]))
    record = dict(period_id=str(period.id), account_id=str(period.account_id),
                  source_document_id=str(document.id), currency=request.currency,
                  balance_convention=balance_convention, controls=controls)
    document.metadata_ = {**document.metadata_, 'statement_import_controls': record,
                          'statement_import_controls_sha256': _digest(record)}


def read_import_controls(period, document, evidence):
    """Validate against the retained review, not today's extraction or guesses."""
    metadata = document.metadata_ or {}
    from services.financial.statement_details import reviewed_controls
    record = metadata.get('statement_import_controls')
    if record is None:
        return reviewed_controls(period, document, None)
    original = metadata['statement_import_original']
    request = metadata['statement_import_request']
    if (_digest(record) != metadata['statement_import_controls_sha256']
            or _digest(original) != metadata['statement_import_original_sha256']
            or _digest(request) != metadata['statement_import_request_sha256']):
        raise ValueError('The retained balance review has changed.')
    original_account_id = str(period.account_id)
    if metadata.get('statement_details_review'):
        reviewed_controls(period, document, None)  # Validate current binding before reading its history.
        original_account_id = metadata['statement_details_history'][0]['before']['account_id']
    if (record['period_id'] != str(period.id) or record['account_id'] != original_account_id
            or record['source_document_id'] != str(document.id)
            or record['currency'] != period.currency or request['currency'] != period.currency
            or original['currency'] != period.currency
            or original['case_id'] != str(period.case_id)
            or original['evidence_file_id'] != str(evidence.id)
            or record['balance_convention'] not in ('liability_owed', 'asset_balance')
            or (original['metadata'].get('balance_convention') or 'asset_balance') != record['balance_convention']):
        raise ValueError('The balance review does not match this statement.')
    originals = {row['id']: row for row in original['rows']}
    from services.financial.manual_balances import manual_balance
    for row in request['rows']:
        balance = manual_balance(row, original)
        if balance:
            originals[row['id']] = balance
    expected = []
    for role in ('opening', 'closing'):
        matches = [row for row in request['rows'] if row['excluded'] and usable_balance(row['balance_minor'], record['balance_convention'])
                   and originals.get(row['id'], {}).get('kind') == 'balance'
                   and originals[row['id']]['fields'].get('description', '').lower() == f'{role} balance']
        if len(matches) == 1:
            row = matches[0]
            amount = int(row['balance_minor'])
            minimum = -9223372036854775808 if record['balance_convention'] == 'asset_balance' else -9223372036854775807
            if not minimum <= amount <= 9223372036854775807:
                raise ValueError('The reviewed balance exceeds the supported range.')
            expected.append(_control(role, row, originals[row['id']]))
    if expected != record['controls']:
        raise ValueError('The balance citations do not match the saved review.')
    if document.page_count is not None and any(Locator.from_json(c['locator']).page > document.page_count for c in expected):
        raise ValueError('A balance citation exceeds the source page count.')
    closure = original['metadata'].get('account_closure')
    closure_citation = None
    if closure:
        matches = [r for r in original['rows'] if r['page_number'] == closure['page_number'] and r['table_index'] == closure['table_index']
                   and r['row_index'] == closure['row_index'] and r['fields'].get('account_closed_on') == closure['date']]
        if len(matches) != 1 or matches[0]['source_cells'] != closure['source_cells'] or not closure['source_cells']:
            raise ValueError('The retained closure notice does not match its source row.')
        locator = Locator.from_json(closure['source_cells'][0]['locator'])
        if locator.page != closure['page_number'] or document.page_count is not None and locator.page > document.page_count:
            raise ValueError('The account closure source exceeds the document.')
        closure_citation = dict(date=closure['date'], original_text=' '.join(c['expected_text'] for c in closure['source_cells']), locator=locator.to_json())
    reasons = [f"{c['role'].title()}: {c['reason']}" for c in expected if c['reason']]
    return reviewed_controls(period, document, dict(import_source_document_id=str(document.id), finalization_id=None,
                currency=record['currency'], balance_convention=record['balance_convention'],
                reason='; '.join(reasons) or 'Account-summary balances accepted at import.',
                controls=expected, account_closure=closure_citation,
                scope='Amounts and PDF locations saved with this import. Corrections preserve the original printed text.'))
