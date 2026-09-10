"""Current ledger sides against sealed, source-bound investigator total readings.

A matching total is a comparison, not certification of complete extraction. This
never substitutes for native format controls or changes a document's proof class.
"""
from postgres.models.evidence import EvidenceFile
from services.financial.ledger_source import _statement_controls, LedgerSourceError


def compare_printed_totals(controls, *, credits, debits):
    if any(type(value) is not int or value < 0 for value in (credits, debits)):
        raise ValueError('Current totals must be exact nonnegative minor units.')
    result = []
    for role, actual in (('credits_total', credits), ('debits_total', debits)):
        matches = [c for c in (controls or {}).get('controls', []) if c['role'] == role]
        if len(matches) > 1:
            raise ValueError('Repeated printed direction control.')
        if not matches:
            result.append(dict(role=role, status='unavailable', printed_minor=None,
                current_minor=str(actual), difference_minor=None, source=None))
            continue
        control = matches[0]
        raw = control['reviewed_value']
        if not isinstance(raw, str) or not raw.isascii() or not raw.isdigit() or not 0 <= int(raw) <= 9223372036854775807:
            raise ValueError('Printed direction control is malformed.')
        delta = actual - int(raw)
        result.append(dict(role=role, status='balanced' if delta == 0 else 'unbalanced',
            printed_minor=raw, current_minor=str(actual), difference_minor=str(delta), source=control))
    return dict(checks=result, limitation='Current admitted row totals compared separately with retained investigator-read printed totals. Unknown controls remain unchecked. Matching totals do not establish complete extraction, native control validation or a higher proof class.')


def retained_total_controls(session, period, document):
    if document.document_type != 'pdf_selected_rows' or document.evidence_file_id is None:
        return None
    evidence = session.get(EvidenceFile, document.evidence_file_id)
    if evidence is None or evidence.case_id != period.case_id or document.case_id != period.case_id:
        raise LedgerSourceError('Printed total source ownership is inconsistent.')
    if evidence.sha256 != document.sha256_at_ingestion:
        raise LedgerSourceError('Printed total source digest differs from the recorded document.')
    return _statement_controls(session, period, document, evidence)
