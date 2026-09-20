"""Find saved decisions across explicitly linked readings of the same case file.

Period names are navigation aids, not permission to attach old rows to new
locations. Different readings are shown for comparison and never remapped.
"""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialSourceDocument
from postgres.models.financial_import_batches import FinancialImportBatch, FinancialImportBatchItem
from services.financial.pdf_candidates import PdfMappingError, _digest


def _ancestors(session, file):
    seen = {str(file.id)} if getattr(file, 'id', None) else set()
    parent = (file.metadata_ or {}).get('statement_parent_evidence_id')
    while parent and parent not in seen:
        seen.add(parent)
        try:
            identifier = UUID(parent)
        except (ValueError, TypeError):
            break
        previous = session.scalar(select(EvidenceFile).where(
            EvidenceFile.id == identifier, EvidenceFile.case_id == file.case_id))
        if previous is None:
            break
        yield previous
        parent = (previous.metadata_ or {}).get('statement_parent_evidence_id')


def saved_ancestor_reviews(session, file):
    records = []
    seen = set()

    def add(previous, saved, origin, statement_id=None):
        request = saved.get('request') or {}
        if not request.get('rows') and not request.get('_saved_balance_corrections'):
            return
        key = request.get('statement_id') or statement_id or ''
        # The same request may have been copied into multiple batches or saved
        # unchanged in later versions. Show it once, keeping the nearest source.
        fingerprint = _digest(dict(statement_id=key, request=request))
        if fingerprint in seen:
            return
        seen.add(fingerprint)
        records.append(dict(id=_digest([str(previous.id), fingerprint]),
            statement_id=key or None, evidence_file_id=str(previous.id),
            filename=previous.original_filename, origin=origin,
            saved_at=saved.get('saved_at'), saved_by=saved.get('saved_by'),
            request=request, review_revision=saved.get('review_revision') or _digest(request)))

    for previous in _ancestors(session, file):
        metadata = previous.metadata_ or {}
        for key, saved in metadata.get('financial_review_progress', {}).items():
            add(previous, saved, 'Statement review', key)
        for saved in reversed(metadata.get('financial_review_history', [])):
            add(previous, saved, 'Earlier statement review')
        # Late corrections are separate from the immutable import request.
        # Keep them available for explicit comparison with a fresh extraction.
        sources = session.scalars(select(FinancialSourceDocument).where(
            FinancialSourceDocument.case_id == file.case_id,
            FinancialSourceDocument.evidence_file_id == previous.id)
            .order_by(FinancialSourceDocument.id))
        for source in sources:
            imported = source.metadata_ or {}
            details = imported.get('statement_details_review')
            if details and imported.get('statement_import_request') and _digest(details) == imported.get('statement_details_review_sha256'):
                request = deepcopy(imported['statement_import_request'])
                request.update(details['details'])
                # Later balances have their own page citations. Never pretend
                # they came from one of the old extraction's transaction rows.
                request['_saved_balance_corrections'] = details['balances']
                latest = imported['statement_details_history'][-1]
                add(previous, dict(request=request, saved_at=latest['at'],
                    saved_by=dict(user_id=latest['actor_id'], name=latest['actor_name'])),
                    'Account and balances corrected after import')
            corrected = [r for r in imported.get('statement_incomplete_records', [])
                         if r.get('correction')]
            if not corrected or not imported.get('statement_import_request'):
                continue
            request = deepcopy(imported['statement_import_request'])
            corrections = {r['id']: r['correction'] for r in corrected}
            request['rows'] = [corrections.get(r['id'], r) for r in request['rows']]
            latest = max(corrected, key=lambda r: r.get('corrected_at', ''))
            currencies = sorted({r['correction_currency'] for r in corrected})
            add(previous, dict(request=request, saved_at=latest.get('corrected_at'),
                saved_by=dict(user_id=latest.get('corrected_by'))),
                f"Corrected imported records ({', '.join(currencies)})")
        items = session.execute(select(FinancialImportBatchItem, FinancialImportBatch)
            .join(FinancialImportBatch, FinancialImportBatch.id == FinancialImportBatchItem.batch_id)
            .where(FinancialImportBatchItem.file_id == previous.id,
                   FinancialImportBatch.case_id == file.case_id,
                   FinancialImportBatchItem.review_request.is_not(None))
            .order_by(FinancialImportBatchItem.updated_at.desc(), FinancialImportBatchItem.id))
        for item, batch in items:
            add(previous, dict(request=item.review_request,
                saved_at=item.updated_at.isoformat(),
                saved_by=(item.summary or {}).get('review_saved_by')),
                'Bulk review', item.statement_key)
    return records


