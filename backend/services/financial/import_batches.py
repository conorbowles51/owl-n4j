"""Case-scoped folder batches. Preparation and imports survive browser navigation."""
import asyncio
import logging
import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4, uuid5
from types import SimpleNamespace
from sqlalchemy import select
from pydantic import ValidationError
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item, FinancialImportOperation as Operation
from postgres.models.evidence import EvidenceFile
from services.financial.pdf_candidates import PdfMappingError, _digest
from services.financial.decisions import Actor
from services.financial.evidence_intake import resolve_financial_selection, prepare_existing_financial_file
from services.financial.statement_import import read_statement_import, StatementImportRequest, check_import_request, confirm_statement_import, _date_roles, _primary_date_role
from services.financial.review_arithmetic import check_proposed_rows, arithmetic_problems, accepted_difference

log = logging.getLogger(__name__)
TERMINAL_FILES = {'checked', 'error'}
REVIEW_MODEL = 'recognised-payments-saved-reviews-v2'
IMPORTS_PER_TURN = 4
FILES_PER_TURN = 4
TURN_SECONDS = 30


def batch_for(session, case_id, batch_id, lock=False):
    query = select(Batch).where(Batch.id == batch_id, Batch.case_id == case_id)
    batch = session.scalar(query.with_for_update() if lock else query)
    if batch is None:
        raise PdfMappingError('Financial processing batch not found in this case.', 404)
    if batch.status == 'removed':
        raise PdfMappingError('This batch was removed. Return to statement files to start a fresh batch.', 409)
    return batch


def create_batch(session, *, case_id, request_id, file_ids, folder_ids, actor):
    selection = resolve_financial_selection(session, case_id=case_id, file_ids=file_ids, folder_ids=folder_ids)
    existing = session.get(Batch, request_id)
    if existing:
        if existing.status == 'removed':
            raise PdfMappingError('This batch was removed. Start a new preparation run.', 409)
        if existing.case_id != case_id or existing.created_by != actor.user_id:
            raise PdfMappingError('This request belongs to another batch.', 409)
        from services.financial.source_lineage import lineage_id
        existing_files = session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id,
            EvidenceFile.id.in_([UUID(f['source_id']) for f in existing.files])))
        if {lineage_id(f) for f in existing_files} != {f['root_file_id'] for f in selection['files']}:
            raise PdfMappingError('The selection changed. Start a new batch for these files.', 409)
        return existing.id
    if not selection['files']:
        raise PdfMappingError('No PDF files were found in this selection.', 422)
    session.add(Batch(id=request_id, case_id=case_id, created_by=actor.user_id, status='preparing',
        actor=dict(name=actor.name, email=actor.email, user_id=str(actor.user_id)),
        files=[dict(source_id=f['id'], file_id=f['id'], filename=f['original_filename'],
                    expected_revision=f['financial_visibility_revision'], status='waiting') for f in selection['files']]))
    session.commit()
    return request_id


def initial_request(proposal):
    metadata = proposal['metadata']
    return dict(expected_revision=proposal['revision'], statement_id=proposal.get('statement_id'),
        currency=proposal['currency'], holder=metadata.get('holder',''), account_number=metadata.get('account_number',''),
        institution=metadata.get('institution',''), period_start=metadata.get('period_start',''), period_end=metadata.get('period_end',''),
        rows=[dict(id=r['id'], excluded=r['excluded'], date=r['fields'].get('date') or r['fields'].get('booking_date') or r['fields'].get('value_date') or '',
            date_unprinted=r['fields'].get('date_basis') == 'statement_end_ordering_only',
            date_values={role:r['fields'].get(role,'') for role in _date_roles(r['fields']) if role != _primary_date_role(r['fields'])},
            description=r['fields'].get('description',''), counterparty=r['fields'].get('counterparty',''),
            amount_minor=r['fields'].get('amount_minor') or ('0' if r['excluded'] else ''), direction=r['fields'].get('direction'),
            balance_minor=r['fields'].get('balance'), reason=r.get('assignment_reason', '')) for r in proposal['rows']])


