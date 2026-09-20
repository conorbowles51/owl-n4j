"""Current receipts for batch items, including later replacement readings."""
from sqlalchemy import select, func, case
from postgres.models.financial import FinancialSourceDocument as Source, FinancialTransaction as Row, FinancialStatementPeriod as Period


def current_imports(session, case_id, source_ids):
    def fetch(ids):
        return {str(row.id): row for row in session.execute(select(Source.id, Source.status, Source.superseded_by_id,
            Source.metadata_['statement_import_request']['replaces_source_document_id'].as_string().label('replaces'),
            Source.metadata_['statement_import_issues'].label('issues'),
            Source.metadata_['statement_incomplete_records'].label('records'),
            Source.metadata_['statement_details_review'].label('review'),
            Source.metadata_['statement_account_id'].as_string().label('account'),
            Source.metadata_['statement_import_request']['currency'].as_string().label('currency'),
            *[Source.metadata_['statement_import_request'][key].as_string().label(key)
                for key in ('holder', 'account_number', 'institution', 'period_start', 'period_end')])
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
    periods = {}
    for period in session.scalars(select(Period).where(Period.case_id == case_id, Period.source_document_id.in_(ids))):
        periods.setdefault(period.source_document_id, []).append(period)
    sums = {}
    for sid, currency, credits, debits in session.execute(select(Row.source_document_id, Row.currency,
            func.sum(case((Row.direction == 'credit', Row.amount_minor), else_=0)),
            func.sum(case((Row.direction == 'debit', Row.amount_minor), else_=0)))
            .where(Row.case_id == case_id, Row.source_document_id.in_(ids), Row.ledger_status == 'admitted',
                Row.superseded_by_id.is_(None)).group_by(Row.source_document_id, Row.currency)):
        sums.setdefault(sid, {})[currency] = (credits or 0, debits or 0)
    def balance_status(row):
        controls = periods.get(row.id, [])
        if len(controls) != 1 or any(not r.get('resolved_transaction_id') for r in row.records or []):
            return 'unavailable'
        period = controls[0]
        if period.opening_balance_minor is None or period.closing_balance_minor is None:
            return 'unavailable'
        totals = sums.get(row.id, {})
        if set(totals) - {period.currency}:
            return 'unavailable'
        credits, debits = totals.get(period.currency, (0, 0))
        return 'matches' if period.opening_balance_minor + credits - debits == period.closing_balance_minor else 'difference'
    return {identifier: dict(source_document_id=str(row.id), issues=row.issues or [], records=row.records or [],
        review={**(row.review or {}), 'details': {
            **{key:getattr(row, key) or '' for key in ('holder', 'account_number', 'institution', 'period_start', 'period_end')},
            **(row.review or {}).get('details', {})}}, account_id=row.account, currency=(row.review or {}).get('currency') or row.currency,
        transaction_count=counts.get(row.id, 0), balance_status=balance_status(row)) for identifier, row in current.items()}
