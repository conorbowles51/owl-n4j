"""Resumable folder/archive uploads with retained hierarchy and one receipt.

Members are verified privately. Registration commits with the group receipt;
phone-processing requests have stable identities across lost acknowledgements.
Original evidence is never overwritten by a later upload with the same name.
"""
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from types import SimpleNamespace
from typing import Literal
from uuid import UUID, uuid4, uuid5
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, defer

from postgres.models.evidence import EvidenceFolder
from postgres.models.evidence_upload import EvidenceUploadGroup, EvidenceUploadSession
from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import authorize_case
from routers.users import get_current_db_user
from routers import evidence_uploads as uploads
from services.evidence_db_storage import EvidenceDBStorage

router = APIRouter(prefix='/api/evidence-upload-groups', tags=['evidence'])
MAX_MEMBERS = 200_000  # folder groups; the largest phone folder measured holds 93,150 files (01 D9)
MAX_ARCHIVE_ENTRIES = 20_000  # an ordinary zip unpacked into evidence rows
PHONE_CONTAINER_SUFFIXES = ('.zip', '.ufdr')
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
    """``lock=True`` holds the group row alone (pause, resume, complete, discard). ``lock='share'`` is for a file's
    own writes (a chunk, a file's finish, a batch of small files): they hold the row together, so several files of
    one selection are saved at once, and a pause or finish still waits for every write in flight. Every member write
    holding the row alone made a selection's files queue one behind another however many the page sent at once
    (measured live on a 81,820-file phone folder: 3 to 6 files a second with four in flight)."""
    # The manifest (one entry per file: 43,123 on a measured phone folder) loads only when read. Every chunk and every
    # file completion locks its group, and decoding the whole manifest each time made a folder's cost grow with its
    # square (measured live: about 2 s per file at 300 of 43,123).
    query = select(EvidenceUploadGroup).options(defer(EvidenceUploadGroup.manifest)).where(
        EvidenceUploadGroup.id == identity)
    if lock:
        query = query.with_for_update(read=lock == 'share').execution_options(populate_existing=True)
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


STAGED = ('staged', 'completed')


def _dir_names(path):
    try:
        return {entry.name for entry in os.scandir(path) if entry.is_dir()}
    except FileNotFoundError:
        return set()


def _is_uuid(name):
    try:
        UUID(name)
        return True
    except ValueError:
        return False


def summary(db, group):
    """The group's counts as ``snapshot(..., include_members=False)`` gives them, without loading its members: the
    uploads list is polled every 2 s and a phone folder has tens of thousands of members. Totals come from one
    aggregate query; the bytes of members not yet saved come from the chunk files of the few that have a chunk
    folder (a saved member keeps all its chunks, so it counts in full)."""
    S = EvidenceUploadSession
    saved = S.status.in_(STAGED)
    file_count, size, staged_count, staged_bytes = db.execute(select(
        func.count(), func.coalesce(func.sum(S.size), 0), func.coalesce(func.sum(case((saved, 1), else_=0)), 0),
        func.coalesce(func.sum(case((saved, S.size), else_=0)), 0)).where(S.group_id == group.id)).one()
    received = int(staged_bytes)
    # A member with a chunk folder whose file is not yet assembled is the one being sent. Saved members keep their
    # chunk folders, so on a phone folder the chunk folders grow to every member; asking the database about all of
    # them on every poll was 40 % of the upload routes' time while a 43,123-file folder was sent (profiled live).
    sending = _dir_names(uploads.ROOT / str(group.case_id)) - _dir_names(
        Path(uploads.EVIDENCE_DATA_ROOT) / str(group.case_id) / '_uploads')
    open_ids = [UUID(name) for name in sending if _is_uuid(name)]
    for at in range(0, len(open_ids), 1000):
        for row in db.scalars(select(S).where(S.group_id == group.id, ~saved, S.id.in_(open_ids[at:at + 1000]))):
            received += sum(min(row.chunk_size, row.size - index * row.chunk_size)
                            for index in uploads.snapshot(row)['received'])
    return dict(id=str(group.id), case_id=str(group.case_id), name=group.name,
        folder_id=str(group.folder_id) if group.folder_id else None,
        kind=group.kind, status=group.status, replace_existing=group.replace_existing,
        file_count=int(file_count), staged_count=int(staged_count), size=int(size), received_bytes=received,
        receipt=group.receipt)


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
    if body.kind == 'archive' and (len(manifest) != 1
                                   or not manifest[0]['path'].lower().endswith(PHONE_CONTAINER_SUFFIXES)):
        raise HTTPException(400, 'Select one ZIP or UFDR file')
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
        .options(defer(EvidenceUploadGroup.manifest)).order_by(EvidenceUploadGroup.created_at))
    return [summary(db, group) for group in groups]


