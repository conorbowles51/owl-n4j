"""Case-authorized transcript review and frozen mixed-processing selections."""
from datetime import datetime, timedelta, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session, defer
from starlette.concurrency import run_in_threadpool
from postgres.session import get_db
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.transcript import TranscriptSource, TranscriptRevision, TranscriptState, EvidenceProcessingPlan
from postgres.models.user import User
from routers.users import get_current_db_user
from routers.case_access import authorize_case
from services import transcript_review as reviews
from services.evidence_db_storage import EvidenceDBStorage

router = APIRouter(prefix='/api/evidence', tags=['transcript review'])


@router.get('/transcript-review/capabilities')
async def audio_capabilities(user: User = Depends(get_current_db_user)):
    from services.evidence_engine_client import audio_review_capabilities
    compatible = False
    if reviews.feature_enabled():
        try:
            compatible = (await audio_review_capabilities()).get('audio_transcript_review_protocol') == 1
        except Exception:
            pass
    return {'enabled': reviews.feature_enabled() and compatible,
            'configured': reviews.feature_enabled(), 'engine_compatible': compatible}


def file_for(db, evidence_id, user, *, edit=False):
    file = db.get(EvidenceFile, evidence_id)
    if file is None:
        raise HTTPException(404, 'Evidence not found')
    authorize_case(db, file.case_id, user, ('evidence', 'upload') if edit else ('case', 'view'))
    return file


def validate_bindings(file, bindings):
    if not bindings:
        return
    from services.neo4j_service import neo4j_service
    nodes = neo4j_service.run_cypher('''MATCH (n:Person {case_id: $case_id})
        WHERE n.id IN $ids AND NOT n:RecycleBin
        RETURN n.id AS id, n.name AS name''', {'case_id': str(file.case_id), 'ids': list(set(bindings.values()))})
    if {row['id'] for row in nodes} != set(bindings.values()):
        raise HTTPException(422, 'A linked person is unavailable in this case. Select the current entity.')
    return {row['id']: row['name'] for row in nodes}


class DraftUpdate(BaseModel):
    restore_original: bool = False
    expected_revision_id: uuid.UUID
    text_overrides: dict[str, str | None] | None = None
    turn_speaker_overrides: dict[str, str | None] | None = None
    speakers: dict[str, str] | None = None
    speaker_merges: dict[str, str] | None = None
    speaker_entity_ids: dict[str, str] | None = None
    body_text: str | None = None


class ReviewInput(BaseModel):
    revision_id: uuid.UUID
    request_key: str = Field(min_length=1, max_length=128)


@router.get('/{evidence_id}/transcript')
def transcript(evidence_id: uuid.UUID, response: Response, db: Session = Depends(get_db),
               user: User = Depends(get_current_db_user)):
    file = file_for(db, evidence_id, user)
    if not reviews.feature_enabled() and db.get(TranscriptState, file.id) is None:
        raise HTTPException(409, 'Transcript review is not enabled')
    result = reviews.read_transcript(db, file)
    db.commit()  # Lazy legacy adoption is atomic, never an implicit approval.
    response.headers['Cache-Control'] = 'private, no-store'
    return result


@router.patch('/{evidence_id}/transcript')
def update_transcript(evidence_id: uuid.UUID, update: DraftUpdate, db: Session = Depends(get_db),
                      user: User = Depends(get_current_db_user)):
    if not reviews.feature_enabled(): raise HTTPException(409, 'Transcript review is not enabled')
    file = file_for(db, evidence_id, user, edit=True)
    changes = update.model_dump(exclude_unset=True, exclude={'expected_revision_id'})
    if changes.get('speaker_entity_ids') is not None:
        changes['_validated_entity_labels'] = validate_bindings(file, changes['speaker_entity_ids']) or {}
    result = reviews.save_draft(db, file, update.expected_revision_id, changes, user.id)
    validate_bindings(file, result['speaker_entity_ids'])
    db.commit()
    return result


@router.post('/{evidence_id}/transcript/reviews', status_code=201)
def approve_transcript(evidence_id: uuid.UUID, update: ReviewInput, db: Session = Depends(get_db),
                       user: User = Depends(get_current_db_user)):
    if not reviews.feature_enabled(): raise HTTPException(409, 'Transcript review is not enabled')
    file = file_for(db, evidence_id, user, edit=True)
    current = reviews.read_transcript(db, file)
    validate_bindings(file, current['speaker_entity_ids'])
    result = reviews.approve_revision(db, file, update.revision_id, user.id, update.request_key)
    db.commit()
    return result


