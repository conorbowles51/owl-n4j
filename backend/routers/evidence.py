"""
Evidence Router

Handles uploading evidence files and triggering ingestion processing.
File storage and AI processing are delegated to the evidence engine when enabled.
"""

import asyncio
import hashlib
import httpx
import os
import logging
import mimetypes
import subprocess
import shutil
import uuid as uuid_mod
import zipfile
from collections import defaultdict
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Dict, List, Optional
from uuid import UUID
from services.manual_changes import records
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Header, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.datastructures import UploadFile as StarletteUploadFile
from starlette.requests import ClientDisconnect

from services.wiretap_tracking import list_processed_wiretaps, is_wiretap_processed, mark_wiretap_processed
from services.wiretap_service import check_wiretap_suitable, process_wiretap_folder_async
from services.background_task_storage import background_task_storage, TaskStatus
from services.evidence_processing_service import process_db_files
from services.neo4j_service import neo4j_service
from services.cypher_generator import generate_cypher_from_graph
from services.evidence_db_storage import EvidenceDBStorage
from services.evidence_text_search_service import search_case_text, search_document_text
from services import evidence_engine_client
from services.response_encoding import plain_or_encoded
from services.financial import PageRenderError, UnadmittedFileError, render_page_png
from services import page_image_cache
from .auth import get_current_user
from routers.case_access import (
    authorize_case,
    case_access_dependency,
    request_json_payload,
)
from routers.users import get_current_db_user
from fastapi import Path as PathParam, Query, status
from postgres.session import get_db
from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceFolder
from postgres.models.user import User
from sqlalchemy import select
from sqlalchemy.orm import Session
from config import BASE_DIR, EVIDENCE_DATA_ROOT, USE_EVIDENCE_ENGINE
from datetime import datetime

logger = logging.getLogger(__name__)
EVIDENCE_ROOT_DIR = EVIDENCE_DATA_ROOT

# Uploaded bytes land in <case>/_staging/<id> first so large evidence is streamed to disk instead of being held in
# memory, inside the case so the engine's phone detector can read it.
_UPLOAD_STAGING_NAME = "_staging"
# An uploaded zip, kept as received after its members are registered (01 section 3 step 4).
_RECEIVED_ARCHIVES_NAME = "_received_archives"
# Case-directory entries that are Loupe's own working areas, never evidence to register by a filesystem sync.
_SYNC_SKIP_DIRS = {_UPLOAD_STAGING_NAME, _RECEIVED_ARCHIVES_NAME}
PHONE_UPLOAD_REFUSED = "Upload phone reports with the folder or archive upload"
PHONE_PROCESS_REFUSED = "Phone reports are read automatically when uploaded."
_STAGE_CHUNK_SIZE = 1024 * 1024

# Platform sidecars that archive tools add; never evidence.
_ARCHIVE_SKIP_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}

# Most file ids one ``/route-check`` request may ask about. Only that read
# endpoint is limited; processing requests are uncapped since 7d04cb24. The
# frontend splits its pages to ROUTE_CHECK_BATCH_LIMIT, which must match.
MAX_BATCH_SIZE = 50


def _evidence_case_permission(request: Request, payload: dict) -> tuple[str, str]:
    if request.method == "GET":
        return ("case", "view")
    return ("evidence", "upload")


_require_evidence_case_access = case_access_dependency(_evidence_case_permission)


def _evidence_record_for_id(db: Session, evidence_id: str):
    try:
        return EvidenceDBStorage.get(db, UUID(evidence_id))
    except (TypeError, ValueError, AttributeError):
        return EvidenceDBStorage.get_by_legacy_id(db, evidence_id)


async def _require_evidence_object_access(
    request: Request,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
) -> None:
    """Authorize evidence IDs against the case stored on each DB record."""
    payload = await request_json_payload(request)
    evidence_ids: set[str] = set()

    path_evidence_id = request.path_params.get("evidence_id")
    if path_evidence_id:
        evidence_ids.add(str(path_evidence_id))

    payload_evidence_id = payload.get("evidence_id")
    if payload_evidence_id:
        evidence_ids.add(str(payload_evidence_id))
    payload_evidence_ids = payload.get("evidence_ids")
    if isinstance(payload_evidence_ids, list):
        evidence_ids.update(str(value) for value in payload_evidence_ids if value)

    permission = ("case", "view") if request.method == "GET" else ("evidence", "upload")
    job_id = None
    if request.method == "GET" and request.url.path.startswith("/api/evidence/engine/jobs/"):
        job_id = str(request.path_params.get("job_id") or "")
    if not evidence_ids and job_id is None:
        return
    # Async only to read the body; the database checks run in the thread pool, not on the event loop.
    await run_in_threadpool(_authorize_evidence_objects, db, current_user, permission, evidence_ids, job_id)


def _authorize_evidence_objects(db: Session, current_user: User, permission, evidence_ids: set[str],
                                job_id: str | None) -> None:
    for evidence_id in evidence_ids:
        record = _evidence_record_for_id(db, evidence_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Evidence not found")
        authorize_case(db, record.case_id, current_user, permission)

    if job_id is not None:
        record = EvidenceDBStorage.find_by_engine_job_id(db, job_id) if job_id else None
        if record is None:
            raise HTTPException(status_code=404, detail="Evidence job not found")
        authorize_case(db, record.case_id, current_user, permission)


from services.financial.view_cache import BATCH_FILES_UNSTAMPED, ModelOutput, cached_view  # noqa: E402

router = APIRouter(
    prefix="/api/evidence",
    tags=["evidence"],
    dependencies=[
        Depends(get_current_db_user),
        Depends(_require_evidence_case_access),
        Depends(_require_evidence_object_access),
    ],
)


def _resolve_stored_path(stored_path: str | None) -> Optional[Path]:
    """Resolve DB stored_path across host and Docker evidence-engine layouts."""
    if not stored_path:
        return None

    direct = Path(stored_path)
    if direct.exists():
        return direct

    normalised = str(stored_path).replace("\\", "/")
    markers = (
        "evidence-data/",
        "/evidence-data/",
        "data/evidence/",
        "/data/evidence/",
        "ingestion/data/",
        "/ingestion/data/",
    )
    for marker in markers:
        marker_index = normalised.find(marker)
        if marker_index == -1:
            continue
        relative = normalised[marker_index + len(marker):].lstrip("/")
        candidate = EVIDENCE_ROOT_DIR / PurePosixPath(relative)
        if candidate.exists():
            return candidate

    return direct


def _evidence_record_from_db(record) -> dict:
    from services.financial.file_visibility import financial_file_visibility
    from services.financial.source_lineage import lineage_id
    return {
        **financial_file_visibility(record),
        "statement_root_evidence_id": lineage_id(record),
        "statement_parent_evidence_id": (record.metadata_ or {}).get('statement_parent_evidence_id'),
        "id": str(record.id),
        "case_id": str(record.case_id),
        "original_filename": record.original_filename,
        "stored_path": record.stored_path or "",
        "folder_id": str(record.folder_id) if record.folder_id else None,
        "size": record.size,
        "sha256": record.sha256,
        "status": record.status,
        "processing_stale": False,
        "is_duplicate": record.is_duplicate,
        "duplicate_of": str(record.duplicate_of_id) if record.duplicate_of_id else None,
        "is_relevant": record.is_relevant,
        "owner": record.owner,
        "created_at": record.created_at.isoformat() if record.created_at else "",
        "processed_at": record.processed_at.isoformat() if record.processed_at else None,
        "last_error": record.last_error,
        "engine_job_id": record.engine_job_id,
        "legacy_id": record.legacy_id,
        "summary": record.summary,
        "transcription": record.transcription,
        'transcript_review': dict((record.metadata_ or {}).get('transcript_review') or {}),
        "transcription_segments": list(record.transcription_segments or []),
        "transcription_speakers": dict(record.transcription_speakers or {}),
        "transcription_speaker_merges": dict(
            record.transcription_speaker_merges or {}
        ),
        "entity_count": record.entity_count,
        "relationship_count": record.relationship_count,
        "last_processed_folder_id": str(record.last_processed_folder_id) if record.last_processed_folder_id else None,
    }


def _uuid_or_none(value: Optional[str]) -> Optional[UUID]:
    if not value:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def add_evidence_log(
    *,
    case_id: str,
    evidence_id: Optional[str],
    filename: Optional[str],
    level: str,
    message: str,
    progress_current: Optional[int] = None,
    progress_total: Optional[int] = None,
) -> None:
    from postgres.session import get_background_session

    extra = {}
    if progress_current is not None:
        extra["progress_current"] = progress_current
    if progress_total is not None:
        extra["progress_total"] = progress_total

    with get_background_session() as log_db:
        EvidenceDBStorage.add_log(
            log_db,
            case_id=UUID(case_id),
            evidence_file_id=_uuid_or_none(evidence_id),
            filename=filename,
            level=level,
            message=message,
            extra=extra,
        )


def _safe_relative_path(raw_path: str) -> PurePosixPath:
    """Normalize an uploaded relative path and reject traversal attempts."""
    cleaned = (raw_path or "unknown").replace("\\", "/").lstrip("/")
    parts = []
    for part in PurePosixPath(cleaned).parts:
        if part in ("", "."):
            continue
        if part == ".." or "/" in part or "\\" in part:
            raise HTTPException(status_code=400, detail=f"Invalid upload path: {raw_path}")
        parts.append(part)
    if not parts:
        parts = ["unknown"]
    return PurePosixPath(*parts)


def _stream_sha256(path: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_STAGE_CHUNK_SIZE), b""):
            hasher.update(chunk)
            size += len(chunk)
    return hasher.hexdigest(), size