def assess(proposal, request=None):
    """Checks stay visible; import availability reflects structural validity."""
    problems = []
    can_import = True
    raw = request or initial_request(proposal)
    rows = proposal['rows']
    current = proposal.get('current_import')
    if proposal.get('document_review'):
        can_import = False
        problems.append(dict(message='This is a receipt or payment document. Open its document review.', row_id=None))
    if proposal.get('reading_failure'):
        can_import = False
        problems.append(dict(message=proposal['reading_failure'], row_id=None))
    recovery = proposal.get('review_recovery')
    if recovery and recovery['required'] and not recovery['acknowledged']:
        problems.append(dict(message='Compare the earlier saved reviews for this file before importing. Saved corrections may belong to different statement periods in the new reading.', row_id=None))
    if not proposal['currency']:
        problems.append(dict(message='Choose the currency printed on these statements.', row_id=None))
    try:
        validated = StatementImportRequest.model_validate(raw)
        check_import_request(proposal, validated)
    except (ValidationError, PdfMappingError) as error:
        can_import = False
        if isinstance(error, ValidationError):
            for issue in error.errors(include_url=False, include_input=False)[:30]:
                path = issue['loc']
                row_id = raw['rows'][path[1]]['id'] if len(path)>1 and path[0]=='rows' and isinstance(path[1],int) and path[1]<len(raw['rows']) else None
                label = {'holder':'account holder','account_number':'account number','currency':'statement currency','amount_minor':'amount','date':'date'}.get(str(path[-1]) if path else '', 'statement details')
                message=issue['msg'].removeprefix('Value error, ')
                if path == ('rows',) and not raw['rows']:
                    if not proposal['currency']:
                        continue  # The currency action already explains the next step.
                    message='No transactions or balances were identified. Open the statement to add its printed balances or missing transactions.'
                elif 'isoformat' in message:
                    message='Enter the complete date shown on the statement.'
                elif issue['type']=='string_pattern_mismatch':
                    message=f'Check the {label} against the statement and enter a usable value.'
                elif issue['type'] in ('string_too_short','missing'):
                    message=f'Enter the {label} shown on the statement.'
                problems.append(dict(message=message, row_id=row_id))
        else:
            problems.append(dict(message=str(error), row_id=None))
    reviewed = {r['id']:r for r in raw['rows']}
    from services.financial.import_issues import row_reviewed
    for row in rows:
        edit = reviewed.get(row['id'],{})
        if row['issues'] and not edit.get('excluded', row['excluded']) and not row_reviewed(row, edit):
            problems.append(dict(message=' '.join(row['issues']),row_id=row['id'],page=row['page_number']))
    balance = check_proposed_rows(proposal, raw['rows'])
    if can_import:
        from services.financial.import_issues import retained_issues
        for issue in retained_issues(proposal, validated):
            if not any(p.get('row_id') == issue.get('row_id') and p['message'] == issue['message'] for p in problems):
                problems.append(issue)
    if not accepted_difference(balance, raw):
        problems.extend(arithmetic_problems(balance))
    # One link per affected row, with all explanations beside it.
    combined=[]
    for problem in problems:
        matching=next((p for p in combined if problem.get('row_id') and p.get('row_id')==problem['row_id']),None)
        if matching:
            if problem['message'] not in matching['message']:
                matching['message']+=' '+problem['message']
            if problem.get('page'): matching['page']=problem['page']
        elif problem not in combined:
            combined.append(problem)
    problems=combined
    summary = dict(revision=proposal['revision'], page_number=min((r.get('page_number', 1) for r in rows if not r['excluded']), default=min(proposal.get('page_numbers') or [1])), transaction_count=sum(not r['excluded'] for r in raw['rows']), currency=proposal['currency'],
        holder=raw.get('holder',''), institution=raw.get('institution',''), account=raw.get('account_number',''), period_start=raw.get('period_start',''),period_end=raw.get('period_end',''),
        balance_status=balance['balance_status'], checks=balance['checks'],
        can_import=can_import, balance_exception=accepted_difference(balance, raw), problems=problems[:50], problem_count=len(problems))
    summary['review_model'] = REVIEW_MODEL
    summary['unclassified_count'] = sum(row['kind'] == 'unclassified' and reviewed.get(row['id'], {}).get('excluded', row['excluded']) for row in rows)
    if can_import:
        from services.financial.import_issues import incomplete_records
        incomplete = len(incomplete_records(proposal, validated))
        summary.update(record_count=summary['transaction_count'], incomplete_count=incomplete,
            transaction_count=summary['transaction_count'] - incomplete)
    if current:
        retained = current.get('issues', problems)
        details = current.get('details', {})
        summary.update({key: details[key] for key in ('holder', 'institution', 'period_start', 'period_end') if key in details})
        if 'account_number' in details:
            summary['account'] = details['account_number']
        summary.update(transaction_count=current['transaction_count'], record_count=current.get('record_count', current['transaction_count']),
            incomplete_count=current.get('incomplete_count', 0), problems=retained[:50], problem_count=len(retained), can_import=False,
            source_document_id=current['source_document_id'], account_id=current['account_id'])
        return 'imported', summary
    if proposal.get('assignment_only'):
        remaining = [row for row in rows if row['kind'] in ('transaction', 'unresolved')]
        summary['assignment_only'] = True
        summary['can_import'] = False
        summary['account'] = 'Unassigned payments · main account ' + proposal.get('printed_main_account', '')
        if not remaining:
            summary.update(transaction_count=0, problems=[], problem_count=0)
            return 'assigned', summary
        assignment_problem = dict(message='Choose the correct account and period for these payments. Open the review and use Assign payments to a statement.', row_id=None)
        summary['problems'] = [assignment_problem, *[p for p in summary['problems'] if p.get('row_id')]][:50]
        summary['problem_count'] = 1 + len([p for p in problems if p.get('row_id')])
        return 'attention', summary
    return ('attention' if problems else 'ready'), summary


def prepare_reviews(session, batch, file):
    cache = {}
    fid = UUID(file['file_id'])
    session.execute(select(EvidenceFile).where(EvidenceFile.id == fid,
        EvidenceFile.case_id == batch.case_id).with_for_update().execution_options(populate_existing=True)).all()
    first = read_statement_import(session,case_id=batch.case_id,evidence_file_id=fid,currency=file.get('currency'),_cache=cache)
    choices = first.get('statement_choices',[])
    identifiers = [c['id'] for c in choices]
    if not identifiers: identifiers=[None]
    for statement_id in identifiers:
        proposal = read_statement_import(session,case_id=batch.case_id,evidence_file_id=fid,currency=file.get('currency') or None,statement_id=statement_id,_cache=cache)
        key = statement_id or proposal.get('statement_id') or ''
        identifier = uuid5(batch.id, str(fid)+':'+key)
        existing = session.get(Item,identifier)
        if existing and (existing.review_request or existing.status in ('imported','pending_import','skipped')):
            continue
        progress = proposal.get('saved_review') or proposal.get('previous_saved_review')
        draft = progress.get('request') if progress else None
        if draft and draft.get('expected_revision') != proposal['revision']:
            if proposal.get('saved_review'):
                raise PdfMappingError('This file has saved corrections from an earlier reading. Open its individual statement review, compare them and save progress before adding it to bulk import.', 409)
            # Keep the new reading editable while earlier values stay in the
            # recovery panel. Assessment holds import until comparison is saved.
            draft = None
        status,summary = assess(proposal, draft)
        summary.update(filename=file['filename'], currency=proposal['currency'], source_id=file['source_id'])
        if existing:
            existing.status=status; existing.summary=summary; existing.review_request=draft
        else:
            session.add(Item(id=identifier,batch_id=batch.id,file_id=fid,statement_key=key,status=status,summary=summary,review_request=draft))
    # A former file-level currency question is replaced by its actual periods.
    if choices:
        stale = session.get(Item,uuid5(batch.id,str(fid)+':'))
        if stale and stale.status=='attention' and not stale.review_request:
            session.delete(stale)
    session.commit()


def import_available(item):
    return item.status in ('ready', 'attention') and item.summary.get('can_import', item.status == 'ready')


def ready_revision(items):
    return _digest(sorted((str(i.id),i.summary['revision'],_digest(i.review_request or {}),
                          (i.summary.get('coverage_review') or {}).get('revision')) for i in items if import_available(i)))


