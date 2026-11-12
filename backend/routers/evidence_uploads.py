"""Resumable ordinary evidence uploads, with a receipt in the registration transaction."""
import hashlib
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from types import SimpleNamespace
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from config import EVIDENCE_DATA_ROOT
from postgres.session import get_db
from postgres.models.evidence_upload import EvidenceUploadSession
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.user import User
from routers.users import get_current_db_user
from routers.case_access import authorize_case
from services.evidence_db_storage import EvidenceDBStorage
from services.evidence_archive import MAX_EXPANDED_BYTES

router = APIRouter(prefix='/api/evidence-upload-sessions', tags=['evidence'])
CHUNK_SIZE = 4 * 1024 * 1024
ROOT = Path(EVIDENCE_DATA_ROOT) / '_resumable_uploads'
# One evidence file reaches as far as one folder selection (Neil, 12 Nov: "Loupe has to accept more than 1gb if it's
# accepting phones"). The old 1 GiB cap refused a 1.3 GB body-cam video after the browser had hashed it for minutes.
# Chunks are saved, verified and assembled one at a time, so the size is bounded by free disk space, checked below.
MAX_FILE_BYTES = MAX_EXPANDED_BYTES
# Kept free on the evidence disk after an upload's parts and its assembled file (the database and other uploads share it).
DISK_RESERVE_BYTES = 1024**3


def gigabytes(size):
    return f'{size / 1024**3:.1f} GB'


