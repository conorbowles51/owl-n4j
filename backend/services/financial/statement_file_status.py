"""Saved import state for the statement file list, independent of browser drafts."""
import threading
from collections import OrderedDict
from copy import deepcopy

from sqlalchemy import select, func, case, cast, String, text
from postgres.models.evidence import EvidenceFile
from postgres.models.financial import (
    FinancialAccount as Account,
    FinancialSourceDocument as Source,
    FinancialStatementPeriod as Period,
    FinancialTransaction as Transaction,
)


# The register is polled while the Financial tab is open. On a large case the
# full computation takes seconds, while the inputs rarely change between
# polls. A result is reused only while a fingerprint of every row the
# computation reads is unchanged: PostgreSQL gives each row version a new
# ``xmin``, so any insert, update or delete (including long transactions that
# commit late) changes the fingerprint. Other databases are never cached.
_FINGERPRINT_SQL = text("""
SELECT 'periods', count(*), md5(string_agg(id::text || ':' || xmin::text, ',' ORDER BY id))
  FROM financial_statement_periods WHERE case_id = :case_id
UNION ALL SELECT 'sources', count(*), md5(string_agg(id::text || ':' || xmin::text, ',' ORDER BY id))
  FROM financial_source_documents WHERE case_id = :case_id
UNION ALL SELECT 'accounts', count(*), md5(string_agg(id::text || ':' || xmin::text, ',' ORDER BY id))
  FROM financial_accounts WHERE case_id = :case_id
UNION ALL SELECT 'transactions', count(*), md5(string_agg(id::text || ':' || xmin::text, ',' ORDER BY id))
  FROM financial_transactions WHERE case_id = :case_id
UNION ALL SELECT 'files', count(*), md5(string_agg(id::text || ':' || xmin::text, ',' ORDER BY id))
  FROM evidence_files WHERE case_id = :case_id
UNION ALL SELECT 'batches', count(*), md5(string_agg(id::text || ':' || xmin::text, ',' ORDER BY id))
  FROM financial_import_batches WHERE case_id = :case_id
UNION ALL SELECT 'items', count(*), md5(string_agg(i.id::text || ':' || i.xmin::text, ',' ORDER BY i.id))
  FROM financial_import_batch_items i JOIN financial_import_batches b ON b.id = i.batch_id WHERE b.case_id = :case_id
UNION ALL SELECT 'texts', count(*), md5(string_agg(t.evidence_file_id::text || ':' || t.xmin::text, ',' ORDER BY t.evidence_file_id))
  FROM evidence_document_texts t JOIN evidence_files f ON f.id = t.evidence_file_id WHERE f.case_id = :case_id
UNION ALL SELECT 'geometry', count(*), md5(string_agg(g.evidence_file_id::text || '/' || g.page_number::text || ':' || g.xmin::text, ','
    ORDER BY g.evidence_file_id, g.page_number))
  FROM evidence_table_geometry g JOIN evidence_files f ON f.id = g.evidence_file_id WHERE f.case_id = :case_id
UNION ALL SELECT 'entries', count(*), md5(string_agg(id::text || ':' || xmin::text, ',' ORDER BY id))
  FROM workspace_entries WHERE case_id = :case_id
UNION ALL SELECT 'links', count(*), md5(string_agg(id::text || ':' || xmin::text, ',' ORDER BY id))
  FROM workspace_entry_links WHERE case_id = :case_id
""")
_CACHE_SIZE = 16
_cache = OrderedDict()
_cache_lock = threading.Lock()


def status_fingerprint(session, case_id):
    """Fingerprint of every row the register reads, or None when not supported."""
    if session.get_bind().dialect.name != 'postgresql':
        return None
    return tuple(tuple(row) for row in session.execute(_FINGERPRINT_SQL, dict(case_id=str(case_id))))