@router.get('/{identity}')
def read_group(identity: UUID, user: User = Depends(get_current_db_user), db: Session = Depends(get_db)):
    return snapshot(db, get_group(db, identity, user))


def payload_root(group):
    return Path(uploads.EVIDENCE_DATA_ROOT) / str(group.case_id) / '_upload_groups' / str(group.id) / 'payload'


# A copy interrupted by a server kill can leave its temporary file behind; inside a phone report folder it would
# change the folder's digest, so a later finish removes these before anything is copied or detected.
PARTIAL_PREFIX = '.owl-partial-'


def remove_partials(root):
    if root.is_dir():
        for leftover in root.rglob(PARTIAL_PREFIX + '*'):
            if leftover.is_file() and not leftover.is_symlink():
                leftover.unlink()


def copy_verified(source, target, expected_hash, expected_size):
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=target.parent, prefix=PARTIAL_PREFIX)
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


def matches(path, expected_hash, expected_size):
    """The file's bytes are exactly the ones its fingerprint names."""
    if path.stat().st_size != expected_size:
        return False
    digest = hashlib.sha256()
    with path.open('rb') as src:
        for chunk in iter(lambda: src.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest() == expected_hash


def verified_source(row):
    """The file assembled when it arrived, read back and checked against its fingerprint; rebuilt from its retained
    parts only when it is missing or fails the check (an interrupted assembly). Assembling every file again at
    registration wrote and flushed each one a second time: 4.1 ms a file, about 3 minutes on a 43,123-file folder."""
    existing = uploads.assembled_path(row)
    if existing.is_file() and matches(existing, row.sha256, row.size):
        return existing
    return uploads.assemble(row)


def place_verified(source, target, expected_hash, expected_size):
    """Put a verified upload in the payload as a second name for the same bytes (a hard link: assembly always writes
    a new file and nothing writes into one, so the bytes cannot change under either name), checked again through the
    new name. Where a link is not possible the file is copied and verified. A copy wrote and flushed every file once
    more: 4.0 ms a file against 0.2 ms for the check and link, and every upload was stored twice."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / (PARTIAL_PREFIX + uuid4().hex)
    try:
        os.link(source, temporary)
    except OSError:
        return copy_verified(source, target, expected_hash, expected_size)
    try:
        if not matches(temporary, expected_hash, expected_size):
            raise HTTPException(409, 'A saved upload failed verification. No evidence was registered.')
        os.replace(temporary, target)
    finally:
        if os.path.lexists(temporary): os.unlink(temporary)


def extract_archive(source, root, keep=None):
    """Unpack a verified zip into the payload root. ``keep(path)``, when given, limits which members are written;
    every member is still checked, and an empty result is then not an error. The entry limit counts what is
    unpacked: a phone zip's report files stay in the zip, so they do not count (a Mac zip of a 29,108-file report
    holds 58,215 entries with its ``__MACOSX`` copies and was refused registration while only checking for files
    beside the report)."""
    result, seen, total = [], set(), 0
    too_many = HTTPException(413, 'Archive has too many entries. Split it into smaller archives.')
    try:
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            if keep is None and len(infos) > MAX_ARCHIVE_ENTRIES:
                raise too_many
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
                if keep is not None and not keep(path.as_posix()):
                    continue
                if len(result) >= MAX_ARCHIVE_ENTRIES:
                    raise too_many
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
    if not result and keep is None:
        raise HTTPException(400, 'The archive contains no files to register')
    return result


NOT_A_PHONE_REPORT = 'not_a_phone_report'
DETECT_UNAVAILABLE = ('Files are saved, but they could not be checked for phone reports. Choose Finish registration '
                      'to retry; files will not be uploaded again.')


def skipped_name(relpath):
    """The engine's skip set (01 section 2.3 step 2), the same names extraction leaves out."""
    parts = [p for p in relpath.split('/') if p]
    return bool(parts) and ('__MACOSX' in parts or parts[-1].startswith('._') or parts[-1] in SKIP_NAMES)


