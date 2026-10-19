"""Resumable folder/archive uploads with retained hierarchy and one receipt.

Members are verified privately. Registration commits with the group receipt;
phone-processing requests have stable identities across lost acknowledgements.
Original evidence is never overwritten by a later upload with the same name.
"""
import hashlib
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from typing import Literal
from uuid import UUID, uuid5
import zipfile

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from postgres.models.evidence import EvidenceFolder
from postgres.models.evidence_upload import EvidenceUploadGroup, EvidenceUploadSession
from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import authorize_case
from routers.users import get_current_db_user
from routers import evidence_uploads as uploads
from services.evidence_db_storage import EvidenceDBStorage

router = APIRouter(prefix='/api/evidence-upload-groups', tags=['evidence'])
MAX_MEMBERS = 20_000
MAX_EXPANDED_BYTES = 64 * 1024**3
SKIP_NAMES = {'.DS_Store', 'Thumbs.db', 'desktop.ini'}


class Member(BaseModel):
    model_config = ConfigDict(extra='forbid')
    path: str = Field(min_length=1, max_length=2048)
    size: int = Field(ge=0, le=8 * 1024**3)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    chunks: list[str] = Field(max_length=2048)


class StartGroup(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    case_id: UUID
    folder_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    kind: Literal['folder', 'archive', 'files']
    replace_existing: bool = False
    members: list[Member] = Field(min_length=1, max_length=MAX_MEMBERS)


def safe_path(raw):
    parts = raw.split('/')
    if (any(p in ('', '.', '..') or '\\' in p or ':' in p or '\x00' in p for p in parts)
            or len(raw) > 2048 or any(len(p) > 255 for p in parts)):
        raise HTTPException(400, 'A file has an unsafe relative path. No evidence was registered.')
    return PurePosixPath(raw)


def get_group(db, identity, user, *, lock=False):
    query = select(EvidenceUploadGroup).where(EvidenceUploadGroup.id == identity)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    group = db.scalar(query)
    if group is None or group.user_id != user.id:
        raise HTTPException(404, 'Upload selection not found')
    authorize_case(db, group.case_id, user, ('evidence', 'upload'))
    return group


def members(db, group):
    return list(db.scalars(select(EvidenceUploadSession).where(
        EvidenceUploadSession.group_id == group.id).order_by(EvidenceUploadSession.filename)))


def snapshot(db, group, *, include_members=True):
    rows = members(db, group)
    paths = {str(uuid5(group.id, m['path'])): m['path'] for m in group.manifest}
    states = [dict(**uploads.snapshot(row), path=paths[str(row.id)]) for row in rows]
    received = sum(min(row['chunk_size'], row['size'] - index * row['chunk_size'])
        for row in states for index in row['received'])
    result = dict(id=str(group.id), case_id=str(group.case_id), name=group.name,
        folder_id=str(group.folder_id) if group.folder_id else None,
        kind=group.kind, status=group.status, replace_existing=group.replace_existing,
        file_count=len(rows), staged_count=sum(row.status in ('staged', 'completed') for row in rows),
        size=sum(row.size for row in rows), received_bytes=received, receipt=group.receipt)
    if include_members:
        result['members'] = states
    return result


@router.post('')
def start_group(body: StartGroup, user: User = Depends(get_current_db_user), db: Session = Depends(get_db)):
    authorize_case(db, body.case_id, user, ('evidence', 'upload'))
    if body.folder_id:
        folder = db.get(EvidenceFolder, body.folder_id)
        if folder is None or folder.case_id != body.case_id:
            raise HTTPException(404, 'Destination folder not found')
    manifest = sorted([member.model_dump() for member in body.members], key=lambda m: m['path'])
    seen = set()
    for member in manifest:
        path = safe_path(member['path'])
        if str(path).casefold() in seen:
            raise HTTPException(400, 'Two selected files have the same path. Choose a folder without ambiguous names.')
        seen.add(str(path).casefold())
        if (len(member['chunks']) != math.ceil(member['size'] / uploads.CHUNK_SIZE)
                or any(not re.fullmatch(r'[a-f0-9]{64}', h) for h in member['chunks'])):
            raise HTTPException(400, 'The upload manifest does not match its file sizes')
    if sum(m['size'] for m in manifest) > MAX_EXPANDED_BYTES:
        raise HTTPException(413, 'This selection exceeds the 64 GB upload limit. Split it into smaller selections.')
    if body.kind == 'archive' and (len(manifest) != 1 or not manifest[0]['path'].lower().endswith('.zip')):
        raise HTTPException(400, 'Select one ZIP archive')
    if body.kind == 'files' and any('/' in m['path'] for m in manifest):
        raise HTTPException(400, 'Use folder upload to retain nested file paths')
    values = body.model_dump(exclude={'members'})
    values['manifest'] = manifest
    group = db.get(EvidenceUploadGroup, body.id)
    if group is None:
        group = EvidenceUploadGroup(**values, user_id=user.id, status='uploading')
        try:
            db.add(group)
            db.flush()
            for member in manifest:
                db.add(EvidenceUploadSession(id=uuid5(body.id, member['path']), group_id=body.id,
                    case_id=body.case_id, user_id=user.id, folder_id=body.folder_id,
                    filename=PurePosixPath(member['path']).name, size=member['size'],
                    sha256=member['sha256'], chunks=member['chunks'], chunk_size=uploads.CHUNK_SIZE, status='uploading'))
            db.commit()
        except IntegrityError:
            db.rollback()
    group = get_group(db, body.id, user)
    if any(getattr(group, key) != value for key, value in values.items()):
        raise HTTPException(409, 'This upload selection belongs to different files or a different destination')
    return snapshot(db, group)


@router.get('')
def list_groups(case_id: UUID, user: User = Depends(get_current_db_user), db: Session = Depends(get_db)):
    authorize_case(db, case_id, user, ('evidence', 'upload'))
    groups = db.scalars(select(EvidenceUploadGroup).where(EvidenceUploadGroup.case_id == case_id,
        EvidenceUploadGroup.user_id == user.id, EvidenceUploadGroup.status != 'completed')
        .order_by(EvidenceUploadGroup.created_at))
    return [snapshot(db, group, include_members=False) for group in groups]


@router.get('/{identity}')
def read_group(identity: UUID, user: User = Depends(get_current_db_user), db: Session = Depends(get_db)):
    return snapshot(db, get_group(db, identity, user))


def payload_root(group):
    return Path(uploads.EVIDENCE_DATA_ROOT) / str(group.case_id) / '_upload_groups' / str(group.id) / 'payload'


def copy_verified(source, target, expected_hash, expected_size):
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=target.parent)
    digest = hashlib.sha256()
    size = 0
    try:
        with source.open('rb') as src, os.fdopen(fd, 'wb') as dst:
            for chunk in iter(lambda: src.read(1024 * 1024), b''):
                size += len(chunk)
                if size > expected_size:
                    raise HTTPException(409, 'A saved upload changed. Resume its original file before registering.')
                digest.update(chunk); dst.write(chunk)
            dst.flush(); os.fsync(dst.fileno())
        if size != expected_size or digest.hexdigest() != expected_hash:
            raise HTTPException(409, 'A saved upload failed verification. No evidence was registered.')
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def extract_archive(source, root):
    result, seen, total = [], set(), 0
    try:
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_MEMBERS:
                raise HTTPException(413, 'Archive has too many entries. Split it into smaller archives.')
            for info in infos:
                if info.is_dir(): continue
                path = safe_path(info.filename.replace('\\', '/'))
                if any(p == '__MACOSX' or p.startswith('._') for p in path.parts) or path.name in SKIP_NAMES:
                    continue
                if stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1:
                    raise HTTPException(400, 'Remove symbolic links or password protection from the archive before uploading.')
                if str(path).casefold() in seen:
                    raise HTTPException(400, 'Archive contains repeated file paths. No evidence was registered.')
                seen.add(str(path).casefold())
                total += info.file_size
                if total > MAX_EXPANDED_BYTES:
                    raise HTTPException(413, 'Expanded archive exceeds 64 GB. Split it into smaller archives.')
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                digest, size = hashlib.sha256(), 0
                with archive.open(info) as src, target.open('wb') as dst:
                    for chunk in iter(lambda: src.read(1024 * 1024), b''):
                        size += len(chunk)
                        if size > info.file_size:
                            raise HTTPException(400, 'Archive entry size failed verification')
                        digest.update(chunk); dst.write(chunk)
                    dst.flush(); os.fsync(dst.fileno())
                if size != info.file_size:
                    raise HTTPException(400, 'Archive entry is incomplete')
                result.append(dict(path=str(path), size=size, sha256=digest.hexdigest(), stored_path=str(target)))
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise HTTPException(400, 'The ZIP archive could not be read. Original uploaded bytes are retained; no evidence was registered.') from exc
    if not result:
        raise HTTPException(400, 'The archive contains no files to register')
    return result