def checked_batch_items(session, case_id, items):
    """Project current coverage concerns without making a GET write changes."""
    items = [item for item in items if item.status != "removed"]
    from services.financial.statement_import_overlap import coverage_review, summary_request, requires_decision, comparison_sources
    pending = session.execute(select(Item, EvidenceFile).join(Batch, Batch.id == Item.batch_id)
        .join(EvidenceFile, EvidenceFile.id == Item.file_id).where(Batch.case_id == case_id,
        EvidenceFile.case_id == case_id, Item.status.in_(('ready','attention','pending_import')))).all()
    sources, prepared = comparison_sources(session, case_id, pending)
    cache = {}
    from postgres.models.financial import FinancialSourceDocument
    saved_files = set(session.scalars(select(FinancialSourceDocument.evidence_file_id).where(
        FinancialSourceDocument.case_id == case_id, FinancialSourceDocument.status == 'admitted',
        FinancialSourceDocument.evidence_file_id.in_([item.file_id for item in items]))))
    imported_ids = [UUID(i.summary['source_document_id']) for i in items
                    if i.status == 'imported' and i.summary.get('source_document_id')]
    from services.financial.batch_import_history import current_imports
    retained = current_imports(session, case_id, imported_ids)
    result = []
    for item in items:
        summary = deepcopy(item.summary)
        state = item.status
        projected_request = item.review_request
        if state in ('ready', 'attention'):
            if item.file_id in saved_files or 'can_import' not in summary or summary.get('review_model') != REVIEW_MODEL:
                try:
                    proposal = read_statement_import(session, case_id=case_id, evidence_file_id=item.file_id,
                        currency=summary.get('currency') or None, statement_id=item.statement_key or None, _cache=cache)
                    from services.financial.review_upgrade import upgrade_request
                    projected_request = upgrade_request(item.review_request, proposal) or item.review_request
                    state, assessment = assess(proposal, None if proposal.get('current_import') else projected_request)
                    summary.update(assessment)
                except PdfMappingError as error:
                    summary.update(can_import=False, problems=[dict(message=str(error), row_id=None)], problem_count=1)
            if state in ('ready', 'attention'):
                raw = {**(projected_request or prepared.get(item.id) or summary_request(summary)), 'statement_id': item.statement_key or None}
                review = coverage_review(session, case_id=case_id, file_id=item.file_id, request=raw, sources=sources)
                problems = [p for p in summary.get('problems', []) if p.get('kind') not in ('coverage', 'coverage_load')]
                extra_count = max(0, summary.get('problem_count', 0) - len(summary.get('problems', [])))
                if raw.get('_coverage_error'):
                    problems.append(dict(kind='coverage_load', row_id=None, message=raw['_coverage_error']))
                if requires_decision(review, raw):
                    problems.append(dict(kind='coverage', row_id=None,
                        message='Another statement covers some of these dates. You can compare their payments now or after importing.'))
                summary.update(coverage_review=review, problems=problems, problem_count=len(problems) + extra_count)
                state = 'attention' if problems else 'ready'
        if state == 'imported' and summary.get('source_document_id') and summary['source_document_id'] not in retained:
            retained.update(current_imports(session, case_id, [UUID(summary['source_document_id'])]))
        if state == 'imported' and summary.get('source_document_id') in retained:
            current = retained[summary['source_document_id']]
            issues, records, review = current['issues'], current['records'], current['review']
            summary.update(source_document_id=current['source_document_id'], account_id=current['account_id'], currency=current['currency'],
                balance_status=current['balance_status'])
            details = review.get('details', {})
            if details:
                summary.update(holder=details.get('holder', ''), account=details.get('account_number', ''),
                    institution=details.get('institution', ''), period_start=details.get('period_start', ''),
                    period_end=details.get('period_end', ''))
                issues = [issue for issue in issues if not (issue.get('kind') == 'statement_detail' and
                    details.get(issue.get('field')))]
            unresolved = sum(not r.get('resolved_transaction_id') for r in records)
            summary.update(problems=issues[:50], problem_count=len(issues), incomplete_count=unresolved,
                transaction_count=current['transaction_count'], record_count=current['transaction_count'] + unresolved)
        summary['disposition_revision'] = _digest(dict(status=item.status, request=item.review_request,
            decision=item.summary.get('import_decision')))
        summary['currency_revision'] = currency_revision(item, summary)
        from services.financial.batch_review_summary import tagged_problems
        summary['problems'] = tagged_problems(summary)
        result.append(SimpleNamespace(id=item.id, file_id=item.file_id, statement_key=item.statement_key,
            status=state, summary=summary, review_request=projected_request,
            review_revision=_digest(item.review_request or {})))
    return result


def currency_revision(item, summary=None):
    return _digest(dict(status=item.status, revision=(summary if summary is not None else item.summary).get('revision'), request=item.review_request))


def rebase_review_currency(old, new, raw, currency):
    """Keep row corrections and printed values when a draft currency changes."""
    from services.financial.currency_correction import rescale_minor
    baseline = initial_request(old)
    merged = initial_request(new)
    old_rows = {r['id']: r for r in baseline['rows']}
    new_rows = {r['id']: r for r in merged['rows']}
    for row in raw['rows']:
        changes = {key: value for key, value in row.items() if value != old_rows.get(row['id'], {}).get(key)}
        if row['id'] not in new_rows:
            if row.get('manual_page'):
                manual = deepcopy(row)
                if old['currency']:
                    for key in ('amount_minor', 'balance_minor'):
                        if manual.get(key) is not None:
                            manual[key] = rescale_minor(manual[key], old['currency'], currency)
                merged['rows'].append(manual)
            elif changes:
                raise PdfMappingError('The new currency changes a corrected row. Open that statement to compare it; no selected currencies were changed.', 409)
        else:
            new_rows[row['id']].update(changes)
            if old['currency']:
                # Preserve readable and manually corrected amounts even
                # when the selected label differs from printed symbols.
                for key in ('amount_minor', 'balance_minor'):
                    value = row.get(key)
                    if isinstance(value, str) and value.lstrip('-').isdigit():
                        new_rows[row['id']][key] = rescale_minor(value, old['currency'], currency)
                if row.get('direction'):
                    new_rows[row['id']]['direction'] = row['direction']
    for key, value in raw.items():
        if key not in ('rows', 'currency', 'expected_revision', 'statement_id', 'balance_exception_revision', 'coverage_review_revision') and value != baseline.get(key):
            merged[key] = deepcopy(value)
    merged.update(currency=currency, expected_revision=new['revision'], statement_id=new.get('statement_id'))
    check_proposed_rows(new, merged['rows'])
    return merged


