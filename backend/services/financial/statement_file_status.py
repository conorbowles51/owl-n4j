"""Saved import state for the statement file list, independent of browser drafts."""
from sqlalchemy import select, func, case, cast, String
from postgres.models.evidence import EvidenceFile
from postgres.models.financial import (
    FinancialAccount as Account,
    FinancialSourceDocument as Source,
    FinancialStatementPeriod as Period,
    FinancialTransaction as Transaction,
)


def statement_file_status(session, *, case_id):
    periods = session.execute(
        select(Period, Source, Account)
        .join(Source, Period.source_document_id == Source.id)
        .join(Account, Period.account_id == Account.id)
        .join(EvidenceFile, Source.evidence_file_id == EvidenceFile.id)
        .where(Period.case_id == case_id, Source.case_id == case_id,
               Account.case_id == case_id, EvidenceFile.case_id == case_id)
        .order_by(Period.period_start, Period.id).limit(5001)
    ).all()
    # A bounded response must not call an omitted file "not imported".
    truncated = len(periods) > 5000
    periods = periods[:5000]
    counts = dict(session.execute(
        select(Transaction.statement_period_id, func.sum(case(
            ((Transaction.ledger_status == 'admitted') &
             Transaction.superseded_by_id.is_(None) &
             (Source.status == 'admitted'), 1), else_=0)))
        .join(Period, Transaction.statement_period_id == Period.id)
        .join(Source, Transaction.source_document_id == Source.id)
        .where(Transaction.case_id == case_id, Period.case_id == case_id,
               Source.case_id == case_id,
               Transaction.source_document_id == Period.source_document_id,
               Transaction.account_id == Period.account_id,
               Period.id.in_([period.id for period, _, _ in periods]))
        .group_by(Transaction.statement_period_id)
    ).all()) if periods else {}
    files = {}
    for period, source, account in periods:
        key = str(source.evidence_file_id)
        item = files.setdefault(key, dict(evidence_file_id=key, current_transactions=0, periods=[]))
        item['current_transactions'] += int(counts.get(period.id, 0))
        item['periods'].append(dict(
            id=str(period.id), account_id=str(account.id),
            account_label=(account.metadata_ or {}).get('display_label') or
                account.identifier_as_printed or account.holder_name or 'Account not identified',
            start=period.period_start.isoformat() if period.period_start else None,
            end=period.period_end.isoformat() if period.period_end else None,
            source_status=source.status,
        ))
    from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
    from services.financial.payment_document_proposal import SCHEMA
    reviews = session.execute(select(WorkspaceEntryLink, WorkspaceEntry)
        .join(WorkspaceEntry, WorkspaceEntryLink.entry_id == WorkspaceEntry.id)
        .join(EvidenceFile, func.replace(cast(EvidenceFile.id, String), '-', '') == func.replace(WorkspaceEntryLink.target_id, '-', ''))
        .where(WorkspaceEntry.case_id == case_id, WorkspaceEntry.deleted_at.is_(None),
               WorkspaceEntryLink.case_id == case_id, EvidenceFile.case_id == case_id,
               WorkspaceEntryLink.target_type == 'evidence',
               WorkspaceEntryLink.link_metadata['schema'].as_string() == SCHEMA)
        .order_by(WorkspaceEntry.created_at.desc(), WorkspaceEntry.id).limit(5001)).all()
    truncated = truncated or len(reviews) > 5000
    seen = set()
    for link, entry in reviews[:5000]:
        original = (link.link_metadata or {}).get('original') or {}
        if not isinstance(original, dict):
            continue
        if (original.get('case_id') != str(case_id) or original.get('evidence_file_id') != link.target_id
                or (entry.id, link.target_id) in seen):
            continue
        seen.add((entry.id, link.target_id))
        item = files.setdefault(link.target_id, dict(evidence_file_id=link.target_id, current_transactions=0, periods=[]))
        item['wire_review_count'] = item.get('wire_review_count', 0) + 1
    return dict(case_id=str(case_id), files=list(files.values()), truncated=truncated)
