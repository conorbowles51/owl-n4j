"""Resumable ordinary evidence uploads, with a receipt in the registration transaction."""
import hashlib
import math
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from config import EVIDENCE_DATA_ROOT
from postgres.session import get_db
from postgres.models.evidence_upload import EvidenceUploadSession
from postgres.models.evidence import EvidenceFolder
from postgres.models.user import User
from routers.users import get_current_db_user
from routers.case_access import authorize_case
from services.evidence_db_storage import EvidenceDBStorage

router = APIRouter(prefix='/api/evidence-upload-sessions', tags=['evidence'])
CHUNK_SIZE = 4 * 1024 * 1024
ROOT = Path(EVIDENCE_DATA_ROOT) / '_resumable_uploads'


class StartUpload(BaseModel):
    id: UUID
    case_id: UUID
    folder_id: UUID | None = None
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=0, le=1_073_741_824)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    chunks: list[str] = Field(max_length=256)


def get_session(db, identity, user, *, lock=False):
    if lock:
        prior = db.get(EvidenceUploadSession, identity)
        if prior is not None and prior.group_id:
            from routers.evidence_upload_groups import get_group
            get_group(db, prior.group_id, user, lock=True)
    query = select(EvidenceUploadSession).where(EvidenceUploadSession.id == identity)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    item = db.scalar(query)
    if item is None or item.user_id != user.id:
        raise HTTPException(404, 'Upload not found')
    authorize_case(db, item.case_id, user, ('evidence', 'upload'))
    return item


def directory(item):
    return ROOT / str(item.case_id) / str(item.id)


def snapshot(item):
    root = directory(item)
    received = []
    for index in range(len(item.chunks)):
        try:
            if (root / f'{index}.part').stat().st_size == min(item.chunk_size, item.size - index * item.chunk_size):
                received.append(index)
        except FileNotFoundError:
            pass
    return dict(id=str(item.id), case_id=str(item.case_id), filename=item.filename,
        folder_id=str(item.folder_id) if item.folder_id else None,
        size=item.size, sha256=item.sha256, chunk_size=item.chunk_size,
        received=received, status=item.status,
        evidence_id=str(item.evidence_id) if item.evidence_id else None,
        group_id=str(item.group_id) if item.group_id else None)


@router.post('')
def start_upload(body: StartUpload, user: User = Depends(get_current_db_user), db: Session = Depends(get_db)):
    authorize_case(db, body.case_id, user, ('evidence', 'upload'))
    if PurePosixPath(body.filename).name != body.filename or body.filename in ('.', '..') or '\\' in body.filename or '\x00' in body.filename:
        raise HTTPException(400, 'Choose a valid filename')
    if len(body.chunks) != math.ceil(body.size / CHUNK_SIZE) or any(not re.fullmatch(r'[a-f0-9]{64}', h) for h in body.chunks):
        raise HTTPException(400, 'Upload chunk manifest does not match the file size')
    if body.folder_id:
        folder = db.get(EvidenceFolder, body.folder_id)
        if not folder or folder.case_id != body.case_id:
            raise HTTPException(404, 'Destination folder not found')
    item = db.get(EvidenceUploadSession, body.id)
    if item is None:
        item = EvidenceUploadSession(**body.model_dump(), user_id=user.id, chunk_size=CHUNK_SIZE, status='uploading')
        db.add(item)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            item = get_session(db, body.id, user)
    item = get_session(db, body.id, user)
    if item.group_id:
        raise HTTPException(409, 'This file belongs to a folder or archive upload. Resume that selection.')
    if any(getattr(item, k) != v for k, v in body.model_dump().items()):
        raise HTTPException(409, 'This upload belongs to different file content or a different destination')
    return snapshot(item)


@router.get('')
def list_uploads(case_id: UUID, user: User = Depends(get_current_db_user), db: Session = Depends(get_db)):
    authorize_case(db, case_id, user, ('evidence', 'upload'))
    rows = db.scalars(select(EvidenceUploadSession).where(EvidenceUploadSession.case_id == case_id,
        EvidenceUploadSession.group_id.is_(None),
        EvidenceUploadSession.user_id == user.id, EvidenceUploadSession.status != 'completed').order_by(EvidenceUploadSession.created_at))
    return [snapshot(row) for row in rows]


@router.get('/{identity}')
def read_upload(identity: UUID, user: User = Depends(get_current_db_user), db: Session = Depends(get_db)):
    return snapshot(get_session(db, identity, user))