def _stage_upload_files(files: List[StarletteUploadFile], staging_dir: Path) -> List[dict]:
    """
    Stream UploadFile objects into staging and return metadata for persistence.

    The incoming filename may include a webkitRelativePath when the frontend is
    uploading a folder. Keep that path as metadata, but write staged bytes under
    unique flat filenames to avoid staging collisions.
    """
    staging_dir.mkdir(parents=True, exist_ok=True)
    staged: List[dict] = []

    for uf in files:
        filename = uf.filename or "unknown"
        relative_path = _safe_relative_path(filename)
        original_filename = relative_path.name
        if original_filename in _ARCHIVE_SKIP_NAMES or original_filename.startswith("._"):
            continue

        staged_path = staging_dir / f"{uuid_mod.uuid4().hex}_{original_filename}"
        hasher = hashlib.sha256()
        size = 0
        try:
            with staged_path.open("wb") as dst:
                while True:
                    chunk = uf.file.read(_STAGE_CHUNK_SIZE)
                    if not chunk:
                        break
                    hasher.update(chunk)
                    dst.write(chunk)
                    size += len(chunk)
        except Exception:
            try:
                staged_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        finally:
            try:
                uf.file.close()
            except Exception:
                pass

        staged.append({
            "original_filename": original_filename,
            "staged_path": staged_path,
            "sha256": hasher.hexdigest(),
            "size": size,
            "relative_path": str(relative_path).replace("\\", "/"),
        })

    return staged


async def _detect_phone(case_id: str, path: Path) -> dict:
    """The engine's phone classification (01 section 2.5) of a path inside the case directory."""
    rel = path.relative_to(EVIDENCE_ROOT_DIR / case_id).as_posix()
    return await evidence_engine_client.detect_phone_container(case_id, rel)


async def _refuse_phone_report(case_id: str, path: Path) -> None:
    """409 when the staged upload holds a phone report, readable or protected (01 section 4.1)."""
    if not USE_EVIDENCE_ENGINE:
        return  # no phone reading on this installation; the upload is ordinary evidence, as before the engine
    try:
        found = await _detect_phone(case_id, path)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="The upload could not be checked for phone reports. Nothing "
                                                    "was registered. Try again shortly.") from exc
    if found.get("outcome", "not_a_phone_report") != "not_a_phone_report":
        raise HTTPException(status_code=409, detail=PHONE_UPLOAD_REFUSED)


def _keep_original_archive(case_id: str, upload: dict) -> Path:
    """Move an uploaded zip out of staging into the case's received-archives area, never overwriting."""
    staged = Path(upload["staged_path"])
    target = EVIDENCE_ROOT_DIR / case_id / _RECEIVED_ARCHIVES_NAME / uuid_mod.uuid4().hex / staged.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(staged), str(target))
    return target


def _extract_archive_to_staging(zip_path: Path, extract_dir: Path) -> List[dict]:
    """
    Extract a zip safely into staging and return upload metadata.

    An ordinary zip posted as one multipart part is unpacked server side with
    zip-slip protection. Phone reports never reach here: the upload refuses
    them first and they go through the resumable group upload, which keeps the
    container whole.
    """
    extract_dir.mkdir(parents=True, exist_ok=True)
    extract_root = extract_dir.resolve()
    uploads: List[dict] = []
    extracted: Dict[Path, str] = {}
    copies_of: Dict[Path, set] = {}  # a path's first target -> the hashes of every copy kept for it

    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            normalized = (info.filename or "").replace("\\", "/").lstrip("/")
            if not normalized:
                continue
            parts = normalized.split("/")
            if any(part == "__MACOSX" or part.startswith("._") for part in parts):
                continue
            if parts[-1] in _ARCHIVE_SKIP_NAMES:
                continue

            relative_path = _safe_relative_path(normalized)
            target = (extract_dir / relative_path).resolve()
            try:
                target.relative_to(extract_root)
            except ValueError:
                continue
            # The same path twice in one archive: the second copy gets "name (n).ext" rather than overwriting the
            # first (which would leave the first row's hash describing bytes no longer on disk). A copy with the
            # same bytes as any earlier copy of that path is the same file and is kept once.
            earlier_copies = copies_of.setdefault(target, set())
            base, n = relative_path, 1
            while target in extracted:
                n += 1
                relative_path = base.with_name(f"{base.stem} ({n}){base.suffix}")
                target = (extract_dir / relative_path).resolve()

            target.parent.mkdir(parents=True, exist_ok=True)
            hasher = hashlib.sha256()
            size = 0
            try:
                with zf.open(info) as src, target.open("wb") as dst:
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

            digest = hasher.hexdigest()
            if digest in earlier_copies:
                target.unlink(missing_ok=True)
                continue
            earlier_copies.add(digest)
            extracted[target] = digest
            uploads.append({
                "original_filename": relative_path.name,
                "staged_path": target,
                "sha256": digest,
                "size": size,
                "relative_path": str(relative_path).replace("\\", "/"),
            })

    return uploads


def _get_folder_parts(db: Session, folder_id: Optional[UUID]) -> List[str]:
    if not folder_id:
        return []
    current = EvidenceDBStorage.get_folder(db, folder_id)
    if not current:
        raise HTTPException(status_code=404, detail="Target folder not found")
    breadcrumbs = EvidenceDBStorage.get_folder_breadcrumbs(db, folder_id)
    return [folder.name for folder in breadcrumbs] + [current.name]


def _get_or_create_folder_chain(
    db: Session,
    case_id: UUID,
    parts: List[str],
    parent_id: Optional[UUID] = None,
    created_by_id: Optional[UUID] = None,
) -> Optional[UUID]:
    current_parent = parent_id
    current_folder: Optional[EvidenceFolder] = None
    for part in parts:
        existing = db.scalars(
            select(EvidenceFolder).where(
                EvidenceFolder.case_id == case_id,
                EvidenceFolder.name == part,
                EvidenceFolder.parent_id == current_parent
                if current_parent
                else EvidenceFolder.parent_id.is_(None),
            )
        ).first()
        if existing:
            current_folder = existing
        else:
            current_folder = EvidenceDBStorage.create_folder(
                db,
                case_id=case_id,
                name=part,
                parent_id=current_parent,
                created_by_id=created_by_id,
            )
        current_parent = current_folder.id
    return current_folder.id if current_folder else parent_id


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _holds_other_bytes(target: Path, sha256: Optional[str]) -> bool:
    """True when something holds target other than a file with the upload's bytes.

    A directory, a link (even a broken one) or any other non-regular entry keeps
    its name: the upload is never taken to be stored there."""
    if not os.path.lexists(target):
        return False
    if target.is_symlink() or not target.is_file():
        return True
    if not sha256:
        return True
    return _file_sha256(target) != sha256


def _free_target(target: Path, sha256: Optional[str]) -> Path:
    """
    The path a staged upload goes to without replacing a different file.

    A file already at target with the same bytes is the same evidence and is
    kept; a different file keeps its path, and the upload takes the first free
    "name (n).ext" beside it, so an evidence row never points at bytes other
    than the ones it was registered with.
    """
    candidate, n = target, 1
    while _holds_other_bytes(candidate, sha256):
        n += 1
        candidate = target.with_name(f"{target.stem} ({n}){target.suffix}")
    return candidate


