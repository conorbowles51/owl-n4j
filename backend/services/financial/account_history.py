"""Source-backed account balances and dated activity, including quiet periods."""
from collections import defaultdict
from sqlalchemy import select, and_
from postgres.models.financial import FinancialStatementPeriod as Period, FinancialSourceDocument as Source, FinancialAccount as Account, FinancialTransaction as Transaction
from postgres.models.evidence import EvidenceFile
from services.financial.pdf_candidates import _digest, PdfMappingError
from services.financial.account_selection import holder_account_ids
from services.financial.account_consolidation import canonical_map, expand_account_ids


def snapshot(period, transactions):
    return _digest(dict(period={key:str(getattr(period, key)) for key in (
        'account_id', 'period_start', 'period_end', 'currency', 'opening_balance_minor', 'closing_balance_minor')},
        rows=sorted((dict(id=str(t.id), amount=str(t.amount_minor), direction=t.direction, status=t.ledger_status,
            dates=[str(t.transaction_date), str(t.posted_date), str(t.value_date), str(t.effective_date)],
            balance=str(t.running_balance_minor), description=t.description,
            superseded=str(t.superseded_by_id)) for t in transactions), key=lambda r:r['id'])))


def record_admission_snapshot(session, document, period):
    if not period: return
    session.flush()
    rows = list(session.scalars(select(Transaction).where(Transaction.case_id == document.case_id,
        Transaction.statement_period_id == period.id, Transaction.source_document_id == document.id,
        Transaction.superseded_by_id.is_(None))))
    metadata = dict(document.metadata_)
    metadata['statement_admission'] = {**metadata.get('statement_admission', {}), 'ledger_snapshot': snapshot(period, rows)}
    document.metadata_ = metadata


def account_history(session, *, case_id, account_id=None, account_ids=None, account_holders=None, start_date=None, end_date=None):
    if start_date and end_date and start_date > end_date:
        raise PdfMappingError('The start date must be on or before the end date.', 422)
    query = select(Period, Source, Account, EvidenceFile.original_filename).join(Source, Period.source_document_id == Source.id).join(Account, Period.account_id == Account.id).outerjoin(EvidenceFile, and_(Source.evidence_file_id == EvidenceFile.id, EvidenceFile.case_id == case_id)).where(
        Period.case_id == case_id, Source.case_id == case_id, Account.case_id == case_id, Source.status == 'admitted')
    selected = list(account_ids or []) + ([account_id] if account_id else [])
    if selected: query = query.where(Period.account_id.in_(expand_account_ids(session, case_id, selected)))
    if account_holders: query = query.where(Period.account_id.in_(holder_account_ids(session, case_id, account_holders)))
    if start_date: query = query.where((Period.period_end >= start_date) | Period.period_end.is_(None))
    if end_date: query = query.where((Period.period_start <= end_date) | Period.period_start.is_(None))
    pairs = list(session.execute(query.order_by(Period.period_start, Period.id).limit(5001)))
    if len(pairs) > 5000:
        raise PdfMappingError('This selection contains more than 5,000 statement periods. Choose fewer accounts or a shorter date range to compare the complete selection.', 422)
    rows = list(session.scalars(select(Transaction).where(Transaction.case_id == case_id,
        Transaction.statement_period_id.in_([p.id for p, _, _, _ in pairs]), Transaction.superseded_by_id.is_(None)))) if pairs else []
    by_period = defaultdict(list)
    for row in rows: by_period[row.statement_period_id].append(row)
    canonical = canonical_map(session, case_id)
    accounts = {a.id:a for a in session.scalars(select(Account).where(Account.case_id == case_id))}
    groups = {}
    for period, document, account, filename in pairs:
        if document.evidence_file_id and filename is None:
            raise PdfMappingError('A statement source could not be verified in this case. Review its source history before comparing account balances.', 409)
        metadata = document.metadata_ or {}
        if metadata.get('financial_import_removal'): continue
        current = [t for t in by_period[period.id] if t.source_document_id == document.id and t.account_id == period.account_id]
        admitted = [t for t in current if t.ledger_status == 'admitted' and t.currency == period.currency]
        from services.financial.saved_statement_admission import current_saved_assessment
        admission = current_saved_assessment(session, document, period, transactions=current)
        verified = bool(admission.get('can_import') and admission.get('assessment_current'))
        quiet = verified and admission.get('no_activity_confirmed') and not admitted
        # Different currencies and liability conventions are separate series,
        # even when the bank prints them on one account or inside one PDF.
        convention = (metadata.get('statement_import_original') or {}).get('metadata', {}).get('balance_convention')
        liability = convention == 'liability_owed' or account.account_type == 'credit_card'
        root = canonical[account.id]
        retained = accounts[root]
        key = f'{root}:{period.currency}:{"liability" if liability else "asset"}'
        group = groups.setdefault(key, dict(key=key, account_id=str(root), currency=period.currency,
            balance_kind='liability' if liability else 'asset',
            label=' · '.join(filter(None, [retained.holder_name, retained.institution_name, retained.identifier_as_printed])) or 'Account details missing', periods=[]))
        activity = {}
        undated = 0
        for tx in admitted:
            day = None if (tx.provenance or {}).get('date_basis') == 'statement_end_ordering_only' else tx.transaction_date or tx.posted_date or tx.value_date or tx.effective_date
            if day is None:
                undated += 1; continue
            entry = activity.setdefault(day.isoformat(), dict(date=day.isoformat(), count=0, credit_minor=0, debit_minor=0))
            entry['count'] += 1; entry[tx.direction + '_minor'] += tx.amount_minor
        sign = -1 if liability else 1
        group['periods'].append(dict(id=str(period.id), source_document_id=str(document.id), evidence_file_id=str(document.evidence_file_id) if document.evidence_file_id else None,
            filename=filename, start=period.period_start.isoformat() if period.period_start else None, end=period.period_end.isoformat() if period.period_end else None,
            opening_minor=str(sign * period.opening_balance_minor) if period.opening_balance_minor is not None else None,
            closing_minor=str(sign * period.closing_balance_minor) if period.closing_balance_minor is not None else None,
            status='confirmed_no_activity' if quiet else 'reconciled' if verified else 'needs_review',
            assessment_current=bool(admission.get('assessment_current')), blockers=admission.get('blockers', []),
            transaction_count=len(admitted), undated_count=undated,
            activity=[{**entry, 'credit_minor':str(entry['credit_minor']), 'debit_minor':str(entry['debit_minor'])} for _, entry in sorted(activity.items())]))
    return dict(case_id=str(case_id), groups=sorted(groups.values(), key=lambda g:(g['currency'],g['balance_kind'],g['label'],g['key'])), applied=False)
