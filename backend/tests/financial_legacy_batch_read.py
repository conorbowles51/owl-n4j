"""Frozen copy of the batch read projection before stored readiness (687da296).

Reference only: equivalence tests compare the stored-projection read against
what this re-reading implementation returned for the same data. Never call it
from service code.
"""
from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial.pdf_candidates import PdfMappingError, _digest
from services.financial import statement_import
from services.financial.import_batches import assess, initial_request, currency_revision, REVIEW_MODEL


def read_statement_import(*args, **kwargs):
    return statement_import.read_statement_import(*args, **kwargs)


def legacy_checked_batch_items(session, case_id, items, *, validate_reviews=False):
    """Project current coverage concerns without making a GET write changes."""
    items = [item for item in items if item.status not in ('removed', 'superseded_reading')]
    # Failed/queued files have no statement reviews to compare. Do not rebuild
    # unrelated case statements while the investigator opens their recovery.
    if not items:
        return []
    from services.financial.statement_import_overlap import coverage_review, summary_request, requires_decision, comparison_sources, duplicate_hold
    pending = session.execute(select(Item, EvidenceFile).join(Batch, Batch.id == Item.batch_id)
        .join(EvidenceFile, EvidenceFile.id == Item.file_id).where(Batch.case_id == case_id,
        EvidenceFile.case_id == case_id, Batch.status != 'removed', Item.status.in_(('ready','attention','pending_import')))).all()
    cache, proposals = {}, {}
    target_ids = {item.id for item in items}
    def read_pending(item, *, include_duplicate_disposition=True):
        # This read owns one fresh projection. Legacy coverage hydration and
        # current batch assessment must not reconstruct the same statement
        # twice; no result survives this request or replaces an import check.
        full_review = item.id in target_ids
        currency = item.summary.get('currency') or None
        key = (item.file_id, currency, item.statement_key, full_review, include_duplicate_disposition)
        if key not in proposals:
            try:
                proposals[key] = read_statement_import(session, case_id=case_id, evidence_file_id=item.file_id,
                    currency=currency, statement_id=item.statement_key or None, _cache=cache,
                    _include_period_checks=full_review, _include_duplicate_disposition=include_duplicate_disposition)
            except PdfMappingError as error:
                proposals[key] = error
        result = proposals[key]
        if isinstance(result, PdfMappingError):
            raise result
        return result
    sources, prepared = comparison_sources(session, case_id, pending, read_pending=read_pending)
    from postgres.models.financial import FinancialSourceDocument
    saved_files = set(session.scalars(select(FinancialSourceDocument.evidence_file_id).where(
        FinancialSourceDocument.case_id == case_id, FinancialSourceDocument.status == 'admitted',
        FinancialSourceDocument.evidence_file_id.in_([item.file_id for item in items]))))
    from services.financial.pending_statement_duplicates import METADATA_KEY, read_duplicate_disposition
    duplicate_files = {file.id: file for file in session.scalars(select(EvidenceFile).where(
        EvidenceFile.case_id == case_id, EvidenceFile.id.in_({item.file_id for item in items})))}
    projected = []
    for item in items:
        summary = deepcopy(item.summary)
        state = item.status
        projected_request = item.review_request
        file = duplicate_files.get(item.file_id)
        stored_duplicate = (file.metadata_ or {}).get(METADATA_KEY, {}).get(item.statement_key or '') if file else None
        if state in ('ready', 'attention', 'duplicate_ignored') and (state == 'duplicate_ignored' or
                (stored_duplicate or {}).get('status') in ('ignored', 'restored')):
            try:
                from services.financial.pending_duplicate_projection import cached_disposition
                context = getattr(sources, 'duplicate_context', None)
                duplicate = cached_disposition(context, file, item.statement_key) if context is not None else None
                # Legacy decisions without guards require a full check. Current
                # guards cover source bytes, geometry, edits and retained work.
                proposal = None
                if duplicate is None or not duplicate.get('current'):
                    proposal = read_pending(item)
                    duplicate = read_duplicate_disposition(session, file, proposal, projected_request)
                summary['duplicate_disposition'] = duplicate
                if duplicate and duplicate.get('current') and duplicate['status'] == 'ignored':
                    state = 'duplicate_ignored'
                    summary.update(can_import=False, problems=[], problem_count=0)
                elif state == 'duplicate_ignored':
                    proposal = proposal or read_pending(item)
                    state, assessment = assess({**proposal, 'duplicate_disposition': duplicate}, projected_request)
                    summary.update(assessment)
            except PdfMappingError as error:
                state = 'attention'
                summary.update(can_import=False, problems=[dict(message=str(error), row_id=None)], problem_count=1)
        if state in ('ready', 'attention'):
            from services.financial.statement_progress import review_progress
            progress = review_progress(file, item.statement_key) if file else None
            conflict = False
            cached_assessment = (progress or {}).get('assessment') or {}
            can_reuse = (progress and not validate_reviews and item.file_id not in saved_files
                and cached_assessment.get('revision') == summary.get('revision')
                and summary.get('review_model') == REVIEW_MODEL
                and cached_assessment.get('review_model') == REVIEW_MODEL)
            if can_reuse:
                from services.financial.effective_statement_review import resolve_review, conflict_summary
                projected_request, conflict = resolve_review(projected_request, progress)
                if not conflict:
                    summary.update(cached_assessment)
                    state = progress['assessment_status']
                else:
                    state, summary = 'attention', conflict_summary(summary)
            elif progress or validate_reviews or item.file_id in saved_files or 'can_import' not in summary or summary.get('review_model') != REVIEW_MODEL:
                try:
                    proposal = read_pending(item)
                    from services.financial.review_upgrade import upgrade_request
                    projected_request = upgrade_request(item.review_request, proposal) or item.review_request
                    from services.financial.effective_statement_review import resolve_review, conflict_summary
                    projected_request, conflict = resolve_review(projected_request, proposal.get('saved_review'),
                        baseline=initial_request(proposal))
                    state, assessment = assess(proposal, None if proposal.get('current_import') else projected_request)
                    summary.update(assessment)
                    if conflict and not proposal.get('current_import'):
                        state, summary = 'attention', conflict_summary(summary)
                except PdfMappingError as error:
                    summary.update(can_import=False, problems=[dict(message=str(error), row_id=None)], problem_count=1)
            if state in ('ready', 'attention'):
                raw = {**(projected_request or prepared.get(item.id) or summary_request(summary)),
                    'statement_id': item.statement_key or None,
                    'account_type': summary.get('account_type', (prepared.get(item.id) or {}).get('account_type', ''))}
                review = coverage_review(session, case_id=case_id, file_id=item.file_id, request=raw, sources=sources)
                problems = [p for p in summary.get('problems', []) if p.get('kind') not in ('coverage', 'coverage_load')]
                extra_count = max(0, summary.get('problem_count', 0) - len(summary.get('problems', [])))
                if raw.get('_coverage_error'):
                    problems.append(dict(kind='coverage_load', row_id=None, message=raw['_coverage_error']))
                if requires_decision(review, raw):
                    problems.append(dict(kind='coverage', matching_statement=duplicate_hold(review, raw), row_id=None,
                        message=('A separate file matches this bank, full account, holder, currency and statement period. Compare the existing statement before importing another copy.'
                            if duplicate_hold(review, raw) else 'Another statement covers some of these dates. You can compare their payments now or after importing.')))
                if duplicate_hold(review, raw):
                    summary['can_import'] = False
                summary.update(coverage_review=review, problems=problems, problem_count=len(problems) + extra_count)
                state = 'attention' if problems else 'ready'
        projected.append((item, state, summary, projected_request))
    # A ready item may have been imported through its individual review. Resolve
    # all such receipts together rather than querying its saved rows per item.
    from services.financial.batch_import_history import current_imports
    retained = current_imports(session, case_id, [UUID(summary['source_document_id'])
        for _, state, summary, _ in projected if state == 'imported' and summary.get('source_document_id')])
    result = []
    for item, state, summary, projected_request in projected:
        if state == 'imported' and summary.get('source_document_id') in retained:
            current = retained[summary['source_document_id']]
            issues, records, review = current['issues'], current['records'], current['review']
            summary.update(source_document_id=current['source_document_id'], account_id=current['account_id'], currency=current['currency'],
                balance_status=current['balance_status'], admission=current['admission'], checks=current['checks'])
            details = review.get('details', {})
            if details:
                summary.update(holder=details.get('holder', ''), account=details.get('account_number', ''),
                    institution=details.get('institution', ''), period_start=details.get('period_start', ''),
                    period_end=details.get('period_end', ''))
            unresolved = sum(not r.get('resolved_transaction_id') for r in records)
            summary.update(problems=issues[:50], problem_count=len(issues), incomplete_count=unresolved,
                transaction_count=current['transaction_count'], record_count=current['transaction_count'] + unresolved)
        if state not in ('ready', 'attention'):
            summary['can_import'] = False
        summary['disposition_revision'] = _digest(dict(status=item.status, request=item.review_request,
            decision=item.summary.get('import_decision')))
        summary['currency_revision'] = currency_revision(item, summary)
        from services.financial.batch_review_summary import tagged_problems
        summary['problems'] = tagged_problems(summary)
        # Older saved summaries can contain explicit JSON nulls for unknown
        # header fields. Keep the stored reading untouched, but do not let
        # comparing None with strings break the batch and its Next navigation.
        if summary.get('filename') is None:
            source = duplicate_files.get(item.file_id)
            summary['filename'] = source.original_filename if source else 'Source unavailable'
        for key in ('currency', 'holder', 'account', 'institution', 'account_type', 'period_start', 'period_end'):
            if key in summary and summary[key] is None:
                summary[key] = ''
        from services.financial.effective_statement_review import batch_review_revision
        from services.financial.statement_progress import review_progress
        result.append(SimpleNamespace(id=item.id, file_id=item.file_id, statement_key=item.statement_key,
            status=state, summary=summary, review_request=projected_request,
            review_revision=batch_review_revision(item.review_request,
                review_progress(duplicate_files[item.file_id], item.statement_key) if item.file_id in duplicate_files else None)))
    return result