def set_selected_currency(session, *, case_id, batch_id, selections, currency, actor):
    """Change unimported statements atomically; preserve all saved corrections."""
    from services.financial.currency_correction import currency_code
    try:
        currency = currency_code(currency)
    except ValueError as exc:
        raise PdfMappingError(str(exc), 422) from exc
    try:
        batch = batch_for(session, case_id, batch_id, True)
        if batch.worker_token and batch.lease_until and batch.lease_until.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
            raise PdfMappingError('The batch is still processing. Your selection is kept; retry when processing finishes.', 409)
        expected = {str(selection.id): selection.revision for selection in selections}
        if len(expected) != len(selections):
            raise PdfMappingError('Select each statement once.', 422)
        items = list(session.scalars(select(Item).where(Item.batch_id == batch.id, Item.id.in_([UUID(i) for i in expected])).order_by(Item.file_id, Item.id).with_for_update()))
        if len(items) != len(expected):
            raise PdfMappingError('A selected statement is not in this batch. Refresh the selection.', 404)
        cache = {}
        for item in items:
            if item.status not in ('ready', 'attention'):
                raise PdfMappingError('A selected statement changed or was already imported. Refresh the selection; no currencies were changed.', 409)
            file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == item.file_id, EvidenceFile.case_id == case_id).with_for_update().execution_options(populate_existing=True))
            if file is None:
                raise PdfMappingError('A selected file is not in this case.', 404)
            old = read_statement_import(session, case_id=case_id, evidence_file_id=item.file_id,
                currency=item.summary.get('currency') or None, statement_id=item.statement_key or None, _cache=cache)
            if old.get('current_import') or currency_revision(item, old) != expected[str(item.id)]:
                raise PdfMappingError('A selected statement reading changed or was imported. Refresh the selection.', 409)
            saved = old.get('saved_review')
            raw = item.review_request or (saved or {}).get('request') or initial_request(old)
            from services.financial.review_upgrade import upgrade_request
            raw = upgrade_request(raw, old) or raw
            if saved and item.review_request and saved['request'] != raw:
                raise PdfMappingError('A selected statement has different saved reviews. Open it to compare those corrections first.', 409)
            if raw['expected_revision'] != old['revision']:
                raise PdfMappingError('A selected statement has corrections from an earlier reading. Open its saved review first.', 409)
            new = read_statement_import(session, case_id=case_id, evidence_file_id=item.file_id,
                currency=currency, statement_id=item.statement_key or None, _cache=cache)
            merged = rebase_review_currency(old, new, raw, currency)
            # A currency decision also saves the current draft for individual
            # review, so leaving the batch cannot restore the old currency.
            record = dict(request=merged, review_revision=_digest(merged), saved_at=datetime.now(timezone.utc).isoformat(),
                saved_by=dict(user_id=str(actor.user_id), name=actor.name))
            metadata = deepcopy(file.metadata_ or {})
            previous = metadata.get('financial_review_progress', {}).get(item.statement_key or '')
            if previous:
                metadata.setdefault('financial_review_history', []).append(previous)
            metadata.setdefault('financial_review_progress', {})[item.statement_key or ''] = record
            file.metadata_ = metadata
            new['saved_review'] = record
            state, summary = assess(new, merged)
            history = list(item.summary.get('currency_history', []))
            history.append(dict(before=old['currency'], after=currency, at=record['saved_at'], actor=record['saved_by']))
            item.status = state
            item.review_request = merged
            item.summary = {**item.summary, **summary, 'currency_history': history}
        session.commit()
        return dict(case_id=str(case_id), batch_id=str(batch_id), updated=len(items), currency=currency)
    except Exception:
        session.rollback()
        raise


def next_problem(session, *, case_id, batch_id, item_id, direction="next", review_group=None):
    from services.financial.batch_review_summary import matches_group, validate_group
    validate_group(review_group)
    batch_for(session, case_id, batch_id)
    items = checked_batch_items(session, case_id, list(session.scalars(select(Item).where(Item.batch_id == batch_id))))
    items.sort(key=lambda i: (i.summary.get('filename',''), i.summary.get('account',''), i.summary.get('period_start',''), str(i.id)))
    index = next((n for n, item in enumerate(items) if item.id == item_id), None)
    if index is None:
        raise PdfMappingError('Statement not found in this batch.', 404)
    ordered = items[index+1:] + items[:index]
    if direction == 'previous':
        ordered.reverse()
    remaining = [i for i in ordered if i.summary.get('problem_count', 0) and i.status != 'skipped' and matches_group(i, review_group)]
    following = remaining[0] if remaining else None
    problems = following.summary.get('problems', []) if following else []
    if review_group and review_group != 'blocked':
        problems = [p for p in problems if p.get('review_reason') == review_group]
    return dict(case_id=str(case_id), batch_id=str(batch_id), remaining=len(remaining),
        item_id=str(following.id) if following else None,
        row_id=next((p.get('row_id') for p in problems if p.get('row_id')), None))


def next_statement(session, *, case_id, batch_id, item_id, direction="next", review_group=None):
    from services.financial.batch_review_summary import matches_group, validate_group
    validate_group(review_group)
    batch_for(session, case_id, batch_id)
    items = list(session.scalars(select(Item).where(Item.batch_id == batch_id, Item.status != 'removed')))
    if review_group:
        items = checked_batch_items(session, case_id, items)
    items.sort(key=lambda i: (i.summary.get('filename', ''), i.summary.get('account', ''),
                             i.summary.get('period_start', ''), str(i.id)))
    index = next((n for n, item in enumerate(items) if item.id == item_id), None)
    if index is None:
        raise PdfMappingError('Statement not found in this batch.', 404)
    if review_group:
        matching = [i for i in items if matches_group(i, review_group)]
        ordered = list(reversed(items[:index])) if direction == 'previous' else items[index+1:]
        following = next((i for i in ordered if matches_group(i, review_group)), None)
        return dict(case_id=str(case_id), batch_id=str(batch_id), item_id=str(following.id) if following else None,
            row_id=None, position=matching.index(following)+1 if following else 0, total=len(matching))
    target = index + (-1 if direction == 'previous' else 1)
    following = items[target] if 0 <= target < len(items) else None
    return dict(case_id=str(case_id), batch_id=str(batch_id), item_id=str(following.id) if following else None,
                row_id=None, position=(target if following else index) + 1, total=len(items))


def available_batch_references(session, case_id, files):
    referenced = {UUID(f[key]) for f in files for key in ('source_id', 'file_id') if f.get(key)}
    return {str(id) for id in session.scalars(select(EvidenceFile.id).where(EvidenceFile.case_id == case_id, EvidenceFile.id.in_(referenced)))}