def write_chunk(item, index, content):
    expected = min(CHUNK_SIZE, item.size - index * CHUNK_SIZE)
    if len(content) != expected or hashlib.sha256(content).hexdigest() != item.chunks[index]:
        raise HTTPException(409, 'Chunk verification failed. Reselect the original file to resume.')
    root = directory(item)
    root.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=root)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(content); output.flush(); os.fsync(output.fileno())
        os.replace(temporary, root / f'{index}.part')
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


@router.put('/{identity}/chunks/{index}')
async def put_chunk(identity: UUID, index: int, request: Request,
    user: User = Depends(get_current_db_user), db: Session = Depends(get_db)):
    item = get_session(db, identity, user)
    if item.status != 'uploading':
        raise HTTPException(409, 'Resume this upload before sending more bytes')
    if not 0 <= index < len(item.chunks): raise HTTPException(400, 'Invalid chunk number')
    content = bytearray()
    async for part in request.stream():
        content.extend(part)
        if len(content) > CHUNK_SIZE: raise HTTPException(413, 'Upload chunk is too large')
    # Pause must not wait for a slow network upload holding the session lock.
    # Recheck under the lock after receiving this bounded chunk.
    item = get_session(db, identity, user, lock=True)
    if item.status != 'uploading':
        raise HTTPException(409, 'Resume this upload before sending more bytes')
    await run_in_threadpool(write_chunk, item, index, content)
    db.commit()
    return snapshot(item)


def assemble(item):
    root = directory(item)
    target = Path(EVIDENCE_DATA_ROOT) / str(item.case_id) / '_uploads' / str(item.id) / item.filename
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=target.parent)
    digest = hashlib.sha256()
    try:
        with os.fdopen(fd, 'wb') as output:
            for index, expected_hash in enumerate(item.chunks):
                path = root / f'{index}.part'
                if not path.is_file(): raise HTTPException(409, 'Upload incomplete. Resume to send missing chunks.')
                content = path.read_bytes()
                if (len(content) != min(item.chunk_size, item.size - index * item.chunk_size)
                        or hashlib.sha256(content).hexdigest() != expected_hash):
                    # The next resume snapshot must report this chunk missing;
                    # otherwise every retry skips it and fails permanently.
                    path.unlink(missing_ok=True)
                    raise HTTPException(409, 'A saved chunk failed verification; upload it again.')
                digest.update(content); output.write(content)
            output.flush(); os.fsync(output.fileno())
        if Path(temporary).stat().st_size != item.size or digest.hexdigest() != item.sha256:
            raise HTTPException(409, 'File verification failed. No evidence record was created.')
        os.replace(temporary, target)
        return target
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


@router.post('/{identity}/{action}')
async def upload_action(identity: UUID, action: str, user: User = Depends(get_current_db_user), db: Session = Depends(get_db)):
    item = get_session(db, identity, user, lock=True)
    if action not in {'pause', 'resume', 'complete'}: raise HTTPException(404, 'Unknown upload action')
    if item.status == 'completed': return snapshot(item)
    if item.group_id:
        from routers.evidence_upload_groups import get_group
        group = get_group(db, item.group_id, user)
        if action != 'complete':
            raise HTTPException(409, 'Pause or resume the whole folder or archive selection')
        if group.status != 'uploading':
            raise HTTPException(409, 'Resume this selection before completing its files')
        if item.status != 'staged':
            await run_in_threadpool(assemble, item)
            item.status = 'staged'
            db.commit()
        return snapshot(item)
    if action != 'complete':
        item.status = 'paused' if action == 'pause' else 'uploading'
    else:
        if item.status == 'paused': raise HTTPException(409, 'Resume this upload before completing it')
        target = await run_in_threadpool(assemble, item)
        records = EvidenceDBStorage.add_files(db, case_id=item.case_id, folder_id=item.folder_id,
            owner=user.email, created_by_id=user.id, files_data=[dict(original_filename=item.filename,
                stored_path=str(target), sha256=item.sha256, size=item.size,
                metadata={'upload_session_id': str(item.id)})])
        db.flush()
        item.evidence_id = records[0].id
        item.status = 'completed'
    # Receipt and evidence registration are committed together. A repeated
    # completion after a lost response returns exactly the same evidence id.
    db.commit()
    return snapshot(item)