def folder_container_sha256(members):
    """A folder container's digest, as the engine computes it (01 section 3 step 1): SHA-256 of the sorted lines
    ``"{sha256}  {size}  {relative path}\\n"`` over every non-skipped file. ``members`` are (relpath, size, sha256)."""
    lines = ''.join('%s  %d  %s\n' % (sha, size, rel) for rel, size, sha in sorted(members) if not skipped_name(rel))
    return hashlib.sha256(lines.encode('utf-8')).hexdigest()


def case_relative(group, path):
    return Path(path).relative_to(Path(uploads.EVIDENCE_DATA_ROOT) / str(group.case_id)).as_posix()


def outside_report(source, root, found, container_path):
    """Members of a readable phone zip that lie outside every report folder in it, unpacked as ordinary evidence:
    documents arriving together need not be related (decision D34). The zip itself stays whole as the container.
    Nothing is unpacked when a report sits at the zip's top level or the zip cannot be read."""
    roots = [r.get('root_path') or '' for r in found.get('roots') or []]
    if found.get('outcome') != 'readable' or not roots or '' in roots:
        return []
    clash = container_path.casefold()

    def keep(path):
        return (not skipped_name(path) and path.casefold() != clash
                and not any(path.startswith(rp + '/') for rp in roots))
    return extract_archive(source, root, keep)


def prepare_payload(group, rows, detect):
    """Verified copy into the payload root. ``detect(case_relative_path)`` is the engine's phone classification
    (01 section 2.5). A phone container is never unpacked here: a zip or UFDR holding a phone report, readable or
    protected, is copied whole (01 section 4.2 step 3); an ordinary zip is unpacked as before. Returns the ordinary
    members and the phone containers."""
    root = payload_root(group)
    remove_partials(root)
    prepared = []
    by_id = {row.id: row for row in rows}
    for member in group.manifest:
        row = by_id[uuid5(group.id, member['path'])]
        source = verified_source(row)
        if group.kind == 'archive':
            found = detect(case_relative(group, source))
            if found.get('outcome', NOT_A_PHONE_REPORT) == NOT_A_PHONE_REPORT:
                return dict(members=extract_archive(source, root), phones=[])
            target = root / safe_path(member['path'])
            place_verified(source, target, member['sha256'], member['size'])
            return dict(members=outside_report(source, root, found, member['path']), phones=[dict(
                path=member['path'], stored_path=str(target), sha256=member['sha256'], size=member['size'],
                name=PurePosixPath(member['path']).name, kind=found.get('container_kind'), outcome=found['outcome'],
                roots=[r['root_path'] for r in found.get('roots') or []] or [''],
                messages=found.get('messages') or [])])
        target = root / safe_path(member['path'])
        place_verified(source, target, member['sha256'], member['size'])
        prepared.append(dict(path=member['path'], size=member['size'], sha256=member['sha256'], stored_path=str(target)))
    found = detect(case_relative(group, root))
    phones = []
    for r in (found.get('roots') or []) if found.get('outcome') != NOT_A_PHONE_REPORT else []:
        # Each report folder is its own container; other files in the same selection stay ordinary evidence,
        # because documents arriving together need not be related (decision D34).
        rp = r['root_path']
        inside = [m for m in prepared if not rp or m['path'].startswith(rp + '/')]
        phones.append(dict(path=rp, stored_path=str(root / rp) if rp else str(root),
            sha256=folder_container_sha256([(m['path'][len(rp) + 1:] if rp else m['path'], m['size'], m['sha256'])
                                            for m in inside]),
            size=sum(m['size'] for m in inside), name=PurePosixPath(rp).name if rp else group.name,
            kind='folder', outcome=found['outcome'], roots=[''], member_paths=[m['path'] for m in inside],
            messages=[m for m in found.get('messages') or [] if m.get('code') != 'several_roots']))
    claimed = {p for phone in phones for p in phone['member_paths']}
    return dict(members=[m for m in prepared if m['path'] not in claimed], phones=phones)