def project_batch_files(files, available):
    """Keep batch list, detail and recovery consistent without writes on GET."""
    files = deepcopy(files)
    for file in files:
        file['review_file_id'] = file.get('file_id') if file.get('file_id') in available else file.get('source_id') if file.get('source_id') in available else None
        if file.get('file_id') not in available:
            file['error'] = ('The prepared reading is unavailable. The original PDF is retained; Retry this file prepares a new reading without removing saved payments.' if file.get('source_id') in available else 'The original PDF is not available in this case. Restore the original evidence before retrying; existing payment history is retained.')
            if file['status'] in TERMINAL_FILES:
                file['status'] = 'error'
    return files


def batch_status(session, *, case_id, batch_id, offset=0, limit=100, only_problems=False, review_group=None):
    from services.financial.import_operations import operations_for
    from services.financial.batch_review_summary import matches_group, review_summary, validate_group, group_label
    validate_group(review_group)
    batch = batch_for(session,case_id,batch_id)
    items=list(session.scalars(select(Item).where(Item.batch_id==batch.id).order_by(Item.file_id,Item.statement_key)))
    items=checked_batch_items(session, case_id, items)
    items.sort(key=lambda i: (i.summary.get('filename',''),i.summary.get('account',''),i.summary.get('period_start',''),str(i.id)))
    shown=[i for i in items if matches_group(i, review_group) and (not only_problems or i.summary.get('problem_count', 0))]
    counts={state:sum(i.status==state for i in items) for state in ('ready','attention','pending_import','imported','skipped','assigned')}
    file_ids = {UUID(f['file_id']) for f in batch.files if f.get('file_id')}
    job_ids = list(session.scalars(select(EvidenceFile.engine_job_id).where(EvidenceFile.case_id == case_id, EvidenceFile.id.in_(file_ids), EvidenceFile.engine_job_id.is_not(None)))) if file_ids else []
    files = project_batch_files(batch.files, available_batch_references(session, case_id, batch.files))
    return dict(id=str(batch.id),case_id=str(case_id),status=batch.status,files=files,counts=counts, reading_job_ids=job_ids,
        review_summary=review_summary(items), review_group=review_group, review_group_label=group_label(review_group),
        operations=operations_for(session, case_id, batch_id),
        statements_with_issues=sum(bool(i.summary.get('problem_count', 0)) for i in items if i.status != 'skipped'),
        available_statements=sum(import_available(i) for i in items),
        available_records=sum(i.summary.get('record_count', i.summary.get('transaction_count', 0)) for i in items if import_available(i)),
        available_transactions=sum(i.summary.get('transaction_count', 0) for i in items if import_available(i)),
        available_incomplete=sum(i.summary.get('incomplete_count', 0) for i in items if import_available(i)),
        issues_count=sum(i.summary.get('problem_count', 0) for i in items if i.status != 'skipped'),
        ready_transactions=sum(i.summary.get('transaction_count',0) for i in items if i.status=='ready'),
        ready_revision=ready_revision(items),total=len(shown),offset=offset,
        items=[dict(id=str(i.id),file_id=str(i.file_id),statement_id=i.statement_key or None,status=i.status,**i.summary) for i in shown[offset:offset+limit]])


def save_review(session, *, case_id, batch_id, item_id, request, expected_review_revision):
    batch=batch_for(session,case_id,batch_id,True)
    file_id = session.scalar(select(Item.file_id).where(Item.id == item_id, Item.batch_id == batch.id))
    if file_id is not None:
        session.execute(select(EvidenceFile).where(EvidenceFile.id == file_id,
            EvidenceFile.case_id == case_id).with_for_update().execution_options(populate_existing=True)).all()
    item=session.scalar(select(Item).where(Item.id==item_id,Item.batch_id==batch.id).with_for_update())
    if item is None or item.status == 'removed': raise PdfMappingError('Statement not found in this batch.',404)
    if _digest(item.review_request or {}) != expected_review_revision:
        raise PdfMappingError('Another user saved changes to this review. Reopen it from the batch before saving.',409)
    if item.status in ('pending_import','imported'): raise PdfMappingError('This statement is already being imported or was imported.',409)
    if item.status == 'skipped': raise PdfMappingError('Restore this statement to review from the batch before saving further changes.',409)
    if request.statement_id != (item.statement_key or None): raise PdfMappingError('Open this statement period from the batch again.',409)
    if request.replaces_source_document_id: raise PdfMappingError('Replace a previous import through its individual review, not bulk import.',422)
    proposal=read_statement_import(session,case_id=case_id,evidence_file_id=item.file_id,currency=request.currency,statement_id=request.statement_id)
    if request.expected_revision != proposal['revision']:
        raise PdfMappingError('The saved reading changed. Reopen this statement before saving corrections.', 409)
    # Save incomplete edits without discarding their source rows or page references.
    check_proposed_rows(proposal, [r.model_dump() for r in request.rows])
    status,summary=assess(proposal,request.model_dump(mode='json'))
    summary.update(filename=item.summary['filename'],source_id=item.summary['source_id'])
    for key in ('import_decision','import_decision_history'):
        if key in item.summary: summary[key] = item.summary[key]
    item.status=status;item.summary=summary;item.review_request=request.model_dump(mode='json')
    checked = checked_batch_items(session, case_id, [item])[0]
    session.commit()
    return dict(status=checked.status, review_revision=_digest(item.review_request))