def statement_file_status(session, *, case_id, use_cache=True):
    fingerprint = status_fingerprint(session, case_id) if use_cache else None
    key = str(case_id)
    if fingerprint is not None:
        with _cache_lock:
            hit = _cache.get(key)
            if hit and hit[0] == fingerprint:
                _cache.move_to_end(key)
                return deepcopy(hit[1])
    result = _statement_file_status(session, case_id=case_id)
    if fingerprint is not None:
        # The fingerprint was taken before the computation. A change committed
        # in between only makes the next poll recompute; it can never pin a
        # stale result.
        with _cache_lock:
            _cache[key] = (fingerprint, deepcopy(result))
            _cache.move_to_end(key)
            while len(_cache) > _CACHE_SIZE:
                _cache.popitem(last=False)
    return result


def _statement_file_status(session, *, case_id):
    # Only the columns the register shows. Loading whole source documents would
    # decode every saved reading (tens of MB on a large case) for each poll.
    periods = session.execute(
        select(Period, Source.evidence_file_id, Source.status,
               Source.metadata_['financial_import_removal'].as_string(),
               Account.id, Account.metadata_['display_label'].as_string(),
               Account.identifier_as_printed, Account.holder_name)
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
               Period.id.in_([row[0].id for row in periods]))
        .group_by(Transaction.statement_period_id)
    ).all()) if periods else {}
    files = {}
    for period, file_id, source_status, removal, account_id, display_label, printed, holder in periods:
        if removal:
            continue
        key = str(file_id)
        item = files.setdefault(key, dict(evidence_file_id=key, current_transactions=0, periods=[]))
        item['current_transactions'] += int(counts.get(period.id, 0))
        item['periods'].append(dict(
            id=str(period.id), account_id=str(account_id),
            account_label=display_label or printed or holder or 'Account not identified',
            start=period.period_start.isoformat() if period.period_start else None,
            end=period.period_end.isoformat() if period.period_end else None,
            source_status=source_status,
        ))
    # Incomplete imports can have no statement period (for example, no usable
    # currency). They still belong in the file register, with an honest count.
    incomplete_sources = session.execute(select(Source.id, Source.evidence_file_id,
            Source.metadata_['statement_incomplete_records'], Source.metadata_['statement_admission']['blockers'],
            Source.metadata_['statement_import_request']['period_start'].as_string(),
            Source.metadata_['statement_import_request']['period_end'].as_string())
        .join(EvidenceFile, Source.evidence_file_id == EvidenceFile.id)
        .where(Source.case_id == case_id, EvidenceFile.case_id == case_id,
               Source.status == 'admitted', Source.document_type == 'statement_review')
        .order_by(Source.id).limit(5001)).all()
    truncated = truncated or len(incomplete_sources) > 5000
    saved_dates = {str(row[0].source_document_id): row[0] for row in periods}
    for source_id, file_id, records, blockers, request_start, request_end in incomplete_sources[:5000]:
        open_records = [row for row in records or [] if not row.get('resolved_transaction_id')]
        if open_records:
            key = str(file_id)
            item = files.setdefault(key, dict(evidence_file_id=key, current_transactions=0, periods=[]))
            item['incomplete_count'] = item.get('incomplete_count', 0) + len(open_records)
            # Records whose values are all present (corrections and manual
            # additions) are held until the whole statement reconciles. They are
            # not missing anything; the card must say what is still needed.
            waiting = sum(row.get('missing_fields') == [] for row in open_records)
            item['awaiting_reconciliation_count'] = item.get('awaiting_reconciliation_count', 0) + waiting
            period = saved_dates.get(str(source_id))
            item.setdefault('incomplete_sources', []).append(dict(
                source_document_id=str(source_id),
                period_start=period.period_start.isoformat() if period and period.period_start else request_start or None,
                period_end=period.period_end.isoformat() if period and period.period_end else request_end or None,
                missing_count=len(open_records) - waiting, awaiting_reconciliation_count=waiting,
                blockers=list(dict.fromkeys([row['hold_reason'] for row in open_records if row.get('hold_reason')] +
                    [issue.get('message') for issue in (blockers or []) if issue.get('message')]))[:3] if waiting else []))
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
    # One read of the case's prepared periods serves both this register (files
    # still in Financial) and the coverage comparison below (which, as before,
    # also compares against files hidden from Financial).
    every_prepared = session.scalars(select(Item).join(Batch, Item.batch_id == Batch.id)
        .join(EvidenceFile, Item.file_id == EvidenceFile.id).where(Batch.case_id == case_id,
            EvidenceFile.case_id == case_id, Batch.status != 'removed', Item.status.notin_(('removed', 'assigned', 'superseded_reading')))
        .order_by(Item.updated_at.desc(), Item.id)).all()
    item_files = {file.id: file for file in session.scalars(select(EvidenceFile)
        .where(EvidenceFile.case_id == case_id, EvidenceFile.id.in_({p.file_id for p in every_prepared})))} if every_prepared else {}
    def _active(file):
        metadata = file.metadata_ or {}
        visibility = metadata.get('financial_file_visibility')
        return (not (isinstance(visibility, dict) and visibility.get('removed') is True)
                and metadata.get('financial_import_removal') is None)
    comparison_pending = [(p, item_files[p.file_id]) for p in every_prepared
                          if p.status in ('ready', 'attention', 'pending_import')]
    prepared = [p for p in every_prepared if _active(item_files[p.file_id])][:20001]
    truncated = truncated or len(prepared) > 20000
    # A statement imported from an individual review can leave older batch
    # snapshots marked ready. Match saved source scope, not the old UI status.
    from types import SimpleNamespace
    source_columns = (Source.id, Source.evidence_file_id, Source.sha256_at_ingestion,
        Source.metadata_['statement_import_statement_id'].as_string(),
        Source.metadata_['statement_recovery_parent_id'].as_string(),
        Source.metadata_['financial_import_removal'].as_string())
    def _light(row):
        return SimpleNamespace(id=row[0], evidence_file_id=row[1], sha256_at_ingestion=row[2],
            statement_id=row[3], parent_id=row[4], removed=bool(row[5]))
    saved_sources = [_light(row) for row in session.execute(select(*source_columns).where(Source.case_id == case_id,
        Source.status == 'admitted', Source.document_type == 'statement_review'))]
    saved_scopes = {(source.sha256_at_ingestion, source.statement_id) for source in saved_sources}
    # A saved split replaces its earlier combined scope. An old batch snapshot
    # must not advertise that same source as a fresh set of available payments.
    from uuid import UUID
    ancestors = {source.parent_id for source in saved_sources} - {None}
    seen_ancestors = set()
    while ancestors:
        current = ancestors - seen_ancestors
        if not current:
            break
        seen_ancestors.update(current)
        ancestors = set()
        for source in map(_light, session.execute(select(*source_columns).where(
                Source.case_id == case_id, Source.id.in_([UUID(key) for key in current])))):
            saved_scopes.add((source.sha256_at_ingestion, source.statement_id))
            if source.parent_id:
                ancestors.add(source.parent_id)
    prepared_files = {p.file_id: item_files[p.file_id] for p in prepared}
    file_hashes = {key: file.sha256 for key, file in prepared_files.items()}
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
    empty_scan = {}
    from services.financial.statement_import_overlap import comparison_sources, coverage_review, summary_request, duplicate_hold, scope
    coverage_sources = None
    coverage_prepared = {}
    for prepared_item in prepared[:20000]:
        summary = prepared_item.summary
        effective_request = prepared_item.review_request
        if prepared_item.status in ('ready', 'attention'):
            from services.financial.statement_progress import review_progress
            from services.financial.effective_statement_review import resolve_review, conflict_summary
            file = prepared_files.get(prepared_item.file_id)
            saved = review_progress(file, prepared_item.statement_key) if file else None
            effective_request, conflict = resolve_review(effective_request, saved)
            if conflict:
                summary = conflict_summary(summary)
            elif saved and effective_request == saved['request']:
                assessment = saved.get('assessment')
                # Reuse only an assessment of this reading; never parse an
                # entire case to render a list. Legacy drafts are picked up by
                # the existing background Refresh statements operation.
                if (assessment and assessment.get('revision') == summary.get('revision')
                        and assessment.get('review_model') == summary.get('review_model')):
                    summary = {**summary, **assessment}
                elif effective_request != prepared_item.review_request:
                    summary = {**summary, 'can_import': False,
                        'problem_count': max(1, summary.get('problem_count', 0))}
        key = str(prepared_item.file_id)
        identity = (key, prepared_item.statement_key)
        if identity in seen_periods:
            continue
        seen_periods.add(identity)
        item = files.setdefault(key, dict(evidence_file_id=key, current_transactions=0, periods=[]))
        item['prepared_periods'] = item.get('prepared_periods', 0) + 1
        decision = decisions.get(identity)
        source_file = prepared_files.get(prepared_item.file_id)
        previous_decision = ((source_file.metadata_ or {}).get(METADATA_KEY, {}).get(prepared_item.statement_key or '') or {}) if source_file else {}
        ignored = bool(decision and decision['current'] and decision['status'] == 'ignored')
        duplicate_review = bool(decision and (not decision['current'] or
            decision['status'] in ('needs_comparison', 'restored'))) or (
            prepared_item.status == 'duplicate_ignored' and not ignored)
        if (decision and not decision['current'] and previous_decision.get('status') in ('retained', 'not_duplicate')
                and prepared_item.status in ('ready', 'attention')):
            # A corrected retained source needs a fresh coverage comparison,
            # not an automatic duplicate hold against itself. Ignored copies
            # and actual conflicting comparisons still require their decision.
            duplicate_review = False
        already_saved = (file_hashes.get(prepared_item.file_id), prepared_item.statement_key or None) in saved_scopes
        available = not already_saved and not ignored and not duplicate_review and prepared_item.status in ('ready', 'attention') and summary.get('can_import', False)
        held = False
        if available:
            raw = {**(effective_request or summary_request(summary)),
                'statement_id': prepared_item.statement_key or None, 'account_type': summary.get('account_type', '')}
            if scope(raw) is not None:
                if coverage_sources is None:
                    coverage_sources, coverage_prepared = comparison_sources(session, case_id,
                        comparison_pending, duplicate_context=context)
                raw = {**(effective_request or coverage_prepared.get(prepared_item.id, raw)), 'statement_id': prepared_item.statement_key or None}
                held = duplicate_hold(coverage_review(session, case_id=case_id, file_id=prepared_item.file_id,
                    request=raw, sources=coverage_sources), raw)
            available = not held
        if available:
            item.setdefault('ready_periods', []).append(dict(
                statement_id=prepared_item.statement_key or '',
                holder=summary.get('holder') or '', institution=summary.get('institution') or '',
                account=summary.get('account') or '', currency=summary.get('currency') or '',
                period_start=summary.get('period_start') or '', period_end=summary.get('period_end') or '',
                transaction_count=summary.get('transaction_count', 0),
                incomplete_count=summary.get('incomplete_count', 0),
                problem_count=summary.get('problem_count', 0)))
        pending_import = prepared_item.status == 'pending_import' and not ignored
        # A second reading of a period this PDF already saved (for example the
        # same pages found under two statement keys) is a repeat, not unsaved.
        repeat = (not already_saved and not available and not pending_import and not ignored
            and not duplicate_review and prepared_item.status != 'skipped' and any(
                (period['start'], period['end']) == (summary.get('period_start'), summary.get('period_end'))
                and (not summary.get('account_id') or period['account_id'] == str(summary['account_id']))
                for period in item['periods']))
        # "Another supplied statement covers some of these dates" is a note to
        # compare if needed, not a check. Count it honestly as an overlap;
        # duplicate holds and conflicting comparisons remain checks.
        problems = summary.get('problems') or []
        overlap_only = (bool(problems) and all(problem.get('kind') == 'coverage' for problem in problems)
            and summary.get('problem_count', 0) <= len(problems))
        has_checks = duplicate_review or held or (bool(summary.get('problem_count', 0)) and not overlap_only)
        # A reading that found nothing at all (no rows, records, dates or
        # balances) is not "read and waiting for review": the card must say so.
        if not ignored and prepared_item.status != 'skipped':
            found = bool(summary.get('transaction_count') or summary.get('record_count')
                or summary.get('incomplete_count') or summary.get('unclassified_count')
                or summary.get('period_start') or summary.get('period_end'))
            empty_scan[key] = empty_scan.get(key, True) and not found
        for field, matched in (
            ('available_periods', available),
            ('ignored_periods', ignored),
            ('pending_periods', pending_import),
            ('repeat_periods', repeat),
            ('periods_with_checks', not ignored and not repeat and has_checks and prepared_item.status != 'skipped'),
            ('overlapping_periods', not ignored and not repeat and not has_checks and overlap_only and prepared_item.status != 'skipped'),
        ):
            item[field] = item.get(field, 0) + int(matched)
    _mark_empty_readings(session, files, [key for key, empty in empty_scan.items() if empty])
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
    # An independently uploaded copy has a different evidence ID, but opening
    # it resolves imports by the source digest. Expose that relationship without
    # attributing the older copy's payments to this file or counting them twice.
    saved_by_hash = {}
    for source in saved_sources:
        if source.removed:
            continue
        owner = files.get(str(source.evidence_file_id))
        if owner and (owner['periods'] or owner.get('incomplete_count')):
            saved_by_hash.setdefault(source.sha256_at_ingestion, set()).add(source.evidence_file_id)
    if saved_by_hash:
        copies = list(session.scalars(select(EvidenceFile).where(
            EvidenceFile.case_id == case_id, *active_file,
            EvidenceFile.sha256.in_(saved_by_hash)).order_by(EvidenceFile.id).limit(20001)))
        truncated = truncated or len(copies) > 20000
        for copy in copies[:20000]:
            related = sorted(str(identifier) for identifier in saved_by_hash[copy.sha256] if identifier != copy.id)
            if related:
                item = files.setdefault(str(copy.id), dict(evidence_file_id=str(copy.id), current_transactions=0, periods=[]))
                item['same_pdf_saved_file_ids'] = related
    return dict(case_id=str(case_id), files=list(files.values()), truncated=truncated)