PROTECTED_TASK_TITLE = 'Unprotected copy needed: {name}'


def register_payload(db, group, user, prepared):
    """One evidence row per ordinary file; one ``phone_extraction`` evidence row per phone container and one
    dispatch item per report root in it (01 sections 4.2 step 4 and 4.4). A protected container is dispatched too:
    the capture job records its container row and hashes and stops with the explanation (2.4, decision D35).
    A protected container also opens a Workspace task, linked to its evidence row (07 J-1a)."""
    files, dispatch, notices = [], [], []
    for member in prepared['members']:
        path = PurePosixPath(member['path'])
        folder = folder_for_path(db, group, user, str(path.parent))
        records = EvidenceDBStorage.add_files(db, case_id=group.case_id, folder_id=folder,
            owner=user.email, created_by_id=user.id, files_data=[dict(
                original_filename=path.name, stored_path=member['stored_path'], sha256=member['sha256'], size=member['size'],
                metadata={'upload_group_id': str(group.id), 'relative_path': member['path'],
                    **({'original_archive_sha256': group.manifest[0]['sha256']} if group.kind == 'archive' else {})})])
        db.flush()
        files.extend(str(record.id) for record in records)
    payload = PurePosixPath('_upload_groups', str(group.id), 'payload')
    for phone in prepared['phones']:
        folder = folder_for_path(db, group, user, str(PurePosixPath(phone['path']).parent))
        [record] = EvidenceDBStorage.add_files(db, case_id=group.case_id, folder_id=folder, owner=user.email,
            created_by_id=user.id, files_data=[dict(
                original_filename=phone['name'], stored_path=phone['stored_path'], sha256=phone['sha256'],
                size=phone['size'], source_type='phone_extraction',
                metadata={'upload_group_id': str(group.id), 'relative_path': phone['path'],
                          'phone_container_kind': phone['kind'], 'phone_detect_outcome': phone['outcome'],
                          'phone_detect_messages': phone['messages']})])
        # Never offered to document processing: the phone reading owns it, and the engine sets processed or failed
        # when the reading ends (evidence-engine app/phone/job.py).
        record.status = 'processing'
        db.flush()
        files.append(str(record.id))
        notices.extend(m['text'] for m in phone['messages'])
        if phone['outcome'] != 'readable':
            from postgres.models.work import CaseTask
            from services.work_service import _replace_links
            text = phone['messages'][0]['text'] if phone['messages'] else ''
            task = CaseTask(case_id=group.case_id, title=PROTECTED_TASK_TITLE.format(name=phone['name'])[:512],
                            description=text or None, status='todo', priority='standard',
                            created_by_user_id=user.id, updated_by_user_id=user.id)
            db.add(task)
            db.flush()
            _replace_links(db, task=task, links=[dict(target_type='evidence', target_id=str(record.id))], user=user)
        container = str(payload / phone['path']) if phone['path'] else str(payload)
        for rp in phone['roots']:
            dispatch.append(dict(request_id=str(uuid5(group.id, 'phone-capture:%s:%s' % (phone['path'], rp))),
                container_path=container, root_path=rp, evidence_folder_id=str(folder) if folder else None,
                container_evidence_id=str(record.id), upload_sha256=phone['sha256'], original_name=phone['name']))
    count = len(prepared['members']) + sum(len(p.get('member_paths') or [1]) for p in prepared['phones'])
    message = f"Uploaded {count:,} {'file' if count == 1 else 'files'}." + (
        ' Folder structure is retained.' if group.kind != 'files' else '')
    if notices:
        message += ' ' + ' '.join(notices)
    elif prepared['members']:
        message += ' Select Process to start ingestion.'
    return dict(file_ids=files, job_ids=[], dispatch=dispatch, message=message)