def confirm_review(*, session_factory, case_id, batch_id, item_id, request,
        expected_review_revision, actor, resolve_path):
    """Save and import one reviewed statement, retaining the batch's durable job.

    Other ready statements remain untouched. Retrying the same submitted values
    resumes the pending job or returns its receipt without importing twice.
    """
    raw = request.model_dump(mode='json')
    with session_factory() as session:
        batch = batch_for(session, case_id, batch_id, True)
        item = session.scalar(select(Item).where(Item.id == item_id, Item.batch_id == batch.id).with_for_update())
        if item is None:
            raise PdfMappingError('Statement not found in this batch.', 404)
        if item.status in ('pending_import', 'imported'):
            if item.review_request != raw:
                raise PdfMappingError('This statement is already being imported or was imported with different values. Reopen it to check the result.', 409)
        else:
            require_running(batch)
            save_review(session, case_id=case_id, batch_id=batch_id, item_id=item_id,
                request=request, expected_review_revision=(
                    _digest(item.review_request) if item.review_request == raw else expected_review_revision))
            batch = batch_for(session, case_id, batch_id, True)
            item = session.scalar(select(Item).where(Item.id == item_id, Item.batch_id == batch.id)
                .with_for_update().execution_options(populate_existing=True))
            if item.review_request != raw:
                raise PdfMappingError('Another reviewer changed these values. Reopen the statement before importing.', 409)
            if item.status != 'imported':
                if not import_available(item):
                    raise PdfMappingError('This statement cannot be imported yet. ' + ' '.join(
                        p['message'] for p in item.summary.get('problems', [])[:3]), 422)
                item.status = 'pending_import'
                item.summary = {**item.summary, 'import_actor':dict(name=actor.name, email=actor.email, user_id=str(actor.user_id))}
                batch.status = 'preparing'
        session.commit()
    with session_factory() as session:
        if session.get(Item, item_id).status != 'imported':
            require_running(batch_for(session, case_id, batch_id))
    _import_item(session_factory, case_id, batch_id, item_id, resolve_path)
    with session_factory() as session:
        item = session.scalar(select(Item).where(Item.id == item_id, Item.batch_id == batch_id))
        if item.status != 'imported':
            raise PdfMappingError(' '.join(p['message'] for p in item.summary.get('problems', [])[:3]) or
                'The import is still running. Reopen this statement to check its result.', 409)
        from services.financial.batch_import_history import current_imports
        current = current_imports(session, case_id, [UUID(item.summary['source_document_id'])])[item.summary['source_document_id']]
        unresolved = sum(not row.get('resolved_transaction_id') for row in current['records'])
        return dict(case_id=str(case_id), evidence_file_id=str(item.file_id), source_document_id=current['source_document_id'],
            account_id=current['account_id'], transaction_count=current['transaction_count'], incomplete_count=unresolved,
            record_count=current['transaction_count'] + unresolved, applied=True)


def queue_import(session, *, case_id,batch_id,expected_revision,actor,request_id=None):
    from services.financial.import_operations import operation_view
    batch=batch_for(session,case_id,batch_id,True)
    operation_id = request_id or uuid5(batch_id, 'import:' + expected_revision)
    existing = session.get(Operation, operation_id)
    if existing:
        if existing.case_id != case_id or existing.batch_id != batch_id or existing.expected_revision != expected_revision:
            raise PdfMappingError('This import request belongs to a different selection. Refresh the batch.', 409)
        return dict(queued=existing and len(existing.outcomes), operation=operation_view(existing))
    require_running(batch)
    items=list(session.scalars(select(Item).where(Item.batch_id==batch.id).with_for_update()))
    checked=checked_batch_items(session, case_id, items)
    if ready_revision(checked)!=expected_revision: raise PdfMappingError('The ready statements changed. Refresh the batch before confirming.',409)
    ready_ids={i.id for i in checked if import_available(i)}
    ready=[i for i in items if i.id in ready_ids]
    if not ready: raise PdfMappingError('There are no new statement records available to import.',422)
    operation = Operation(id=operation_id, case_id=case_id, batch_id=batch_id, expected_revision=expected_revision,
        actor=dict(name=actor.name, user_id=str(actor.user_id)),
        outcomes=[dict(item_id=str(i.id), file_id=str(i.file_id), filename=i.summary.get('filename', ''),
            period_start=i.summary.get('period_start', ''), period_end=i.summary.get('period_end', ''),
            status='queued') for i in ready])
    session.add(operation)
    for item in ready:
        item.status='pending_import'
        projection = next(i for i in checked if i.id == item.id)
        if projection.review_request != item.review_request:
            metadata = deepcopy(item.summary)
            metadata.setdefault('review_upgrade_history', []).append(dict(request=item.review_request,
                at=datetime.now(timezone.utc).isoformat(), actor_id=str(actor.user_id)))
            item.summary = metadata
            item.review_request = projection.review_request
        checked_summary = {**item.summary, **projection.summary}
        item.summary={**checked_summary,'import_operation_id':str(operation_id), 'import_actor':dict(name=actor.name,email=actor.email,user_id=str(actor.user_id))}
    batch.status='preparing'
    session.commit()
    return dict(queued=len(ready), operation=operation_view(operation))


def leave_unimported(session, *, case_id, batch_id, item_id, action, reason, expected_revision, actor):
    batch_for(session, case_id, batch_id, True)
    item = session.scalar(select(Item).where(Item.id == item_id, Item.batch_id == batch_id).with_for_update())
    if item is None:
        raise PdfMappingError('Statement not found in this batch.', 404)
    revision = _digest(dict(status=item.status, request=item.review_request, decision=item.summary.get('import_decision')))
    if revision != expected_revision or item.status in ('imported','pending_import','assigned','removed'):
        raise PdfMappingError('The statement changed. Refresh the batch before changing its import choice.', 409)
    if (action == 'restore' and item.status != 'skipped') or (action == 'skip' and item.status == 'skipped'):
        raise PdfMappingError('The import choice has already changed. Refresh the batch.', 409)
    if action not in ('skip','restore') or not reason.strip():
        raise PdfMappingError('Choose whether to leave this statement unimported and record the reason.', 422)
    history = list(item.summary.get('import_decision_history', []))
    decision = dict(action=action, reason=reason.strip(), actor=dict(user_id=str(actor.user_id), name=actor.name),
                    at=datetime.now(timezone.utc).isoformat())
    history.append(decision)
    item.summary = {**item.summary, 'import_decision': decision, 'import_decision_history': history}
    if action == 'skip':
        item.status = 'skipped'
    else:
        proposal = read_statement_import(session, case_id=case_id, evidence_file_id=item.file_id,
            currency=item.summary.get('currency'), statement_id=item.statement_key or None)
        state, summary = assess(proposal, item.review_request)
        item.status = state
        item.summary = {**item.summary, **summary}
    session.commit()
    return dict(applied=True, status=item.status)


