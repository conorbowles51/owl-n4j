"""Move extracted rows between unimported periods without changing their sources.

The file owns the assignment. Each saved review keeps its own corrected values;
the operation migrates both sides atomically and binds its preview to all drafts.
"""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID, uuid5
from typing import Annotated
from pydantic import Field
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial.pdf_candidates import PdfMappingError, _Contract, _Digest, _digest
from services.financial.statement_import import StatementReviewDraft


class RowAssignmentRequest(_Contract):
    request: StatementReviewDraft
    target_statement_id: _Digest
    row_ids: Annotated[list[Annotated[str, Field(min_length=1, max_length=80)]], Field(min_length=1, max_length=25000)]
    reason: Annotated[str, Field(min_length=1, max_length=2000)]
    expected_review_revision: Annotated[str, Field(min_length=1, max_length=64)]
    batch_id: UUID | None = None
    expected_preview: _Digest | None = None


def _base(session, file, currency, statement_id, cache):
    from services.financial.statement_import import read_statement_import
    key = ('assignment-base', str(file.id), currency, statement_id)
    if key not in cache:
        try:
            cache[key] = read_statement_import(session, case_id=file.case_id, evidence_file_id=file.id,
                currency=currency, statement_id=statement_id, _cache=cache,
                _include_period_checks=False, _apply_assignments=False)
        except PdfMappingError as exc:
            if exc.status_code == 409 and statement_id in (file.metadata_ or {}).get('financial_row_assignments', {}).get('base_revisions', {}):
                raise PdfMappingError('The PDF reading changed after transactions were moved. Reprocess a new version and compare the saved reviews; existing assignments and imports are retained.', 409) from exc
            raise
    return cache[key]


def assigned_proposal(session, file, proposal, cache):
    state = (file.metadata_ or {}).get('financial_row_assignments')
    period = proposal.get('statement_id')
    if not state or period not in state['base_revisions']:
        return proposal
    if state.get('currency') and proposal['currency'] != state['currency']:
        raise PdfMappingError('These saved transaction moves use ' + state['currency'] + '. Select that currency to reopen their reviews.', 409)
    for key, expected in state['base_revisions'].items():
        if _base(session, file, proposal['currency'], key, cache)['revision'] != expected:
            raise PdfMappingError('The PDF reading changed after transactions were moved. Reprocess a new version and compare the saved reviews; existing assignments and imports are retained.', 409)
    result = deepcopy(proposal)
    outgoing = {key for key, move in state['rows'].items()
                if move['original_statement_id'] == period and move['target_statement_id'] != period}
    result['rows'] = [row for row in result['rows'] if row['id'] not in outgoing]
    sources = {(s['page_number'], s['table_index']): s for s in result['sources']}
    for key, move in state['rows'].items():
        if move['target_statement_id'] != period:
            continue
        original = _base(session, file, proposal['currency'], move['original_statement_id'], cache)
        row = next((r for r in original['rows'] if r['id'] == key), None)
        if row is None:
            raise PdfMappingError('A moved transaction is no longer in its original reading. Reprocess a new version before importing.', 409)
        row = deepcopy(row)
        row['assignment'] = deepcopy(move)
        row['assignment_reason'] = '\n'.join(event['reason'] for event in move['history'])
        result['rows'] = [r for r in result['rows'] if r['id'] != key]
        result['rows'].append(row)
        for source in original['sources']:
            if (source['page_number'], source['table_index']) == (row['page_number'], row['table_index']):
                sources[(source['page_number'], source['table_index'])] = source
    # Preserve printed page order where it was identified; within each page,
    # source positions place incoming rows without altering their PDF location.
    pages = list(proposal['statement_page_numbers'])
    pages.extend(sorted({r['page_number'] for r in result['rows']} - set(pages)))
    page_order = {page: index for index, page in enumerate(pages)}
    result['rows'].sort(key=lambda r: (page_order[r['page_number']], r['table_index'], r['row_index']))
    result['sources'] = list(sources.values())
    result['statement_page_numbers'] = pages
    result['statement_row_addresses'] = [[r['page_number'], r['table_index'], r['row_index']] for r in result['rows']]
    result['statement_source_regions'] = None  # Never reuse a pre-move region envelope.
    result['assigned_period_ids'] = sorted(state['base_revisions'])
    relevant = {key: move for key, move in state['rows'].items()
                if period in (move['original_statement_id'], move['target_statement_id'])}
    result['row_assignments'] = list(relevant.values())
    result['revision'] = _digest(dict(reading=proposal['revision'], assignments=relevant))
    result['transaction_count'] = sum(not row['excluded'] for row in result['rows'])
    result['needs_attention'] = sum(bool(row['issues']) for row in result['rows']) + len(result['issues'])
    from services.financial.statement_import import _check_review_size
    _check_review_size(result['rows'])
    return result