def prepare_payload(group, rows):
    root = payload_root(group)
    prepared = []
    by_id = {row.id: row for row in rows}
    for member in group.manifest:
        row = by_id[uuid5(group.id, member['path'])]
        # Reassemble from retained verified chunks if a prior finalisation was interrupted.
        source = uploads.assemble(row)
        if group.kind == 'archive':
            return extract_archive(source, root)
        target = root / safe_path(member['path'])
        copy_verified(source, target, member['sha256'], member['size'])
        prepared.append(dict(path=member['path'], size=member['size'], sha256=member['sha256'], stored_path=str(target)))
    return prepared


def register_payload(db, group, user, prepared):
    from routers.evidence import _find_cellebrite_report_roots_from_uploads
    phone_roots = _find_cellebrite_report_roots_from_uploads([
        dict(relative_path=m['path'], staged_path=m['stored_path']) for m in prepared])
    # A parent report owns its nested exports. Do not enqueue that subtree a
    # second time just because a nested XML also carries the UFED namespace.
    phone_roots = [root for root in phone_roots if not any(
        other != root and (not other or root.startswith(other + '/')) for other in phone_roots)]
    files, dispatch = [], []
    for member in prepared:
        path = PurePosixPath(member['path'])
        if any(not root or member['path'].startswith(root + '/') for root in phone_roots):
            continue
        folder = folder_for_path(db, group, user, str(path.parent))
        records = EvidenceDBStorage.add_files(db, case_id=group.case_id, folder_id=folder,
            owner=user.email, created_by_id=user.id, files_data=[dict(
                original_filename=path.name, stored_path=member['stored_path'], sha256=member['sha256'], size=member['size'],
                metadata={'upload_group_id': str(group.id), 'relative_path': member['path'],
                    **({'original_archive_sha256': group.manifest[0]['sha256']} if group.kind == 'archive' else {})})])
        db.flush()
        files.extend(str(record.id) for record in records)
    for root in phone_roots:
        folder = folder_for_path(db, group, user, root)
        dispatch.append(dict(request_id=str(uuid5(group.id, 'processing:' + root)),
            folder_path=str(PurePosixPath('_upload_groups', str(group.id), 'payload', root)),
            evidence_folder_id=str(folder) if folder else None))
    return dict(file_ids=files, job_ids=[], dispatch=dispatch,
        message=f'Uploaded {len(prepared)} files.' + (' Folder structure is retained.' if group.kind != 'files' else '')
            + (' Phone reports are queued separately for processing.' if dispatch else ' Select Process to start ingestion.'))


