"""Current receipts for batch items, including later replacement readings."""
from sqlalchemy import select, func
from postgres.models.financial import FinancialSourceDocument as Source, FinancialTransaction as Row


def current_imports(session, case_id, source_ids):
    def fetch(ids):
        return {str(row.id): row for row in session.execute(select(Source.id, Source.status, Source.superseded_by_id,
            Source.metadata_['statement_import_request']['replaces_source_document_id'].as_string().label('replaces'),
            Source.metadata_['statement_import_issues'].label('issues'),
            Source.metadata_['statement_incomplete_records'].label('records'),
            Source.metadata_['statement_details_review'].label('review'),
            Source.metadata_['statement_account_id'].as_string().label('account'),
            Source.metadata_['statement_import_request']['currency'].as_string().label('currency'))
            .where(Source.case_id == case_id, Source.id.in_(ids)))} if ids else {}
    found = fetch(source_ids)
    pending = set()
    for source in found.values():
        if source.superseded_by_id and str(source.superseded_by_id) not in found:
            pending.add(source.superseded_by_id)
    while pending:
        following = fetch(pending)
        found.update(following)
        pending = {row.superseded_by_id for row in following.values()
            if row.superseded_by_id and str(row.superseded_by_id) not in found}
    current = {}
    for identifier in source_ids:
        row = found.get(str(identifier)); seen = set()
        while row and row.superseded_by_id and row.id not in seen:
            seen.add(row.id)
            child = found.get(str(row.superseded_by_id))
            if child is None or child.replaces != str(row.id):
                break  # A duplicate exclusion is not a refreshed reading.
            row = child
        if row:
            current[str(identifier)] = row
    ids = [row.id for row in current.values() if row.status == 'admitted']
    counts = {identifier: count for identifier, count in session.execute(select(Row.source_document_id, func.count()).where(
        Row.case_id == case_id, Row.source_document_id.in_(ids), Row.ledger_status == 'admitted',
        Row.superseded_by_id.is_(None)).group_by(Row.source_document_id))} if ids else {}
    return {identifier: dict(source_document_id=str(row.id), issues=row.issues or [], records=row.records or [],
        review=row.review or {}, account_id=row.account, currency=(row.review or {}).get('currency') or row.currency,
        transaction_count=counts.get(row.id, 0)) for identifier, row in current.items()}