EMPTY_READING_REASONS = {
    'scanned_image': 'Nothing could be read: scanned image, needs visual reading',
    'layout_not_supported': 'Nothing could be read: layout not supported yet',
    'no_statement': 'Reading found no statement',
}


def empty_reading_reason(source_locations):
    """Why a reading with no rows, dates or balances found nothing.

    Pages recognised only from images (OCR) need a visual reading; a page with
    a usable text layer that produced nothing is a layout the readers do not
    support yet; a file with no readable pages is not a statement as read."""
    origins = {(location or {}).get('text_origin') for location in source_locations or []
               if (location or {}).get('kind', 'page') == 'page'} - {None}
    if 'digital_text_layer' in origins:
        return 'layout_not_supported'
    if origins:
        return 'scanned_image'
    return 'no_statement'


def _mark_empty_readings(session, files, keys):
    """Label files whose every current reading is empty and nothing was saved."""
    from uuid import UUID
    from postgres.models.evidence import EvidenceDocumentText
    candidates = [key for key in keys if not files[key]['periods'] and not files[key].get('incomplete_count')]
    if not candidates:
        return
    locations = dict(session.execute(select(EvidenceDocumentText.evidence_file_id, EvidenceDocumentText.source_locations)
        .where(EvidenceDocumentText.evidence_file_id.in_([UUID(key) for key in candidates]))).all())
    for key in candidates:
        reason = empty_reading_reason(locations.get(UUID(key)))
        files[key]['empty_reading'] = dict(reason=reason, message=EMPTY_READING_REASONS[reason])
