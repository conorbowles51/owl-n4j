"""
Evidence Router

Handles uploading evidence files and triggering ingestion processing.
"""

import subprocess
import shutil
import hashlib
import uuid
import zipfile
import errno
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel
# Starlette's MultiPartParser emits its own UploadFile instances. fastapi.UploadFile
# is a *subclass* of that, so isinstance(parsed, fastapi.UploadFile) is False —
# we'd silently drop every file. Use the Starlette base class for type checks
# against parser output and let the subclass relationship cover both.
from starlette.datastructures import UploadFile as StarletteUploadFile

from services.evidence_service import evidence_service
from services.evidence_storage import evidence_storage, EVIDENCE_ROOT_DIR
from services.evidence_log_storage import evidence_log_storage
from services.wiretap_tracking import list_processed_wiretaps, is_wiretap_processed, mark_wiretap_processed
from services.wiretap_service import check_wiretap_suitable, process_wiretap_folder_async
from services.cellebrite_service import check_cellebrite_report, process_cellebrite_report
from services.background_task_storage import background_task_storage, TaskStatus
from services.neo4j_service import neo4j_service
from services.case_storage import case_storage
from services.cypher_generator import generate_cypher_from_graph
from .auth import get_current_user
from routers.users import get_current_db_user
from fastapi import Query, status
from postgres.session import get_db
from postgres.models.user import User
from sqlalchemy.orm import Session
from config import BASE_DIR
from datetime import datetime


# Hard limit on file IDs per single processing request.
# Clients must split larger batches into chunks of this size.
MAX_BATCH_SIZE = 50

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


class EvidenceRecord(BaseModel):
    id: str
    case_id: str
    original_filename: str
    stored_path: str
    size: int
    sha256: str
    status: str
    duplicate_of: Optional[str] = None
    created_at: str
    processed_at: Optional[str] = None
    last_error: Optional[str] = None
    summary: Optional[str] = None  # Document summary if available


class EvidenceListResponse(BaseModel):
    files: List[EvidenceRecord]


class UploadResponse(BaseModel):
    """Response for file uploads - can be synchronous or background."""
    files: Optional[List[EvidenceRecord]] = None  # For synchronous uploads
    task_id: Optional[str] = None  # Single task ID (for backwards compatibility)
    task_ids: Optional[List[str]] = None  # Multiple task IDs (for folder uploads)
    message: Optional[str] = None  # Status message


class ProcessRequest(BaseModel):
    case_id: Optional[str] = None
    file_ids: List[str]
    profile: Optional[str] = None  # LLM profile name (e.g., "fraud", "generic")
    max_workers: Optional[int] = None  # Maximum parallel files to process
    image_provider: Optional[str] = None  # "tesseract" (local OCR) or "openai" (GPT-4 Vision)


class ProcessResponse(BaseModel):
    processed: int
    skipped: int
    errors: int
    # Case version info may be present when case_id is provided
    case_id: Optional[str] = None
    case_version: Optional[int] = None
    case_timestamp: Optional[str] = None


class EvidenceLog(BaseModel):
    id: str
    case_id: Optional[str] = None
    evidence_id: Optional[str] = None
    filename: Optional[str] = None
    level: str
    message: str
    timestamp: str
    progress_current: Optional[int] = None
    progress_total: Optional[int] = None


class EvidenceLogListResponse(BaseModel):
    logs: List[EvidenceLog]


_CELLEBRITE_NS_MARKER = b"http://pa.cellebrite.com/report/2.0"

# Pure path-pattern fingerprint for Cellebrite extraction artifacts.
# Used in addition to (not instead of) the directory-prefix filter so we
# also catch cases where a Cellebrite report folder doesn't expose a plain
# `*.xml` at its top level — UFED exports often use suffixed names like
# `Report.xmlExtra`, `Report.xmlTranslation`, `Report.xmlNodeSource` that
# don't match `*.xml` globbing. Pure string match, zero file I/O.
_CELLEBRITE_PATH_SEGMENTS = (
    "/files/Audio/", "/files/Video/", "/files/Image/", "/files/Images/",
    "/files/Document/", "/files/Documents/", "/files/Configuration/",
    "/files/Application/", "/files/Applications/", "/files/Database/",
    "/files/Databases/", "/files/Text/", "/files/Archive/", "/files/Archives/",
    "/thumbnails/", "/useraccounts/", "/databases/", "/decoded/", "/native/",
)
_CELLEBRITE_FILENAME_SUFFIXES = (
    ".xmlextra", ".xmltranslation", ".xmlnodesource", ".xmlmodel",
    ".xmlmodelsource", ".xmltagged", ".xmllast", ".xmlmdfsource",
)


def _looks_like_cellebrite_artifact(stored_path: str) -> bool:
    """
    Heuristic: does this stored_path point inside a Cellebrite UFED tree?
    Path-only check, no filesystem access.
    """
    if not stored_path:
        return False
    sp = stored_path.replace("\\", "/")
    if any(seg in sp for seg in _CELLEBRITE_PATH_SEGMENTS):
        return True
    lower = sp.lower()
    if any(lower.endswith(suf) for suf in _CELLEBRITE_FILENAME_SUFFIXES):
        return True
    return False


def _is_cellebrite_report_root(dir_path: Path) -> bool:
    """
    Cheap check for a Cellebrite UFED report root: any .xml file in this
    directory whose first 4KB contains the Cellebrite namespace.

    Reads at most 4KB per XML, no recursion. Used to prune the sync walk
    so we never touch the thousands of media/database files inside an
    extraction. Those files only get read when the user explicitly
    triggers Cellebrite processing on the folder.
    """
    try:
        for xml_file in dir_path.glob("*.xml"):
            try:
                with xml_file.open("rb") as f:
                    head = f.read(4096)
                if _CELLEBRITE_NS_MARKER in head:
                    return True
            except (OSError, IOError):
                continue
    except (OSError, IOError):
        pass
    return False


# (case_id) -> (case_dir_mtime_ns, list_of_root_prefix_strings)
_CELLEBRITE_ROOTS_CACHE: dict = {}


def _cellebrite_root_prefixes(case_id: str) -> List[str]:
    """
    Return absolute-path prefix strings for every Cellebrite UFED report
    folder directly under the case's evidence root. Used by `list_evidence`
    to filter out the (often hundreds of thousands of) extraction artifact
    rows that pre-date the sync_filesystem prune fix.

    Only top-level directories are checked — Cellebrite reports are always
    uploaded as a single folder, never nested. Cached per (case_id, mtime)
    so repeated calls during a page load are free.
    """
    case_dir = EVIDENCE_ROOT_DIR / case_id
    if not case_dir.exists() or not case_dir.is_dir():
        return []
    try:
        mtime = case_dir.stat().st_mtime_ns
    except OSError:
        mtime = 0
    cached = _CELLEBRITE_ROOTS_CACHE.get(case_id)
    if cached and cached[0] == mtime:
        return cached[1]

    prefixes: List[str] = []
    try:
        for entry in case_dir.iterdir():
            if entry.is_dir() and _is_cellebrite_report_root(entry):
                prefixes.append(str(entry).replace("\\", "/").rstrip("/") + "/")
    except OSError:
        pass

    _CELLEBRITE_ROOTS_CACHE[case_id] = (mtime, prefixes)
    return prefixes


def _register_cellebrite_dir_record(
    case_id: str,
    folder_path: Path,
    folder_name: str,
    owner: Optional[str],
    det: dict,
) -> Optional[str]:
    """Register a single directory-level evidence record for a Cellebrite report
    root if one does not already exist. Idempotent — skips if stored_path matches.
    Returns the evidence ID if created (or already present), None on failure.
    """
    folder_str = str(folder_path).replace("\\", "/").rstrip("/")
    for rec in evidence_storage.list_files(case_id=case_id):
        if rec.get("is_cellebrite_folder") and str(rec.get("stored_path", "")).replace("\\", "/").rstrip("/") == folder_str:
            return rec.get("id")

    sentinel_sha256 = hashlib.sha256(
        f"cellebrite-dir:{case_id}:{folder_name}".encode()
    ).hexdigest()

    created = evidence_storage.add_files(
        case_id=case_id,
        files=[{
            "original_filename": folder_name,
            "stored_path": folder_path,
            "sha256": sentinel_sha256,
            "size": 0,
        }],
        owner=owner,
    )
    if created:
        evidence_id = created[0]["id"]
        evidence_storage.update_record(
            evidence_id,
            is_cellebrite_folder=True,
            cellebrite_report_name=det.get("report_name") or folder_name,
            cellebrite_device_model=det.get("device_model"),
            cellebrite_phone_numbers=det.get("phone_numbers") or [],
        )
        return evidence_id
    return None