def choose_currency(session, *, case_id,batch_id,source_id,currency):
    from services.financial.money import get_currency
    get_currency(currency)
    batch=batch_for(session,case_id,batch_id,True)
    require_running(batch)
    if batch.worker_token and batch.lease_until and batch.lease_until.replace(tzinfo=timezone.utc)>datetime.now(timezone.utc):
        raise PdfMappingError('This batch is still checking files. Try choosing the currency when processing finishes.',409)
    files=deepcopy(batch.files)
    target=next((f for f in files if f['source_id']==str(source_id)),None)
    if target is None: raise PdfMappingError('File not found in this batch.',404)
    if session.scalar(select(Item.id).where(Item.batch_id==batch.id,Item.file_id==UUID(target['file_id']),Item.status.in_(['imported','pending_import']))):
        raise PdfMappingError('This file already has imported statements. Use individual statement review to correct currency.',409)
    saved=list(session.scalars(select(Item).where(Item.batch_id==batch.id,Item.file_id==UUID(target['file_id']))))
    if any(item.review_request for item in saved):
        raise PdfMappingError('This file has saved corrections. Review each statement to change its currency.',409)
    target.update(currency=currency,status='processing');target.pop('error',None)
    batch.files=files;batch.status='preparing';session.commit()


PAUSED_STATES = {'pausing', 'paused'}


def require_running(batch):
    if batch.status in PAUSED_STATES:
        raise PdfMappingError('This batch is paused. Resume it before importing or preparing more statements. Saved reviews are retained.', 409)


def control_batch(session, *, case_id, batch_id, action):
    batch = batch_for(session, case_id, batch_id, True)
    now = datetime.now(timezone.utc)
    active = bool(batch.worker_token and batch.lease_until and batch.lease_until.replace(tzinfo=timezone.utc) > now)
    if action == 'pause':
        if batch.status in ('preparing', 'pausing'):
            batch.status = 'pausing' if active else 'paused'
    elif action == 'resume':
        if batch.status == 'pausing' and active:
            raise PdfMappingError('The current statement is still finishing. Resume when the batch shows Paused.', 409)
        if batch.status in PAUSED_STATES:
            batch.status = 'preparing'
            batch.worker_token = None
            batch.lease_until = None
    else:
        raise PdfMappingError('Unknown batch action.', 404)
    session.commit()
    return dict(case_id=str(case_id), batch_id=str(batch_id), status=batch.status)


async def _finish_atomic(function, *args):
    # Cancellation does not stop a thread. Retain its lease until the atomic
    # statement operation has returned before acknowledging the interruption.
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


async def advance_batch(factory,batch_id,resolve_path,process_files):
    token=str(uuid4());now=datetime.now(timezone.utc)
    with factory() as db:
        batch=db.scalar(select(Batch).where(Batch.id==batch_id).with_for_update(skip_locked=True))
        if not batch: return
        if batch.status == 'pausing':
            if not batch.lease_until or batch.lease_until.replace(tzinfo=timezone.utc) <= now:
                batch.status = 'paused'; batch.worker_token = None; batch.lease_until = None; db.commit()
            return
        if batch.status != 'preparing': return
        lease=batch.lease_until
        if lease and lease.replace(tzinfo=timezone.utc)>now: return
        batch.worker_token=token;batch.lease_until=now+timedelta(minutes=5);db.commit()
        case_id=batch.case_id
    async def renew_lease():
        while True:
            await asyncio.sleep(30)
            with factory() as db:
                active=batch_for(db,case_id,batch_id,True)
                if active.worker_token!=token: return
                active.lease_until=datetime.now(timezone.utc)+timedelta(minutes=5)
                db.commit()
    def should_stop():
        with factory() as db:
            current = batch_for(db, case_id, batch_id)
            return current.worker_token != token or current.status in PAUSED_STATES
    heartbeat=asyncio.create_task(renew_lease())
    interrupted=False
    try:
        started = time.monotonic()
        # An investigator's accepted imports do not wait for every PDF in the
        # batch. Bounded turns also allow other cases to make progress.
        with factory() as db:
            pending=list(db.scalars(select(Item.id).where(Item.batch_id==batch_id,Item.status=='pending_import')
                .order_by(Item.updated_at, Item.id).limit(IMPORTS_PER_TURN)))
        for item_id in pending:
            if should_stop() or time.monotonic() - started >= TURN_SECONDS:
                break
            await _finish_atomic(_import_item,factory,case_id,batch_id,item_id,resolve_path)
            with factory() as db:
                batch=batch_for(db,case_id,batch_id,True)
                if batch.worker_token!=token: return
                batch.lease_until=datetime.now(timezone.utc)+timedelta(minutes=5);db.commit()
        with factory() as db:
            batch=batch_for(db,case_id,batch_id)
            files=deepcopy(batch.files)
        candidates = sorted(((index, file) for index, file in enumerate(files) if file['status'] not in TERMINAL_FILES),
            key=lambda pair: (pair[1].get('last_checked_at', ''), pair[0]))[:FILES_PER_TURN]
        for index,file in candidates:
            if should_stop() or time.monotonic() - started >= TURN_SECONDS:
                break
            previous_status = file['status']
            try:
                with factory() as db:
                    batch=batch_for(db,case_id,batch_id)
                    actor=Actor(**{**batch.actor,'user_id':UUID(batch.actor['user_id'])})
                    if file['status']=='waiting':
                        result=await prepare_existing_financial_file(db,case_id=case_id,evidence_file_id=UUID(file['source_id']),expected_revision=file['expected_revision'],actor=actor,resolve_path=resolve_path,process_files=process_files)
                        file['file_id']=result['evidence_file_id'];file['status']='processing'
                    target=db.get(EvidenceFile,UUID(file['file_id']))
                    if target is not None and target.case_id != case_id:
                        raise PdfMappingError('The prepared reading is not available in this case. Retry from the original PDF.', 409)
                    if not target or target.status=='failed': raise PdfMappingError('The PDF could not be processed. Open the file to inspect or retry its reading.',422)
                    processed = target.status=='processed'
                    # The no-op visibility check still locks the evidence row.
                    # Release it before a second session inserts a referencing batch item.
                    db.commit()
                if processed:
                    await _finish_atomic(_review_file,factory,batch_id,case_id,deepcopy(file))
                    file['status']='checked'
            except Exception as error:
                log.exception('Financial batch file preparation failed')
                file['status']='error';file['error']=str(error) if isinstance(error,PdfMappingError) else 'This file could not be prepared. Open it to review the processing error.'
            file['last_checked_at'] = datetime.now(timezone.utc).isoformat()
            if file['status'] != previous_status:
                file['last_progress_at'] = file['last_checked_at']
            with factory() as db:
                batch=batch_for(db,case_id,batch_id,True)
                if batch.worker_token!=token: return
                fresh=deepcopy(batch.files);fresh[index]=file;batch.files=fresh
                batch.lease_until=datetime.now(timezone.utc)+timedelta(minutes=5);db.commit()
    except asyncio.CancelledError:
        interrupted=True
        raise
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat,return_exceptions=True)
        with factory() as db:
            batch=batch_for(db,case_id,batch_id,True)
            if batch.worker_token==token and not interrupted:
                has_imports=db.scalar(select(Item.id).where(Item.batch_id==batch_id,Item.status=='pending_import').limit(1))
                batch.status = 'paused' if batch.status in PAUSED_STATES else ('review' if not has_imports and all(f['status'] in TERMINAL_FILES for f in batch.files) else 'preparing')
                batch.worker_token=None;batch.lease_until=None;db.commit()