def recovery_state(session, file, *, sources, choices, statement_id, revision, cache=None):
    cache = cache if cache is not None else {}
    key = ('previous-reviews', str(file.id))
    if key not in cache:
        cache[key] = saved_ancestor_reviews(session, file)
    records = cache[key]
    if not records:
        return None, None
    reading_key = ('recovery-reading', str(file.id))
    if reading_key not in cache:
        cache[reading_key] = _digest(dict(file=str(file.id), sha256=file.sha256, sources=sources,
            periods=[c['id'] for c in choices]))
    recovery_revision = _digest([cache[reading_key], sorted(r['id'] for r in records)])
    available = {c['id'] for c in choices} or {None}
    exact = [r for r in records if r['statement_id'] == statement_id]
    # More than one saved alternative is not resolved by picking a timestamp.
    previous = exact[0] if len(exact) == 1 else None
    unmatched = sum(r['statement_id'] not in available for r in records)
    required = bool(unmatched or len(exact) > 1 or
                    (revision and previous and previous['request'].get('expected_revision') != revision))
    comparison = (file.metadata_ or {}).get('financial_review_comparison', {})
    acknowledged = comparison.get('revision') == recovery_revision
    summaries = [dict(id=r['id'], evidence_file_id=r['evidence_file_id'], filename=r['filename'],
        statement_id=r['statement_id'], origin=r['origin'], saved_at=r['saved_at'],
        saved_by=r['saved_by'], holder=r['request'].get('holder', ''),
        account=r['request'].get('account_number', ''), currency=r['request'].get('currency', ''),
        period_start=r['request'].get('period_start', ''), period_end=r['request'].get('period_end', ''),
        row_count=len(r['request']['rows']), changed_row_count=sum(bool(row.get('reason')) for row in r['request']['rows']),
        period_found=r['statement_id'] in available) for r in records]
    return dict(revision=recovery_revision, required=required, acknowledged=acknowledged,
        unmatched_count=unmatched, reviews=summaries,
        compared_at=comparison.get('saved_at') if acknowledged else None), previous


def previous_review_detail(session, *, case_id, evidence_file_id, review_id, offset=0, limit=30):
    file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_file_id,
        EvidenceFile.case_id == case_id))
    if file is None:
        raise PdfMappingError('Statement not found in this case.', 404)
    record = next((r for r in saved_ancestor_reviews(session, file) if r['id'] == review_id), None)
    if record is None:
        raise PdfMappingError('The earlier saved review changed or is unavailable. Reopen this statement.', 409)
    request = record['request']
    return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id),
        review_id=review_id, request={**request, 'rows': request['rows'][offset:offset + limit]},
        row_count=len(request['rows']), offset=offset)


def acknowledge_recovery(session, *, case_id, evidence_file_id, expected_revision, actor):
    from services.financial.statement_import import read_statement_import
    file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_file_id,
        EvidenceFile.case_id == case_id).with_for_update().execution_options(populate_existing=True))
    if file is None:
        raise PdfMappingError('Statement not found in this case.', 404)
    proposal = read_statement_import(session, case_id=case_id, evidence_file_id=evidence_file_id,
        _include_period_checks=False)
    recovery = proposal.get('review_recovery')
    if not recovery or recovery['revision'] != expected_revision:
        raise PdfMappingError('The saved reviews or new reading changed. Reload and compare them before continuing.', 409)
    saved = dict(revision=expected_revision, saved_at=datetime.now(timezone.utc).isoformat(),
        saved_by=dict(user_id=str(actor.user_id), name=actor.name))
    metadata = deepcopy(file.metadata_ or {})
    metadata.setdefault('financial_review_comparison_history', []).append(saved)
    metadata['financial_review_comparison'] = saved
    file.metadata_ = metadata
    # A file-wide comparison should not require opening and saving every
    # unchanged period just to refresh its old readiness message.
    from services.financial.import_batches import assess
    items = session.scalars(select(FinancialImportBatchItem)
        .join(FinancialImportBatch, FinancialImportBatch.id == FinancialImportBatchItem.batch_id)
        .where(FinancialImportBatch.case_id == case_id,
               FinancialImportBatchItem.file_id == evidence_file_id,
               FinancialImportBatchItem.status.in_(('attention', 'ready')))
        .with_for_update(of=FinancialImportBatchItem)).all()
    cache = {}
    for item in items:
        current = read_statement_import(session, case_id=case_id, evidence_file_id=evidence_file_id,
            currency=item.summary.get('currency'), statement_id=item.statement_key or None,
            _include_period_checks=False, _cache=cache)
        if item.summary.get('revision') != current['revision']:
            continue  # A changed reading needs its own edit recovery, not just acknowledgement.
        status, summary = assess(current, item.review_request)
        item.status = status
        item.summary = {**item.summary, **summary}
    session.commit()
    return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), **saved)