class StartUpload(BaseModel):
    id: UUID
    case_id: UUID
    folder_id: UUID | None = None
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    # A bound on the request only; the file's own limit is MAX_FILE_BYTES, refused in words by start_upload.
    chunks: list[str] = Field(max_length=4 * MAX_FILE_BYTES // (4 * 1024 * 1024))


def free_bytes():
    root = Path(EVIDENCE_DATA_ROOT)
    while not root.exists() and root != root.parent:
        root = root.parent
    return shutil.disk_usage(root).free


def refuse_without_space(filename, needed):
    """507 naming the bytes needed and the bytes free, before a byte is sent or assembled."""
    free = free_bytes()
    if needed + DISK_RESERVE_BYTES > free:
        raise HTTPException(507, f'{filename} was not uploaded: it needs {gigabytes(needed)} of storage '
            f'({needed:,} bytes) and {gigabytes(free)} ({free:,} bytes) is free.')


def get_session(db, identity, user, *, lock=False):
    if lock:
        prior = db.get(EvidenceUploadSession, identity)
        if prior is not None and prior.group_id:
            from routers.evidence_upload_groups import get_group
            get_group(db, prior.group_id, user, lock='share')
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


def remove_parts(item):
    """A completed upload's file is evidence (verified against its hash when assembled); its saved parts are
    no longer needed. Failures are logged and left for the sweep."""
    try:
        shutil.rmtree(directory(item))
    except FileNotFoundError:
        pass
    except OSError:
        import logging
        logging.getLogger(__name__).warning('Could not remove the saved parts of upload %s', item.id, exc_info=True)


def sweep_completed_parts(db, *, apply=False):
    """Part folders of uploads whose status is 'completed' (their evidence is registered). Folders of any
    other status, with no upload record, or whose evidence file is gone, are left. Returns counts; removes them only with ``apply``."""
    out = dict(folders=0, files=0, bytes=0, removed=0, left_other_status=0, left_no_record=0, left_no_evidence=0)
    # A completed upload whose evidence is gone (deleted from the case later) keeps its parts: they are the
    # only copy left (2 Nov sweep: 34 such folders). Evidence counts by its link or the same file in the case.
    has_evidence = or_(
        exists().where(EvidenceFile.id == EvidenceUploadSession.evidence_id),
        exists().where(EvidenceFile.case_id == EvidenceUploadSession.case_id,
                       EvidenceFile.sha256 == EvidenceUploadSession.sha256))
    if not ROOT.is_dir():
        return out
    for case_dir in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        names = {p.name: p for p in case_dir.iterdir() if p.is_dir()}
        ids = []
        for name in names:
            try:
                ids.append(UUID(name))
            except ValueError:
                pass
        status = {}
        for at in range(0, len(ids), 1000):
            status.update({str(i): (s, e) for i, s, e in db.execute(select(EvidenceUploadSession.id,
                EvidenceUploadSession.status, has_evidence).where(EvidenceUploadSession.id.in_(ids[at:at + 1000])))})
        for name, path in names.items():
            if name not in status:
                out['left_no_record'] += 1
                continue
            if status[name][0] != 'completed':
                out['left_other_status'] += 1
                continue
            if not status[name][1]:
                out['left_no_evidence'] += 1
                continue
            files = [entry for entry in os.scandir(path) if entry.is_file()]
            out['folders'] += 1
            out['files'] += len(files)
            out['bytes'] += sum(entry.stat().st_size for entry in files)
            if apply:
                shutil.rmtree(path, ignore_errors=True)
                out['removed'] += not path.exists()
    return out


def snapshot(item, *, trust_staged=False):
    """``trust_staged``: a staged member (assembled and checked against its fingerprint) counts every chunk without
    a look at its parts. A selection's snapshot passes it: it stat'd every chunk of every saved member, 130 s for an
    81,820-file selection at load 50 (6 Nov). Registration still reads the parts (default), so a staged member whose
    parts were lost is found there and sent again."""
    root = directory(item)
    received = []
    full = item.status == 'completed' or (trust_staged and item.status == 'staged')
    if full:
        # Every chunk was received and verified; the parts are removed once the file is evidence.
        received = list(range(len(item.chunks)))
    for index in range(len(item.chunks) if not full else 0):
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
    if body.size > MAX_FILE_BYTES:
        raise HTTPException(413, f'{body.filename} is {gigabytes(body.size)}; one file can be at most '
            f'{gigabytes(MAX_FILE_BYTES)}, so it was not uploaded.')
    if len(body.chunks) != math.ceil(body.size / CHUNK_SIZE) or any(not re.fullmatch(r'[a-f0-9]{64}', h) for h in body.chunks):
        raise HTTPException(400, 'Upload chunk manifest does not match the file size')
    if body.folder_id:
        folder = db.get(EvidenceFolder, body.folder_id)
        if not folder or folder.case_id != body.case_id:
            raise HTTPException(404, 'Destination folder not found')
    item = db.get(EvidenceUploadSession, body.id)
    if item is None:
        # Its parts and then the assembled file are both on disk until the evidence is registered.
        refuse_without_space(body.filename, 2 * body.size)
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
    # Async only to receive the body; database and disk work run in the thread pool, not on the event loop.
    await run_in_threadpool(_check_chunk_accepted, db, identity, user, index)
    content = bytearray()
    async for part in request.stream():
        content.extend(part)
        if len(content) > CHUNK_SIZE: raise HTTPException(413, 'Upload chunk is too large')
    return await run_in_threadpool(_save_chunk, db, identity, user, index, content)


def _check_chunk_accepted(db: Session, identity: UUID, user: User, index: int) -> None:
    item = get_session(db, identity, user)
    if item.status != 'uploading':
        raise HTTPException(409, 'Resume this upload before sending more bytes')
    if not 0 <= index < len(item.chunks): raise HTTPException(400, 'Invalid chunk number')


def _save_chunk(db: Session, identity: UUID, user: User, index: int, content: bytearray):
    # Pause must not wait for a slow network upload holding the session lock.
    # Recheck under the lock after receiving this bounded chunk.
    item = get_session(db, identity, user, lock=True)
    if item.status != 'uploading':
        raise HTTPException(409, 'Resume this upload before sending more bytes')
    write_chunk(item, index, content)
    db.commit()
    return snapshot(item)


def assembled_path(item):
    return Path(EVIDENCE_DATA_ROOT) / str(item.case_id) / '_uploads' / str(item.id) / item.filename


def assemble(item):
    root = directory(item)
    target = assembled_path(item)
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


def assemble_outside_transaction(db, item):
    """Assemble an ordinary upload with no transaction open. Assembly reads and hashes every byte (minutes for a
    file of many GB); the session row lock, or an idle open transaction, held that long would stall a pause, a
    release and the database (an idle-in-transaction upload stalled two releases, 12 Nov)."""
    spec = SimpleNamespace(id=item.id, case_id=item.case_id, filename=item.filename, size=item.size,
        chunk_size=item.chunk_size, chunks=list(item.chunks), sha256=item.sha256)
    db.commit()
    refuse_without_space(spec.filename, spec.size)
    return assemble(spec)


@router.post('/{identity}/{action}')
def upload_action(identity: UUID, action: str, user: User = Depends(get_current_db_user), db: Session = Depends(get_db)):
    item = get_session(db, identity, user, lock=True)
    if action not in {'pause', 'resume', 'complete'}: raise HTTPException(404, 'Unknown upload action')
    if item.status == 'completed':
        remove_parts(item)  # a repeat after a lost response, or parts left by an earlier failure
        return snapshot(item)
    if item.group_id:
        from routers.evidence_upload_groups import get_group
        group = get_group(db, item.group_id, user)
        if action != 'complete':
            raise HTTPException(409, 'Pause or resume the whole folder or archive selection')
        if group.status != 'uploading':
            raise HTTPException(409, 'Resume this selection before completing its files')
        if item.status != 'staged':
            assemble(item)
            item.status = 'staged'
            db.commit()
        return snapshot(item)
    if action != 'complete':
        item.status = 'paused' if action == 'pause' else 'uploading'
    else:
        if item.status == 'paused': raise HTTPException(409, 'Resume this upload before completing it')
        target = assemble_outside_transaction(db, item)
        # Locked again: a pause or another completion may have landed while the file was assembled.
        item = get_session(db, identity, user, lock=True)
        if item.status == 'completed':
            remove_parts(item)
            return snapshot(item)
        if item.status == 'paused': raise HTTPException(409, 'Resume this upload before completing it')
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
    if item.status == 'completed':
        remove_parts(item)
    return snapshot(item)