def _review_file(factory,batch_id,case_id,file):
    with factory() as db:
        prepare_reviews(db,batch_for(db,case_id,batch_id),file)


def _import_item(factory,case_id,batch_id,item_id,resolve_path):
    from services.financial.import_operations import record_outcome
    with factory() as db:
        item=db.scalar(select(Item).join(Batch, Item.batch_id == Batch.id).where(Item.id==item_id,Item.batch_id==batch_id,
            Batch.case_id == case_id).with_for_update(of=Item))
        if not item or item.status!='pending_import': return
        try:
            proposal=read_statement_import(db,case_id=case_id,evidence_file_id=item.file_id,currency=item.summary.get('currency'),statement_id=item.statement_key or None)
            raw=item.review_request or initial_request(proposal)
            if raw['expected_revision']!=item.summary['revision'] or proposal['revision']!=item.summary['revision']:
                raise PdfMappingError('The statement changed after the batch was checked. Open it and review the new reading.',409)
            request=StatementImportRequest.model_validate(raw)
            actor=item.summary['import_actor'];actor=Actor(**{**actor,'user_id':UUID(actor['user_id'])})
            receipt=confirm_statement_import(session_factory=factory,case_id=case_id,evidence_file_id=item.file_id,request=request,actor=actor,resolve_path=resolve_path)
            retained = receipt.get('issues', item.summary.get('problems', []))
            item.status='imported';item.summary={**item.summary,'transaction_count':receipt['transaction_count'],
                'record_count':receipt.get('record_count', receipt['transaction_count']),
                'incomplete_count':receipt.get('incomplete_count', 0), 'problems':retained[:50], 'problem_count':len(retained), 'can_import':False,
                'source_document_id':receipt['source_document_id'],'account_id':receipt['account_id']}
            record_outcome(db, case_id, item, 'imported' if receipt.get('created', True) else 'already_present',
                source_document_id=receipt['source_document_id'], transaction_count=receipt['transaction_count'],
                incomplete_count=receipt.get('incomplete_count', 0))
        except Exception as error:
            log.exception('Financial batch import failed')
            item.status='attention';item.summary={**item.summary,'can_import':False, 'import_failed':True, 'problem_count':1, 'problems':[dict(message=str(error) if isinstance(error,PdfMappingError) else 'Import could not be confirmed. Open this statement to check its current import before retrying.',row_id=None)]}
            record_outcome(db, case_id, item, 'failed', message=item.summary['problems'][0]['message'])
        db.commit()


async def run_batches_forever():
    from postgres.session import _get_session_local
    from routers.evidence import _resolve_stored_path
    from services.evidence_processing_service import process_db_files
    while True:
        try:
            factory=_get_session_local()
            with factory() as db:
                ids=list(db.scalars(select(Batch.id).where(Batch.status.in_(('preparing', 'pausing'))).order_by(Batch.updated_at, Batch.id).limit(100)))
            capacity = asyncio.Semaphore(2)
            async def advance(identifier):
                async with capacity:
                    try:
                        await advance_batch(factory,identifier,_resolve_stored_path,process_db_files)
                    except Exception:
                        log.exception('A financial batch turn failed; other batches continue')
            await asyncio.gather(*(advance(identifier) for identifier in ids))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('Financial batch processing interrupted; will resume')
        await asyncio.sleep(5)


def retry_file(session, *, case_id, batch_id, source_id):
    from services.financial.file_visibility import financial_file_visibility
    batch=batch_for(session,case_id,batch_id,True)
    require_running(batch)
    files=deepcopy(batch.files)
    target=next((f for f in files if f['source_id']==str(source_id)),None)
    if target is None: raise PdfMappingError('File not found in this batch.',404)
    prepared = session.scalar(select(EvidenceFile.id).where(EvidenceFile.case_id == case_id,
        EvidenceFile.id == UUID(target['file_id']))) if target.get('file_id') else None
    # Status reads can discover a missing prepared reference after the worker
    # recorded "checked". Honour the retry offered by that view, using only
    # this case's original. Active work remains idempotent and is not restarted.
    missing_prepared = target['status'] == 'checked' and prepared is None
    if target['status'] != 'error' and not missing_prepared:
        return dict(queued=False, status=target['status'])
    # Error files are terminal and cannot belong to the worker's active turn.
    # Its per-file merge preserves this newly queued entry; don't block recovery
    # merely because a different file is being read in the same batch.
    source=session.scalar(select(EvidenceFile).where(EvidenceFile.id==source_id,EvidenceFile.case_id==case_id))
    if source is None: raise PdfMappingError('The original PDF is no longer available in this case.',404)
    target.update(status='waiting',file_id=str(source.id),expected_revision=financial_file_visibility(source)['financial_visibility_revision'])
    target.pop('error',None)
    batch.files=files;batch.status='preparing';session.commit()
    return dict(queued=True, status='waiting')


def refresh_statement_list(session, *, case_id, batch_id):
    """Discover newly supported periods from saved geometry, keeping reviews."""
    batch = batch_for(session, case_id, batch_id, True)
    require_running(batch)
    if batch.status == 'preparing':
        return dict(queued=True, already_processing=True)
    files = deepcopy(batch.files)
    count = 0
    for file in files:
        if file['status'] == 'checked':
            # Processing skips Evidence intake; the worker reuses the existing
            # text/geometry and prepare_reviews keeps edited/imported items.
            file['status'] = 'processing'
            count += 1
    if count:
        batch.files = files
        batch.status = 'preparing'
        session.commit()
    return dict(queued=bool(count), files=count, already_processing=False)
