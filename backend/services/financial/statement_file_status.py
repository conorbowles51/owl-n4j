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
        if (source.metadata_ or {}).get('financial_import_removal'):
            continue
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
    # Incomplete imports can have no statement period (for example, no usable
    # currency). They still belong in the file register, with an honest count.
    incomplete_sources = session.execute(select(Source.evidence_file_id, Source.metadata_['statement_incomplete_records'])
        .join(EvidenceFile, Source.evidence_file_id == EvidenceFile.id)
        .where(Source.case_id == case_id, EvidenceFile.case_id == case_id,
               Source.status == 'admitted', Source.document_type == 'statement_review')
        .order_by(Source.id).limit(5001)).all()
    truncated = truncated or len(incomplete_sources) > 5000
    for file_id, records in incomplete_sources[:5000]:
        count = sum(not row.get('resolved_transaction_id') for row in records or [])
        if count:
            key = str(file_id)
            item = files.setdefault(key, dict(evidence_file_id=key, current_transactions=0, periods=[]))
            item['incomplete_count'] = item.get('incomplete_count', 0) + count
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
        count_key = 'receipt_review_count' if original.get('kind') == 'deposit_receipt' else 'wire_review_count'
        item[count_key] = item.get(count_key, 0) + 1
    # Preparation and admission are separate facts. A PDF with 50 saved periods
    # and one prepared period must not be labelled simply "Imported".
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
    active_file = (
        EvidenceFile.metadata_['financial_file_visibility']['removed'].as_boolean().is_not(True),
        EvidenceFile.metadata_['financial_import_removal'].as_string().is_(None),
    )
    prepared = session.scalars(select(Item).join(Batch, Item.batch_id == Batch.id)
        .join(EvidenceFile, Item.file_id == EvidenceFile.id).where(Batch.case_id == case_id,
            EvidenceFile.case_id == case_id, *active_file, Batch.status != 'removed', Item.status.notin_(('removed', 'assigned', 'superseded_reading')))
        .order_by(Item.updated_at.desc(), Item.id).limit(20001)).all()
    truncated = truncated or len(prepared) > 20000
    # A statement imported from an individual review can leave older batch
    # snapshots marked ready. Match saved source scope, not the old UI status.
    saved_sources = list(session.scalars(select(Source).where(Source.case_id == case_id,
        Source.status == 'admitted', Source.document_type == 'statement_review')))
    saved_scopes = {(source.sha256_at_ingestion, source.metadata_.get('statement_import_statement_id')) for source in saved_sources}
    # A saved split replaces its earlier combined scope. An old batch snapshot
    # must not advertise that same source as a fresh set of available payments.
    from uuid import UUID
    ancestors = {source.metadata_.get('statement_recovery_parent_id') for source in saved_sources} - {None}
    seen_ancestors = set()
    while ancestors:
        current = ancestors - seen_ancestors
        if not current:
            break
        seen_ancestors.update(current)
        ancestors = set()
        for source in session.scalars(select(Source).where(Source.case_id == case_id, Source.id.in_([UUID(key) for key in current]))):
            saved_scopes.add((source.sha256_at_ingestion, source.metadata_.get('statement_import_statement_id')))
            parent = source.metadata_.get('statement_recovery_parent_id')
            if parent:
                ancestors.add(parent)
    file_hashes = dict(session.execute(select(EvidenceFile.id, EvidenceFile.sha256)
        .where(EvidenceFile.case_id == case_id, EvidenceFile.id.in_([p.file_id for p in prepared]))).all())
    # Decisions can be recorded directly from a statement, without updating its
    # old batch snapshot. Validate their lightweight source/review fingerprints
    # together; reconstructing every PDF on a listing would be prohibitively
    # expensive and a stale ignored label must never suppress current work.
    from services.financial.pending_statement_duplicates import METADATA_KEY
    from services.financial.pending_duplicate_projection import load_projection_context, cached_disposition
    # Removal retains duplicate decisions as evidence history. That history
    # must not recreate active prepared periods after the imports were removed.
    decision_files = list(session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id,
        *active_file, EvidenceFile.metadata_[METADATA_KEY].as_string().is_not(None)).order_by(EvidenceFile.id).limit(5001)))
    truncated = truncated or len(decision_files) > 5000
    decision_files = decision_files[:5000]
    related_ids = set()
    for file in decision_files:
        for decision in (file.metadata_ or {}).get(METADATA_KEY, {}).values():
            try:
                related_ids.add(UUID((decision.get('retained') or {})['evidence_file_id']))
            except (KeyError, ValueError, TypeError):
                continue
    known_ids = {file.id for file in decision_files}
    related_files = list(session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id,
        EvidenceFile.id.in_(related_ids - known_ids)))) if related_ids - known_ids else []
    context = load_projection_context(session, case_id, [*decision_files, *related_files]) if decision_files else None
    decisions = {}
    for file in decision_files:
        for statement_id in (file.metadata_ or {}).get(METADATA_KEY, {}):
            decision = cached_disposition(context, file, statement_id)
            decisions[(str(file.id), statement_id)] = decision
            if decision['status'] in ('ignored', 'needs_comparison', 'restored'):
                item = files.setdefault(str(file.id), dict(evidence_file_id=str(file.id), current_transactions=0, periods=[]))
                item.setdefault('duplicate_dispositions', []).append(dict(statement_id=statement_id or None,
                    currency=(decision.get('scope') or {}).get('currency'), decision=decision))
    seen_periods = set()
    from services.financial.statement_import_overlap import comparison_sources, coverage_review, summary_request, duplicate_hold, scope
    coverage_sources = None
    coverage_prepared = {}
    for prepared_item in prepared[:20000]:
        key = str(prepared_item.file_id)
        identity = (key, prepared_item.statement_key)
        if identity in seen_periods:
            continue
        seen_periods.add(identity)
        item = files.setdefault(key, dict(evidence_file_id=key, current_transactions=0, periods=[]))
        item['prepared_periods'] = item.get('prepared_periods', 0) + 1
        decision = decisions.get(identity)
        ignored = bool(decision and decision['current'] and decision['status'] == 'ignored')
        duplicate_review = bool(decision and (not decision['current'] or
            decision['status'] in ('needs_comparison', 'restored'))) or (
            prepared_item.status == 'duplicate_ignored' and not ignored)
        already_saved = (file_hashes.get(prepared_item.file_id), prepared_item.statement_key or None) in saved_scopes
        available = not already_saved and not ignored and not duplicate_review and prepared_item.status in ('ready', 'attention') and prepared_item.summary.get('can_import', False)
        held = False
        if available:
            raw = {**(prepared_item.review_request or summary_request(prepared_item.summary)),
                'statement_id': prepared_item.statement_key or None, 'account_type': prepared_item.summary.get('account_type', '')}
            if scope(raw) is not None:
                if coverage_sources is None:
                    coverage_sources, coverage_prepared = comparison_sources(session, case_id)
                raw = {**coverage_prepared.get(prepared_item.id, raw), 'statement_id': prepared_item.statement_key or None}
                held = duplicate_hold(coverage_review(session, case_id=case_id, file_id=prepared_item.file_id,
                    request=raw, sources=coverage_sources), raw)
            available = not held
        if available:
            summary = prepared_item.summary
            item.setdefault('ready_periods', []).append(dict(
                statement_id=prepared_item.statement_key or '',
                holder=summary.get('holder') or '', institution=summary.get('institution') or '',
                account=summary.get('account') or '', currency=summary.get('currency') or '',
                period_start=summary.get('period_start') or '', period_end=summary.get('period_end') or '',
                transaction_count=summary.get('transaction_count', 0),
                incomplete_count=summary.get('incomplete_count', 0),
                problem_count=summary.get('problem_count', 0)))
        for field, matched in (
            ('available_periods', available),
            ('ignored_periods', ignored),
            ('pending_periods', prepared_item.status == 'pending_import' and not ignored),
            ('periods_with_checks', not ignored and (duplicate_review or held or bool(prepared_item.summary.get('problem_count', 0))) and prepared_item.status != 'skipped'),
        ):
            item[field] = item.get(field, 0) + int(matched)
    # Direct statement decisions also appear before the file joins a batch.
    for (key, statement_id), decision in decisions.items():
        if (key, statement_id) in seen_periods:
            continue
        item = files.setdefault(key, dict(evidence_file_id=key, current_transactions=0, periods=[]))
        item['prepared_periods'] = item.get('prepared_periods', 0) + 1
        ignored = decision['current'] and decision['status'] == 'ignored'
        item['ignored_periods'] = item.get('ignored_periods', 0) + int(ignored)
        if not decision['current'] or decision['status'] in ('needs_comparison', 'restored'):
            item['periods_with_checks'] = item.get('periods_with_checks', 0) + 1
    return dict(case_id=str(case_id), files=list(files.values()), truncated=truncated)
