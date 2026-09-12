"""Retain source-bound balance readings from the normal statement import."""
from services.financial.locators import Locator
from services.financial.pdf_candidates import _digest


def _control(role, row, original):
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


def retain_import_controls(document, period, request, originals, openings, closings):
    controls = []
    for role, rows in (('opening', openings), ('closing', closings)):
        if len(rows) == 1:
            row = rows[0]
            controls.append(_control(role, row.model_dump(mode='json'), originals[row.id]))
    record = dict(period_id=str(period.id), account_id=str(period.account_id),
                  source_document_id=str(document.id), currency=request.currency,
                  balance_convention='liability_owed', controls=controls)
    document.metadata_ = {**document.metadata_, 'statement_import_controls': record,
                          'statement_import_controls_sha256': _digest(record)}


def read_import_controls(period, document, evidence):
    """Validate against the retained review, not today's extraction or guesses."""
    metadata = document.metadata_ or {}
    record = metadata.get('statement_import_controls')
    if record is None:
        return None  # Older imports did not retain this contract.
    original = metadata['statement_import_original']
    request = metadata['statement_import_request']
    if (_digest(record) != metadata['statement_import_controls_sha256']
            or _digest(original) != metadata['statement_import_original_sha256']
            or _digest(request) != metadata['statement_import_request_sha256']):
        raise ValueError('The retained balance review has changed.')
    if (record['period_id'] != str(period.id) or record['account_id'] != str(period.account_id)
            or record['source_document_id'] != str(document.id)
            or record['currency'] != period.currency or request['currency'] != period.currency
            or original['currency'] != period.currency
            or original['case_id'] != str(period.case_id)
            or original['evidence_file_id'] != str(evidence.id)
            or original['metadata'].get('balance_convention') != 'liability_owed'
            or record['balance_convention'] != 'liability_owed'):
        raise ValueError('The balance review does not match this statement.')
    originals = {row['id']: row for row in original['rows']}
    expected = []
    for role in ('opening', 'closing'):
        matches = [row for row in request['rows'] if row['excluded'] and row['balance_minor'] is not None
                   and originals.get(row['id'], {}).get('kind') == 'balance'
                   and originals[row['id']]['fields'].get('description', '').lower() == f'{role} balance']
        if len(matches) == 1:
            row = matches[0]
            amount = int(row['balance_minor'])
            if not -9223372036854775807 <= amount <= 9223372036854775807:
                raise ValueError('The reviewed balance exceeds the supported range.')
            expected.append(_control(role, row, originals[row['id']]))
    if expected != record['controls']:
        raise ValueError('The balance citations do not match the saved review.')
    if document.page_count is not None and any(Locator.from_json(c['locator']).page > document.page_count for c in expected):
        raise ValueError('A balance citation exceeds the source page count.')
    reasons = [f"{c['role'].title()}: {c['reason']}" for c in expected if c['reason']]
    return dict(import_source_document_id=str(document.id), finalization_id=None,
                currency=record['currency'], balance_convention=record['balance_convention'],
                reason='; '.join(reasons) or 'Account-summary balances accepted at import.',
                controls=expected,
                scope='Amounts and PDF locations saved with this import. Corrections preserve the original printed text.')