def folder_for_path(db, group, user, relative_path):
    if relative_path in ('', '.'):
        return group.folder_id
    return EvidenceDBStorage.get_or_create_folder_path(db, case_id=group.case_id,
        relative_path=relative_path, parent_id=group.folder_id, created_by_id=user.id).id


async def dispatch_reports(group, user):
    from services import evidence_engine_client
    jobs = []
    for item in group.receipt.get('dispatch', []):
        job = await evidence_engine_client.create_phone_capture_job(
            str(group.case_id), request_id=item['request_id'], container_path=item['container_path'],
            root_path=item['root_path'], container_evidence_id=item['container_evidence_id'],
            evidence_folder_id=item['evidence_folder_id'], requested_by_user_id=str(user.id),
            original_name=item.get('original_name'), upload_sha256=item.get('upload_sha256'),
            upload_group_id=str(group.id))
        jobs.append(str(job['id']))
    return jobs


def engine_detector(case_id):
    """The engine's classification, called from the worker thread that prepares the payload."""
    import anyio.from_thread
    from services import evidence_engine_client

    def detect(path):
        try:
            return anyio.from_thread.run(evidence_engine_client.detect_phone_container, str(case_id), path)
        except Exception as exc:
            raise HTTPException(503, DETECT_UNAVAILABLE) from exc
    return detect


ALREADY_REGISTERED = ('Files from this selection are already in Evidence, so it cannot be discarded. Nothing was '
                      'removed.')


def discard_group(db, identity, user):
    """Abandon a selection that has registered nothing: its saved parts, any copy made by an interrupted finish,
    its member rows and the group row are removed. Refused once the selection holds a receipt (its files are
    evidence then, and evidence is removed only through Evidence)."""
    group = get_group(db, identity, user, lock=True)
    if group.receipt or group.status in ('dispatching', 'completed'):
        raise HTTPException(409, ALREADY_REGISTERED)
    S = EvidenceUploadSession
    rows = db.execute(select(S.id, S.case_id, S.status).where(S.group_id == group.id)).all()
    for row in rows:
        shutil.rmtree(uploads.directory(row), ignore_errors=True)
    shutil.rmtree(payload_root(group).parent, ignore_errors=True)
    result = dict(id=str(group.id), status='discarded', file_count=len(rows),
                  saved_count=sum(1 for row in rows if row.status in STAGED))
    db.execute(delete(S).where(S.group_id == group.id))
    db.execute(delete(EvidenceUploadGroup).where(EvidenceUploadGroup.id == group.id))
    db.commit()
    return result


# Small files of one selection travel many to a request (lx-uploadspeed C). Measured on a live 81,820-file phone
# folder: 80 % of its files are under 16 KB, and each file cost three requests (its state, its one chunk, its finish)
# and two flushed writes (the chunk, then the assembled file). One batch request carries up to BATCH_MAX_FILES files
# of one part each (at most uploads.CHUNK_SIZE bytes), BATCH_MAX_BYTES in all. Every file is checked against the
# SHA-256 it was chosen with and saved exactly as a finished single-file send saves it: the assembled file, its one
# part, its own upload row marked staged. Registration later makes one evidence row per file, unchanged.
BATCH_MAX_FILES = 1000
BATCH_MAX_BYTES = 8 * 1024 * 1024
BATCH_MAX_HEADER = 256 * 1024
BATCH_MISMATCH = ('{name} does not match the fingerprint taken when it was chosen, so it was not saved. Select the '
                  'original folder again; files already saved are kept.')