@router.get("", response_model=EvidenceListResponse)
def list_evidence(
    case_id: Optional[str] = None,
    status: Optional[str] = None,
    include_cellebrite_artifacts: bool = False,
    user: dict = Depends(get_current_user),
):
    """
    List evidence files.

    Args:
        case_id: Optional case ID to filter by.
        status: Optional status filter
            ('unprocessed', 'processing', 'processed', 'duplicate', 'failed').
        include_cellebrite_artifacts: If False (default), files that live
            inside a Cellebrite UFED report subtree are filtered out. Those
            files are not user-meaningful evidence rows — they are extraction
            artifacts processed via /evidence/cellebrite/process. Including
            them shipped 100K+ rows / ~100 MB JSON for a single case and
            hung the Process Evidence page on slow links.

    Document summaries are intentionally NOT inlined here — for cases with
    thousands of processed files the Neo4j batch fetch made this endpoint
    slow enough to hang the Process Evidence page. Fetch summaries on demand
    via GET /api/evidence/summary/{filename}.
    """
    try:
        files = evidence_service.list_files(
            case_id=case_id,
            status=status,
        )
        if not include_cellebrite_artifacts and case_id:
            prefixes = _cellebrite_root_prefixes(case_id)
            if prefixes:
                # Path-fingerprint filter is only applied when at least one
                # Cellebrite report root was detected for this case — that
                # way non-Cellebrite cases never risk a false positive on
                # an unrelated `files/Video/` or `thumbnails/` subfolder.
                def _is_artifact(rec: dict) -> bool:
                    sp = (rec.get("stored_path") or "").replace("\\", "/")
                    if any(sp.startswith(p) for p in prefixes):
                        return True
                    return _looks_like_cellebrite_artifact(sp)
                files = [r for r in files if not _is_artifact(r)]

        # Project to a slim shape — `summary` (~2 KB per processed row) is
        # fetched on demand via /evidence/summary/{filename} when the user
        # opens a row. Shallow copy so we don't mutate the in-memory store.
        files = [{k: v for k, v in rec.items() if k != "summary"} for rec in files]

        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _sync_filesystem_blocking(case_id: str, owner_email: str) -> dict:
    """
    Walk the case directory and register any files that don't have an
    evidence record yet. Runs synchronously — call via run_in_threadpool
    from request handlers so it doesn't block the event loop.

    Two safeguards against the "Cellebrite extraction has 50,000 files"
    pathology that previously hung the Process Evidence page:
      1. Cellebrite report subtrees are detected via XML signature on
         entry and skipped wholesale. Their files are processed via the
         dedicated Cellebrite endpoint, not as individual evidence rows.
      2. For files that *do* need registering, sha256 is streamed in
         1 MiB chunks rather than `read_bytes()`, so a multi-GB file
         never sits in RAM.

    The common case — no new files — does zero file I/O beyond os.stat.
    """
    import os
    import logging

    logger = logging.getLogger(__name__)

    case_dir = EVIDENCE_ROOT_DIR / case_id
    if not case_dir.exists() or not case_dir.is_dir():
        return {"created": 0, "message": "Case directory does not exist"}

    existing_records = evidence_storage.list_files(case_id=case_id)

    known_paths = set()
    for rec in existing_records:
        sp = rec.get("stored_path", "")
        if sp:
            known_paths.add(sp.replace('\\', '/'))
            try:
                known_paths.add(str(Path(sp).resolve()).replace('\\', '/'))
            except Exception:
                pass

    new_file_paths: list[Path] = []
    skipped_cellebrite_dirs: list[str] = []

    for dirpath, dirnames, filenames in os.walk(case_dir):
        current_dir = Path(dirpath)

        # If this directory is a Cellebrite report root, register a single
        # folder-level evidence record (so it appears in the evidence tab
        # as "ready for processing"), then prune the entire subtree so we
        # never touch the thousands of extraction artifact files inside.
        if _is_cellebrite_report_root(current_dir):
            skipped_cellebrite_dirs.append(str(current_dir.relative_to(case_dir)) or ".")
            # Parse the report header so the folder record carries the phone
            # number / device model for the evidence tab (header-only parse,
            # one per report root). case_id omitted to skip the Neo4j probe.
            det = check_cellebrite_report(current_dir)
            _register_cellebrite_dir_record(
                case_id, current_dir, current_dir.name, owner_email, det
            )
            dirnames[:] = []
            continue

        # Skip dot-directories in-place so os.walk doesn't descend.
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]

        for filename in filenames:
            if filename.startswith('.'):
                continue
            file_path = current_dir / filename

            abs_path_str = str(file_path).replace('\\', '/')
            try:
                resolved_str = str(file_path.resolve()).replace('\\', '/')
            except Exception:
                resolved_str = abs_path_str

            if abs_path_str in known_paths or resolved_str in known_paths:
                continue

            relative_path = str(file_path.relative_to(case_dir)).replace('\\', '/')
            if any(p.endswith(relative_path) for p in known_paths):
                continue

            new_file_paths.append(file_path)

    if skipped_cellebrite_dirs:
        logger.info(
            f"Filesystem sync: skipped {len(skipped_cellebrite_dirs)} Cellebrite "
            f"report folder(s) for case {case_id}: {skipped_cellebrite_dirs[:5]}"
        )

    file_infos = []
    for file_path in new_file_paths:
        try:
            size = file_path.stat().st_size
            h = hashlib.sha256()
            with file_path.open("rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            sha = h.hexdigest()
        except (OSError, PermissionError) as e:
            logger.warning(f"Cannot read file {file_path}: {e}")
            continue

        file_infos.append({
            "original_filename": file_path.name,
            "stored_path": file_path,
            "sha256": sha,
            "size": size,
        })

    created_count = 0
    if file_infos:
        new_records = evidence_storage.add_files(
            case_id=case_id,
            files=file_infos,
            owner=owner_email,
        )
        created_count = len(new_records)
        logger.info(f"Filesystem sync: created {created_count} evidence records for case {case_id}")

    return {"created": created_count, "message": f"Synced {created_count} file(s)"}


@router.post("/sync-filesystem")
async def sync_filesystem(
    case_id: str = Query(..., description="Case ID to sync"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Sync the filesystem with evidence records.

    Scans the case's data directory for files that don't have corresponding
    evidence records and creates 'unprocessed' records for them.
    This handles cases where files exist on disk but weren't properly registered.
    """
    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(case_id), current_user, required_permission=("evidence", "upload"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        # Offload the directory walk + hashing to a worker thread so the
        # ASGI event loop stays free to serve other requests (e.g. /evidence)
        # while a big Cellebrite case is being scanned.
        return await run_in_threadpool(_sync_filesystem_blocking, case_id, current_user.email)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/duplicates/{sha256}", response_model=EvidenceListResponse)
def find_duplicates(
    sha256: str,
    user: dict = Depends(get_current_user),
):
    """
    Find all files with the same SHA256 hash (duplicates).
    """
    try:
        files = evidence_service.find_duplicates(sha256)
        # Filter by owner to only show user's files
        files = [f for f in files if f.get("owner") == user["username"]]
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Where uploaded bytes land while still being streamed off the wire. Lives on
# the same filesystem as EVIDENCE_ROOT_DIR so a successful upload can be moved
# into place atomically via os.replace.
_UPLOAD_STAGING_ROOT = EVIDENCE_ROOT_DIR / "_staging"

# 1 MiB read chunks — large enough to amortize syscall overhead, small enough
# to stay out of RAM on multi-GB uploads.
_STAGE_CHUNK_SIZE = 1024 * 1024

# Mac/Windows metadata noise that frequently rides along inside Cellebrite
# Reader exports. Skipping them keeps the case dir clean and saves the
# ingestion pipeline from choking on Apple resource forks.
_ARCHIVE_SKIP_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}


def _extract_archive_to_staging(zip_path: Path, extract_dir: Path) -> List[dict]:
    """
    Extract a zip into `extract_dir` with zip-slip protection and return
    upload dicts shaped exactly like `_stage_upload_files` so the rest of
    the pipeline can treat the result as a folder upload.

    Streams each entry through SHA-256 + sized write at _STAGE_CHUNK_SIZE so
    we never hold an entire entry in memory — Cellebrite archives can be
    multi-GB once unpacked.
    """
    extract_dir.mkdir(parents=True, exist_ok=True)
    extract_root = extract_dir.resolve()
    uploads: List[dict] = []

    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            entry_name = info.filename or ""
            normalized = entry_name.replace("\\", "/").lstrip("/")
            if not normalized:
                continue
            parts = normalized.split("/")
            # __MACOSX/* and AppleDouble (._foo) sidecars carry no content.
            if any(part == "__MACOSX" or part.startswith("._") for part in parts):
                continue
            leaf = parts[-1]
            if leaf in _ARCHIVE_SKIP_NAMES:
                continue
            # Zip-slip: refuse anything that resolves outside the extract root.
            target = (extract_dir / normalized).resolve()
            try:
                target.relative_to(extract_root)
            except ValueError:
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            hasher = hashlib.sha256()
            size = 0
            try:
                with zf.open(info) as src, open(target, "wb") as dst:
                    while True:
                        chunk = src.read(_STAGE_CHUNK_SIZE)
                        if not chunk:
                            break
                        hasher.update(chunk)
                        dst.write(chunk)
                        size += len(chunk)
            except Exception:
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    pass
                raise

            uploads.append(
                {
                    "original_filename": leaf,
                    "staged_path": target,
                    "sha256": hasher.hexdigest(),
                    "size": size,
                    "relative_path": normalized,
                }
            )

    return uploads


def _stage_upload_files(files: List[UploadFile], staging_dir: Path) -> List[dict]:
    """
    Stream each UploadFile into a unique file under `staging_dir`, computing
    SHA-256 + size on the fly. Returns a list of upload dicts shaped for
    evidence_service (no in-memory bytes).

    Runs synchronously — call it from a thread pool so the async event loop
    is not blocked.
    """
    staging_dir.mkdir(parents=True, exist_ok=True)
    staged: List[dict] = []

    for uf in files:
        filename = uf.filename or ""

        # Frontend appends `formData.append('files', file, relativePath)` so
        # uf.filename carries the path for folder uploads. Split it.
        if "/" in filename or "\\" in filename:
            relative_path = filename.replace("\\", "/")
            original_filename = relative_path.rsplit("/", 1)[-1]
        else:
            relative_path = None
            original_filename = filename

        staged_path = staging_dir / f"{uuid.uuid4().hex}.upload"
        hasher = hashlib.sha256()
        size = 0

        # uf.file is a SpooledTemporaryFile — synchronous read is fine here
        # since we're already in a thread pool.
        src = uf.file
        try:
            src.seek(0)
        except (AttributeError, OSError):
            pass

        try:
            with open(staged_path, "wb") as dst:
                while True:
                    chunk = src.read(_STAGE_CHUNK_SIZE)
                    if not chunk:
                        break
                    hasher.update(chunk)
                    dst.write(chunk)
                    size += len(chunk)
        except Exception:
            # Best-effort cleanup of partial staged file before re-raising.
            try:
                staged_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

        staged.append(
            {
                "original_filename": original_filename,
                "staged_path": staged_path,
                "sha256": hasher.hexdigest(),
                "size": size,
                "relative_path": relative_path,
            }
        )

    return staged


@router.post("/upload", response_model=UploadResponse)
async def upload_evidence(
    request: Request,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Upload one or more evidence files for a case.

    Files are streamed straight to a staging area on disk (no in-memory
    buffering of the full payload), then either registered synchronously
    or handed off to a background task that moves them into the case data
    directory.

    If is_folder is 'true' or more than 5 files are uploaded, creates background tasks.

    Parsed via request.form() with raised limits — Starlette's defaults
    (1000 files / 1000 fields) cut off folder uploads with thousands of
    files mid-stream, which the browser surfaces as ERR_FAILED.

    When `is_archive=true` the client sends a single .zip; the route stages
    that one part, unpacks it server-side, and feeds the extracted tree
    through the existing folder-ingestion path. This avoids the multi-
    thousand multipart parts that overwhelm dev-server proxies.
    """
    # request.form() streams each multipart part to a SpooledTemporaryFile that
    # rolls over to disk under TMPDIR. If that staging filesystem fills (or the
    # box is out of memory), the spool raises here — outside the try/except
    # below — and the client gets an opaque "Internal Server Error" with no
    # response body. Catch it and return an actionable message instead.
    try:
        form = await request.form(max_files=20000, max_fields=20000)
    except OSError as e:
        if getattr(e, "errno", None) == errno.ENOSPC:
            raise HTTPException(
                status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
                detail=(
                    "Server ran out of disk space while staging the upload. "
                    "Free space on the server and retry."
                ),
            )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read the upload from the connection: {e}",
        )
    except MemoryError:
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail="Server ran out of memory while staging the upload. Retry shortly.",
        )
    case_id = form.get("case_id")
    is_folder = form.get("is_folder")
    is_archive = form.get("is_archive")
    files = [v for v in form.getlist("files") if isinstance(v, StarletteUploadFile)]

    if not case_id:
        raise HTTPException(status_code=400, detail="case_id is required")
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    is_archive_upload = bool(is_archive) and is_archive.lower() == "true"
    if is_archive_upload and len(files) != 1:
        raise HTTPException(
            status_code=400,
            detail="Archive upload expects exactly one .zip file.",
        )

    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(case_id), current_user, required_permission=("evidence", "upload"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        is_folder_upload = (is_folder and is_folder.lower() == 'true') or is_archive_upload

        # Stage every upload to disk first. This is the slow, network-bound
        # part of the request and runs in a worker thread so it doesn't block
        # the event loop.
        staging_dir = _UPLOAD_STAGING_ROOT / uuid.uuid4().hex
        try:
            uploads = await run_in_threadpool(_stage_upload_files, files, staging_dir)

            if is_archive_upload:
                # Replace the staged zip with its extracted file tree. The
                # tree mirrors what a webkitdirectory folder upload would
                # have produced, so the rest of the pipeline is unchanged.
                zip_entry = uploads[0]
                zip_path = Path(zip_entry["staged_path"])
                if not zipfile.is_zipfile(zip_path):
                    raise HTTPException(
                        status_code=400,
                        detail="Uploaded archive is not a valid .zip file.",
                    )
                extract_dir = staging_dir / "_extracted"
                try:
                    uploads = await run_in_threadpool(
                        _extract_archive_to_staging, zip_path, extract_dir
                    )
                finally:
                    # The original archive is no longer needed regardless
                    # of extraction outcome — remove it to free disk.
                    try:
                        zip_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                if not uploads:
                    raise HTTPException(
                        status_code=400,
                        detail="Archive contained no extractable files.",
                    )

                # Detect top-level Cellebrite report folders in the extracted
                # tree and register a folder-level evidence record for each.
                # This makes the extraction visible in the evidence tab as
                # "ready for Cellebrite processing" even while the background
                # task is still moving individual files into place.
                top_folders: dict = {}
                for u in uploads:
                    rp = (u.get("relative_path") or "").replace("\\", "/")
                    if "/" in rp:
                        top_folders.setdefault(rp.split("/")[0], True)
                for fn in top_folders:
                    staged_folder = extract_dir / fn
                    if staged_folder.is_dir() and _is_cellebrite_report_root(staged_folder):
                        final_path = EVIDENCE_ROOT_DIR / case_id / fn
                        # Parse the report header off the staged tree (files are
                        # still there pre-move) so the folder record carries the
                        # phone number / device model. Without this the evidence
                        # tab would always claim "no phone number detected" and
                        # demand a manual identifier even for reports that have
                        # one. case_id omitted to skip the Neo4j duplicate probe.
                        det = check_cellebrite_report(staged_folder)
                        _register_cellebrite_dir_record(
                            case_id, final_path, fn, current_user.email, det
                        )

        except Exception:
            # Stage or extract failed — remove anything we managed to write.
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise

        # Use len(uploads) so an archive that unpacks into thousands of
        # files always lands on the background path (the synchronous path
        # blocks the request and offers no progress).
        use_background = is_folder_upload or len(uploads) > 5

        try:
            if use_background:
                if is_folder_upload:
                    task_ids = evidence_service.upload_folders_background(
                        case_id=case_id,
                        files=uploads,
                        owner=current_user.email,
                    )
                    response = UploadResponse(
                        task_id=task_ids[0] if task_ids else None,
                        task_ids=task_ids,
                        message=f"Uploading {len(task_ids)} folder(s) in background" if task_ids else "No folders to upload",
                    )
                else:
                    task_id = evidence_service.upload_files_background(
                        case_id=case_id,
                        files=uploads,
                        owner=current_user.email,
                    )
                    response = UploadResponse(
                        task_id=task_id,
                        message=f"Uploading {len(uploads)} file(s) in background",
                    )
            else:
                # Synchronous path for small file sets — same staged uploads.
                records = evidence_service.add_uploaded_files(
                    case_id=case_id,
                    uploads=uploads,
                    owner=current_user.email,
                )
                response = UploadResponse(files=records)
        finally:
            # Either the files were moved into the case dir (success) or the
            # background thread will move them shortly. The staging dir
            # itself is now empty (or will be) — clean it up best-effort.
            # ignore_errors=True so a still-pending bg task doesn't make us crash.
            try:
                if staging_dir.exists() and not any(staging_dir.iterdir()):
                    staging_dir.rmdir()
            except OSError:
                pass

        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process/background")
def process_evidence_background(
    request: ProcessRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Process selected evidence files in the background.

    Returns immediately with a task ID. Use the background-tasks API
    to monitor progress.
    """
    if not request.file_ids:
        raise HTTPException(status_code=400, detail="No file_ids provided")

    if len(request.file_ids) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files ({len(request.file_ids)}). Maximum {MAX_BATCH_SIZE} files per request. Please batch your requests.",
        )

    try:
        if request.case_id:
            from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
            from uuid import UUID
            try:
                check_case_access(db, UUID(request.case_id), current_user, required_permission=("evidence", "upload"))
            except (CaseNotFound, CaseAccessDenied) as e:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        task_id = evidence_service.process_files_background(
            evidence_ids=request.file_ids,
            case_id=request.case_id,
            owner=current_user.email,
            profile=request.profile,
            max_workers=request.max_workers,
            image_provider=request.image_provider,
        )
        return {"task_id": task_id, "message": "Processing started in background"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process", response_model=ProcessResponse)
async def process_evidence(
    request: ProcessRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Process selected evidence files synchronously.

    Deduplicates by file hash so identical files are only ingested once.
    For multiple files, consider using /process/background instead.
    """
    if not request.file_ids:
        raise HTTPException(status_code=400, detail="No file_ids provided")

    try:
        if request.case_id:
            from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
            from uuid import UUID
            try:
                check_case_access(db, UUID(request.case_id), current_user, required_permission=("evidence", "upload"))
            except (CaseNotFound, CaseAccessDenied) as e:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        # Run the potentially long-running ingestion work in a threadpool
        # so that other requests (like /evidence/logs) can still be served
        # while processing is ongoing.
        summary = await run_in_threadpool(
            evidence_service.process_files,
            request.file_ids,
            request.case_id,
            current_user.email,
            request.profile,
        )
        return ProcessResponse(**summary)
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ingestion pipeline not available: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class MediaAnalyzeRequest(BaseModel):
    # "transcription" (audio/video) | "image" (image recognition). Auto-detected
    # from the file's category when omitted.
    kind: Optional[str] = None
    provider: Optional[str] = None       # image: "openai" (default) | "tesseract"
    language: Optional[str] = None       # transcription language hint (e.g. "es", "en")
    task: Optional[str] = "transcribe"   # "transcribe" | "translate" (→ English)
    force: bool = False                  # re-run even if a cached result exists


def _detect_media_kind(rec: dict) -> Optional[str]:
    """image | transcription | None — from the Cellebrite category, else the
    filename extension."""
    cat = (rec.get("cellebrite_category") or "").lower()
    if cat == "image":
        return "image"
    if cat in ("audio", "video"):
        return "transcription"
    name = (rec.get("original_filename") or rec.get("stored_path") or "").lower()
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    if ext in {"jpg", "jpeg", "png", "gif", "bmp", "webp", "heic", "heif", "tif", "tiff"}:
        return "image"
    if ext in {"mp3", "wav", "m4a", "aac", "ogg", "opus", "amr", "flac", "3gp", "mp4", "mov", "m4v", "mkv", "webm"}:
        return "transcription"
    return None


@router.post("/{evidence_id}/media-analyze")
async def media_analyze_evidence(
    evidence_id: str,
    request: MediaAnalyzeRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """On-demand AI media analysis of a single evidence file: transcription
    (audio/video, local Whisper) or image recognition (OpenAI vision, Tesseract
    fallback). Results are cached on the evidence record so re-opening is
    instant. Used by the file viewer and Cellebrite message-attachment actions.
    """
    rec = evidence_storage.get(evidence_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Evidence not found")

    if rec.get("case_id"):
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(rec["case_id"]), current_user, required_permission=("evidence", "upload"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    kind = (request.kind or _detect_media_kind(rec) or "").lower()
    if kind not in ("image", "transcription"):
        raise HTTPException(
            status_code=400,
            detail="Cannot determine media kind — pass kind='image' or 'transcription'.",
        )

    cache_key = "image_analysis" if kind == "image" else "transcription"
    if not request.force:
        cached = (rec.get("media_analysis") or {}).get(cache_key)
        if cached:
            return {"cached": True, "kind": kind, "result": cached}

    try:
        if kind == "image":
            result = await run_in_threadpool(
                evidence_service.analyze_image_evidence, evidence_id, request.provider or "openai"
            )
        else:
            result = await run_in_threadpool(
                evidence_service.transcribe_evidence, evidence_id, request.language, request.task or "transcribe"
            )
        return {"cached": False, "kind": kind, "result": result}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (RuntimeError, ImportError) as e:
        # Tool unavailable (e.g. Whisper/ffmpeg not installed, vision key unset)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{evidence_id}/analysis")
def get_evidence_analysis(
    evidence_id: str,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Return any cached AI media-analysis results for a file (so the UI can
    show a transcription / image description it computed earlier)."""
    rec = evidence_storage.get(evidence_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    if rec.get("case_id"):
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(rec["case_id"]), current_user, required_permission=("case", "view"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    return {
        "evidence_id": evidence_id,
        "kind_available": list((rec.get("media_analysis") or {}).keys()),
        "media_analysis": rec.get("media_analysis") or {},
    }


@router.get("/logs", response_model=EvidenceLogListResponse)
def get_evidence_logs(
    case_id: Optional[str] = None,
    limit: int = 200,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Get recent evidence ingestion logs, optionally filtered by case_id.
    """
    try:
        if case_id:
            from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
            from uuid import UUID
            try:
                check_case_access(db, UUID(case_id), current_user, required_permission=("case", "view"))
            except (CaseNotFound, CaseAccessDenied) as e:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        logs = evidence_log_storage.list_logs(case_id=case_id, limit=limit)
        return {"logs": logs}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wiretap/check")
def check_wiretap_folder(
    case_id: str = Query(..., description="Case ID"),
    folder_path: str = Query(..., description="Relative folder path from case data directory"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Check if a folder is suitable for wiretap processing.
    """
    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(case_id), current_user, required_permission=("case", "view"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        # Build full path to folder
        case_data_dir = BASE_DIR / "ingestion" / "data" / case_id
        full_folder_path = case_data_dir / folder_path
        
        # Security check: ensure path is within case directory
        try:
            full_folder_path.resolve().relative_to(case_data_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Path outside case directory")
        
        # Check suitability
        result = check_wiretap_suitable(full_folder_path)
        
        # Check if folder has been processed as wiretap
        result["processed"] = is_wiretap_processed(case_id, folder_path)
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class WiretapProcessRequest(BaseModel):
    """Request to process wiretap folders."""
    case_id: str
    folder_paths: List[str]  # List of folder paths relative to case data directory
    whisper_model: str = "base"  # Whisper model size


class WiretapProcessResponse(BaseModel):
    """Response from wiretap processing."""
    success: bool
    message: str
    task_id: Optional[str] = None  # First task ID for backwards compatibility


@router.post("/wiretap/process", response_model=WiretapProcessResponse)
async def process_wiretap_folders(
    request: WiretapProcessRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Process one or more wiretap folders.

    Creates a separate background task for each folder. Each folder is processed independently.
    """
    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(request.case_id), current_user, required_permission=("evidence", "upload"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        case_data_dir = BASE_DIR / "ingestion" / "data" / request.case_id

        # Do minimal validation (just path format check) - full validation happens in background
        # This allows the endpoint to return quickly
        validated_paths = []
        for folder_path in request.folder_paths:
            # Basic path sanitization check
            if not folder_path or not isinstance(folder_path, str):
                raise HTTPException(status_code=400, detail=f"Invalid folder path: {folder_path}")
            # Check for path traversal attempts
            if ".." in folder_path or folder_path.startswith("/"):
                raise HTTPException(status_code=403, detail=f"Path outside case directory: {folder_path}")
            validated_paths.append(folder_path)

        # Always use background processing for wiretap folders
        # Create a separate background task for each folder
        task_ids = []

        # Capture email outside the closure for use in background tasks
        user_email = current_user.email

        for folder_path in validated_paths:
            # Create a background task for this folder
            task = background_task_storage.create_task(
                task_type="wiretap_processing",
                task_name=f"Process wiretap folder: {folder_path.split('/')[-1] or folder_path}",
                case_id=request.case_id,
                owner=user_email,
                metadata={
                    "folder_path": folder_path,  # Single folder path for this task
                    "whisper_model": request.whisper_model,
                }
            )
            task_id = task["id"]
            task_ids.append(task_id)
            
            def create_background_task(fp, tid):
                """Create a background task function with proper closure."""
                async def process_single_wiretap_folder_background():
                    """Background task function to process a single wiretap folder."""
                    from services.evidence_log_storage import evidence_log_storage
                    
                    # Full validation happens here in the background
                    full_path = case_data_dir / fp
                    try:
                        # Resolve and check it's within case directory
                        resolved = full_path.resolve()
                        case_resolved = case_data_dir.resolve()
                        resolved.relative_to(case_resolved)
                    except (ValueError, OSError) as e:
                        evidence_log_storage.add_log(
                            case_id=request.case_id,
                            evidence_id=None,
                            filename=None,
                            level="error",
                            message=f"Invalid folder path: {fp} - {str(e)}"
                        )
                        background_task_storage.update_task(
                            tid,
                            status=TaskStatus.FAILED.value,
                            error=f"Invalid path: {str(e)}",
                            completed_at=datetime.now().isoformat()
                        )
                        return
                    
                    if not full_path.exists():
                        evidence_log_storage.add_log(
                            case_id=request.case_id,
                            evidence_id=None,
                            filename=None,
                            level="error",
                            message=f"Folder not found: {fp}"
                        )
                        background_task_storage.update_task(
                            tid,
                            status=TaskStatus.FAILED.value,
                            error="Folder not found",
                            completed_at=datetime.now().isoformat()
                        )
                        return
                    
                    if not full_path.is_dir():
                        evidence_log_storage.add_log(
                            case_id=request.case_id,
                            evidence_id=None,
                            filename=None,
                            level="error",
                            message=f"Path is not a directory: {fp}"
                        )
                        background_task_storage.update_task(
                            tid,
                            status=TaskStatus.FAILED.value,
                            error="Not a directory",
                            completed_at=datetime.now().isoformat()
                        )
                        return
                    
                    # Update task status to running
                    background_task_storage.update_task(
                        tid,
                        status=TaskStatus.RUNNING.value,
                        started_at=datetime.now().isoformat(),
                        progress_total=1
                    )
                    
                    try:
                        def log_callback(message: str):
                            evidence_log_storage.add_log(
                                case_id=request.case_id,
                                evidence_id=None,
                                filename=None,
                                level="info",
                                message=f"[{full_path.name}] {message}"
                            )
                        
                        # Use async version to avoid blocking the event loop
                        result = await process_wiretap_folder_async(
                            full_path,
                            request.case_id,
                            request.whisper_model,
                            log_callback
                        )
                        
                        if result["success"]:
                            # Mark folder as processed
                            mark_wiretap_processed(
                                request.case_id,
                                fp
                            )
                            
                            background_task_storage.update_task(
                                tid,
                                progress_completed=1,
                                status=TaskStatus.COMPLETED.value,
                                completed_at=datetime.now().isoformat()
                            )
                            
                            # Save case version after successful processing
                            try:
                                # Look up case name (fallback to case_id if not found)
                                case = case_storage.get_case(request.case_id)
                                case_name = case["name"] if case and case.get("name") else request.case_id
                                
                                # Save as a new version on this case
                                # Note: Cypher queries are no longer stored - graph data persists in Neo4j
                                case_result = case_storage.save_case_version(
                                    case_id=request.case_id,
                                    case_name=case_name,
                                    snapshots=[],
                                    save_notes=f"Auto-save after processing wiretap folder: {fp}",
                                    owner=user_email,
                                )
                                
                                evidence_log_storage.add_log(
                                    case_id=request.case_id,
                                    evidence_id=None,
                                    filename=None,
                                    level="info",
                                    message=(
                                        "Saved new case version after wiretap processing: "
                                        f"case_id={case_result.get('case_id')}, "
                                        f"version={case_result.get('version')}."
                                    ),
                                )
                            except Exception as e:
                                # Do not fail wiretap processing if case saving fails; just log
                                print(f"Warning: failed to attach graph Cypher to case {request.case_id}: {e}")
                                evidence_log_storage.add_log(
                                    case_id=request.case_id,
                                    evidence_id=None,
                                    filename=None,
                                    level="error",
                                    message=f"Failed to save case version after wiretap processing: {e}",
                                )
                        else:
                            # Include output in error message for debugging
                            error_msg = result.get("error", "Unknown error")
                            output = result.get("output", "")
                            if output:
                                # Append last few lines of output to error for context
                                output_lines = output.split('\n')
                                last_lines = '\n'.join(output_lines[-10:])  # Last 10 lines
                                error_msg = f"{error_msg}\n\nScript output:\n{last_lines}"
                            
                            # Log the full error to evidence logs
                            evidence_log_storage.add_log(
                                case_id=request.case_id,
                                evidence_id=None,
                                filename=None,
                                level="error",
                                message=f"Wiretap processing failed: {error_msg}"
                            )
                            
                            background_task_storage.update_task(
                                tid,
                                status=TaskStatus.FAILED.value,
                                error=error_msg,
                                completed_at=datetime.now().isoformat()
                            )
                    except Exception as e:
                        background_task_storage.update_task(
                            tid,
                            status=TaskStatus.FAILED.value,
                            error=str(e),
                            completed_at=datetime.now().isoformat()
                        )
                
                return process_single_wiretap_folder_background
            
            # Schedule the background task for this folder with proper closure
            background_tasks.add_task(create_background_task(folder_path, task_id))
        
        # Return first task ID for backwards compatibility
        return WiretapProcessResponse(
            success=True,
            message=f"Processing {len(validated_paths)} wiretap folder(s) in background ({len(task_ids)} task(s) created)",
            task_id=task_ids[0] if task_ids else None
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Cellebrite UFED Report endpoints
# ------------------------------------------------------------------


@router.get("/cellebrite/check")
def check_cellebrite_folder(
    case_id: str = Query(..., description="Case ID"),
    folder_path: str = Query(..., description="Relative folder path from case data directory"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Check if a folder contains a Cellebrite UFED phone extraction report.
    Returns report metadata if detected.
    """
    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(case_id), current_user, required_permission=("case", "view"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        case_data_dir = BASE_DIR / "ingestion" / "data" / case_id
        full_folder_path = case_data_dir / folder_path

        # Security: ensure path is within case directory
        try:
            full_folder_path.resolve().relative_to(case_data_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Path outside case directory")

        result = check_cellebrite_report(full_folder_path, case_id=case_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CellebriteProcessRequest(BaseModel):
    """Request to process a Cellebrite report folder."""
    case_id: str
    folder_path: str  # Folder path relative to case data directory
    # When True, replace any existing PhoneReport in this case that
    # would collide (same key / IMEI / evidence_number). The frontend
    # sets this only after the user confirms in a duplicate dialog.
    force: bool = False
    # Investigator-supplied device-owner identity. Required when the
    # report carries no extractable phone number (the check endpoint
    # returns empty phone_numbers and the UI prompts for one); optional
    # otherwise, where it's added as an extra owner alias. See the
    # cellebrite-phone-number-required rule.
    device_identifier: Optional[str] = None


class CellebriteProcessResponse(BaseModel):
    """Response from Cellebrite processing."""
    success: bool
    message: str
    task_id: Optional[str] = None


@router.post("/cellebrite/process", response_model=CellebriteProcessResponse)
def process_cellebrite_folder(
    request: CellebriteProcessRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Process a Cellebrite UFED report folder.
    Creates a background task for the ingestion pipeline.
    """
    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(request.case_id), current_user, required_permission=("evidence", "upload"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        case_data_dir = BASE_DIR / "ingestion" / "data" / request.case_id
        full_folder_path = case_data_dir / request.folder_path

        # Security: path traversal check
        try:
            full_folder_path.resolve().relative_to(case_data_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Path outside case directory")

        if not full_folder_path.exists() or not full_folder_path.is_dir():
            raise HTTPException(status_code=404, detail="Folder not found")

        # Quick pre-check that it looks like a Cellebrite report,
        # scoped to this case so we can detect duplicates up-front.
        detection = check_cellebrite_report(full_folder_path, case_id=request.case_id)
        if not detection.get("suitable"):
            raise HTTPException(
                status_code=400,
                detail=detection.get("message", "Not a valid Cellebrite report"),
            )

        # Precondition: a device with no extractable phone number needs an
        # investigator-supplied identifier, else the PhoneReport has no
        # owning identity (see cellebrite-phone-number-required). The check
        # endpoint already surfaces phone_numbers so the UI can prompt;
        # this 422 is the server-side guard for direct/forced callers.
        detected_numbers = detection.get("phone_numbers") or []
        supplied_identifier = (request.device_identifier or "").strip()
        if not detected_numbers and not supplied_identifier:
            raise HTTPException(
                status_code=422,
                detail={
                    "reason": "missing_device_identifier",
                    "message": (
                        "This device has no phone number in the Cellebrite "
                        "report. Supply a device identifier to attribute its "
                        "data (conversations, calls, etc.)."
                    ),
                    "device_model": detection.get("device_model"),
                    "report_name": detection.get("report_name"),
                },
            )

        # Block duplicate ingests unless the user explicitly opts in
        # via `force`. Returns 409 with the existing-report payload so
        # the frontend can show a clear "replace existing?" dialog.
        if detection.get("duplicate") and not request.force:
            raise HTTPException(
                status_code=409,
                detail={
                    "reason": "duplicate_phone_report",
                    "message": detection.get("message"),
                    "existing": detection.get("existing"),
                    "incoming": {
                        "report_key": detection.get("report_key"),
                        "device_model": detection.get("device_model"),
                        "case_number": detection.get("case_number"),
                        "evidence_number": detection.get("evidence_number"),
                        "imei": detection.get("imei"),
                    },
                },
            )

        # Advisory lock: refuse if a sibling cellebrite_ingestion task is
        # already in-flight for the same (case_id, report_key). Catches the
        # race where two POSTs (e.g. user double-click, browser retry on a
        # stalled response, dialog re-confirmed) both pass the duplicate
        # check because the first task hasn't written its PhoneReport node
        # yet. `force=true` does NOT override this — running force-replace
        # against an actively-writing task corrupts the partial state.
        # Without this, case 43f1afb1's C5 ingested twice on 2026-05-23
        # (04:11:08 → 409, 04:11:13 → 200 OK) leaving evidence.json with
        # 188k duplicate rows from two parallel writers.
        incoming_report_key = detection.get("report_key")
        if incoming_report_key:
            for status_filter in ("pending", "running"):
                inflight = background_task_storage.list_tasks(
                    case_id=request.case_id,
                    status=status_filter,
                    limit=100,
                )
                for t in inflight:
                    if t.get("task_type") != "cellebrite_ingestion":
                        continue
                    md = t.get("metadata") or {}
                    sibling_key = (
                        f"cellebrite-{md.get('case_number') or 'unknown'}"
                        f"-{md.get('evidence_number') or 'unknown'}"
                    )
                    if sibling_key == incoming_report_key:
                        raise HTTPException(
                            status_code=409,
                            detail={
                                "reason": "ingestion_in_progress",
                                "message": (
                                    f"A Cellebrite ingestion for this report is already "
                                    f"{status_filter} (task {t['id'][:8]}). Wait for it "
                                    f"to finish before re-ingesting."
                                ),
                                "existing_task_id": t.get("id"),
                                "existing_status": status_filter,
                            },
                        )

        # Create background task
        task = background_task_storage.create_task(
            task_type="cellebrite_ingestion",
            task_name=f"Cellebrite report: {detection.get('report_name', request.folder_path)}",
            case_id=request.case_id,
            owner=current_user.email,
            metadata={
                "folder_path": request.folder_path,
                "report_name": detection.get("report_name"),
                "case_number": detection.get("case_number"),
                "evidence_number": detection.get("evidence_number"),
                "model_count": detection.get("model_count"),
            },
        )
        task_id = task["id"]
        user_email = current_user.email

        force_flag = request.force
        device_identifier = supplied_identifier or None

        def run_cellebrite_background():
            process_cellebrite_report(
                folder_path=full_folder_path,
                case_id=request.case_id,
                task_id=task_id,
                owner=user_email,
                force=force_flag,
                device_identifier=device_identifier,
            )

        import threading
        thread = threading.Thread(target=run_cellebrite_background, daemon=False)
        thread.start()

        return CellebriteProcessResponse(
            success=True,
            message=f"Cellebrite ingestion started ({detection.get('model_count', 0)} models to process)",
            task_id=task_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{evidence_id}")
def delete_evidence_file(
    evidence_id: str,
    case_id: str = Query(..., description="Case ID for scoping"),
    delete_exclusive_entities: bool = Query(True, description="Also delete entities only mentioned in this file"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Delete an evidence file and optionally its exclusive entities.

    This will:
    1. Remove the evidence record from storage
    2. Delete the physical file from disk
    3. Delete the Document node from Neo4j
    4. If delete_exclusive_entities=True, delete entities that are ONLY
       mentioned in this document (not shared with other documents)
    5. Clean up related embeddings from ChromaDB
    6. Exclusive entities are soft-deleted to the recycling bin
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(case_id), current_user, required_permission=("evidence", "upload"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        # 1. Get the evidence record
        record = evidence_storage.get(evidence_id)
        if not record:
            raise HTTPException(status_code=404, detail="Evidence file not found")

        if record.get("case_id") != case_id:
            raise HTTPException(status_code=403, detail="Evidence file does not belong to this case")

        # Check if file is currently being processed — prevent deletion race condition
        from services.evidence_service import EvidenceService
        if EvidenceService.is_evidence_being_processed(case_id, evidence_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete file while it is being processed. Wait for processing to complete."
            )

        filename = record.get("original_filename", "")
        stored_path = record.get("stored_path")
        result_info = {
            "evidence_id": evidence_id,
            "filename": filename,
            "file_deleted": False,
            "document_deleted": False,
            "exclusive_entities_recycled": [],
            "shared_entities_unlinked": [],
            "chromadb_cleaned": False,
        }

        # 2. Delete from Neo4j (Document node + exclusive entities)
        try:
            doc_node = neo4j_service.find_document_node(filename, case_id)
            if doc_node:
                doc_key = doc_node["key"]

                if delete_exclusive_entities:
                    # Find exclusive entities BEFORE deleting doc, then soft-delete them
                    exclusive = neo4j_service.find_exclusive_entities(doc_key, case_id)

                    # Soft-delete exclusive entities to recycling bin first
                    for entity in exclusive:
                        try:
                            neo4j_service.soft_delete_entity(
                                node_key=entity["key"],
                                case_id=case_id,
                                deleted_by=current_user.email,
                                reason=f"file_delete:{filename}",
                            )
                            result_info["exclusive_entities_recycled"].append(entity)
                        except Exception as e:
                            logger.warning(f"Failed to recycle entity {entity['key']}: {e}")

                # Find shared entities (for response info) before deleting doc
                try:
                    shared = neo4j_service.find_document_node(doc_key, case_id)  # just to verify
                except Exception:
                    pass

                # Remove MENTIONED_IN relationships from remaining entities
                # and delete the Document node itself
                neo4j_service.delete_node(doc_key, case_id=case_id)
                result_info["document_deleted"] = True

                # 3. Clean up ChromaDB embeddings
                try:
                    from services.vector_db_service import get_vector_db_service
                    vector_db = get_vector_db_service()
                    if vector_db:
                        # Delete all chunk embeddings for this document
                        vector_db.delete_chunks_by_doc(doc_key)
                        # Delete exclusive entity embeddings
                        for entity in result_info["exclusive_entities_recycled"]:
                            vector_db.delete_entity(entity["key"])
                        result_info["chromadb_cleaned"] = True
                except Exception as e:
                    logger.warning(f"ChromaDB cleanup error: {e}")
            else:
                logger.info(f"No Document node found in Neo4j for {filename}")
        except ValueError as e:
            logger.info(f"Neo4j document deletion: {e}")
        except Exception as e:
            logger.warning(f"Neo4j cleanup error: {e}")

        # 4. Delete physical file from disk
        if stored_path:
            file_path = Path(stored_path)
            if file_path.exists():
                try:
                    file_path.unlink()
                    result_info["file_deleted"] = True
                except Exception as e:
                    logger.warning(f"Failed to delete physical file: {e}")

        # 5. Delete evidence record from JSON storage
        evidence_storage.delete_record(evidence_id)

        return result_info

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{evidence_id}/file")
def get_evidence_file(
    evidence_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Serve the actual file content for a given evidence ID.
    
    Returns the PDF/document file with appropriate content type headers.
    Used by the document viewer to display original source documents.
    """
    try:
        # Get the evidence record
        record = evidence_storage.get(evidence_id)
        
        if not record:
            raise HTTPException(status_code=404, detail="Evidence not found") 
        
        # Get the stored file path
        stored_path = record.get("stored_path")
        if not stored_path:
            raise HTTPException(status_code=404, detail="File path not found")
        
        file_path = Path(stored_path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found on disk")
        
        # Determine content type based on file extension
        filename = record.get("original_filename", file_path.name)
        extension = file_path.suffix.lower()
        
        content_type_map = {
            ".pdf": "application/pdf",
            ".txt": "text/plain",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
            ".svg": "image/svg+xml",
            ".mp4": "video/mp4",
            ".webm": "video/webm",
            ".mov": "video/quicktime",
            ".avi": "video/x-msvideo",
            ".mkv": "video/x-matroska",
            ".flv": "video/x-flv",
            ".wmv": "video/x-ms-wmv",
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".ogg": "audio/ogg",
            ".flac": "audio/flac",
            ".aac": "audio/aac",
            ".m4a": "audio/mp4",
        }
        
        content_type = content_type_map.get(extension, "application/octet-stream")
        
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename=\"{filename}\"",
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


FRAMES_CACHE_DIR = BASE_DIR / "data" / "video_frames"


def _extract_video_frames(video_path: Path, output_dir: Path, interval: int = 30, max_frames: int = 50) -> List[dict]:
    """Extract key frames from a video file using ffmpeg."""
    output_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg_cmd = shutil.which("ffmpeg") or "ffmpeg"
    ffprobe_cmd = shutil.which("ffprobe") or "ffprobe"

    # Get duration
    duration = 0.0
    try:
        probe = subprocess.run(
            [ffprobe_cmd, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, timeout=30,
        )
        duration = float(probe.stdout.strip() or 0)
    except Exception:
        pass

    if duration > 0 and interval > duration:
        interval = max(1, int(duration / 5))

    try:
        subprocess.run(
            [ffmpeg_cmd, "-i", str(video_path), "-vf", f"fps=1/{interval}",
             "-frames:v", str(max_frames), "-q:v", "2", "-y",
             str(output_dir / "frame_%04d.jpg")],
            capture_output=True, text=True, timeout=300,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="ffmpeg not found. Install ffmpeg to extract video frames.")

    frames = []
    for idx, fp in enumerate(sorted(output_dir.glob("frame_*.jpg"))):
        ts = idx * interval
        mins, secs = divmod(ts, 60)
        hrs, mins = divmod(mins, 60)
        frames.append({
            "frame_number": idx + 1,
            "timestamp_seconds": ts,
            "timestamp_str": f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs else f"{mins:02d}:{secs:02d}",
            "filename": fp.name,
        })
    return frames


@router.get("/{evidence_id}/frames")
async def get_video_frames(
    evidence_id: str,
    interval: int = Query(30, description="Seconds between frame captures"),
    max_frames: int = Query(50, description="Maximum number of frames"),
    user: dict = Depends(get_current_user),
):
    """
    Extract and return key frames from a video evidence file.
    Frames are cached so subsequent requests are instant.
    """
    record = evidence_storage.get(evidence_id)
    if not record:
        raise HTTPException(status_code=404, detail="Evidence not found")

    stored_path = record.get("stored_path")
    if not stored_path:
        raise HTTPException(status_code=404, detail="File path not found")

    video_path = Path(stored_path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found on disk")

    video_exts = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".flv", ".wmv"}
    if video_path.suffix.lower() not in video_exts:
        raise HTTPException(status_code=400, detail="File is not a video")

    cache_dir = FRAMES_CACHE_DIR / evidence_id
    frames_meta = []

    if cache_dir.exists() and any(cache_dir.glob("frame_*.jpg")):
        for idx, fp in enumerate(sorted(cache_dir.glob("frame_*.jpg"))):
            ts = idx * interval
            mins, secs = divmod(ts, 60)
            hrs, mins = divmod(mins, 60)
            frames_meta.append({
                "frame_number": idx + 1,
                "timestamp_seconds": ts,
                "timestamp_str": f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs else f"{mins:02d}:{secs:02d}",
                "filename": fp.name,
            })
    else:
        frames_meta = await run_in_threadpool(
            _extract_video_frames, video_path, cache_dir, interval, max_frames
        )

    return {
        "evidence_id": evidence_id,
        "filename": record.get("original_filename", video_path.name),
        "frame_count": len(frames_meta),
        "frames": frames_meta,
    }


@router.get("/{evidence_id}/frames/{filename}")
def get_video_frame_image(
    evidence_id: str,
    filename: str,
    user: dict = Depends(get_current_user),
):
    """Serve an individual extracted frame image."""
    if not filename.startswith("frame_") or not filename.endswith(".jpg"):
        raise HTTPException(status_code=400, detail="Invalid frame filename")

    frame_path = FRAMES_CACHE_DIR / evidence_id / filename
    if not frame_path.exists():
        raise HTTPException(status_code=404, detail="Frame not found. Extract frames first via GET /{evidence_id}/frames")

    return FileResponse(frame_path, media_type="image/jpeg")


class SetRelevanceRequest(BaseModel):
    evidence_ids: List[str]
    is_relevant: bool


@router.put("/relevance")
def set_evidence_relevance(
    body: SetRelevanceRequest,
    user: dict = Depends(get_current_user),
):
    """Mark evidence files as relevant or non-relevant."""
    if not body.evidence_ids:
        raise HTTPException(status_code=400, detail="No evidence IDs provided")
    updated = evidence_storage.set_relevance(body.evidence_ids, body.is_relevant)
    return {"updated": updated, "is_relevant": body.is_relevant}


@router.put("/relevance/from-theory")
def set_relevance_from_theory(
    case_id: str = Query(..., description="Case ID"),
    theory_id: str = Query(..., description="Theory ID"),
    user: dict = Depends(get_current_user),
):
    """
    Mark all evidence files linked to a theory as relevant.
    Collects IDs from attached_evidence_ids, attached_document_ids,
    and any evidence files referenced by graph nodes in the theory's snapshot.
    """
    from services.workspace_service import workspace_service

    theory = workspace_service.get_theory(case_id, theory_id)
    if not theory:
        raise HTTPException(status_code=404, detail="Theory not found")

    evidence_ids = set()

    for field in ("attached_evidence_ids", "attached_document_ids"):
        for eid in (theory.get(field) or []):
            evidence_ids.add(eid)

    snapshot_id = theory.get("attached_snapshot_ids", [None])
    if snapshot_id and isinstance(snapshot_id, list):
        snapshot_id = snapshot_id[0] if snapshot_id else None
    if snapshot_id:
        try:
            from services.snapshot_storage import snapshot_storage
            snapshot = snapshot_storage.get(snapshot_id)
            if snapshot:
                nodes = snapshot.get("graph_data", {}).get("nodes", [])
                all_files = evidence_storage.list_files(case_id=case_id)
                filename_to_id = {f.get("original_filename", "").lower(): f["id"] for f in all_files}
                for node in nodes:
                    for prop_key in ("source", "source_doc", "source_document", "file"):
                        val = node.get("properties", {}).get(prop_key)
                        if val and isinstance(val, str):
                            match = filename_to_id.get(val.lower())
                            if match:
                                evidence_ids.add(match)
        except Exception:
            pass

    updated = 0
    if evidence_ids:
        updated = evidence_storage.set_relevance(list(evidence_ids), True)

    return {"updated": updated, "theory_id": theory_id, "evidence_ids_marked": list(evidence_ids)}


@router.get("/wiretap/processed")
def list_wiretap_processed(
    case_id: Optional[str] = Query(None, description="Case ID to filter by (optional)"),
    user: dict = Depends(get_current_user),
):
    """
    List all successfully processed wiretap folders.
    
    Args:
        case_id: Optional case ID to filter by. If not provided, returns all processed wiretaps.
    
    Returns:
        List of processed wiretap folders with case_id, folder_path, and processed_at
    """
    try:
        return list_processed_wiretaps(case_id=case_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-filename/{filename}")
def get_evidence_by_filename(
    filename: str,
    case_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """
    Find evidence by original filename and return file info.
    
    This endpoint helps the frontend locate evidence IDs from document names
    stored in entity citations.
    """
    try:
        # Search for files matching the filename
        all_files = evidence_storage.list_files(
            case_id=case_id,
        )
        
        # Find matching file
        for record in all_files:
            if record.get("original_filename") == filename:
                # Get document summary if available
                summary = None
                if case_id:
                    try:
                        summary = neo4j_service.get_document_summary(filename, case_id)
                    except Exception:
                        # Summary retrieval is optional
                        pass
                
                return {
                    "found": True,
                    "evidence_id": record.get("id"),
                    "case_id": record.get("case_id"),
                    "original_filename": record.get("original_filename"),
                    "stored_path": record.get("stored_path"),
                    "summary": summary,
                }
        
        return {"found": False, "message": f"No evidence file found with name: {filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary/{filename}")
def get_document_summary(
    filename: str,
    case_id: str = Query(..., description="Case ID"),
    user: dict = Depends(get_current_user),
):
    """
    Get the AI-generated summary for a document.
    
    Returns the summary stored in Neo4j for the document with the given filename.
    """
    try:
        summary = neo4j_service.get_document_summary(filename, case_id)
        return {
            "filename": filename,
            "case_id": case_id,
            "summary": summary,
            "has_summary": summary is not None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/folder-summary/{folder_name}")
def get_folder_summary(
    folder_name: str,
    case_id: str = Query(..., description="Case ID"),
    user: dict = Depends(get_current_user),
):
    """
    Get the AI-generated summary for a processed folder by folder name.
    
    Args:
        folder_name: Folder name (e.g., "00000128")
        case_id: Case ID to filter by
    
    Returns:
        Folder summary if found
    """
    try:
        summary = neo4j_service.get_folder_summary(folder_name, case_id)
        return {
            "folder_name": folder_name,
            "case_id": case_id,
            "summary": summary,
            "has_summary": summary is not None,
        }
    except HTTPException:
        raise


@router.get("/transcription-translation")
def get_transcription_translation(
    case_id: str = Query(..., description="Case ID"),
    folder_name: str = Query(..., description="Wiretap folder name (e.g. 00000128)"),
    user: dict = Depends(get_current_user),
):
    """
    Get wiretap Spanish transcription and English translation for a folder, when available.
    """
    try:
        result = neo4j_service.get_transcription_translation(folder_name, case_id)
        return {
            "folder_name": folder_name,
            "case_id": case_id,
            **result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Folder Profile Management Endpoints

class FolderFileInfo(BaseModel):
    name: str
    path: str
    type: str  # "file" or "directory"
    size: Optional[int] = None


class FolderFilesResponse(BaseModel):
    files: List[FolderFileInfo]
    folder_path: str


class FolderProfileGenerateRequest(BaseModel):
    folder_path: str
    case_id: str
    user_instructions: str
    file_list: List[FolderFileInfo]


class FolderProfileTestRequest(BaseModel):
    folder_path: str
    case_id: str
    profile_name: str


@router.get("/folder/files", response_model=FolderFilesResponse)
def list_folder_files(
    case_id: str = Query(..., description="Case ID"),
    folder_path: str = Query(..., description="Relative folder path from case data directory"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    List files in a folder for profile creation.
    """
    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(case_id), current_user, required_permission=("case", "view"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        case_data_dir = BASE_DIR / "ingestion" / "data" / case_id
        if not case_data_dir.exists():
            raise HTTPException(status_code=404, detail="Case data directory not found")
        
        full_folder_path = (case_data_dir / folder_path).resolve()
        case_resolved = case_data_dir.resolve()
        
        try:
            full_folder_path.relative_to(case_resolved)
        except ValueError:
            raise HTTPException(status_code=403, detail="Path outside case directory")
        
        if not full_folder_path.exists() or not full_folder_path.is_dir():
            raise HTTPException(status_code=404, detail="Folder not found")
        
        files = []
        for item_path in sorted(full_folder_path.iterdir()):
            if item_path.name.startswith('.'):
                continue
            
            relative_path = item_path.relative_to(full_folder_path)
            files.append(FolderFileInfo(
                name=item_path.name,
                path=str(relative_path),
                type="directory" if item_path.is_dir() else "file",
                size=item_path.stat().st_size if item_path.is_file() else None
            ))
        
        return FolderFilesResponse(files=files, folder_path=folder_path)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/folder/profile/generate")
async def generate_folder_profile(
    request: FolderProfileGenerateRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Generate a folder processing profile from natural language instructions.
    Uses LLM to interpret user instructions and create a profile structure.
    """
    import json
    import logging

    logger = logging.getLogger(__name__)

    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(request.case_id), current_user, required_permission=("evidence", "upload"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        from services.llm_service import llm_service
        
        # Validate that we have files to work with
        if not request.file_list:
            raise HTTPException(status_code=400, detail="No files provided in file_list")
        
        # Validate user instructions
        if not request.user_instructions or not request.user_instructions.strip():
            raise HTTPException(status_code=400, detail="User instructions cannot be empty")
        
        logger.info(f"Generating folder profile for case {request.case_id}, folder {request.folder_path} with {len(request.file_list)} files")
        
        # Build prompt for LLM
        file_list_str = "\n".join([f"- {f.name} ({f.type})" for f in request.file_list])
        
        prompt = f"""You are helping a user configure a folder processing profile.

The user has uploaded a folder with these files:
{file_list_str}

The user wants this processing:
{request.user_instructions}

Generate a JSON profile structure that defines how to process this folder. The profile should include:
1. A "folder_processing" section with:
   - "type": "special" (to indicate files are related)
   - "file_rules": Array of rules, each with:
     - "pattern": File pattern (e.g., "*.wav,*.mp3" or "*.sri")
     - "role": Role of the file ("audio", "metadata", "interpretation", "document", "image", "video", etc.)
     - For audio: "actions": ["transcribe", "translate"], "transcribe_languages": [...], "translate_languages": [...], "whisper_model": "base"
     - For metadata: "parser": "sri" (or other), "metadata_extraction": {{...}}
     - For interpretation: "parser": "rtf", "extract_participants": true, "extract_interpretation": true
     - For image: "provider": "tesseract" (local OCR) or "openai" (GPT-4 Vision for rich scene descriptions)
     - For video: "actions": ["transcribe", "analyze_frames"] (transcribe audio + extract/analyze key frames)
   - "processing_rules": Text description explaining how files relate and how to process them
   - "output_format": "wiretap_structured" or "combined" or "media_structured" or "custom"
   - "related_files_indicator": true

Respond with valid JSON only, matching this structure:
{{
  "folder_processing": {{
    "type": "special",
    "file_rules": [...],
    "processing_rules": "...",
    "output_format": "...",
    "related_files_indicator": true
  }}
}}"""
        
        logger.info("Calling LLM service to generate profile...")
        
        # Call LLM with JSON mode and timeout
        # Note: LLM calls can take 30-90 seconds depending on the model and prompt complexity
        # This is expected behavior - the request will show "Waiting for Server" during this time
        llm_timeout = 90  # Increased to 90 seconds to accommodate slower models
        
        try:
            # Run LLM call in thread pool to avoid blocking the event loop
            llm_response = await run_in_threadpool(
                llm_service.call,
                prompt=prompt,
                temperature=0.3,
                json_mode=True,
                timeout=llm_timeout
            )
            logger.info(f"LLM service responded (length: {len(llm_response) if llm_response else 0})")
        except Exception as llm_err:
            logger.error(f"LLM service call failed: {str(llm_err)}")
            # Check if it's a timeout error
            error_str = str(llm_err).lower()
            if 'timeout' in error_str or 'timed out' in error_str or '504' in str(llm_err):
                raise HTTPException(
                    status_code=504,
                    detail=f"LLM service timeout: Profile generation took longer than {llm_timeout} seconds. The LLM call is taking longer than expected. Please try again with simpler instructions or check if your LLM service is responding."
                )
            raise HTTPException(
                status_code=500,
                detail=f"LLM service error: {str(llm_err)}. This might be due to a timeout or service unavailability. Please check your LLM configuration."
            )
        
        if not llm_response:
            raise HTTPException(status_code=500, detail="LLM service returned empty response")
        
        # Parse LLM response
        try:
            profile_data = json.loads(llm_response)
        except json.JSONDecodeError as json_err:
            logger.warning(f"Failed to parse LLM response as JSON: {str(json_err)}")
            logger.debug(f"LLM response content: {llm_response[:500]}")
            # Try to extract JSON from response if it's wrapped
            import re
            json_match = re.search(r'\{[\s\S]*\}', llm_response)
            if json_match:
                try:
                    profile_data = json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to parse LLM response as JSON. Response preview: {llm_response[:200]}"
                    )
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"LLM response is not valid JSON. Response preview: {llm_response[:200]}"
                )
        
        folder_processing = profile_data.get("folder_processing", {})
        
        if not folder_processing:
            logger.warning("Generated profile does not contain folder_processing section")
            # Create a basic structure if missing
            folder_processing = {
                "type": "special",
                "file_rules": [],
                "processing_rules": request.user_instructions,
                "output_format": "combined",
                "related_files_indicator": True
            }
        
        logger.info("Profile generation completed successfully")
        
        return {
            "success": True,
            "profile": folder_processing,
            "raw_response": llm_response[:500] if len(llm_response) > 500 else llm_response  # Truncate for response
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error generating folder profile: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate profile: {str(e)}")


@router.post("/folder/profile/test")
def test_folder_profile(
    request: FolderProfileTestRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Test a folder processing profile on a folder (dry run or full processing).
    Returns a background task ID for processing.
    """
    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(request.case_id), current_user, required_permission=("evidence", "upload"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        case_data_dir = BASE_DIR / "ingestion" / "data" / request.case_id
        if not case_data_dir.exists():
            raise HTTPException(status_code=404, detail="Case data directory not found")

        full_folder_path = (case_data_dir / request.folder_path).resolve()
        case_resolved = case_data_dir.resolve()

        try:
            full_folder_path.relative_to(case_resolved)
        except ValueError:
            raise HTTPException(status_code=403, detail="Path outside case directory")

        if not full_folder_path.exists() or not full_folder_path.is_dir():
            raise HTTPException(status_code=404, detail="Folder not found")

        # Create background task for testing
        task = background_task_storage.create_task(
            task_type="folder_profile_test",
            task_name=f"Test folder profile: {request.folder_path}",
            case_id=request.case_id,
            owner=current_user.email,
            metadata={
                "folder_path": request.folder_path,
                "profile_name": request.profile_name,
            }
        )
        task_id = task["id"]
        
        # Import and run folder ingestion in background
        def test_folder_profile_background():
            from pathlib import Path
            import sys
            INGESTION_SCRIPTS_PATH = BASE_DIR / "ingestion" / "scripts"
            if str(INGESTION_SCRIPTS_PATH) not in sys.path:
                sys.path.insert(0, str(INGESTION_SCRIPTS_PATH))
            
            from folder_ingestion import ingest_folder_with_profile
            
            def log_callback(message: str):
                evidence_log_storage.add_log(
                    case_id=request.case_id,
                    evidence_id=None,
                    filename=None,
                    level="info",
                    message=f"[Profile Test] {message}"
                )
            
            try:
                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.RUNNING.value,
                    started_at=datetime.now().isoformat(),
                )
                
                result = ingest_folder_with_profile(
                    folder_path=full_folder_path,
                    profile_name=request.profile_name,
                    case_id=request.case_id,
                    log_callback=log_callback
                )
                
                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED.value,
                    completed_at=datetime.now().isoformat(),
                    metadata={
                        "result": result
                    }
                )
            except Exception as e:
                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.FAILED.value,
                    error=str(e),
                    completed_at=datetime.now().isoformat(),
                )
        
        import threading
        thread = threading.Thread(target=test_folder_profile_background, daemon=False)
        thread.start()
        
        return {
            "success": True,
            "task_id": task_id,
            "message": "Folder profile test started"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Phase 5: Tag + Entity-link endpoints
# ---------------------------------------------------------------------------


class TagsAddRequest(BaseModel):
    case_id: str
    evidence_ids: List[str]
    tags: List[str]


class TagsRemoveRequest(BaseModel):
    case_id: str
    evidence_ids: List[str]
    tags: List[str]


class TagsSetRequest(BaseModel):
    case_id: str
    evidence_id: str
    tags: List[str]


class EntityLinkRequest(BaseModel):
    case_id: str
    evidence_ids: List[str]
    entity_ids: List[str]


def _verify_case_for(case_id: str, current_user, db) -> None:
    """Local helper: share the existing case access check logic."""
    from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
    from uuid import UUID
    try:
        check_case_access(db, UUID(case_id), current_user, required_permission=("evidence", "upload"))
    except (CaseNotFound, CaseAccessDenied) as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/tags/add")
def add_evidence_tags(
    body: TagsAddRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Add tags to one or more evidence records."""
    _verify_case_for(body.case_id, current_user, db)
    updated = evidence_storage.add_tags(body.evidence_ids, body.tags)
    return {"updated": updated, "tags": body.tags}


@router.post("/tags/remove")
def remove_evidence_tags(
    body: TagsRemoveRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Remove tags from one or more evidence records."""
    _verify_case_for(body.case_id, current_user, db)
    updated = evidence_storage.remove_tags(body.evidence_ids, body.tags)
    return {"updated": updated, "tags": body.tags}


@router.post("/tags/set")
def set_evidence_tags(
    body: TagsSetRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Replace the tag list on a single evidence record."""
    _verify_case_for(body.case_id, current_user, db)
    ok = evidence_storage.set_tags(body.evidence_id, body.tags)
    if not ok:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return {"ok": True, "tags": sorted(set((body.tags or [])))}


@router.get("/tags")
def get_case_tags(
    case_id: str = Query(...),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Return the case's tag cloud: [{tag, count}]."""
    _verify_case_for(case_id, current_user, db)
    return {"tags": evidence_storage.get_tag_counts(case_id)}


@router.post("/entity-links/add")
def add_entity_links(
    body: EntityLinkRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Link evidence records to entity IDs."""
    _verify_case_for(body.case_id, current_user, db)
    updated = evidence_storage.link_entities(body.evidence_ids, body.entity_ids)
    return {"updated": updated, "entity_ids": body.entity_ids}


@router.post("/entity-links/remove")
def remove_entity_links(
    body: EntityLinkRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Unlink evidence records from entity IDs."""
    _verify_case_for(body.case_id, current_user, db)
    updated = evidence_storage.unlink_entities(body.evidence_ids, body.entity_ids)
    return {"updated": updated, "entity_ids": body.entity_ids}


@router.get("/by-entity")
def list_evidence_by_entity(
    case_id: str = Query(...),
    entity_id: str = Query(...),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Return all evidence records in a case linked to a given entity."""
    _verify_case_for(case_id, current_user, db)
    records = evidence_storage.list_by_entity(case_id, entity_id)
    return {"files": records, "total": len(records)}