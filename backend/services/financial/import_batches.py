"""Case-scoped folder batches. Preparation and imports survive browser navigation."""
import asyncio
import logging
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4, uuid5
from sqlalchemy import select
from pydantic import ValidationError
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from postgres.models.evidence import EvidenceFile, EvidenceDocumentText
from services.financial.pdf_candidates import PdfMappingError, _digest
from services.financial.decisions import Actor
from services.financial.evidence_intake import resolve_financial_selection, prepare_existing_financial_file
from services.financial.statement_import import read_statement_import, StatementImportRequest, check_import_request, confirm_statement_import, _date_roles, _primary_date_role
from services.financial.review_arithmetic import check_proposed_rows, arithmetic_problems, accepted_difference

log = logging.getLogger(__name__)
TERMINAL_FILES = {'checked', 'error'}


def batch_for(session, case_id, batch_id, lock=False):
    query = select(Batch).where(Batch.id == batch_id, Batch.case_id == case_id)
    batch = session.scalar(query.with_for_update() if lock else query)
    if batch is None:
        raise PdfMappingError('Financial processing batch not found in this case.', 404)
    return batch


def create_batch(session, *, case_id, request_id, file_ids, folder_ids, actor):
    selection = resolve_financial_selection(session, case_id=case_id, file_ids=file_ids, folder_ids=folder_ids)
    existing = session.get(Batch, request_id)
    if existing:
        if existing.case_id != case_id or existing.created_by != actor.user_id:
            raise PdfMappingError('This request belongs to another batch.', 409)
        if {f['source_id'] for f in existing.files} != {f['id'] for f in selection['files']}:
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
    """Ready means the same request can pass the existing single-import validator."""
    problems = []
    raw = request or initial_request(proposal)
    rows = proposal['rows']
    current = proposal.get('current_import')
    if proposal.get('document_review'):
        problems.append(dict(message='This is a receipt or payment document. Open its document review.', row_id=None))
    if proposal.get('reading_failure'):
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
        if isinstance(error, ValidationError):
            for issue in error.errors(include_url=False, include_input=False)[:30]:
                path = issue['loc']
                row_id = raw['rows'][path[1]]['id'] if len(path)>1 and path[0]=='rows' and isinstance(path[1],int) and path[1]<len(raw['rows']) else None
                label = {'holder':'account holder','account_number':'account number','currency':'statement currency','amount_minor':'amount','date':'date'}.get(str(path[-1]) if path else '', 'statement details')
                message=issue['msg'].removeprefix('Value error, ')
                if 'isoformat' in message:
                    message='Enter the complete date shown on the statement.'
                elif issue['type']=='string_pattern_mismatch':
                    message=f'Check the {label} against the statement and enter a usable value.'
                elif issue['type'] in ('string_too_short','missing'):
                    message=f'Enter the {label} shown on the statement.'
                problems.append(dict(message=message, row_id=row_id))
        else:
            problems.append(dict(message=str(error), row_id=None))
    reviewed = {r['id']:r for r in raw['rows']}
    for row in rows:
        edit = reviewed.get(row['id'],{})
        if row['issues'] and not edit.get('reason','').strip():
            problems.append(dict(message=' '.join(row['issues']),row_id=row['id'],page=row['page_number']))
    balance = check_proposed_rows(proposal, raw['rows'])
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
    summary = dict(revision=proposal['revision'], transaction_count=sum(not r['excluded'] for r in raw['rows']), currency=proposal['currency'],
        holder=raw.get('holder',''), account=raw.get('account_number',''), period_start=raw.get('period_start',''),period_end=raw.get('period_end',''),
        balance_status=balance['balance_status'], checks=balance['checks'],
        balance_exception=accepted_difference(balance, raw), problems=problems[:50], problem_count=len(problems))
    if current:
        summary.update(transaction_count=current['transaction_count'], problems=[], problem_count=0,
            source_document_id=current['source_document_id'], account_id=current['account_id'])
        return 'imported', summary
    return ('attention' if problems else 'ready'), summary