@router.get('/{evidence_id}/transcript/revisions')
def history(evidence_id: uuid.UUID, cursor: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
            db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    file_for(db, evidence_id, user)
    rows = list(db.scalars(select(TranscriptRevision).where(TranscriptRevision.evidence_file_id == evidence_id)
        .order_by(TranscriptRevision.created_at.desc(), TranscriptRevision.id.desc()).offset(cursor).limit(limit + 1)))
    return {'items': [{'id': str(r.id), 'parent_id': str(r.parent_id) if r.parent_id else None,
        'digest': r.digest, 'author_id': str(r.author_id) if r.author_id else None, 'created_at': r.created_at} for r in rows[:limit]],
        'next_cursor': cursor + limit if len(rows) > limit else None}


@router.get('/{evidence_id}/transcript/revisions/{revision_id}')
def revision(evidence_id: uuid.UUID, revision_id: uuid.UUID, db: Session = Depends(get_db),
             user: User = Depends(get_current_db_user)):
    file_for(db, evidence_id, user)
    record = db.get(TranscriptRevision, revision_id)
    if record is None or record.evidence_file_id != evidence_id:
        raise HTTPException(404, 'Transcript revision not found')
    source = db.get(TranscriptSource, record.source_id)
    return {'id': str(record.id), 'payload': record.payload, 'digest': record.digest,
            'rendered': reviews.render_revision(source, record)}


class Selection(BaseModel):
    case_id: uuid.UUID
    file_ids: list[uuid.UUID] | None = Field(default=None, max_length=10000)
    folder_id: str | None = None
    recursive: bool = False
    ready_audio_only: bool = False
    review_queue: bool = False
    reprocess_completed: bool = False


@router.get('/transcript-queue/list')
def transcript_queue(case_id: uuid.UUID, folder_id: str = 'root', recursive: bool = False,
                     state: str = Query('awaiting_review', pattern='^(awaiting_review|ready)$'),
                     cursor: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100),
                     db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    authorize_case(db, case_id, user, ('case', 'view'))
    conditions = [EvidenceFile.case_id == case_id, EvidenceFile.status != 'processing']
    if folder_id != 'root':
        try: folder_uuid = uuid.UUID(folder_id)
        except ValueError: raise HTTPException(422, 'Invalid folder')
        folder = db.get(EvidenceFolder, folder_uuid)
        if not folder or folder.case_id != case_id: raise HTTPException(404, 'Folder not found')
        conditions.append(EvidenceFile.id.in_(EvidenceDBStorage.collect_recursive_file_ids(db, folder_uuid))
                          if recursive else EvidenceFile.folder_id == folder_uuid)
    elif not recursive:
        conditions.append(EvidenceFile.folder_id.is_(None))
    ready = (TranscriptState.reviewed_revision_id == TranscriptState.working_revision_id) & or_(
        TranscriptState.published_revision_id.is_(None), TranscriptState.published_revision_id != TranscriptState.working_revision_id)
    ready = ready & (EvidenceFile.status != 'processed') & TranscriptState.published_revision_id.is_(None)
    awaiting = or_(TranscriptState.reviewed_revision_id.is_(None), TranscriptState.reviewed_revision_id != TranscriptState.working_revision_id)
    base = select(EvidenceFile.id, EvidenceFile.original_filename).join(TranscriptState,
        TranscriptState.evidence_file_id == EvidenceFile.id).where(*conditions)
    counts = {}
    for key, condition in [('ready', ready), ('awaiting_review', awaiting)]:
        counts[key] = db.scalar(select(func.count()).select_from(base.where(condition).subquery())) or 0
    rows = db.execute(base.where(ready if state == 'ready' else awaiting)
        .order_by(EvidenceFile.original_filename, EvidenceFile.id).offset(cursor).limit(limit + 1)).all()
    return {'counts': counts, 'items': [{'id': str(row.id), 'name': row.original_filename} for row in rows[:limit]],
            'next_cursor': cursor + limit if len(rows) > limit else None}


def resolve_selection(db, selection):
    query = select(EvidenceFile).options(defer(EvidenceFile.transcription), defer(EvidenceFile.transcription_segments)).where(EvidenceFile.case_id == selection.case_id)
    if selection.file_ids is not None:
        query = query.where(EvidenceFile.id.in_(selection.file_ids))
    elif selection.folder_id not in (None, 'root'):
        try: folder_id = uuid.UUID(selection.folder_id)
        except ValueError: raise HTTPException(422, 'Invalid folder')
        folder = db.get(EvidenceFolder, folder_id)
        if not folder or folder.case_id != selection.case_id:
            raise HTTPException(404, 'Folder not found in case')
        if selection.recursive:
            query = query.where(EvidenceFile.id.in_(EvidenceDBStorage.collect_recursive_file_ids(db, folder_id)))
        else:
            query = query.where(EvidenceFile.folder_id == folder_id)
    elif not selection.recursive:
        query = query.where(EvidenceFile.folder_id.is_(None))
    files = list(db.scalars(query.order_by(EvidenceFile.original_filename, EvidenceFile.id)))
    if selection.file_ids is not None and {f.id for f in files} != set(selection.file_ids):
        raise HTTPException(404, 'One or more selected files were not found in this case')
    return files


def _prepare_processing_plan(selection, db, user):
    authorize_case(db, selection.case_id, user, ('case', 'view'))
    files = resolve_selection(db, selection)
    transcribed_ids = set(db.scalars(select(EvidenceFile.id).where(EvidenceFile.case_id == selection.case_id,
        or_(EvidenceFile.transcription != '', EvidenceFile.transcription_segments != []))))
    items = []
    for file in files:
        info = reviews.summary(file)
        audio = reviews.is_audio(file)
        if selection.ready_audio_only and (not audio or info.get('review_state') != 'ready' or file.status in ('processing', 'processed') or info.get('published_revision_id')):
            continue
        if selection.review_queue and (not audio or info.get('review_state') != 'awaiting_review'):
            continue
        skipped = file.status == 'processing' or (file.status == 'processed' and not selection.reprocess_completed)
        items.append({'id': str(file.id), 'name': file.original_filename, 'audio': audio,
            'folder_id': str(file.folder_id) if file.folder_id else None, 'source_sha256': file.sha256,
            'revision_id': info.get('revision_id'), 'reviewed': info.get('reviewed', False),
            'has_transcript': file.id in transcribed_ids, 'skipped': skipped,
            'reason': 'Already processing' if file.status == 'processing' else 'Already processed' if skipped else None})
    actor_id = user.id
    db.commit()  # No database transaction is held while querying engine readiness.
    return items, actor_id


def _store_processing_plan(selection, items, actor_id, review_enabled, db):
    plan = EvidenceProcessingPlan(case_id=selection.case_id, actor_id=actor_id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        payload={'selection': selection.model_dump(mode='json'), 'files': items, 'review_enabled': review_enabled})
    db.add(plan); db.commit()
    return describe_plan(plan)


@router.post('/processing-plans', status_code=201)
async def create_processing_plan(selection: Selection, db: Session = Depends(get_db),
                                 user: User = Depends(get_current_db_user)):
    items, actor_id = await run_in_threadpool(_prepare_processing_plan, selection, db, user)
    capability = await audio_capabilities(user) if any(item['audio'] for item in items) else {'enabled': False}
    return await run_in_threadpool(_store_processing_plan, selection, items, actor_id, capability['enabled'], db)


def describe_plan(plan):
    items = plan.payload['files']
    active = [item for item in items if not item['skipped']]
    return {'id': str(plan.id), 'case_id': str(plan.case_id), 'expires_at': plan.expires_at,
        'file_count': len(items), 'eligible_count': len(active), 'audio_count': sum(i['audio'] for i in active),
        'review_enabled': plan.payload.get('review_enabled', False),
        'unreviewed_audio_count': sum(i['audio'] and not i['reviewed'] for i in active) if plan.payload.get('review_enabled') else 0,
        'document_count': sum(not i['audio'] for i in active), 'skipped_count': len(items) - len(active),
        'selection': plan.payload['selection'], 'files': items[:100], 'execution': execution_receipt(plan.execution)}


def execution_receipt(execution):
    if execution is None:
        return None
    return {key: value for key, value in execution.items()
            if key not in ('processing_snapshots', 'folder_snapshots', 'lease_expires_at')}


def get_plan(db, plan_id, user, *, lock=False):
    query = select(EvidenceProcessingPlan).where(EvidenceProcessingPlan.id == plan_id)
    if lock: query = query.with_for_update()
    plan = db.scalar(query.execution_options(populate_existing=True))
    if not plan or plan.actor_id != user.id:
        raise HTTPException(404, 'Processing selection not found')
    authorize_case(db, plan.case_id, user, ('case', 'view'))
    return plan


@router.get('/processing-plans/{plan_id}')
def processing_plan(plan_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    return describe_plan(get_plan(db, plan_id, user))


@router.get('/processing-plans/{plan_id}/files')
def plan_files(plan_id: uuid.UUID, cursor: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100),
               db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    items = get_plan(db, plan_id, user).payload['files']
    return {'items': items[cursor:cursor + limit], 'next_cursor': cursor + limit if len(items) > cursor + limit else None}


class ExecutionInput(BaseModel):
    request_key: str = Field(min_length=1, max_length=128)
    audio_mode: str | None = Field(default=None, pattern='^(review_first|direct)$')


def _accept_plan_execution(plan_id, update, db, user):
    from services.evidence_processing_service import process_db_files, _stored_path
    from services.financial.admission_gate import gate_document_processing
    from services.financial import UnadmittedFileError
    plan = get_plan(db, plan_id, user)
    authorize_case(db, plan.case_id, user, ('evidence', 'upload'))
    from services.financial.audit_chain import lock_case_audit_chain
    lock_case_audit_chain(db, plan.case_id)
    plan = get_plan(db, plan_id, user, lock=True)
    if update.audio_mode == 'review_first' and not plan.payload.get('review_enabled'):
        raise HTTPException(409, 'Transcript review is not enabled with a compatible evidence engine')
    if plan.execution:
        if plan.execution['request_key'] != update.request_key or plan.execution['audio_mode'] != update.audio_mode:
            raise HTTPException(409, 'This selection was already submitted with different input')
        if plan.execution.get('state') == 'completed':
            receipt = execution_receipt(plan.execution)
            db.commit()
            return None, receipt
        if plan.execution.get('lease_expires_at', '') > datetime.now(timezone.utc).isoformat():
            receipt = execution_receipt(plan.execution)
            db.commit()
            return None, receipt
        plan.execution = {**plan.execution, 'lease_expires_at': (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()}
        db.commit()
    else:
        expiry = plan.expires_at.replace(tzinfo=timezone.utc) if plan.expires_at.tzinfo is None else plan.expires_at
        if expiry < datetime.now(timezone.utc):
            raise HTTPException(409, 'Processing selection expired. Check the files again.')
        if describe_plan(plan)['unreviewed_audio_count'] and not update.audio_mode:
            raise HTTPException(409, 'Choose how to process the unreviewed recordings')
        chosen = [item for item in plan.payload['files'] if not item['skipped']]
        files = list(db.scalars(select(EvidenceFile).where(EvidenceFile.id.in_([uuid.UUID(i['id']) for i in chosen]))
            .order_by(EvidenceFile.id).with_for_update().execution_options(populate_existing=True)))
        by_id = {str(f.id): f for f in files}
        for item in chosen:
            file = by_id.get(item['id'])
            if (file is None or file.case_id != plan.case_id or file.status == 'processing'
                or reviews.summary(file).get('revision_id') != item['revision_id']
                or (str(file.folder_id) if file.folder_id else None) != item.get('folder_id')
                or file.sha256 != item.get('source_sha256')):
                raise HTTPException(409, {'code': 'selection_changed', 'message': 'A selected file changed. Refresh the selection.'})
            if item['revision_id']:
                saved = db.get(TranscriptRevision, uuid.UUID(item['revision_id']))
                if saved is None or saved.evidence_file_id != file.id or saved.case_id != file.case_id:
                    raise HTTPException(409, 'Saved transcript identity changed')
                validate_bindings(file, saved.payload['speaker_entity_ids'])
            reservation = (file.metadata_ or {}).get('processing_reservation') or {}
            if reservation and reservation.get('plan_id') != str(plan.id) and reservation.get('expires_at', '') > datetime.now(timezone.utc).isoformat():
                raise HTTPException(409, 'A selected file was reserved by another processing request.')
        try: gate_document_processing(db, case_id=plan.case_id, files=files, resolve_path=_stored_path)
        except UnadmittedFileError as error: raise HTTPException(409, error.as_dict())
        from services.folder_context_service import build_processing_snapshot
        snapshots = {str(folder_id): build_processing_snapshot(db, case_id=plan.case_id,
            folder_id=folder_id, include_sibling_ids=True) for folder_id in {file.folder_id for file in files}}
        lease_expires_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        for file in files:
            file.metadata_ = {**(file.metadata_ or {}), 'processing_reservation': {'plan_id': str(plan.id), 'expires_at': lease_expires_at}}
        plan.execution = {'request_key': update.request_key, 'audio_mode': update.audio_mode,
            'state': 'accepted', 'job_ids': [], 'file_ids': [i['id'] for i in chosen],
            'lease_expires_at': lease_expires_at, 'folder_snapshots': snapshots}
        db.commit()
    snapshots = {}
    for item in plan.payload['files']:
        folder = (plan.execution.get('folder_snapshots') or {}).get(str(item.get('folder_id')))
        if folder is not None:
            snapshots[item['id']] = {**folder, 'sibling_files': [sibling for sibling in folder.get('sibling_files', [])
                if sibling.get('evidence_file_id') != item['id']]}
    arguments = dict(case_id=plan.case_id,
        file_ids=[uuid.UUID(i) for i in plan.execution['file_ids']],
        force_reprocess=plan.payload['selection']['reprocess_completed'],
        audio_mode=update.audio_mode, requested_by_user_id=user.id,
        transcript_revisions={item['id']: item['revision_id'] for item in plan.payload['files'] if item['revision_id']},
        reviewed_ids={item['id'] for item in plan.payload['files'] if item['reviewed']},
        execution_plan_id=str(plan.id), processing_snapshots=snapshots or plan.execution.get('processing_snapshots'))
    db.commit()
    return arguments, None


def _finish_plan_execution(plan_id, result, db, user):
    from services.financial.audit_chain import lock_case_audit_chain
    plan = get_plan(db, plan_id, user)
    lock_case_audit_chain(db, plan.case_id)
    plan = get_plan(db, plan_id, user, lock=True)
    for file_id in plan.execution['file_ids']:
        file = db.get(EvidenceFile, uuid.UUID(file_id))
        if file and (file.metadata_ or {}).get('processing_reservation', {}).get('plan_id') == str(plan.id):
            metadata = dict(file.metadata_ or {}); metadata.pop('processing_reservation', None); file.metadata_ = metadata
    plan.execution = {**plan.execution, **result, 'state': 'completed'}
    db.commit()
    return execution_receipt(plan.execution)


def _retry_plan_execution(plan_id, db, user):
    from services.financial.audit_chain import lock_case_audit_chain
    db.rollback()
    plan = get_plan(db, plan_id, user)
    lock_case_audit_chain(db, plan.case_id)
    plan = get_plan(db, plan_id, user, lock=True)
    plan.execution = {**plan.execution, 'lease_expires_at': '', 'state': 'retry'}
    db.commit()


@router.post('/processing-plans/{plan_id}/executions', status_code=202)
async def execute_plan(plan_id: uuid.UUID, update: ExecutionInput, db: Session = Depends(get_db),
                       user: User = Depends(get_current_db_user)):
    from services.evidence_processing_service import process_db_files
    from services.financial import UnadmittedFileError
    arguments, receipt = await run_in_threadpool(_accept_plan_execution, plan_id, update, db, user)
    if receipt is not None:
        return receipt
    try:
        result = await process_db_files(db, **arguments)
        return await run_in_threadpool(_finish_plan_execution, plan_id, result, db, user)
    except Exception as error:
        await run_in_threadpool(_retry_plan_execution, plan_id, db, user)
        if isinstance(error, UnadmittedFileError):
            raise HTTPException(409, error.as_dict()) from error
        if isinstance(error, HTTPException):
            raise
        raise HTTPException(503, 'Processing could not be fully confirmed. Retry this same selection; accepted jobs are retained.')