def assignment_choices(session, file, choices, currency, cache):
    state = (file.metadata_ or {}).get('financial_row_assignments')
    if not state or not currency:
        return choices
    from services.financial.import_batches import initial_request
    from services.financial.review_arithmetic import check_proposed_rows
    result = []
    for choice in choices:
        if choice['id'] not in state['base_revisions']:
            result.append(choice)
            continue
        proposal = assigned_proposal(session, file, _base(session, file, currency, choice['id'], cache), cache)
        saved = (proposal.get('saved_review') or {}).get('request')
        request = saved if saved and saved['expected_revision'] == proposal['revision'] else initial_request(proposal)
        result.append({**choice, 'checks': check_proposed_rows(proposal, request['rows'])})
    return result


def _label(request):
    return ' · '.join(filter(None, (request.get('holder'), request.get('account_number'),
        ' to '.join(filter(None, (request.get('period_start'), request.get('period_end')))))))


def reassign_rows(session, *, case_id, evidence_file_id, body, actor, apply=False):
    from services.financial.statement_import import read_statement_import
    from services.financial.import_batches import initial_request, assess
    from services.financial.review_arithmetic import check_proposed_rows
    file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_file_id,
        EvidenceFile.case_id == case_id).with_for_update().execution_options(populate_existing=True))
    if file is None:
        raise PdfMappingError('Statement not found in this case.', 404)
    source_id, target_id = body.request.statement_id, body.target_statement_id
    if not source_id or source_id == target_id:
        raise PdfMappingError('Choose a different recognised account and statement period in this PDF.', 422)
    selected = set(body.row_ids)
    if len(selected) != len(body.row_ids) or not body.reason.strip():
        raise PdfMappingError('Select each transaction once and explain why it belongs to the other statement.', 422)
    cache = {}
    proposals = {key: read_statement_import(session, case_id=case_id, evidence_file_id=evidence_file_id,
        currency=body.request.currency, statement_id=key, _cache=cache, _include_period_checks=False)
        for key in (source_id, target_id)}
    if any(p.get('current_import') for p in proposals.values()):
        raise PdfMappingError('A statement in this move is already imported. Its existing transactions must be corrected through their import history.', 409)
    if any(p.get('document_review') or p.get('reading_failure') for p in proposals.values()):
        raise PdfMappingError('Choose two recognised statement periods before moving transactions.', 422)
    originals = {row['id']: row for row in proposals[source_id]['rows']}
    if not selected <= originals.keys() or any(originals[key]['kind'] not in ('transaction', 'unresolved') for key in selected):
        raise PdfMappingError('Only extracted transaction rows can move. Keep balances, totals and manually added rows in their current review.', 422)
    if selected & {row['id'] for row in proposals[target_id]['rows']}:
        raise PdfMappingError('The destination already contains a selected source row. Compare its existing reading before moving it.', 409)
    items = list(session.scalars(select(Item).join(Batch, Batch.id == Item.batch_id).where(
        Batch.case_id == case_id, Item.file_id == evidence_file_id, Item.statement_key.in_((source_id, target_id)))
        .order_by(Item.id).with_for_update(of=Item).execution_options(populate_existing=True)))
    if any(item.status in ('pending_import', 'imported') for item in items):
        raise PdfMappingError('A statement in this move is being imported or was imported. Refresh its batch before continuing.', 409)
    metadata = deepcopy(file.metadata_ or {})
    progress = metadata.get('financial_review_progress', {})
    contexts = {None: {key: deepcopy((progress.get(key) or {}).get('request') or initial_request(proposals[key]))
                       for key in (source_id, target_id)}}
    batch_items = {}
    for item in items:
        batch_items[(item.batch_id, item.statement_key)] = item
        contexts.setdefault(item.batch_id, {})[item.statement_key] = deepcopy(item.review_request or
            (progress.get(item.statement_key) or {}).get('request') or initial_request(proposals[item.statement_key]))
    for requests in contexts.values():
        for key in (source_id, target_id):
            requests.setdefault(key, deepcopy(contexts[None][key]))
    if body.batch_id:
        active = batch_items.get((body.batch_id, source_id))
        if active is None:
            raise PdfMappingError('Open the source statement from this batch again.', 404)
        current_revision = _digest(active.review_request or {})
    else:
        current_revision = (progress.get(source_id) or {}).get('review_revision', 'initial')
    if current_revision != body.expected_review_revision:
        raise PdfMappingError('Another reviewer saved this statement. Reopen it before moving rows; their changes have not been overwritten.', 409)
    contexts[body.batch_id][source_id] = body.request.model_dump(mode='json')
    for requests in contexts.values():
        for key, request in requests.items():
            if request['expected_revision'] != proposals[key]['revision']:
                raise PdfMappingError('An affected statement has corrections from an older reading. Compare and save that review before moving transactions.', 409)
            if request['currency'] != body.request.currency:
                raise PdfMappingError('The statements use different currencies. Moving a row cannot convert its currency.', 422)
            check_proposed_rows(proposals[key], request['rows'])
    before_checks = {key: check_proposed_rows(proposals[key], contexts[body.batch_id][key]['rows'])
                     for key in (source_id, target_id)}
    # Any save, import queue, reading change or different selection invalidates
    # the preview. The payload itself is included so unsaved edits are bound too.
    preview_revision = _digest(dict(body=body.model_dump(mode='json', exclude={'expected_preview'}),
        proposals={key:p['revision'] for key,p in proposals.items()}, progress=progress,
        items=[dict(id=str(i.id), status=i.status, summary=i.summary, request=i.review_request) for i in items],
        assignments=metadata.get('financial_row_assignments')))
    if apply and body.expected_preview != preview_revision:
        raise PdfMappingError('The statements or saved reviews changed after the preview. Preview this move again.', 409)
    state = deepcopy(metadata.get('financial_row_assignments') or dict(base_revisions={}, rows={}, currency=body.request.currency))
    for key in (source_id, target_id):
        state['base_revisions'][key] = _base(session, file, body.request.currency, key, cache)['revision']
    event = dict(from_statement_id=source_id, to_statement_id=target_id, reason=body.reason.strip(),
                 saved_at=datetime.now(timezone.utc).isoformat(), saved_by=dict(user_id=str(actor.user_id), name=actor.name))
    for key in sorted(selected):
        previous = state['rows'].get(key)
        state['rows'][key] = dict(row_id=key, original_statement_id=previous['original_statement_id'] if previous else source_id,
            target_statement_id=target_id, history=[*(previous['history'] if previous else []), event])
    metadata['financial_row_assignments'] = state
    # A detached view calculates the preview without writing or triggering an
    # autoflush. The real Evidence row is updated only after final validation.
    from types import SimpleNamespace
    future_file = SimpleNamespace(id=file.id, case_id=file.case_id, metadata_=metadata)
    after = {key: assigned_proposal(session, future_file,
             _base(session, file, body.request.currency, key, cache), cache) for key in (source_id, target_id)}
    for requests in contexts.values():
        moving = [deepcopy(row) for row in requests[source_id]['rows'] if row['id'] in selected]
        for row in moving:
            row['reason'] = '\n'.join(filter(None, (row.get('reason', '').strip(),
                'Moved to ' + _label(requests[target_id]) + ': ' + body.reason.strip())))
            if len(row['reason']) > 4096:
                raise PdfMappingError('A selected row has a long correction history. Shorten its explanation before moving it.', 422)
        requests[source_id]['rows'] = [r for r in requests[source_id]['rows'] if r['id'] not in selected]
        requests[target_id]['rows'].extend(moving)
        for key, request in requests.items():
            request['expected_revision'] = after[key]['revision']
            request['balance_exception_revision'] = None
            request['balance_exception_reason'] = ''
            StatementReviewDraft.model_validate(request)
            check_proposed_rows(after[key], request['rows'])
    active = contexts[body.batch_id]
    result = dict(case_id=str(case_id), evidence_file_id=str(file.id), revision=preview_revision,
        moved_rows=len(selected), affected_reviews=len(contexts),
        statements=[dict(statement_id=key, label=_label(active[key]),
            before=before_checks[key],
            after=check_proposed_rows(after[key], active[key]['rows'])) for key in (source_id, target_id)])
    if not apply:
        return {**result, 'applied': False}
    saved_at = event['saved_at']
    for key, request in contexts[None].items():
        previous = progress.get(key)
        if previous:
            metadata.setdefault('financial_review_history', []).append(previous)
        metadata.setdefault('financial_review_progress', {})[key] = dict(request=request,
            review_revision=_digest(request), saved_at=saved_at, saved_by=event['saved_by'])
    metadata.setdefault('financial_assignment_history', []).append({**event, 'row_ids': sorted(selected), 'preview_revision': preview_revision})
    file.metadata_ = metadata
    for batch_id, requests in contexts.items():
        if batch_id is None:
            continue
        for key, request in requests.items():
            item = batch_items.get((batch_id, key))
            if item is None:
                sibling = next(i for i in items if i.batch_id == batch_id)
                item = Item(id=uuid5(batch_id, str(file.id)+':'+key), batch_id=batch_id, file_id=file.id,
                    statement_key=key, status='attention', summary=dict(sibling.summary))
                session.add(item)
            # Keep earlier batch values for later reprocessing comparisons.
            if item.review_request:
                metadata.setdefault('financial_review_history', []).append(dict(request=deepcopy(item.review_request),
                    review_revision=_digest(item.review_request), saved_at=item.updated_at.isoformat(),
                    saved_by=(item.summary or {}).get('review_saved_by')))
            proposal = {**after[key], 'saved_review': metadata['financial_review_progress'][key]}
            status, summary = assess(proposal, request)
            item.status = status
            item.summary = {**item.summary, **summary, 'review_saved_by': event['saved_by']}
            item.review_request = request
    file.metadata_ = deepcopy(metadata)
    session.commit()
    return {**result, 'applied': True}