def inferred_currency(session, file_id, proposal):
    if proposal['currency']:
        return proposal['currency']
    text = session.get(EvidenceDocumentText, file_id)
    content = text.content if text else ''
    codes = set(re.findall(r'\b(?:USD|EUR|GBP|CAD|AUD|JPY|CHF|NZD|KWD)\b',content))
    if len(codes)==1:
        return next(iter(codes))
    # These recognised US issuer layouts use dollars. A dollar symbol by itself,
    # or conflicting printed currency codes, is not enough for other layouts.
    choices = proposal.get('statement_choices',[])
    if not codes and choices and all(c.get('layout_id') in ('capital-one-card','merrick-card','andrews-share-statement') for c in choices) and '$' in content:
        return 'USD'
    return ''


def prepare_reviews(session, batch, file):
    cache = {}
    fid = UUID(file['file_id'])
    session.execute(select(EvidenceFile).where(EvidenceFile.id == fid,
        EvidenceFile.case_id == batch.case_id).with_for_update().execution_options(populate_existing=True)).all()
    first = read_statement_import(session,case_id=batch.case_id,evidence_file_id=fid,currency=file.get('currency'),_cache=cache)
    currency = file.get('currency') or inferred_currency(session,fid,first)
    choices = first.get('statement_choices',[])
    identifiers = [c['id'] for c in choices] if currency else [None]
    if not identifiers: identifiers=[None]
    for statement_id in identifiers:
        proposal = read_statement_import(session,case_id=batch.case_id,evidence_file_id=fid,currency=currency or None,statement_id=statement_id,_cache=cache)
        key = statement_id or proposal.get('statement_id') or ''
        identifier = uuid5(batch.id, str(fid)+':'+key)
        existing = session.get(Item,identifier)
        if existing and (existing.review_request or existing.status in ('imported','pending_import')):
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
        summary.update(filename=file['filename'], currency=currency, source_id=file['source_id'])
        if existing:
            existing.status=status; existing.summary=summary; existing.review_request=draft
        else:
            session.add(Item(id=identifier,batch_id=batch.id,file_id=fid,statement_key=key,status=status,summary=summary,review_request=draft))
    # A former file-level currency question is replaced by its actual periods.
    if currency and choices:
        stale = session.get(Item,uuid5(batch.id,str(fid)+':'))
        if stale and stale.status=='attention' and not stale.review_request:
            session.delete(stale)
    session.commit()


def ready_revision(items):
    return _digest(sorted((str(i.id),i.summary['revision'],_digest(i.review_request or {})) for i in items if i.status=='ready'))


def next_problem(session, *, case_id, batch_id, item_id, direction="next"):
    batch_for(session, case_id, batch_id)
    items = list(session.scalars(select(Item).where(Item.batch_id == batch_id)))
    items.sort(key=lambda i: (i.summary.get('filename',''), i.summary.get('account',''), i.summary.get('period_start',''), str(i.id)))
    index = next((n for n, item in enumerate(items) if item.id == item_id), None)
    if index is None:
        raise PdfMappingError('Statement not found in this batch.', 404)
    ordered = items[index+1:] + items[:index]
    if direction == 'previous':
        ordered.reverse()
    remaining = [i for i in ordered if i.status == 'attention']
    following = remaining[0] if remaining else None
    return dict(case_id=str(case_id), batch_id=str(batch_id), remaining=len(remaining),
        item_id=str(following.id) if following else None,
        row_id=next((p.get('row_id') for p in following.summary.get('problems', []) if p.get('row_id')), None) if following else None)


