"""A large selection of statement files for the review queue, kept on the server under a short id.

Statement files > select files > Review selected put every chosen file's id in the queue's address and in each queue
read (45 characters per file): beyond about 720 files the address passes nginx's 32k header buffer and is refused
414, and d5b330d1 has 1,363 statement files. A selection that large is saved once here; the address and every read
carry its id. The ids are kept as chosen, in the memo directory every worker shares (view_cache._memo_dir), so a
reload or the other worker finds them. Nothing in the database is written. An id that is not found is refused, never
read as "every file".
"""
import hashlib
import json
import os
import threading
import time
from uuid import UUID

from sqlalchemy import select

from services.financial.pdf_candidates import PdfMappingError

KEPT_SECONDS = 30 * 24 * 3600
MAX_FILES = 20_000
GONE = 'This selection of files is no longer available. Choose the files again in Statement files.'


def _directory():
    from services.financial.view_cache import _memo_dir
    directory = _memo_dir()
    return None if directory is None else directory / 'queue-selections'


def _path(directory, selection_id):
    if len(selection_id) != 32 or any(c not in '0123456789abcdef' for c in selection_id):
        raise PdfMappingError(GONE, 404)
    return directory / (selection_id + '.json')


def save(session, *, case_id, file_ids):
    """The id of these files' selection in this case (the same files give the same id). Every id must be a file of
    this case: one that is not is refused with the count, never dropped."""
    ids = sorted({str(UUID(str(identifier))) for identifier in file_ids})
    if not ids:
        raise PdfMappingError('Choose at least one file.', 422)
    if len(ids) > MAX_FILES:
        raise PdfMappingError(f'Choose at most {MAX_FILES:,} files.', 422)
    known = _case_file_ids(session, case_id, ids)
    missing = len(ids) - len(known)
    if missing:
        raise PdfMappingError(f'{missing} of the chosen files {"is" if missing == 1 else "are"} not in this case.', 422)
    directory = _directory()
    if directory is None:
        raise PdfMappingError('Large selections cannot be kept on this server. Choose fewer files.', 503)
    selection_id = hashlib.sha256(json.dumps([str(case_id), ids]).encode()).hexdigest()[:32]
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = _path(directory, selection_id)
    # One temporary name per process and thread: two saves of the same selection at once (a double click) must not
    # write into each other's file.
    temporary = path.with_name(path.name + '.%d.%d.tmp' % (os.getpid(), threading.get_ident()))
    temporary.write_text(json.dumps(dict(case_id=str(case_id), file_ids=ids)), encoding='utf-8')
    os.replace(temporary, path)  # also renews its time: a selection in use is kept
    _trim(directory)
    return selection_id


def _case_file_ids(session, case_id, ids):
    from postgres.models.evidence import EvidenceFile
    return {str(identifier) for identifier in session.scalars(select(EvidenceFile.id).where(
        EvidenceFile.case_id == case_id, EvidenceFile.id.in_([UUID(identifier) for identifier in ids])))}


def file_ids(case_id, selection_id):
    """The selection's file ids; refused (404) when it is not found or belongs to another case."""
    directory = _directory()
    if directory is None:
        raise PdfMappingError(GONE, 404)
    path = _path(directory, selection_id)
    try:
        saved = json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        raise PdfMappingError(GONE, 404)
    if saved.get('case_id') != str(case_id):
        raise PdfMappingError(GONE, 404)
    try:
        os.utime(path)
    except OSError:
        pass
    return [UUID(identifier) for identifier in saved['file_ids']]


def _trim(directory):
    now = time.time()
    for path in directory.iterdir():
        try:
            if now - path.stat().st_mtime > (3600 if path.name.endswith('.tmp') else KEPT_SECONDS):
                path.unlink(missing_ok=True)
        except OSError:
            continue
