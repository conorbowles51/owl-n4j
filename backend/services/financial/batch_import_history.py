"""Read-only current receipts for batch items and later replacement readings."""
from collections import defaultdict

from sqlalchemy import select

from postgres.models.financial import (
    FinancialSourceDocument as Source,
    FinancialStatementPeriod as Period,
    FinancialTransaction as Row,
)
from services.financial.saved_statement_admission import current_saved_assessment
from services.financial.statement_details import saved_currency, saved_details


def project_individual_receipts(session, case_id, items):
    """Project exact saved receipts for the lightweight batch list, read-only.

    This is a receipt lookup, not a new readiness or reconciliation assessment.
    Only an unambiguous admitted receipt for the same evidence version, bytes
    and statement key can finish an old pending review. Cross-file copies,
    reread geometry overlaps and replacement chains still belong to the full
    review; neither filenames nor account labels establish this identity.
    """
    from types import SimpleNamespace
    from postgres.models.evidence import EvidenceFile

    file_ids = {item.file_id for item in items if item.status in ('ready', 'attention')}
    if not file_ids:
        return items
    matches = defaultdict(list)
    # Select receipt identity only, never the potentially large original OCR
    # proposal or all payments. One shared query covers every listed batch.
    query = select(Source.id, Source.evidence_file_id,
        Source.metadata_['statement_import_statement_id'].as_string(),
        Source.metadata_['financial_import_removal']).join(
            EvidenceFile, EvidenceFile.id == Source.evidence_file_id).where(
        Source.case_id == case_id, EvidenceFile.case_id == case_id,
        Source.evidence_file_id.in_(file_ids), Source.status == 'admitted',
        Source.sha256_at_ingestion == EvidenceFile.sha256)
    for source_id, file_id, statement_key, removal in session.execute(query):
        if not removal:
            matches[(file_id, statement_key or '')].append(source_id)
    result = []
    for item in items:
        receipts = matches.get((item.file_id, item.statement_key or ''), [])
        if item.status not in ('ready', 'attention') or len(receipts) != 1:
            result.append(item)
            continue
        result.append(SimpleNamespace(id=item.id, batch_id=item.batch_id,
            file_id=item.file_id, statement_key=item.statement_key,
            status='imported', summary={**item.summary, 'can_import': False,
                'source_document_id': str(receipts[0])}, review_request=item.review_request))
    return result


def current_imports(session, case_id, source_ids):
    """Load shared source data once, then assess the current saved values.

    Stored import issues and admission results describe an earlier revision.
    They must not replace the current assessment after a payment/detail edit.
    Replacement chains are followed in bulk; duplicate exclusions are not
    replacements and never redirect the investigator to another statement.
    """
    source_ids = list(dict.fromkeys(source_ids))
    if not source_ids:
        return {}

    def fetch(ids):
        return {str(row.id): row for row in session.scalars(select(Source).where(
            Source.case_id == case_id, Source.id.in_(ids)))}

    found = fetch(source_ids)
    pending = {row.superseded_by_id for row in found.values()
               if row.superseded_by_id and str(row.superseded_by_id) not in found}
    while pending:
        following = fetch(pending)
        found.update(following)
        pending = {row.superseded_by_id for row in following.values()
                   if row.superseded_by_id and str(row.superseded_by_id) not in found}

    current = {}
    for identifier in source_ids:
        row = found.get(str(identifier))
        seen = set()
        while row and row.superseded_by_id and row.id not in seen:
            seen.add(row.id)
            child = found.get(str(row.superseded_by_id))
            replaces = ((child.metadata_ or {}).get('statement_import_request') or {}).get(
                'replaces_source_document_id') if child else None
            if child is None or replaces != str(row.id):
                break
            row = child
        if row:
            current[str(identifier)] = row

    ids = {row.id for row in current.values()}
    periods, transactions = defaultdict(list), defaultdict(list)
    if ids:
        for period in session.scalars(select(Period).where(
                Period.case_id == case_id, Period.source_document_id.in_(ids))):
            periods[period.source_document_id].append(period)
        # Include excluded/quarantined current rows in the assessment. Omitting
        # them would conceal assignment or reconciliation problems.
        for row in session.scalars(select(Row).where(
                Row.case_id == case_id, Row.source_document_id.in_(ids),
                Row.superseded_by_id.is_(None))):
            transactions[row.source_document_id].append(row)

    receipts = {}
    for document in {row.id: row for row in current.values()}.values():
        metadata = document.metadata_ or {}
        controls = periods[document.id]
        period = controls[0] if len(controls) == 1 else None
        rows = transactions[document.id]
        admission = current_saved_assessment(session, document,
            period if document.status == 'admitted' else None, transactions=rows)
        calculation = admission.get('calculation') or {}
        balance_status = 'unavailable'
        if any(check.get('status') == 'difference' for check in admission['checks']):
            balance_status = 'difference'
        elif calculation.get('available') and admission['can_import'] and admission['assessment_current']:
            balance_status = 'matches'
        details = saved_details(document)
        if period:
            details.update({key: getattr(period, key).isoformat() if getattr(period, key) else ''
                            for key in ('period_start', 'period_end')})
        receipts[document.id] = dict(
            source_document_id=str(document.id),
            issues=admission['blockers'],
            records=metadata.get('statement_incomplete_records') or [],
            review={**(metadata.get('statement_details_review') or {}), 'details': details},
            account_id=str(period.account_id) if period else metadata.get('statement_account_id'),
            currency=period.currency if period else saved_currency(document),
            transaction_count=sum(row.ledger_status == 'admitted' for row in rows)
                if document.status == 'admitted' else 0,
            balance_status=balance_status,
            admission=admission,
            checks=admission['checks'],
        )
    return {identifier: receipts[document.id] for identifier, document in current.items()}