def batch_status(session, *, case_id, batch_id, offset=0, limit=100, only_problems=False):
    batch = batch_for(session,case_id,batch_id)
    items=list(session.scalars(select(Item).where(Item.batch_id==batch.id).order_by(Item.file_id,Item.statement_key)))
    items.sort(key=lambda i: (i.summary.get('filename',''),i.summary.get('account',''),i.summary.get('period_start',''),str(i.id)))
    shown=[i for i in items if not only_problems or i.status=='attention']
    counts={state:sum(i.status==state for i in items) for state in ('ready','attention','pending_import','imported')}
    return dict(id=str(batch.id),case_id=str(case_id),status=batch.status,files=batch.files,counts=counts,
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
    if item is None: raise PdfMappingError('Statement not found in this batch.',404)
    if _digest(item.review_request or {}) != expected_review_revision:
        raise PdfMappingError('Another user saved changes to this review. Reopen it from the batch before saving.',409)
    if item.status in ('pending_import','imported'): raise PdfMappingError('This statement is already being imported or was imported.',409)
    if request.statement_id != (item.statement_key or None): raise PdfMappingError('Open this statement period from the batch again.',409)
    if request.replaces_source_document_id: raise PdfMappingError('Replace a previous import through its individual review, not bulk import.',422)
    proposal=read_statement_import(session,case_id=case_id,evidence_file_id=item.file_id,currency=request.currency,statement_id=request.statement_id)
    if request.expected_revision != proposal['revision']:
        raise PdfMappingError('The saved reading changed. Reopen this statement before saving corrections.', 409)
    # Incomplete edits can be saved. Only the strict assessment can mark them
    # ready for import; source rows and manual page references remain intact.
    check_proposed_rows(proposal, [r.model_dump() for r in request.rows])
    status,summary=assess(proposal,request.model_dump(mode='json'))
    summary.update(filename=item.summary['filename'],source_id=item.summary['source_id'])
    item.status=status;item.summary=summary;item.review_request=request.model_dump(mode='json')
    session.commit()
    return dict(status=status, review_revision=_digest(item.review_request))


def queue_import(session, *, case_id,batch_id,expected_revision,actor):
    batch=batch_for(session,case_id,batch_id,True)
    items=list(session.scalars(select(Item).where(Item.batch_id==batch.id).with_for_update()))
    if ready_revision(items)!=expected_revision: raise PdfMappingError('The ready statements changed. Refresh the batch before confirming.',409)
    ready=[i for i in items if i.status=='ready']
    if not ready: raise PdfMappingError('There are no ready statements to import.',422)
    for item in ready:
        item.status='pending_import'
        item.summary={**item.summary,'import_actor':dict(name=actor.name,email=actor.email,user_id=str(actor.user_id))}
    batch.status='preparing'
    session.commit()
    return dict(queued=len(ready))


def choose_currency(session, *, case_id,batch_id,source_id,currency):
    from services.financial.money import get_currency
    get_currency(currency)
    batch=batch_for(session,case_id,batch_id,True)
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


async def advance_batch(factory,batch_id,resolve_path,process_files):
    token=str(uuid4());now=datetime.now(timezone.utc)
    with factory() as db:
        batch=db.scalar(select(Batch).where(Batch.id==batch_id).with_for_update(skip_locked=True))
        if not batch or batch.status!='preparing': return
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
    heartbeat=asyncio.create_task(renew_lease())
    interrupted=False
    try:
        with factory() as db:
            batch=batch_for(db,case_id,batch_id)
            files=deepcopy(batch.files)
        for index,file in enumerate(files):
            if file['status'] in TERMINAL_FILES: continue
            try:
                with factory() as db:
                    batch=batch_for(db,case_id,batch_id)
                    actor=Actor(**{**batch.actor,'user_id':UUID(batch.actor['user_id'])})
                    if file['status']=='waiting':
                        result=await prepare_existing_financial_file(db,case_id=case_id,evidence_file_id=UUID(file['source_id']),expected_revision=file['expected_revision'],actor=actor,resolve_path=resolve_path,process_files=process_files)
                        file['file_id']=result['evidence_file_id'];file['status']='processing'
                    target=db.get(EvidenceFile,UUID(file['file_id']))
                    if not target or target.status=='failed': raise PdfMappingError('The PDF could not be processed. Open the file to inspect or retry its reading.',422)
                    processed = target.status=='processed'
                    # The no-op visibility check still locks the evidence row.
                    # Release it before a second session inserts a referencing batch item.
                    db.commit()
                if processed:
                    await asyncio.to_thread(_review_file,factory,batch_id,case_id,deepcopy(file))
                    file['status']='checked'
            except Exception as error:
                log.exception('Financial batch file preparation failed')
                file['status']='error';file['error']=str(error) if isinstance(error,PdfMappingError) else 'This file could not be prepared. Open it to review the processing error.'
            with factory() as db:
                batch=batch_for(db,case_id,batch_id,True)
                if batch.worker_token!=token: return
                fresh=deepcopy(batch.files);fresh[index]=file;batch.files=fresh
                batch.lease_until=datetime.now(timezone.utc)+timedelta(minutes=5);db.commit()
        with factory() as db:
            pending=list(db.scalars(select(Item.id).where(Item.batch_id==batch_id,Item.status=='pending_import')))
        for item_id in pending:
            await asyncio.to_thread(_import_item,factory,case_id,batch_id,item_id,resolve_path)
            with factory() as db:
                batch=batch_for(db,case_id,batch_id,True)
                if batch.worker_token!=token: return
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
                batch.status='review' if not has_imports and all(f['status'] in TERMINAL_FILES for f in batch.files) else 'preparing'
                batch.worker_token=None;batch.lease_until=None;db.commit()


def _review_file(factory,batch_id,case_id,file):
    with factory() as db:
        prepare_reviews(db,batch_for(db,case_id,batch_id),file)


def _import_item(factory,case_id,batch_id,item_id,resolve_path):
    with factory() as db:
        item=db.scalar(select(Item).where(Item.id==item_id,Item.batch_id==batch_id))
        if not item or item.status!='pending_import': return
        try:
            proposal=read_statement_import(db,case_id=case_id,evidence_file_id=item.file_id,currency=item.summary.get('currency'),statement_id=item.statement_key or None)
            raw=item.review_request or initial_request(proposal)
            if raw['expected_revision']!=item.summary['revision'] or proposal['revision']!=item.summary['revision']:
                raise PdfMappingError('The statement changed after the batch was checked. Open it and review the new reading.',409)
            request=StatementImportRequest.model_validate(raw)
            actor=item.summary['import_actor'];actor=Actor(**{**actor,'user_id':UUID(actor['user_id'])})
            receipt=confirm_statement_import(session_factory=factory,case_id=case_id,evidence_file_id=item.file_id,request=request,actor=actor,resolve_path=resolve_path)
            item.status='imported';item.summary={**item.summary,'transaction_count':receipt['transaction_count'],'problems':[],
                'source_document_id':receipt['source_document_id'],'account_id':receipt['account_id']}
        except Exception as error:
            log.exception('Financial batch import failed')
            item.status='attention';item.summary={**item.summary,'problems':[dict(message=str(error) if isinstance(error,PdfMappingError) else 'Import could not be confirmed. Open this statement to check its current import before retrying.',row_id=None)]}
        db.commit()


async def run_batches_forever():
    from postgres.session import _get_session_local
    from routers.evidence import _resolve_stored_path
    from services.evidence_processing_service import process_db_files
    while True:
        try:
            factory=_get_session_local()
            with factory() as db:
                ids=list(db.scalars(select(Batch.id).where(Batch.status=='preparing').order_by(Batch.created_at).limit(100)))
            for batch_id in ids:
                await advance_batch(factory,batch_id,_resolve_stored_path,process_db_files)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('Financial batch processing interrupted; will resume')
        await asyncio.sleep(5)


def retry_file(session, *, case_id, batch_id, source_id):
    from services.financial.file_visibility import financial_file_visibility
    batch=batch_for(session,case_id,batch_id,True)
    files=deepcopy(batch.files)
    target=next((f for f in files if f['source_id']==str(source_id)),None)
    if target is None: raise PdfMappingError('File not found in this batch.',404)
    if target['status']!='error': return
    if batch.worker_token and batch.lease_until and batch.lease_until.replace(tzinfo=timezone.utc)>datetime.now(timezone.utc):
        raise PdfMappingError('This batch is still checking files. Retry when its current check finishes.',409)
    source=session.scalar(select(EvidenceFile).where(EvidenceFile.id==source_id,EvidenceFile.case_id==case_id))
    if source is None: raise PdfMappingError('The original PDF is no longer available in this case.',404)
    target.update(status='waiting',expected_revision=financial_file_visibility(source)['financial_visibility_revision'])
    target.pop('error',None)
    batch.files=files;batch.status='preparing';session.commit()