def _claim(target: Path) -> bool:
    """Create target empty if nothing is there, atomically; False when a file already holds the name."""
    try:
        os.close(os.open(str(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644))
        return True
    except FileExistsError:
        return False


def _place_staged(staged_path: Path, target: Path, sha256: Optional[str] = None) -> Path:
    """
    Move a staged file to target, or to the next free "name (n).ext" when a
    different file took target in the meantime; returns where it went.

    The name is claimed with an exclusive create, so two uploads of the same
    name at the same moment cannot both see it free and the second overwrite
    the first. A file already there with the same bytes is kept as it is.
    """
    if staged_path.resolve() == target:
        return target
    while True:
        if _claim(target):
            try:
                shutil.move(str(staged_path), str(target))
            except BaseException:
                # The staged file is still where it was; the empty claim must not keep the name.
                target.unlink(missing_ok=True)
                raise
            return target
        if not os.path.lexists(target):
            continue  # removed since the claim was refused: claim it again
        if not _holds_other_bytes(target, sha256):
            staged_path.unlink(missing_ok=True)
            return target
        target = _free_target(target, sha256)


def _persist_staged_uploads(
    *,
    db: Session,
    case_id: UUID,
    case_id_text: str,
    uploads: List[dict],
    owner: str,
    folder_id: Optional[UUID],
    created_by_id: Optional[UUID],
    register_files: bool,
    metadata: Optional[dict] = None,
) -> List[dict]:
    """
    Move staged files into the case directory and optionally create DB rows.
    ``metadata`` is added to every registered row.
    """
    case_dir = EVIDENCE_ROOT_DIR / case_id_text
    case_dir.mkdir(parents=True, exist_ok=True)
    case_resolved = case_dir.resolve()
    root_parts = _get_folder_parts(db, folder_id)
    grouped: Dict[Optional[UUID], List[dict]] = defaultdict(list)

    for upload in uploads:
        relative_path = _safe_relative_path(upload.get("relative_path") or upload.get("original_filename"))
        target_relative = PurePosixPath(*root_parts, *relative_path.parts) if root_parts else relative_path
        target = (case_dir / target_relative).resolve()
        try:
            target.relative_to(case_resolved)
        except ValueError:
            raise HTTPException(status_code=403, detail="Upload path escaped the case directory")

        target.parent.mkdir(parents=True, exist_ok=True)
        staged_path = Path(upload["staged_path"])
        if staged_path.resolve() != target:
            target = _free_target(target, upload.get("sha256"))
        target = _place_staged(staged_path, target, upload.get("sha256"))

        if not register_files:
            continue

        parent_parts = list(relative_path.parent.parts)
        file_folder_id = _get_or_create_folder_chain(
            db,
            case_id=case_id,
            parts=parent_parts,
            parent_id=folder_id,
            created_by_id=created_by_id,
        )
        grouped[file_folder_id].append({
            "original_filename": relative_path.name,
            "stored_path": str(target),
            "sha256": upload["sha256"],
            "size": upload.get("size", 0),
            **({"metadata": dict(metadata)} if metadata else {}),
        })

    created = []
    if register_files:
        for group_folder_id, file_infos in grouped.items():
            created.extend(EvidenceDBStorage.add_files(
                db,
                case_id=case_id,
                files_data=file_infos,
                owner=owner,
                folder_id=group_folder_id,
                created_by_id=created_by_id,
            ))

    return [_evidence_record_from_db(record) for record in created]


class EvidenceRecord(BaseModel):
    id: str
    case_id: str
    original_filename: str
    stored_path: str = ""
    folder_id: Optional[str] = None
    size: int
    sha256: str
    status: str
    financial_removed: bool = False
    statement_root_evidence_id: Optional[str] = None
    statement_parent_evidence_id: Optional[str] = None
    reading_versions: list[dict] = Field(default_factory=list)
    financial_visibility_revision: str = "initial"
    financial_visibility_changed_at: Optional[str] = None
    financial_imports_removed: bool = False
    processing_stale: bool = False
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None
    is_relevant: bool = False
    owner: Optional[str] = None
    created_at: str
    processed_at: Optional[str] = None
    last_error: Optional[str] = None
    summary: Optional[str] = None  # Document summary if available
    transcription: Optional[str] = None  # Full audio transcript if available
    transcription_segments: List[dict] = Field(default_factory=list)
    transcription_speakers: Dict[str, str] = Field(default_factory=dict)
    transcription_speaker_merges: Dict[str, str] = Field(default_factory=dict)
    transcript_review: dict = Field(default_factory=dict)
    entity_count: Optional[int] = None
    relationship_count: Optional[int] = None
    engine_job_id: Optional[str] = None  # Evidence engine job ID for progress tracking
    legacy_id: Optional[str] = None
    last_processed_folder_id: Optional[str] = None


class EvidenceListResponse(BaseModel):
    files: List[EvidenceRecord]


class UploadResponse(BaseModel):
    """Response for file uploads - can be synchronous or background."""
    files: Optional[List[EvidenceRecord]] = None  # For synchronous uploads
    task_id: Optional[str] = None  # Single task ID (for backwards compatibility)
    task_ids: Optional[List[str]] = None  # Multiple task IDs (for folder uploads)
    job_ids: Optional[List[str]] = None  # Evidence engine job IDs (for WebSocket progress)
    message: Optional[str] = None  # Status message


from typing import Literal

class ProcessRequest(BaseModel):
    preparation_mode: Literal["full", "pdf_review", "audio_review"] = "full"
    audio_mode: Literal['review_first', 'direct'] | None = None
    case_id: Optional[str] = None
    file_ids: List[str]
    profile: Optional[str] = None  # LLM profile name (e.g., "fraud", "generic")
    max_workers: Optional[int] = None  # Maximum parallel files to process
    image_provider: Optional[str] = None  # "tesseract" (local OCR) or "openai" (GPT-4 Vision)


class RouteCheckRequest(BaseModel):
    """The same two identifiers ``ProcessRequest`` takes, and nothing else.

    Deliberately the same shape, because the point of the check is to answer a
    question about the exact request that is about to be made.  A check taking
    different identifiers could be answered for a different set of files than
    the one processed, and the interface would have no way to notice.
    """

    case_id: str
    file_ids: List[str]


class ProcessResponse(BaseModel):
    processed: int
    skipped: int
    errors: int
    # Case version info may be present when case_id is provided
    case_id: Optional[str] = None
    case_version: Optional[int] = None
    case_timestamp: Optional[str] = None


class TranscriptSpeakersUpdate(BaseModel):
    expected_revision_id: Optional[str] = None
    speakers: Dict[str, str]
    merges: Dict[str, str] = Field(default_factory=dict)


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


class TextSearchHit(BaseModel):
    id: str
    start_char: int
    end_char: int
    snippet: str
    highlight_start: int
    highlight_end: int
    page_number: Optional[int] = None
    location_label: Optional[str] = None
    # a line of a phone conversation names its record (02 section 9.7)
    location_kind: Optional[str] = None
    record_uid: Optional[str] = None
    extraction_id: Optional[str] = None


class TextSearchDocument(BaseModel):
    evidence_id: str
    document_name: str
    source_type: Optional[str] = None
    folder_path: str
    total_matches: int
    shown_matches: int
    matches_truncated: bool
    matches: List[TextSearchHit]


class CaseTextSearchResponse(BaseModel):
    query: str
    total_matches: int
    total_documents: int
    case_documents: int
    searchable_documents: int
    document_limit: int
    document_offset: int
    returned_documents: int
    has_more_documents: bool
    documents: List[TextSearchDocument]


class DocumentTextMatchesResponse(BaseModel):
    query: str
    evidence_id: str
    total_matches: int
    returned_matches: int
    offset: int
    limit: int
    has_more: bool
    matches: List[TextSearchHit]


def _validated_text_query(q: str) -> str:
    query = q.strip()
    if len(query) < 2 or len(query) > 256:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Search query must contain between 2 and 256 characters",
        )
    return query


# These reads await nothing: as plain functions they run in the thread pool. As async functions they ran on the
# worker's event loop, and listing d5b330d1's statement files (12-20 s) held every other request of that worker
# until it finished.
# Computed once and served again while no row it read has changed (view_cache: the Financial page's statement
# register lists d5b330d1's 3,158 files in 10-20 s). The sign-in check is a route dependency, not a parameter, so
# the person's token is not part of what is saved.
@router.get("", response_model=EvidenceListResponse, dependencies=[Depends(get_current_user)])
# Of the statement batches it reads their id, case and files list (file_scope: each file's ids), never the keys the
# release sweeps stamp on each file: proved by test_financial_batch_stamp_views.
@cached_view('evidence-list', columns={'financial_import_batches': ('id', 'case_id', BATCH_FILES_UNSTAMPED)})
def list_evidence(
    case_id: str = Query(..., description="Case ID"),
    status_filter: Optional[str] = Query(None, alias="status"),
    include_cellebrite_artifacts: bool = False,
    include_reading_versions: bool = False,
    financial_only: bool = False,
    db: Session = Depends(get_db),
):
    """
    List evidence files.

    Args:
        case_id: Case ID to filter by.
        status_filter: Optional status filter
            ('unprocessed', 'processing', 'processed', 'duplicate', 'failed').
    """
    try:
        db_files = EvidenceDBStorage.list_files(db, case_id=UUID(case_id), status=status_filter, include_reading_versions=include_reading_versions)
        if financial_only:
            from services.financial.file_scope import financial_file_ids
            financial_ids = financial_file_ids(db, case_id=UUID(case_id))
            db_files = [row for row in db_files if row.id in financial_ids]
        if not include_cellebrite_artifacts:
            db_files = [row for row in db_files if row.source_type != "cellebrite"]
        from services.financial.source_lineage import reading_history, case_lineage
        history = reading_history(db, db_files)
        # Financial's full version list may group only validated source families.
        roots = {str(file.id): root for root, versions in case_lineage(db, UUID(case_id)).items() for file in versions} if include_reading_versions else {}
        listing = {"files": [{**_evidence_record_from_db(f),
            'statement_root_evidence_id': roots.get(str(f.id), str(f.id)),
            'reading_versions': history.get(str(f.id), [])} for f in db_files]}
        # What FastAPI sends for the response model: a saved answer is sent as it is, past the model.
        return ModelOutput(EvidenceListResponse.model_validate(listing).model_dump(mode='json'))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# The fields of each file the Financial page's statement register reads (frontend use-statement-register.ts
# statementFile); its schema drops every other field of the listing.
STATEMENT_REGISTER_FIELDS = (
    'id', 'case_id', 'original_filename', 'status', 'created_at', 'statement_root_evidence_id',
    'statement_parent_evidence_id', 'financial_removed', 'financial_imports_removed',
    'financial_visibility_revision', 'financial_visibility_changed_at')


@router.get("/statement-register", dependencies=[Depends(get_current_user)])
@cached_view('statement-register')
def list_statement_register(
    case_id: str = Query(..., description="Case ID"),
    db: Session = Depends(get_db),
):
    """The Financial page's statement register: the listing ``GET /api/evidence`` answers with
    ``include_reading_versions=true&financial_only=true``, each file given only the fields the register reads
    (STATEMENT_REGISTER_FIELDS; a field the listing leaves out stays out). d5b330d1: 3,176 files, 4.6 MB whole.
    Made from the kept copy of that listing when one is current, so both come from the same rows."""
    from services.financial.view_cache import kept_copy
    scope = dict(case_id=case_id, status_filter=None, include_cellebrite_artifacts=False,
                 include_reading_versions=True, financial_only=True)
    listing = kept_copy('evidence-list', scope)
    if listing is None:
        listing = list_evidence(db=db, **scope)
    return {"files": [{field: file[field] for field in STATEMENT_REGISTER_FIELDS if field in file}
                      for file in listing["files"]]}