def folder_for_path(db, group, user, relative_path):
    if relative_path in ('', '.'):
        return group.folder_id
    return EvidenceDBStorage.get_or_create_folder_path(db, case_id=group.case_id,
        relative_path=relative_path, parent_id=group.folder_id, created_by_id=user.id).id


async def dispatch_reports(group, user):
    from services import evidence_engine_client
    jobs = []
    for item in group.receipt.get('dispatch', []):
        job = await evidence_engine_client.create_cellebrite_job(str(group.case_id),
            folder_path=item['folder_path'], evidence_folder_id=item['evidence_folder_id'],
            owner=user.email, force=group.replace_existing, requested_by_user_id=str(user.id),
            request_id=item['request_id'])
        jobs.append(str(job['id']))
    return jobs


@router.post('/{identity}/{action}')
async def group_action(identity: UUID, action: str, user: User = Depends(get_current_db_user), db: Session = Depends(get_db)):
    if action not in {'pause', 'resume', 'complete'}:
        raise HTTPException(404, 'Unknown upload action')
    group = get_group(db, identity, user, lock=True)
    if group.status == 'completed': return snapshot(db, group)
    rows = members(db, group)
    if action in {'pause', 'resume'}:
        if group.receipt:
            raise HTTPException(409, 'Files are saved. Finish registration to reconnect their processing jobs.')
        group.status = 'paused' if action == 'pause' else 'uploading'
        for row in rows:
            if row.status != 'staged': row.status = group.status
        db.commit()
        return snapshot(db, group)
    if group.status == 'paused':
        raise HTTPException(409, 'Resume this selection before completing it')
    if not group.receipt:
        if any(row.status != 'staged' for row in rows):
            raise HTTPException(409, 'Some files have not finished uploading. Resume the selection to send the missing parts.')
        try:
            prepared = await run_in_threadpool(prepare_payload, group, rows)
        except HTTPException as exc:
            if exc.status_code == 409:
                for row in rows:
                    if len(uploads.snapshot(row)['received']) != len(row.chunks):
                        row.status = 'uploading'
                db.commit()
            raise
        group.receipt = register_payload(db, group, user, prepared)
        group.status = 'dispatching' if group.receipt['dispatch'] else 'completed'
        if group.status == 'completed':
            for row in rows: row.status = 'completed'
        # The receipt and evidence rows commit together before any external job call.
        db.commit()
    if group.status == 'dispatching':
        try:
            jobs = await dispatch_reports(group, user)
        except Exception as exc:
            raise HTTPException(503, 'Files are saved, but processing could not be queued. Choose Finish registration to retry; files will not be uploaded again.') from exc
        group = get_group(db, identity, user, lock=True)
        group.receipt = {**group.receipt, 'job_ids': jobs}
        group.status = 'completed'
        for row in members(db, group): row.status = 'completed'
        db.commit()
    return snapshot(db, group)