def _batch_spec(body):
    """The first line of a batch is JSON ``{"files": [{"id": <member id>, "size": <bytes>}, ...]}``; the files'
    bytes follow it back to back in that order."""
    end = body.find(b'\n', 0, BATCH_MAX_HEADER)
    try:
        if end < 0:
            raise ValueError
        files = json.loads(bytes(body[:end]))['files']
        spec = [(UUID(str(item['id'])), item['size']) for item in files]
    except (ValueError, KeyError, TypeError):
        raise HTTPException(400, 'The batch does not describe its files. Nothing in it was saved.')
    if (not spec or len(spec) > BATCH_MAX_FILES or len({i for i, _ in spec}) != len(spec)
            or any(type(size) is not int or size < 0 for _, size in spec)
            or sum(size for _, size in spec) != len(body) - end - 1):
        raise HTTPException(400, 'The batch does not match its description. Nothing in it was saved.')
    return spec, end + 1


def _write_flushed(path, content):
    """``content`` at ``path`` through a temporary file in the same folder; the caller flushes ``fd`` and replaces."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    with os.fdopen(fd, 'wb', closefd=False) as output:
        output.write(content)
    return fd, temporary


def save_batch(db, identity, user, body):
    spec, offset = _batch_spec(body)
    group = get_group(db, identity, user, lock='share')
    if group.status != 'uploading':
        raise HTTPException(409, 'Resume this selection before sending more files')
    S = EvidenceUploadSession
    rows = {row.id: row for row in db.scalars(select(S).where(S.group_id == group.id, S.id.in_([i for i, _ in spec]))
                                              .order_by(S.id).with_for_update())}
    if len(rows) != len(spec):
        raise HTTPException(404, 'A file in this batch is not part of this selection. Nothing in it was saved.')
    view = memoryview(body)
    pending, results = [], []
    try:
        for identity_, size in spec:
            row, content = rows[identity_], view[offset:offset + size]
            offset += size
            if row.size != size or size > uploads.CHUNK_SIZE or len(row.chunks) != (1 if size else 0):
                raise HTTPException(400, 'A file in this batch is not a one-part file of its chosen size. Nothing '
                                         'in it was saved.')
            if row.status in STAGED:  # a repeat after a lost response: saved already, kept as it is
                results.append(dict(id=str(row.id), status=row.status))
                continue
            if row.status != 'uploading':
                raise HTTPException(409, 'Resume this selection before sending more files')
            digest = hashlib.sha256(content).hexdigest()
            if digest != row.sha256 or (size and digest != row.chunks[0]):
                results.append(dict(id=str(row.id), status=row.status, error=BATCH_MISMATCH.format(name=row.filename)))
                continue
            target = uploads.assembled_path(row)
            fd, temporary = _write_flushed(target, content)
            pending.append((row, fd, temporary, target))
            results.append(dict(id=str(row.id), status='staged'))
        # Every file is written first and flushed after, which lets the disk take the flushes together (measured on
        # the evidence disk: 10.4 ms a file against 17.4 ms written and flushed one at a time).
        while pending:
            row, fd, temporary, target = pending.pop(0)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            try:
                os.replace(temporary, target)
            except OSError:
                os.unlink(temporary)
                raise
            if row.size:
                # The file's one part is the same bytes: a second name for the assembled file, as a finished
                # single-file send leaves its part (resume, the received count and a re-assembly read it).
                part = uploads.directory(row) / '0.part'
                part.parent.mkdir(parents=True, exist_ok=True)
                link = part.parent / f'.batch-{uuid4().hex}'
                try:
                    os.link(target, link)
                    os.replace(link, part)
                except OSError:
                    if os.path.lexists(link): os.unlink(link)
                    uploads.write_chunk(row, 0, target.read_bytes())
            row.status = 'staged'
    finally:
        for _, fd, temporary, _ in pending:
            os.close(fd)
            if os.path.exists(temporary): os.unlink(temporary)
    db.commit()
    return dict(files=results)


def _check_batch_open(db, identity, user):
    if get_group(db, identity, user).status != 'uploading':
        raise HTTPException(409, 'Resume this selection before sending more files')


@router.put('/{identity}/files')
async def put_files(identity: UUID, request: Request, user: User = Depends(get_current_db_user),
                    db: Session = Depends(get_db)):
    # Async only to receive the body; database and disk work run in the thread pool, not on the event loop.
    await run_in_threadpool(_check_batch_open, db, identity, user)
    body = bytearray()
    async for part in request.stream():
        body.extend(part)
        if len(body) > BATCH_MAX_BYTES + BATCH_MAX_HEADER:
            raise HTTPException(413, 'This batch is too large')
    return await run_in_threadpool(save_batch, db, identity, user, body)


@router.post('/{identity}/{action}')
async def group_action(identity: UUID, action: str, user: User = Depends(get_current_db_user), db: Session = Depends(get_db)):
    if action == 'discard':
        return await run_in_threadpool(discard_group, db, identity, user)
    if action not in {'pause', 'resume', 'complete'}:
        raise HTTPException(404, 'Unknown upload action')
    # Async for the engine calls; every database step runs in the thread pool, in the same order and transaction
    # (the group row stays locked from the first step to the commit that ends it).

    def start():
        group = get_group(db, identity, user, lock=True)
        if group.status == 'completed': return None, None, snapshot(db, group)
        rows = members(db, group)
        if action in {'pause', 'resume'}:
            if group.receipt:
                raise HTTPException(409, 'Files are saved. Finish registration to reconnect their processing jobs.')
            group.status = 'paused' if action == 'pause' else 'uploading'
            for row in rows:
                if row.status != 'staged': row.status = group.status
            db.commit()
            return None, None, snapshot(db, group)
        if group.status == 'paused':
            raise HTTPException(409, 'Resume this selection before completing it')
        if not group.receipt and any(row.status != 'staged' for row in rows):
            raise HTTPException(409, 'Some files have not finished uploading. Resume the selection to send the missing parts.')
        return group, rows, None

    group, rows, answer = await run_in_threadpool(start)
    if answer is not None:
        return answer
    if not group.receipt:
        try:
            prepared = await run_in_threadpool(prepare_payload, group, rows, engine_detector(group.case_id))
        except HTTPException as exc:
            if exc.status_code == 409:
                def mark_unfinished():
                    for row in rows:
                        if len(uploads.snapshot(row)['received']) != len(row.chunks):
                            row.status = 'uploading'
                    db.commit()
                await run_in_threadpool(mark_unfinished)
            raise

        def register():
            group.receipt = register_payload(db, group, user, prepared)
            group.status = 'dispatching' if group.receipt['dispatch'] else 'completed'
            if group.status == 'completed':
                for row in rows: row.status = 'completed'
            # The receipt and evidence rows commit together before any external job call.
            db.commit()
            if group.status == 'completed':
                for row in rows: uploads.remove_parts(row)
        await run_in_threadpool(register)
    # What the engine calls read, loaded here: after a commit the objects reload on first use.
    dispatch = await run_in_threadpool(lambda: None if group.status != 'dispatching' else (
        SimpleNamespace(id=group.id, case_id=group.case_id, receipt=group.receipt),
        SimpleNamespace(email=user.email, id=user.id)))
    if dispatch is not None:
        try:
            jobs = await dispatch_reports(*dispatch)
        except Exception as exc:
            raise HTTPException(503, 'Files are saved, but processing could not be queued. Choose Finish registration to retry; files will not be uploaded again.') from exc

        def finish():
            group = get_group(db, identity, user, lock=True)
            group.receipt = {**group.receipt, 'job_ids': jobs}
            group.status = 'completed'
            done = members(db, group)
            for row in done: row.status = 'completed'
            db.commit()
            for row in done: uploads.remove_parts(row)
            return snapshot(db, group)
        return await run_in_threadpool(finish)
    return await run_in_threadpool(snapshot, db, group)