@router.get("/text-search", response_model=CaseTextSearchResponse)
def text_search(
    response: Response,
    case_id: UUID = Query(..., description="Case ID"),
    q: str = Query(..., min_length=2, max_length=256),
    document_limit: int = Query(25, ge=1, le=100),
    document_offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = _validated_text_query(q)
    result = search_case_text(
        db,
        case_id=case_id,
        query=query,
        document_limit=document_limit,
        document_offset=document_offset,
    )
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/deleted")
def list_deleted_evidence(
    case_id: str = Query(..., description="Case ID"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Deleted items of a case's Evidence: who deleted each file, when, what it holds, days left to restore."""
    from uuid import UUID
    from routers.case_access import authorize_case_view
    from services import evidence_casebin
    case_uuid = authorize_case_view(db, case_id, current_user)
    return dict(files=evidence_casebin.list_deleted(db, case_uuid),
                retention_days=evidence_casebin.DELETED_RETENTION_DAYS,
                can_restore=evidence_casebin.can_restore(db, case_uuid, current_user))


@router.get("/{evidence_id}", response_model=EvidenceRecord)
def get_evidence_record(
    evidence_id: str,
    db: Session = Depends(get_db),
):
    """Return one authorized evidence record for deep-linked citations."""

    record = _evidence_record_for_id(db, evidence_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    from services.financial.source_lineage import reading_history
    return {**_evidence_record_from_db(record), 'reading_versions': reading_history(db, [record]).get(str(record.id), [])}


@router.get("/{evidence_id}/text-matches", response_model=DocumentTextMatchesResponse)
def document_text_matches(
    evidence_id: str,
    response: Response,
    q: str = Query(..., min_length=2, max_length=256),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = _validated_text_query(q)
    record = _evidence_record_for_id(db, evidence_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    result = search_document_text(
        db,
        evidence_id=record.id,
        query=query,
        limit=limit,
        offset=offset,
    )
    response.headers["Cache-Control"] = "no-store"
    return result


@router.put("/{evidence_id}/transcript-speakers")
@records('transcript_speaker_correct', 'change', subject_type='evidence', subject=lambda c: c['kw'].get('evidence_id'), field='speakers', case=lambda c: c['body'].get('case_id') or (c['result'] or {}).get('case_id') if isinstance(c['result'], dict) else c['body'].get('case_id'))
def update_transcript_speakers(
    evidence_id: str,
    update: TranscriptSpeakersUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Persist investigator-assigned names and reversible diarization label merges."""
    record = _evidence_record_for_id(db, evidence_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence not found")

    segments = record.transcription_segments or []
    known_speakers = {
        str(segment.get("speaker"))
        for segment in segments
        if isinstance(segment, dict) and segment.get("speaker")
    }
    if len(update.speakers) > 32:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A transcript can have at most 32 named speakers",
        )

    normalized: Dict[str, str] = {}
    for raw_speaker, raw_name in update.speakers.items():
        speaker = raw_speaker.strip()
        name = raw_name.strip()
        if speaker not in known_speakers:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Unknown transcript speaker: {speaker}",
            )
        if len(name) > 80:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Speaker names must be 80 characters or fewer",
            )
        if name:
            normalized[speaker] = name

    if len(update.merges) > 32:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A transcript can have at most 32 speaker merges",
        )

    requested_merges: Dict[str, str] = {}
    for raw_source, raw_target in update.merges.items():
        source = raw_source.strip()
        target = raw_target.strip()
        if source not in known_speakers:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Unknown transcript speaker: {source}",
            )
        if target not in known_speakers:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Unknown transcript speaker: {target}",
            )
        if source != target:
            requested_merges[source] = target

    def resolve_merge_target(source: str) -> str:
        current = source
        visited: set[str] = set()
        while current in requested_merges:
            if current in visited:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Speaker merges cannot contain a cycle",
                )
            visited.add(current)
            current = requested_merges[current]
        return current

    normalized_merges = {
        source: resolve_merge_target(source) for source in requested_merges
    }

    from services.transcript_review import feature_enabled
    if hasattr(record, 'case_id') and not feature_enabled():
        from postgres.models.transcript import TranscriptState
        if db.get(TranscriptState, record.id):
            raise HTTPException(409, 'Transcript review is unavailable. Saved speaker revisions are retained.')
    if hasattr(record, 'case_id') and feature_enabled():
        from services import transcript_review
        state = transcript_review.ensure_source(db, record)
        if state:
            if update.expected_revision_id is None and state.review_required:
                raise HTTPException(409, 'Open Transcript review to change this saved revision safely.')
            transcript_review.save_draft(db, record, update.expected_revision_id or str(state.working_revision_id),
                {'speakers': normalized, 'speaker_merges': normalized_merges}, getattr(current_user, 'id', None))
            if update.expected_revision_id is None:
                state.review_required = False  # Legacy naming remains usable until explicit review/edit opt-in.
                transcript_review.refresh_summary(db, record, state)
    record.transcription_speakers = normalized
    record.transcription_speaker_merges = normalized_merges
    db.commit()
    return {"speakers": normalized, "merges": normalized_merges}




_REPORT_NAMESPACE = b"http://pa.cellebrite.com/report/2.0"


def _local_phone_report_dirs(case_dir: Path) -> set:
    """Folders below the case directory holding an XML file whose first 4 KB name the phone report namespace. A
    found folder is not searched further. Loupe's own working areas and hidden folders are skipped, as in a sync."""
    found = set()
    for dirpath, dirnames, filenames in os.walk(case_dir):
        current = Path(dirpath)
        if current == case_dir:
            dirnames[:] = [n for n in dirnames if n not in _SYNC_SKIP_DIRS]
        dirnames[:] = [n for n in dirnames if not n.startswith(".")]
        if current == case_dir:
            continue
        for name in filenames:
            if not name.lower().endswith(".xml"):
                continue
            try:
                with (current / name).open("rb") as handle:
                    head = handle.read(4096)
            except OSError:
                continue
            if _REPORT_NAMESPACE in head:
                found.add(current)
                dirnames[:] = []
                break
    return found


def _phone_report_dirs(case_id: str, case_dir: Path) -> set:
    """Report folders under the case directory, from the engine's detector, so a sync never registers a phone
    report's files one by one. Refuses when the detector cannot be reached rather than guessing. With the engine
    switched off, folders are found locally by the report namespace in an XML file's head."""
    if not USE_EVIDENCE_ENGINE:
        return _local_phone_report_dirs(case_dir)
    import anyio.from_thread
    try:
        found = anyio.from_thread.run(evidence_engine_client.detect_phone_container, case_id, "")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Phone report folders could not be identified, so nothing was "
                                                    "synced. Try again shortly.") from exc
    return {case_dir / r["root_path"] for r in found.get("roots") or [] if r.get("root_path")}


@router.post("/sync-filesystem")
def sync_filesystem(
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
    import hashlib
    import logging

    logger = logging.getLogger(__name__)

    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(case_id), current_user, required_permission=("evidence", "upload"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        case_dir = EVIDENCE_ROOT_DIR / case_id
        if not case_dir.exists() or not case_dir.is_dir():
            return {"created": 0, "message": "Case directory does not exist"}

        from services.evidence_db_storage import EvidenceDBStorage

        case_uuid = UUID(case_id)

        # Get existing evidence records for this case from Postgres
        db_files = EvidenceDBStorage.list_files(db, case_id=case_uuid)

        # Build a set of known stored paths
        known_stored_paths = set()
        for rec in db_files:
            sp = rec.stored_path or ""
            if sp:
                known_stored_paths.add(sp)
                try:
                    known_stored_paths.add(str(Path(sp).resolve()))
                except Exception:
                    pass

        # Walk the case directory for files without evidence records. Pruned: Loupe's own working areas, phone
        # containers already registered as one evidence row (a folder container's stored path is the folder), and
        # phone report folders the engine's detector finds (01 section 4.1). A phone report's files are not
        # evidence rows (01 D7); one report can hold tens of thousands of them.
        created_count = 0
        grouped: Dict[Optional[UUID], List[dict]] = defaultdict(list)
        phone_roots = _phone_report_dirs(case_id, case_dir)
        skipped_phone_dirs: List[str] = []

        for dirpath, dirnames, filenames in os.walk(case_dir):
            current_dir = Path(dirpath)
            if current_dir == case_dir:
                dirnames[:] = [name for name in dirnames if name not in _SYNC_SKIP_DIRS]
            if current_dir != case_dir and (str(current_dir) in known_stored_paths or current_dir in phone_roots):
                skipped_phone_dirs.append(current_dir.relative_to(case_dir).as_posix())
                dirnames[:] = []
                continue

            dirnames[:] = [name for name in dirnames if not name.startswith(".")]

            for filename in filenames:
                if filename.startswith("."):
                    continue
                file_path = current_dir / filename

                abs_path_str = str(file_path)
                resolved_str = str(file_path.resolve())

                if abs_path_str in known_stored_paths or resolved_str in known_stored_paths:
                    continue

                try:
                    sha256, size = _stream_sha256(file_path)
                except (OSError, PermissionError) as e:
                    logger.warning(f"Cannot read file {file_path}: {e}")
                    continue

                relative_parent = file_path.relative_to(case_dir).parent
                parent_parts = [
                    part for part in relative_parent.parts
                    if part not in ("", ".")
                ]
                folder_uuid = _get_or_create_folder_chain(
                    db,
                    case_id=case_uuid,
                    parts=list(parent_parts),
                    created_by_id=current_user.id,
                )
                grouped[folder_uuid].append({
                    "original_filename": file_path.name,
                    "stored_path": str(file_path),
                    "sha256": sha256,
                    "size": size,
                })

        for folder_uuid, file_infos in grouped.items():
            new_records = EvidenceDBStorage.add_files(
                db,
                case_id=case_uuid,
                files_data=file_infos,
                owner=current_user.email,
                folder_id=folder_uuid,
                created_by_id=current_user.id,
            )
            created_count += len(new_records)

        if created_count:
            logger.info(f"Filesystem sync: created {created_count} evidence records for case {case_id}")
        if skipped_phone_dirs:
            logger.info("Filesystem sync: left %s phone report folder(s) for case %s to the phone upload",
                        len(skipped_phone_dirs), case_id)
        db.commit()

        return {"created": created_count, "message": f"Synced {created_count} file(s)"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/duplicates/{sha256}", response_model=EvidenceListResponse)
def find_duplicates(
    sha256: str,
    case_id: str = Query(..., description="Case ID"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Find all files with the same SHA256 hash (duplicates).
    """
    try:
        case_uuid = UUID(case_id)
        files = [
            _evidence_record_from_db(f)
            for f in EvidenceDBStorage.find_all_by_hash(db, sha256)
            if f.case_id == case_uuid
        ]
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload", response_model=UploadResponse)
async def upload_evidence(
    request: Request,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Upload one or more evidence files for a case.

    Files are streamed to disk-backed staging first, then moved into the case
    evidence directory and registered in Postgres. Folder uploads preserve the
    browser-provided relative paths. Archive uploads (`is_archive=true`) unpack
    a single .zip server-side and keep the zip as received. A phone report is
    refused with 409 before anything is registered: phone reports go through
    the resumable group upload, which keeps the container whole (01 section 4.1).
    """
    try:
        form = await request.form(max_files=20000, max_fields=20000)
    except ClientDisconnect:
        logger.warning("Evidence upload client disconnected before the request body was fully received")
        raise HTTPException(
            status_code=499,
            detail="Upload was cancelled before the server received the complete file",
        )
    case_id = str(form.get("case_id") or "")
    is_folder = str(form.get("is_folder") or "").lower() == "true"
    is_archive = str(form.get("is_archive") or "").lower() == "true"
    replace_existing = str(form.get("replace_existing") or "").lower() == "true"
    folder_id_raw = form.get("folder_id")
    folder_id = str(folder_id_raw) if folder_id_raw else None
    files = [value for value in form.getlist("files") if isinstance(value, StarletteUploadFile)]

    if not case_id:
        raise HTTPException(status_code=400, detail="case_id is required")
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    if is_archive and len(files) != 1:
        raise HTTPException(status_code=400, detail="Archive upload expects exactly one .zip file")

    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        case_uuid = UUID(case_id)
        folder_uuid = UUID(folder_id) if folder_id else None

        # Async for the form, staging and engine calls; every database step runs in the thread pool.
        def check_target():
            try:
                check_case_access(db, case_uuid, current_user, required_permission=("evidence", "upload"))
            except (CaseNotFound, CaseAccessDenied) as e:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
            if folder_uuid:
                folder = EvidenceDBStorage.get_folder(db, folder_uuid)
                if not folder or str(folder.case_id) != case_id:
                    raise HTTPException(status_code=404, detail="Target folder not found")

        await run_in_threadpool(check_target)

        # Staged inside the case directory so the engine's phone detector can read it (its paths are case-relative).
        staging_dir = EVIDENCE_ROOT_DIR / str(case_uuid) / _UPLOAD_STAGING_NAME / uuid_mod.uuid4().hex
        try:
            uploads = await run_in_threadpool(_stage_upload_files, files, staging_dir)
            if not uploads:
                raise HTTPException(status_code=400, detail="No extractable files uploaded")

            kept_archive: Optional[dict] = None
            if is_archive:
                zip_path = Path(uploads[0]["staged_path"])
                if not zipfile.is_zipfile(zip_path):
                    raise HTTPException(status_code=400, detail="Uploaded archive is not a valid .zip file")
                await _refuse_phone_report(str(case_uuid), zip_path)
                kept_archive = uploads[0]
                uploads = await run_in_threadpool(_extract_archive_to_staging, zip_path, staging_dir / "_extracted")
                if not uploads:
                    raise HTTPException(status_code=400, detail="Archive contained no extractable files")
            else:
                await _refuse_phone_report(str(case_uuid), staging_dir)

            # The user is handed on as its two fields, read here: after the commit the row would reload on the loop.
            def register():
                metadata = None
                if kept_archive is not None:
                    # The uploaded zip is kept beside the case as received (01 section 3 step 4); every member row
                    # names it.
                    kept = _keep_original_archive(str(case_uuid), kept_archive)
                    metadata = {"original_archive_sha256": kept_archive["sha256"],
                                "original_archive_path": str(kept)}
                records = _persist_staged_uploads(
                    db=db,
                    case_id=case_uuid,
                    case_id_text=case_id,
                    uploads=uploads,
                    owner=current_user.email,
                    folder_id=folder_uuid,
                    created_by_id=current_user.id,
                    register_files=True,
                    metadata=metadata,
                )
                db.commit()
                return records

            records = await run_in_threadpool(register)
            upload_kind = "folder" if is_folder or is_archive else "file"
            return UploadResponse(
                files=records,
                job_ids=None,
                message=f"Uploaded {len(records)} {upload_kind}{'' if len(records) == 1 else 's'}",
            )
        finally:
            # On success every staged file has moved into the case and only empty directories remain; on failure
            # nothing staged was registered.
            shutil.rmtree(staging_dir, ignore_errors=True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _record_financial_read(db, user, case_id, file_ids, copies):
    """Activity trail: a person asked Financial to read these files (never blocks the request)."""
    from services import activity_trail
    from postgres.models.evidence import EvidenceFile as AuditFile
    try:
        sent = list(db.scalars(select(AuditFile).where(AuditFile.case_id == UUID(str(case_id)),
            AuditFile.id.in_([UUID(str(i)) for i in file_ids]))))
    except Exception:
        sent = []
    activity_trail.record('financial_send', db=db, commit=True, user=user, case_id=case_id,
        details=dict(how='read_in_financial', file_count=len(sent), copies=len(copies),
                     files=activity_trail.file_entries(sent)))


@router.post("/process/background")
async def process_evidence_background(
    request: ProcessRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Process selected evidence files in the background.

    DB-backed evidence files are dispatched through the evidence engine using
    folder-aware processing snapshots. Legacy file IDs still use the older
    background ingestion pipeline.
    """
    if not request.file_ids:
        raise HTTPException(status_code=400, detail="No file_ids provided")

    try:
        if request.case_id:
            from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
            from uuid import UUID
            try:
                await run_in_threadpool(check_case_access, db, UUID(request.case_id), current_user,
                                        required_permission=("evidence", "upload"))
            except (CaseNotFound, CaseAccessDenied) as e:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        await run_in_threadpool(_refuse_phone_containers, db, request.file_ids)
        db_backed_ids, missing_ids = await run_in_threadpool(_split_db_backed_legacy, request.file_ids, db)
        if missing_ids:
            raise HTTPException(
                status_code=404,
                detail=f"{len(missing_ids)} file id(s) were not found in Postgres evidence storage",
            )

        messages = []
        job_ids = []
        copies = []
        user_id = current_user.id  # read before the Financial intake commits (a load on the event loop after)

        if db_backed_ids and request.preparation_mode == "pdf_review" and request.case_id:
            # Financial reading: exact copies of a file already in Financial are
            # not read again; the rest join the case's automatic statement batch.
            from services.financial.auto_read import intake_pdf_review
            db_backed_ids, copies = await run_in_threadpool(
                intake_pdf_review, db, case_id=UUID(request.case_id), file_ids=db_backed_ids)
            if copies:
                messages.append(f"{len(copies)} file(s) already in Financial; not read again")
            await run_in_threadpool(_record_financial_read, db, current_user, request.case_id,
                                    list(db_backed_ids) + [c['file_id'] for c in copies], copies)

        if db_backed_ids:
            if not request.case_id:
                raise HTTPException(status_code=400, detail="case_id is required for DB-backed evidence files")
            engine_result = await process_db_files(
                db,
                case_id=UUID(request.case_id),
                file_ids=db_backed_ids,
                force_reprocess=False,
                preparation_mode=request.preparation_mode,
                requested_by_user_id=user_id,
                audio_mode=request.audio_mode,
            )
            job_ids = engine_result.get("job_ids", [])
            if engine_result.get("message"):
                messages.append(engine_result["message"])

        return {
            "task_id": None,
            "job_ids": job_ids or None,
            "message": "; ".join(messages) if messages else "No files to process",
            **({"copies": copies} if copies else {}),
        }
    except UnadmittedFileError as e:
        # 409 and not 403.  The caller has the permission this route asks for
        # -- they passed ``evidence:upload`` above.  What is missing is not
        # rights but a decision: one or more of these files is bank data the
        # router holds back, and nobody has said on the record that it should
        # go to the document pipeline anyway.  A 403 would tell them to ask an
        # administrator, which would not help.
        #
        # The body names every held file and what was found in it, so the
        # interface can offer the admission without a second round trip to
        # ``/route-check`` -- whose answer, taken later, may not be the one
        # this refusal was based on.
        #
        raise HTTPException(status_code=409, detail=e.as_dict())
    except HTTPException:
        # A 403, 404 or 409 raised above stays what it is; only an unexpected failure is a 500.
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/route-check")
async def check_evidence_financial_route(
    request: RouteCheckRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Say which of these uploaded files are bank files, before processing them.

    Called in the gap between ``POST /upload``, which stages a file and returns
    no job, and ``POST /process/background``, which is what actually enqueues
    work.  Four formats -- camt.053, BAI2, MT940 and NACHA -- are parsed exactly
    by the financial ledger, and sending one of them through the document
    pipeline instead would have a model infer its figures from extracted text.
    The result is indistinguishable downstream from a parsed reading, so the
    only place to tell them apart is before the choice is made.

    A cheap "what is this?" ahead of an expensive process. It takes
    ``file_ids``, because that is what this pipeline processes and what the
    caller is about to pass to ``/process/background``.  For the same reason there is no path
    traversal guard: the paths come from evidence rows scoped to a case the
    caller can already see, not from the caller, which is a stronger guarantee
    than checking a string for "..".

    ``POST`` rather than ``GET`` because selections may contain many file IDs,
    which do not belong in a query string.
    """
    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from services.financial.route_check import check_case_files, summarise

        try:
            case_uuid = UUID(request.case_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="case_id is not a valid UUID")

        # A read, so viewing the case is the right bar -- lower than the ``evidence:upload``
        # that ``/process/background`` requires.  Someone who may look at a case
        # may ask what its files are without being able to spend money on them.
        try:
            await run_in_threadpool(check_case_access, db, case_uuid, current_user, required_permission=("case", "view"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        if not request.file_ids:
            raise HTTPException(status_code=400, detail="No file_ids provided")

        # An id that is not a UUID is a fault in the caller, not a fact about a
        # file, so it is rejected rather than given a per-file outcome.  Giving
        # it one would put a made-up file in a list the interface reads as a
        # description of real ones.
        malformed = []
        file_uuids = []
        for raw in request.file_ids:
            try:
                file_uuids.append(UUID(raw))
            except (ValueError, AttributeError, TypeError):
                malformed.append(str(raw))
        if malformed:
            raise HTTPException(
                status_code=400,
                detail=f"{len(malformed)} file id(s) are not valid UUIDs: {', '.join(malformed[:5])}",
            )

        # A phone report is answered as what it is for this check, not a bank file (not_native), without opening
        # it: the phone reading owns it, processing skips it, and one in a page of files must not take the route
        # badges of the others away or hold a selection.
        phone = await run_in_threadpool(_phone_container_ids, db, file_uuids)
        others = [f for f in file_uuids if f not in phone]
        checks = [] if not others else await run_in_threadpool(
            check_case_files,
            db,
            case_id=case_uuid,
            file_ids=others,
            resolve_path=_resolve_stored_path,
        )
        if phone:
            from services.financial.route_check import FileRouteCheck
            names = dict(await run_in_threadpool(lambda: db.execute(
                select(EvidenceFile.id, EvidenceFile.original_filename).where(EvidenceFile.id.in_(phone))).all()))
            answered = {c.file_id: c for c in checks}
            answered.update({str(i): FileRouteCheck(file_id=str(i), file_name=names.get(i)) for i in phone})
            checks = [answered[str(f)] for f in file_uuids if str(f) in answered]
        return {
            "case_id": str(case_uuid),
            "files": [check.as_dict() for check in checks],
            "summary": summarise(checks),
        }
    except HTTPException:
        # Re-raised before the catch-all so that a 400, 403 or 409 stays what it is.
        raise
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

    DB-backed evidence files are dispatched through the evidence engine using
    folder-aware processing snapshots. Legacy file IDs are processed through
    the older synchronous ingestion pipeline.
    """
    if not request.file_ids:
        raise HTTPException(status_code=400, detail="No file_ids provided")

    try:
        if request.case_id:
            from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
            from uuid import UUID
            try:
                await run_in_threadpool(check_case_access, db, UUID(request.case_id), current_user,
                                        required_permission=("evidence", "upload"))
            except (CaseNotFound, CaseAccessDenied) as e:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        await run_in_threadpool(_refuse_phone_containers, db, request.file_ids)
        db_backed_ids, missing_ids = await run_in_threadpool(_split_db_backed_legacy, request.file_ids, db)
        if missing_ids:
            raise HTTPException(
                status_code=404,
                detail=f"{len(missing_ids)} file id(s) were not found in Postgres evidence storage",
            )

        processed = 0
        skipped = 0
        errors = 0

        if db_backed_ids:
            if not request.case_id:
                raise HTTPException(status_code=400, detail="case_id is required for DB-backed evidence files")
            engine_result = await process_db_files(
                db,
                case_id=UUID(request.case_id),
                file_ids=db_backed_ids,
                force_reprocess=False,
                preparation_mode=request.preparation_mode,
                requested_by_user_id=current_user.id,
                audio_mode=request.audio_mode,
            )
            processed += engine_result.get("file_count", 0)
            skipped += engine_result.get("skipped_count", 0)

        return ProcessResponse(processed=processed, skipped=skipped, errors=errors)
    except UnadmittedFileError as e:
        # Same refusal as ``/process/background``, for the same reason and in
        # the same shape.  Both routes reach ``process_db_files``, so a gate on
        # only one of them would be a door with a lock beside it.
        raise HTTPException(status_code=409, detail=e.as_dict())
    except HTTPException:
        raise
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ingestion pipeline not available: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _phone_container_ids(db: Session, file_ids) -> set:
    ids = []
    for raw in file_ids or []:
        try:
            ids.append(UUID(str(raw)))
        except (ValueError, TypeError, AttributeError):
            continue
    if not ids:
        return set()
    return set(db.scalars(select(EvidenceFile.id).where(EvidenceFile.id.in_(ids),
                                                         EvidenceFile.source_type == "phone_extraction")))


def _refuse_phone_containers(db: Session, file_ids) -> None:
    """409 only when every requested row is a phone report: the capture job reads those (01 section 4.4). In a
    mixed selection the phone rows are skipped by the processing service and the others go ahead."""
    ids = [raw for raw in (file_ids or [])]
    phone = _phone_container_ids(db, ids)
    if ids and phone and len(phone) >= len({str(i) for i in ids}):
        raise HTTPException(status_code=409, detail=PHONE_PROCESS_REFUSED)


def _split_db_backed_legacy(file_ids: List[str], db: Session) -> tuple:
    """Split file IDs into Postgres evidence files and missing IDs."""
    db_backed_ids = []
    legacy_ids = []
    for fid in file_ids:
        rec = None
        try:
            rec = EvidenceDBStorage.get(db, UUID(fid))
        except (ValueError, AttributeError):
            rec = None
        if rec:
            db_backed_ids.append(rec.id)
        else:
            legacy_ids.append(fid)
    return db_backed_ids, legacy_ids


@router.get("/logs", response_model=EvidenceLogListResponse)
def get_evidence_logs(
    case_id: str = Query(..., description="Case ID"),
    limit: int = 200,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Get recent evidence ingestion logs for a case.
    """
    try:
        from services.evidence_db_storage import EvidenceDBStorage
        from uuid import UUID
        case_uuid = UUID(case_id)
        db_logs = EvidenceDBStorage.list_logs(db, case_id=case_uuid, limit=limit)
        logs = []
        for log in db_logs:
            logs.append({
                "id": str(log.id),
                "case_id": str(log.case_id) if log.case_id else None,
                "evidence_id": str(log.evidence_file_id) if log.evidence_file_id else None,
                "filename": log.filename,
                "level": log.level,
                "message": log.message,
                "timestamp": log.created_at.isoformat() if log.created_at else "",
            })
        return {"logs": logs}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/engine/jobs")
async def list_engine_jobs(
    request: Request,
    case_id: str = Query(..., description="Case ID"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Proxy: list all processing jobs from the evidence engine for a case.

    The database work (access check, reconcile, file links) runs in a worker thread: this handler awaits the engine,
    so it stays async, and nothing blocking may run on the event loop.

    The list (3.15 MB on d5b330d1, polled every minute from an open Evidence page) carries an ETag with
    ``private, no-cache``: the browser asks again with If-None-Match and an unchanged list is answered 304 with no
    body. The bytes of a 200 are the ones FastAPI wrote before."""
    try:
        await run_in_threadpool(_check_engine_jobs_access, db, case_id, current_user)

        if not USE_EVIDENCE_ENGINE:
            return []

        jobs = await evidence_engine_client.list_jobs(case_id)
        linked = await run_in_threadpool(_reconcile_and_link_engine_jobs, db, case_id, jobs)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Failed to list engine jobs: %s", e)
        return []
    # Outside the engine's failure handling: an encoding error is a 500, as it was before, not an empty list.
    return await run_in_threadpool(_jobs_answer, linked, request.headers.get("if-none-match"))


def _jobs_answer(jobs: list, if_none_match: Optional[str]) -> Response:
    """The job list as FastAPI would encode it, with an ETag; 304 when the browser already holds these bytes."""
    # The engine's list is plain JSON data: d5b330d1's took 0.19 s to walk with jsonable_encoder, for the same bytes.
    answer = JSONResponse(plain_or_encoded(jobs))
    # Weak: the same tag names the plain and the gzipped body (the same JSON).
    etag = 'W/"' + hashlib.sha256(answer.body).hexdigest()[:32] + '"'
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    sent = [tag.strip().removeprefix("W/") for tag in (if_none_match or "").split(",")]
    if etag.removeprefix("W/") in sent:
        # The gzip middleware adds Vary to a 200 it compresses; a 304 has no body for it to see.
        return Response(status_code=304, headers={**headers, "Vary": "Accept-Encoding"})
    answer.headers.update(headers)
    return answer


def _check_engine_jobs_access(db: Session, case_id: str, current_user: User) -> None:
    from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied

    try:
        check_case_access(db, UUID(case_id), current_user, required_permission=("case", "view"))
    except (CaseNotFound, CaseAccessDenied) as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


def _reconcile_and_link_engine_jobs(db: Session, case_id: str, jobs: list) -> list:
    from services.evidence_job_sync import reconcile_case_poll

    reconcile_case_poll(db, case_id, jobs)
    # Two columns: whole rows were loaded here only to build this map (3.3-4.0 s on the largest case).
    file_ids_by_job_id = {
        str(engine_job_id): str(file_id)
        for engine_job_id, file_id in db.execute(
            select(EvidenceFile.engine_job_id, EvidenceFile.id).where(
                EvidenceFile.case_id == UUID(case_id),
                EvidenceFile.engine_job_id.is_not(None),
            )
        ).all()
        if engine_job_id
    }
    for job in jobs:
        job["evidence_file_id"] = file_ids_by_job_id.get(str(job.get("id")))
    return jobs


@router.get("/engine/jobs/{job_id}")
async def get_engine_job(
    job_id: str,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Proxy: get status of a single processing job from the evidence engine."""
    try:
        if not USE_EVIDENCE_ENGINE:
            raise HTTPException(status_code=404, detail="Evidence engine not enabled")

        from services.evidence_job_sync import reconcile_job_by_id
        from services.evidence_db_storage import EvidenceDBStorage

        job = await reconcile_job_by_id(db, job_id)
        db_rec = await run_in_threadpool(EvidenceDBStorage.find_by_engine_job_id, db, job_id)
        if db_rec:
            job["evidence_file_id"] = str(db_rec.id)
        return job
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/engine/jobs/{job_id}")
async def delete_engine_job(
    job_id: str,
    case_id: str = Query(..., description="Case ID"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Proxy: delete a single terminal processing job from the evidence engine."""
    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID

        try:
            await run_in_threadpool(check_case_access, db, UUID(case_id), current_user, required_permission=("case", "edit"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        await evidence_engine_client.delete_job(job_id)
        return {"deleted": 1, "job_id": job_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/engine/jobs/{job_id}/{action}")
async def control_engine_job(job_id: str, action: str,
    current_user: User = Depends(get_current_db_user), db: Session = Depends(get_db)):
    if action not in {"pause", "resume", "cancel"}:
        raise HTTPException(status_code=404, detail="Unknown job action")
    record = await run_in_threadpool(EvidenceDBStorage.find_by_engine_job_id, db, job_id)
    case_id = record.case_id if record is not None else None
    if case_id is None:
        # A phone reading belongs to its container's evidence row, not to one row per job; its case is the job's.
        try:
            job = await evidence_engine_client.get_job(job_id)
        except Exception:
            job = None
        if not job or job.get("job_type") != "phone_capture":
            raise HTTPException(status_code=404, detail="Evidence job not found")
        case_id = UUID(str(job["case_id"]))
    if action == "cancel" and (record is not None):
        raise HTTPException(status_code=409, detail="Only phone report readings can be cancelled")
    await run_in_threadpool(authorize_case, db, case_id, current_user, ("evidence", "upload"))
    try:
        return await evidence_engine_client.control_job(job_id, str(case_id), action)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code,
            detail=exc.response.json().get("detail", "Could not change processing state")) from exc


@router.delete("/engine/jobs")
async def clear_engine_jobs(
    case_id: str = Query(..., description="Case ID"),
    terminal_only: bool = Query(True),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Proxy: clear terminal processing jobs for a case from the evidence engine."""
    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID

        try:
            await run_in_threadpool(check_case_access, db, UUID(case_id), current_user, required_permission=("case", "edit"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        return await evidence_engine_client.clear_case_jobs(case_id, terminal_only=terminal_only)
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
        case_data_dir = EVIDENCE_ROOT_DIR / case_id
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
def process_wiretap_folders(
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

        case_data_dir = EVIDENCE_ROOT_DIR / request.case_id

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
                    # Full validation happens here in the background
                    full_path = case_data_dir / fp
                    try:
                        # Resolve and check it's within case directory
                        resolved = full_path.resolve()
                        case_resolved = case_data_dir.resolve()
                        resolved.relative_to(case_resolved)
                    except (ValueError, OSError) as e:
                        add_evidence_log(
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
                        add_evidence_log(
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
                        add_evidence_log(
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
                            add_evidence_log(
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
                            add_evidence_log(
                                case_id=request.case_id,
                                evidence_id=None,
                                filename=None,
                                level="info",
                                message=f"Wiretap folder processed: {fp}",
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
                            add_evidence_log(
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


@router.post("/{evidence_id}/restore")
def restore_deleted_evidence(
    evidence_id: str,
    case_id: str = Query(..., description="Case ID"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Bring a file back from Deleted items: the row, its graph and its text search, exactly as they were."""
    from routers.case_access import authorize_case_view
    from services import evidence_casebin
    case_uuid = authorize_case_view(db, case_id, current_user)
    try:
        return evidence_casebin.restore_file(db, case_uuid, evidence_id, current_user)
    except evidence_casebin.EvidenceNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except evidence_casebin.EvidenceNotDeleted as e:
        raise HTTPException(status_code=409, detail=str(e))
    except evidence_casebin.EvidenceRestoreDenied as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/{evidence_id}")
def delete_evidence_file(
    evidence_id: str,
    case_id: str = Query(..., description="Case ID for scoping"),
    delete_exclusive_entities: bool = Query(True, description="Also hide entities only mentioned in this file"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Move an evidence file to Deleted items for 30 days (services/evidence_casebin.py).

    The file, its record, its Document node, the entities found only in it and its text search are kept and hidden
    from every screen, search and agent; the case owner or an admin can restore it. After 30 days it is purged with
    the delete used before (graph recycle bin for its exclusive entities, file and record removed).
    """
    from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
    from services import evidence_casebin
    from uuid import UUID
    try:
        check_case_access(db, UUID(case_id), current_user, required_permission=("evidence", "upload"))
    except (CaseNotFound, CaseAccessDenied, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    db_record = None
    try:
        db_record = EvidenceDBStorage.get(db, UUID(evidence_id))
    except (ValueError, AttributeError):
        db_record = EvidenceDBStorage.get_by_legacy_id(db, evidence_id)
    if not db_record:
        raise HTTPException(status_code=404, detail="Evidence file not found")
    if str(db_record.case_id) != case_id:
        raise HTTPException(status_code=403, detail="Evidence file does not belong to this case")
    if db_record.status == "processing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete file while it is being processed. Wait for processing to complete."
        )
    from services.financial.import_removal import financial_hold, financial_hold_message
    hold = financial_hold(db, case_id=db_record.case_id, file_ids=[db_record.id])
    if hold:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=financial_hold_message(hold))
    ledger = evidence_casebin.ledger_hold(db, db_record.case_id, [db_record.id])
    if ledger:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ledger)
    if evidence_casebin.import_in_progress(db, db_record.case_id, [db_record.id]):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A Financial import is still preparing "
                            "this file. Wait for it to finish, or remove the import, then delete the file.")
    try:
        return evidence_casebin.delete_file(db, db_record, current_user,
                                            delete_exclusive_entities=delete_exclusive_entities)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{evidence_id}/file")
def get_evidence_file(
    evidence_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    range_header: Optional[str] = Header(None, alias="Range"),
):
    """
    Serve the actual file content for a given evidence ID.

    All files are served from the backend's local disk (EVIDENCE_ROOT_DIR).
    """
    try:
        # Look up by UUID or legacy ID
        record = None
        try:
            from uuid import UUID
            record = EvidenceDBStorage.get(db, UUID(evidence_id))
        except (ValueError, AttributeError):
            record = EvidenceDBStorage.get_by_legacy_id(db, evidence_id)

        if not record:
            raise HTTPException(status_code=404, detail="Evidence not found")

        # A phone conversation text has no file: it is written from the phone's records (02 section 9.7)
        if record.source_type == "phone_text":
            from fastapi.responses import PlainTextResponse
            text_row = db.get(EvidenceDocumentText, record.id)
            if text_row is None:
                raise HTTPException(status_code=404, detail="This conversation's text is not written yet")
            return PlainTextResponse(text_row.content or "", headers={"Content-Disposition": "inline"})

        # A phone file kept inside an uploaded archive has no path of its own: the phone file reader serves it
        # straight from the archive (cb-media item F). A phone file from a folder upload is served from disk below.
        if record.source_type == "phone_file" and str(record.stored_path or "").startswith("phone-file:"):
            return _phone_file_response(db, record, range_header)

        # Primary path: serve from backend disk
        filename = record.original_filename or "file"
        stored_path = record.stored_path

        file_path = _resolve_stored_path(stored_path)
        if not file_path or not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found on disk")

        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type=content_type,
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _phone_file_response(db: Session, record, range_header: Optional[str] = None):
    """An archive-kept phone file, read from the archive. A byte range is answered with 206 (the member is
    decompressed up to the start), so audio and video can be seeked and Safari plays them; past the end is 416."""
    from urllib.parse import quote

    from services.phone import media as phone_media
    from services.ranged_stream import ranged_response

    try:
        _name, size, opener = phone_media.content(db.connection(), record.case_id, record.source_ref)
    except phone_media.ContentRefused as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    filename = record.original_filename or "file"

    def open_member():
        handle = opener()
        if handle is None:  # the archive changed between the check and the read
            raise HTTPException(status_code=409, detail="The uploaded archive changed while this file was being "
                                                        "opened. Try again.")
        return handle

    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return ranged_response(range_header, open_member, size, content_type, {
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": "inline; filename*=UTF-8''%s" % quote(filename)})


def _load_pymupdf():
    """The PDF rendering library, or None where it is not installed.

    PyMuPDF is declared in requirements.txt. If an incomplete installation
    cannot load it, the page-image endpoint answers 503 while the rest of
    this router keeps working. ``pymupdf`` is the
    current import name; ``fitz`` is the same library's older name, kept as
    a fallback for environments that predate the rename.
    """
    try:
        import pymupdf
        return pymupdf
    except Exception:
        try:
            import fitz
            return fitz
        except Exception:
            return None


@router.get("/{evidence_id}/page/{page_number}/image")
async def get_evidence_page_image(
    request: Request,
    evidence_id: str,
    page_number: int = PathParam(ge=1),
    width: int = Query(1200, ge=100, le=3000),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Render one page of a PDF evidence file as a PNG.

    This is the image a stored source rectangle refers to: the page as
    displayed, with any page rotation already applied by the library, so a
    viewer drawing a locator's rectangle as fractions of this image places
    it where the value was actually read.  The caller chooses only the
    width; height follows from the page's own aspect ratio.

    A page is rendered once and kept (services/page_image_cache.py); the
    answer carries an ETag with ``private, no-cache``, so every view runs
    the access check above and the lookup here, and a browser holding the
    image gets a 304.  The database work and the render run off the event
    loop; a render waits for one of the render slots, and is skipped when
    the browser has gone away while it waited.
    """
    file_path, sha256 = await run_in_threadpool(_page_image_source, db, evidence_id)
    entry = await run_in_threadpool(page_image_cache.entry_for, file_path, sha256, page=page_number, width=width)

    def render():
        pdf_library = _load_pymupdf()
        if pdf_library is None:
            raise HTTPException(
                status_code=503,
                detail="Page rendering is unavailable: PyMuPDF is not installed on this server",
            )
        try:
            document = pdf_library.open(file_path)
        except Exception:
            raise HTTPException(status_code=422, detail="The file could not be opened as a PDF")
        try:
            return render_page_png(document, page_number=page_number, width=width), document.page_count
        except PageRenderError as error:
            # The service's messages are written to be shown to the person who
            # asked, unedited; a page that does not exist is a 404 like any
            # other missing resource.
            raise HTTPException(status_code=404, detail=str(error))
        finally:
            document.close()

    return await page_image_cache.serve(request, entry, render)


def _page_image_source(db: Session, evidence_id: str):
    """(path, sha256) of a PDF evidence file, or the 404/400 a page request gets."""
    # Look up by UUID or legacy ID, as get_evidence_file does.
    record = _evidence_record_for_id(db, evidence_id)
    if not record:
        raise HTTPException(status_code=404, detail="Evidence not found")

    file_path = _resolve_stored_path(record.stored_path)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    if file_path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="File is not a PDF")
    return file_path, record.sha256


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
    db: Session = Depends(get_db),
):
    """
    Extract and return key frames from a video evidence file.
    Frames are cached so subsequent requests are instant.
    """
    from services.evidence_db_storage import EvidenceDBStorage
    from uuid import UUID

    record = None
    try:
        record = await run_in_threadpool(EvidenceDBStorage.get, db, UUID(evidence_id))
    except (ValueError, AttributeError):
        record = await run_in_threadpool(EvidenceDBStorage.get_by_legacy_id, db, evidence_id)
    if not record:
        raise HTTPException(status_code=404, detail="Evidence not found")

    stored_path = record.stored_path
    if not stored_path:
        raise HTTPException(status_code=404, detail="File path not found")

    video_path = _resolve_stored_path(stored_path) or Path(stored_path)
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
        "filename": record.original_filename or video_path.name,
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


def _verify_evidence_case_access(
    case_id: str,
    current_user: User,
    db: Session,
    required_permission: tuple[str, str] = ("evidence", "upload"),
) -> UUID:
    from services.case_service import CaseAccessDenied, CaseNotFound, check_case_access

    try:
        case_uuid = UUID(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid case_id") from exc

    try:
        check_case_access(db, case_uuid, current_user, required_permission=required_permission)
    except CaseNotFound:
        raise HTTPException(status_code=404, detail="Case not found")
    except CaseAccessDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return case_uuid


@router.put("/relevance")
@records('evidence_relevance_set', lambda c: 'change' if c['body'].get('is_relevant', True) else 'set_aside', subject_type='evidence', subject=lambda c: ','.join(map(str, c['body'].get('evidence_ids') or []))[:200], field='relevance')
def set_evidence_relevance(
    body: SetRelevanceRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark evidence files as relevant or non-relevant."""
    from services.evidence_db_storage import EvidenceDBStorage
    from uuid import UUID

    if not body.evidence_ids:
        raise HTTPException(status_code=400, detail="No evidence IDs provided")
    file_uuids = []
    for eid in body.evidence_ids:
        try:
            file_uuids.append(UUID(eid))
        except ValueError:
            rec = EvidenceDBStorage.get_by_legacy_id(db, eid)
            if rec:
                file_uuids.append(rec.id)
    updated = EvidenceDBStorage.set_relevance(db, file_uuids, body.is_relevant)
    db.commit()
    return {"updated": updated, "is_relevant": body.is_relevant}


@router.post("/tags/add")
def add_evidence_tags(
    body: TagsAddRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Add tags to one or more evidence records."""
    _verify_evidence_case_access(body.case_id, current_user, db)
    updated = EvidenceDBStorage.add_tags(db, body.evidence_ids, body.tags)
    db.commit()
    return {"updated": updated, "tags": body.tags}


@router.post("/tags/remove")
def remove_evidence_tags(
    body: TagsRemoveRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Remove tags from one or more evidence records."""
    _verify_evidence_case_access(body.case_id, current_user, db)
    updated = EvidenceDBStorage.remove_tags(db, body.evidence_ids, body.tags)
    db.commit()
    return {"updated": updated, "tags": body.tags}


@router.post("/tags/set")
def set_evidence_tags(
    body: TagsSetRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Replace the tag list on a single evidence record."""
    _verify_evidence_case_access(body.case_id, current_user, db)
    ok = EvidenceDBStorage.set_tags(db, body.evidence_id, body.tags)
    if not ok:
        raise HTTPException(status_code=404, detail="Evidence not found")
    db.commit()
    return {"ok": True, "tags": sorted(set(body.tags or []))}


@router.get("/tags")
def get_case_tags(
    case_id: str = Query(...),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Return the case's evidence tag cloud."""
    case_uuid = _verify_evidence_case_access(case_id, current_user, db, ("case", "view"))
    return {"tags": EvidenceDBStorage.get_tag_counts(db, case_uuid)}


@router.get("/wiretap/processed")
def list_wiretap_processed(
    case_id: str = Query(..., description="Case ID"),
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


def _evidence_by_name(db: Session, current_user: User, filename: str, case_id: str, evidence_file_id: Optional[str]):
    """The one file a name (or name + id) points at in a case the user can see. A name several visible files share is
    a 409 with the candidates, never a guess; a missing name is None."""
    from services.evidence_db_storage import EvidenceDBStorage
    from uuid import UUID

    try:
        case_uuid = UUID(case_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="case_id is not a case id")
    _check_engine_jobs_access(db, case_id, current_user)
    found = EvidenceDBStorage.find_all_by_filename(db, filename, case_uuid)
    if evidence_file_id:
        found = [f for f in found if str(f.id) == str(evidence_file_id)]
    if len(found) > 1:
        raise HTTPException(status_code=409, detail={
            "reason": f"{len(found)} files in this case are called {filename}; choose one.",
            "candidates": EvidenceDBStorage.filename_candidates(found)})
    return found[0] if found else None


@router.get("/by-filename/{filename}")
def get_evidence_by_filename(
    filename: str,
    case_id: str = Query(..., description="Case ID"),
    evidence_file_id: Optional[str] = Query(None, description="Which file, when several share the name"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Find evidence by original filename and return file info.

    This endpoint helps the frontend locate evidence IDs from document names stored in entity citations. A name
    shared by several visible files of the case answers 409 with the candidates.
    """
    record = _evidence_by_name(db, current_user, filename, case_id, evidence_file_id)
    if record:
        return {
            "found": True,
            "evidence_id": str(record.id),
            "case_id": str(record.case_id),
            "original_filename": record.original_filename,
            "stored_path": record.stored_path,
            "summary": record.summary,
        }
    return {"found": False, "message": f"No evidence file found with name: {filename}"}


@router.get("/summary/{filename}")
def get_document_summary(
    filename: str,
    case_id: str = Query(..., description="Case ID"),
    evidence_file_id: Optional[str] = Query(None, description="Which file, when several share the name"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Get the AI-generated summary for a document.

    Returns the summary stored on the EvidenceFile record in Postgres. A name shared by several visible files of
    the case answers 409 with the candidates.
    """
    record = _evidence_by_name(db, current_user, filename, case_id, evidence_file_id)
    summary = record.summary if record else None
    return {
        "filename": filename,
        "case_id": case_id,
        "evidence_file_id": str(record.id) if record else None,
        "summary": summary,
        "has_summary": summary is not None,
    }


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

        case_data_dir = EVIDENCE_ROOT_DIR / case_id
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
            await run_in_threadpool(check_case_access, db, UUID(request.case_id), current_user, required_permission=("evidence", "upload"))
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

        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=(
                "Legacy folder profile test processing has been retired. "
                "Use folder context plus evidence-engine processing instead."
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# File-level entity & relationship endpoints (Neo4j)
# ---------------------------------------------------------------------------


@router.get("/{evidence_id}/entities")
def get_file_entities(
    evidence_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Return entities extracted from a specific evidence file."""
    from services.evidence_db_storage import EvidenceDBStorage
    from uuid import UUID

    try:
        eid = UUID(evidence_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid evidence ID")

    file_rec = EvidenceDBStorage.get(db, eid)
    if not file_rec:
        raise HTTPException(status_code=404, detail="File not found")

    filename = file_rec.original_filename
    case_id = str(file_rec.case_id)

    query = """
    MATCH (n)
    WHERE n.case_id = $case_id AND $filename IN n.source_files
    RETURN n.id AS id, n.key AS key, n.name AS name, labels(n) AS labels,
           n.specific_type AS specific_type, n.confidence AS confidence
    ORDER BY n.confidence DESC
    LIMIT 50
    """
    results = neo4j_service.run_cypher(query, {"case_id": case_id, "filename": filename})
    entities = []
    for r in results:
        labels = [l for l in r["labels"] if l not in ("_Entity",)]
        category = labels[0] if labels else "Other"
        entities.append({
            "id": r["id"],
            "key": r["key"],
            "name": r["name"],
            "category": category,
            "specific_type": r["specific_type"],
            "confidence": r["confidence"],
        })
    return entities


@router.get("/{evidence_id}/relationships")
def get_file_relationships(
    evidence_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Return relationships extracted from a specific evidence file."""
    from services.evidence_db_storage import EvidenceDBStorage
    from uuid import UUID

    try:
        eid = UUID(evidence_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid evidence ID")

    file_rec = EvidenceDBStorage.get(db, eid)
    if not file_rec:
        raise HTTPException(status_code=404, detail="File not found")

    filename = file_rec.original_filename
    case_id = str(file_rec.case_id)

    query = """
    MATCH (a)-[r]->(b)
    WHERE r.case_id = $case_id AND $filename IN r.source_files
    RETURN a.name AS source_name, b.name AS target_name,
           type(r) AS type, r.detail AS detail, r.confidence AS confidence
    ORDER BY r.confidence DESC
    LIMIT 50
    """
    results = neo4j_service.run_cypher(query, {"case_id": case_id, "filename": filename})
    return [
        {
            "source_entity_name": r["source_name"],
            "target_entity_name": r["target_name"],
            "type": r["type"],
            "detail": r["detail"],
            "confidence": r["confidence"],
        }
        for r in results
    ]
