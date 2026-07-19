"""
Evidence Router

Handles uploading evidence files and triggering ingestion processing.
File storage and AI processing are delegated to the evidence engine when enabled.
"""

import asyncio
import hashlib
import os
import logging
import mimetypes
import subprocess
import shutil
import uuid as uuid_mod
import zipfile
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from starlette.datastructures import UploadFile as StarletteUploadFile
from starlette.requests import ClientDisconnect

from services.wiretap_tracking import list_processed_wiretaps, is_wiretap_processed, mark_wiretap_processed
from services.wiretap_service import check_wiretap_suitable, process_wiretap_folder_async
from services.background_task_storage import background_task_storage, TaskStatus
from services.evidence_processing_service import process_db_files
from services.neo4j_service import neo4j_service
from services.cypher_generator import generate_cypher_from_graph
from services.evidence_db_storage import EvidenceDBStorage
from services import evidence_engine_client
from .auth import get_current_user
from routers.case_access import (
    authorize_case,
    case_access_dependency,
    request_json_payload,
)
from routers.users import get_current_db_user
from fastapi import Query, status
from postgres.session import get_db
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.user import User
from sqlalchemy import select
from sqlalchemy.orm import Session
from config import BASE_DIR, EVIDENCE_DATA_ROOT, USE_EVIDENCE_ENGINE
from datetime import datetime

logger = logging.getLogger(__name__)
EVIDENCE_ROOT_DIR = EVIDENCE_DATA_ROOT

# Uploaded bytes land here first so large evidence and Cellebrite archives are
# streamed to disk instead of being held in memory.
_UPLOAD_STAGING_ROOT = EVIDENCE_ROOT_DIR / "_staging"
_STAGE_CHUNK_SIZE = 1024 * 1024

# Cellebrite Reader exports commonly include these platform sidecars.
_ARCHIVE_SKIP_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
_CELLEBRITE_NS_MARKER = b"http://pa.cellebrite.com/report/2.0"


# Hard limit on file IDs per single processing request.
# Clients must split larger batches into chunks of this size.
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
    for evidence_id in evidence_ids:
        record = _evidence_record_for_id(db, evidence_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Evidence not found")
        authorize_case(db, record.case_id, current_user, permission)

    if request.method == "GET" and request.url.path.startswith("/api/evidence/engine/jobs/"):
        job_id = request.path_params.get("job_id")
        record = EvidenceDBStorage.find_by_engine_job_id(db, str(job_id)) if job_id else None
        if record is None:
            raise HTTPException(status_code=404, detail="Evidence job not found")
        authorize_case(db, record.case_id, current_user, permission)


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
    return {
        "id": str(record.id),
        "case_id": str(record.case_id),
        "original_filename": record.original_filename,
        "stored_path": record.stored_path or "",
        "size": record.size,
        "sha256": record.sha256,
        "status": record.status,
        "duplicate_of": str(record.duplicate_of_id) if record.duplicate_of_id else None,
        "created_at": record.created_at.isoformat() if record.created_at else "",
        "processed_at": record.processed_at.isoformat() if record.processed_at else None,
        "last_error": record.last_error,
        "engine_job_id": record.engine_job_id,
        "summary": record.summary,
        "transcription": record.transcription,
        "entity_count": record.entity_count,
        "relationship_count": record.relationship_count,
        "processing_stale": record.processing_stale,
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


def _is_cellebrite_report_root(dir_path: Path) -> bool:
    """Cheaply detect a Cellebrite UFED report root by reading XML headers."""
    try:
        for xml_file in dir_path.glob("*.xml"):
            try:
                with xml_file.open("rb") as handle:
                    if _CELLEBRITE_NS_MARKER in handle.read(4096):
                        return True
            except (OSError, IOError):
                continue
    except (OSError, IOError):
        return False
    return False


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


def _extract_archive_to_staging(zip_path: Path, extract_dir: Path) -> List[dict]:
    """
    Extract a zip safely into staging and return upload metadata.

    This is the Neil flow, adapted for Postgres storage: a single large
    Cellebrite zip can be posted as one multipart part, then unpacked server
    side with zip-slip protection.
    """
    extract_dir.mkdir(parents=True, exist_ok=True)
    extract_root = extract_dir.resolve()
    uploads: List[dict] = []

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

            uploads.append({
                "original_filename": relative_path.name,
                "staged_path": target,
                "sha256": hasher.hexdigest(),
                "size": size,
                "relative_path": str(relative_path).replace("\\", "/"),
            })

    return uploads


def _find_cellebrite_report_roots(extract_dir: Path) -> List[str]:
    roots: List[str] = []
    if _is_cellebrite_report_root(extract_dir):
        roots.append("")
    try:
        for child in extract_dir.iterdir():
            if child.is_dir() and _is_cellebrite_report_root(child):
                roots.append(child.name)
    except OSError:
        pass
    return roots


def _find_cellebrite_report_roots_from_uploads(uploads: List[dict]) -> List[str]:
    """Detect Cellebrite report roots from staged folder-upload metadata."""
    roots: List[str] = []
    seen = set()
    for upload in uploads:
        relative_path = _safe_relative_path(upload.get("relative_path") or "")
        if relative_path.suffix.lower() != ".xml":
            continue
        try:
            with Path(upload["staged_path"]).open("rb") as handle:
                if _CELLEBRITE_NS_MARKER not in handle.read(4096):
                    continue
        except (OSError, IOError):
            continue

        root = "" if len(relative_path.parts) == 1 else str(relative_path.parent).replace("\\", "/")
        if root not in seen:
            seen.add(root)
            roots.append(root)
    return roots


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


def _resolve_case_folder(case_id: str, folder_path: str) -> Path:
    case_data_dir = EVIDENCE_ROOT_DIR / case_id
    full_folder_path = (case_data_dir / folder_path).resolve()
    try:
        full_folder_path.relative_to(case_data_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Path outside case directory")
    return full_folder_path


def _combine_case_relative_path(prefix_parts: List[str], root: str) -> str:
    root_parts = [part for part in PurePosixPath(root).parts if part not in ("", ".")]
    parts = [*prefix_parts, *root_parts]
    return str(PurePosixPath(*parts)).replace("\\", "/") if parts else "."


async def _enqueue_cellebrite_engine_job(
    *,
    case_id: str,
    folder_path: str,
    evidence_folder_id: Optional[UUID] = None,
    current_user: User,
    force: bool,
    fail_on_duplicate: bool,
) -> tuple[dict, dict]:
    if not USE_EVIDENCE_ENGINE:
        raise HTTPException(status_code=503, detail="Evidence engine is not enabled")

    full_folder_path = _resolve_case_folder(case_id, folder_path)
    if not full_folder_path.exists() or not full_folder_path.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    detection = await evidence_engine_client.check_cellebrite_folder(
        case_id,
        folder_path=folder_path,
    )
    if not detection.get("suitable"):
        raise HTTPException(
            status_code=400,
            detail=detection.get("message", "Not a valid Cellebrite report"),
        )

    if fail_on_duplicate and detection.get("duplicate") and not force:
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

    job = await evidence_engine_client.create_cellebrite_job(
        case_id,
        folder_path=folder_path,
        evidence_folder_id=str(evidence_folder_id) if evidence_folder_id else None,
        report_name=detection.get("report_name") or full_folder_path.name,
        report_key=detection.get("report_key"),
        owner=current_user.email,
        force=force,
        requested_by_user_id=str(current_user.id) if current_user.id else None,
    )
    return job, detection


def _move_staged_uploads_to_case(
    *,
    case_id_text: str,
    uploads: List[dict],
    root_parts: List[str],
) -> None:
    """Move staged files into a case directory without registering DB rows."""
    case_dir = EVIDENCE_ROOT_DIR / case_id_text
    case_dir.mkdir(parents=True, exist_ok=True)
    case_resolved = case_dir.resolve()

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
            if target.exists():
                target.unlink()
            shutil.move(str(staged_path), str(target))


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
) -> List[dict]:
    """
    Move staged files into the case directory and optionally create DB rows.

    Cellebrite archives use register_files=False: the raw extraction must exist
    on disk for the phone ingester, but only linked media should become
    `source_type='cellebrite'` evidence rows during the Cellebrite ingest.
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
            if target.exists():
                target.unlink()
            shutil.move(str(staged_path), str(target))

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
    size: int
    sha256: str
    status: str
    duplicate_of: Optional[str] = None
    created_at: str
    processed_at: Optional[str] = None
    last_error: Optional[str] = None
    summary: Optional[str] = None  # Document summary if available
    transcription: Optional[str] = None  # Full audio transcript if available
    entity_count: Optional[int] = None
    relationship_count: Optional[int] = None
    engine_job_id: Optional[str] = None  # Evidence engine job ID for progress tracking
    processing_stale: bool = False


class EvidenceListResponse(BaseModel):
    files: List[EvidenceRecord]


class UploadResponse(BaseModel):
    """Response for file uploads - can be synchronous or background."""
    files: Optional[List[EvidenceRecord]] = None  # For synchronous uploads
    task_id: Optional[str] = None  # Single task ID (for backwards compatibility)
    task_ids: Optional[List[str]] = None  # Multiple task IDs (for folder uploads)
    job_ids: Optional[List[str]] = None  # Evidence engine job IDs (for WebSocket progress)
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


@router.get("", response_model=EvidenceListResponse)
async def list_evidence(
    case_id: str = Query(..., description="Case ID"),
    status_filter: Optional[str] = Query(None, alias="status"),
    include_cellebrite_artifacts: bool = False,
    user: dict = Depends(get_current_user),
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
        db_files = EvidenceDBStorage.list_files(db, case_id=UUID(case_id), status=status_filter)
        if not include_cellebrite_artifacts:
            db_files = [row for row in db_files if row.source_type != "cellebrite"]
        return {"files": [_evidence_record_from_db(f) for f in db_files]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




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

        # Walk the case directory for files without evidence records. Prune
        # Cellebrite report roots; those are ingested through the dedicated
        # phone-report pipeline and can contain tens of thousands of artifacts.
        created_count = 0
        grouped: Dict[Optional[UUID], List[dict]] = defaultdict(list)
        skipped_cellebrite_dirs: List[str] = []

        for dirpath, dirnames, filenames in os.walk(case_dir):
            current_dir = Path(dirpath)
            if current_dir == _UPLOAD_STAGING_ROOT:
                dirnames[:] = []
                continue
            if _is_cellebrite_report_root(current_dir):
                skipped_cellebrite_dirs.append(str(current_dir.relative_to(case_dir)) or ".")
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
        if skipped_cellebrite_dirs:
            logger.info(
                "Filesystem sync: skipped %s Cellebrite report folder(s) for case %s: %s",
                len(skipped_cellebrite_dirs),
                case_id,
                skipped_cellebrite_dirs[:5],
            )
        db.commit()

        return {"created": created_count, "message": f"Synced {created_count} file(s)"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/duplicates/{sha256}", response_model=EvidenceListResponse)
async def find_duplicates(
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
    a single .zip server-side; Cellebrite report archives are staged on disk but
    not registered as generic evidence rows because the dedicated Cellebrite
    ingester registers linked media with `source_type='cellebrite'`.
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
        try:
            check_case_access(db, case_uuid, current_user, required_permission=("evidence", "upload"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        folder_uuid = UUID(folder_id) if folder_id else None
        if folder_uuid:
            folder = EvidenceDBStorage.get_folder(db, folder_uuid)
            if not folder or str(folder.case_id) != case_id:
                raise HTTPException(status_code=404, detail="Target folder not found")

        staging_dir = _UPLOAD_STAGING_ROOT / uuid_mod.uuid4().hex
        archive_extract_dir: Optional[Path] = None
        try:
            uploads = await run_in_threadpool(_stage_upload_files, files, staging_dir)
            if not uploads:
                raise HTTPException(status_code=400, detail="No extractable files uploaded")

            cellebrite_roots: List[str] = []
            if is_archive:
                zip_path = Path(uploads[0]["staged_path"])
                if not zipfile.is_zipfile(zip_path):
                    raise HTTPException(status_code=400, detail="Uploaded archive is not a valid .zip file")
                archive_extract_dir = staging_dir / "_extracted"
                uploads = await run_in_threadpool(_extract_archive_to_staging, zip_path, archive_extract_dir)
                try:
                    zip_path.unlink(missing_ok=True)
                except OSError:
                    pass
                if not uploads:
                    raise HTTPException(status_code=400, detail="Archive contained no extractable files")
                cellebrite_roots = _find_cellebrite_report_roots(archive_extract_dir)
            elif is_folder:
                cellebrite_roots = _find_cellebrite_report_roots_from_uploads(uploads)

            register_files = not bool(cellebrite_roots)
            if register_files:
                records = _persist_staged_uploads(
                    db=db,
                    case_id=case_uuid,
                    case_id_text=case_id,
                    uploads=uploads,
                    owner=current_user.email,
                    folder_id=folder_uuid,
                    created_by_id=current_user.id,
                    register_files=True,
                )
            else:
                root_parts = _get_folder_parts(db, folder_uuid)
                await run_in_threadpool(
                    _move_staged_uploads_to_case,
                    case_id_text=case_id,
                    uploads=uploads,
                    root_parts=root_parts,
                )
                records = []

            if cellebrite_roots:
                report_folder_ids: Dict[str, Optional[UUID]] = {}
                for root in cellebrite_roots:
                    root_parts = [part for part in PurePosixPath(root).parts if part]
                    if root_parts:
                        report_folder_ids[root] = _get_or_create_folder_chain(
                            db,
                            case_id=case_uuid,
                            parts=root_parts,
                            parent_id=folder_uuid,
                            created_by_id=current_user.id,
                        )
                    else:
                        report_folder_ids[root] = folder_uuid

            db.commit()

            if cellebrite_roots:
                prefix_parts = _get_folder_parts(db, folder_uuid) if folder_uuid else []
                queued_jobs = []
                queued_roots = []
                for root in cellebrite_roots:
                    report_folder = _combine_case_relative_path(prefix_parts, root)
                    job, _detection = await _enqueue_cellebrite_engine_job(
                        case_id=case_id,
                        folder_path=report_folder,
                        evidence_folder_id=report_folder_ids.get(root),
                        current_user=current_user,
                        force=replace_existing,
                        fail_on_duplicate=False,
                    )
                    queued_jobs.append(str(job.get("id")))
                    queued_roots.append(report_folder)

                roots_display = ", ".join(queued_roots)
                return UploadResponse(
                    files=[],
                    job_ids=queued_jobs,
                    message=(
                        "Uploaded Cellebrite archive and queued processing for "
                        f"{roots_display}"
                    ),
                )

            upload_kind = "folder" if is_folder or is_archive else "file"
            return UploadResponse(
                files=records,
                job_ids=None,
                message=f"Uploaded {len(records)} {upload_kind}{'' if len(records) == 1 else 's'}",
            )
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise
        finally:
            try:
                if staging_dir.exists() and not any(staging_dir.iterdir()):
                    staging_dir.rmdir()
            except OSError:
                pass
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

        db_backed_ids, missing_ids = _split_db_backed_legacy(request.file_ids, db)
        if missing_ids:
            raise HTTPException(
                status_code=404,
                detail=f"{len(missing_ids)} file id(s) were not found in Postgres evidence storage",
            )

        messages = []
        job_ids = []

        if db_backed_ids:
            if not request.case_id:
                raise HTTPException(status_code=400, detail="case_id is required for DB-backed evidence files")
            engine_result = await process_db_files(
                db,
                case_id=UUID(request.case_id),
                file_ids=db_backed_ids,
                force_reprocess=False,
                requested_by_user_id=current_user.id,
            )
            job_ids = engine_result.get("job_ids", [])
            if engine_result.get("message"):
                messages.append(engine_result["message"])

        return {
            "task_id": None,
            "job_ids": job_ids or None,
            "message": "; ".join(messages) if messages else "No files to process",
        }
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
                check_case_access(db, UUID(request.case_id), current_user, required_permission=("evidence", "upload"))
            except (CaseNotFound, CaseAccessDenied) as e:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        db_backed_ids, missing_ids = _split_db_backed_legacy(request.file_ids, db)
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
                requested_by_user_id=current_user.id,
            )
            processed += engine_result.get("file_count", 0)
            skipped += engine_result.get("skipped_count", 0)

        return ProcessResponse(processed=processed, skipped=skipped, errors=errors)
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ingestion pipeline not available: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
async def get_evidence_logs(
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
    case_id: str = Query(..., description="Case ID"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Proxy: list all processing jobs from the evidence engine for a case."""
    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(case_id), current_user, required_permission=("case", "view"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        if not USE_EVIDENCE_ENGINE:
            return []

        from postgres.models.evidence import EvidenceFile
        from services.evidence_job_sync import reconcile_jobs_payload
        from uuid import UUID

        jobs = await evidence_engine_client.list_jobs(case_id)
        reconcile_jobs_payload(db, jobs)
        db.commit()

        db_records = list(
            db.scalars(
                select(EvidenceFile).where(EvidenceFile.case_id == UUID(case_id))
            ).all()
        )
        file_ids_by_job_id = {
            str(rec.engine_job_id): str(rec.id)
            for rec in db_records
            if rec.engine_job_id
        }
        for job in jobs:
            job["evidence_file_id"] = file_ids_by_job_id.get(str(job.get("id")))
        return jobs
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Failed to list engine jobs: %s", e)
        return []


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
        db_rec = EvidenceDBStorage.find_by_engine_job_id(db, job_id)
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
            check_case_access(db, UUID(case_id), current_user, required_permission=("case", "edit"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        await evidence_engine_client.delete_job(job_id)
        return {"deleted": 1, "job_id": job_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
            check_case_access(db, UUID(case_id), current_user, required_permission=("case", "edit"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        return await evidence_engine_client.clear_case_jobs(case_id, terminal_only=terminal_only)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wiretap/check")
async def check_wiretap_folder(
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


class CellebriteProcessRequest(BaseModel):
    """Request to process a Cellebrite UFED report folder."""
    case_id: str
    folder_path: str
    force: bool = False
    replace_existing: bool = False


class CellebriteProcessResponse(BaseModel):
    """Response from Cellebrite processing."""
    success: bool
    message: str
    task_id: Optional[str] = None
    job_id: Optional[str] = None
    job_ids: Optional[List[str]] = None


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


# ------------------------------------------------------------------
# Cellebrite UFED Report endpoints
# ------------------------------------------------------------------


@router.get("/cellebrite/check")
async def check_cellebrite_folder(
    case_id: str = Query(..., description="Case ID"),
    folder_path: str = Query(..., description="Relative folder path from case data directory"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Check if a case folder contains a Cellebrite UFED report."""
    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        case_uuid = UUID(case_id)
        try:
            check_case_access(db, case_uuid, current_user, required_permission=("case", "view"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        if not folder_path or ".." in folder_path or folder_path.startswith(("/", "\\")):
            raise HTTPException(status_code=403, detail="Path outside case directory")

        if not USE_EVIDENCE_ENGINE:
            raise HTTPException(status_code=503, detail="Evidence engine is not enabled")

        return await evidence_engine_client.check_cellebrite_folder(
            case_id,
            folder_path=folder_path,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cellebrite/process", response_model=CellebriteProcessResponse)
async def process_cellebrite_folder(
    request: CellebriteProcessRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Queue a Cellebrite UFED report folder for evidence-engine processing."""
    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        case_uuid = UUID(request.case_id)
        try:
            check_case_access(db, case_uuid, current_user, required_permission=("evidence", "upload"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        if (
            not request.folder_path
            or ".." in request.folder_path
            or request.folder_path.startswith(("/", "\\"))
        ):
            raise HTTPException(status_code=403, detail="Path outside case directory")

        force = bool(request.force or request.replace_existing)
        evidence_folder_id = _get_or_create_folder_chain(
            db,
            case_id=case_uuid,
            parts=[
                part
                for part in PurePosixPath(request.folder_path).parts
                if part not in ("", ".", "..")
            ],
            created_by_id=current_user.id,
        )
        db.commit()
        job, detection = await _enqueue_cellebrite_engine_job(
            case_id=request.case_id,
            folder_path=request.folder_path,
            evidence_folder_id=evidence_folder_id,
            current_user=current_user,
            force=force,
            fail_on_duplicate=True,
        )

        return CellebriteProcessResponse(
            success=True,
            message=f"Cellebrite ingestion queued ({detection.get('model_count', 0)} models to process)",
            task_id=None,
            job_id=str(job.get("id")),
            job_ids=[str(job.get("id"))],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{evidence_id}")
async def delete_evidence_file(
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

        # 1. Get the evidence record from Postgres
        db_record = None
        try:
            db_record = EvidenceDBStorage.get(db, UUID(evidence_id))
        except (ValueError, AttributeError):
            db_record = EvidenceDBStorage.get_by_legacy_id(db, evidence_id)

        if not db_record:
            raise HTTPException(status_code=404, detail="Evidence file not found")
        if str(db_record.case_id) != case_id:
            raise HTTPException(status_code=403, detail="Evidence file does not belong to this case")

        # Check if file is currently being processed
        if db_record.status == "processing":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete file while it is being processed. Wait for processing to complete."
            )

        filename = db_record.original_filename
        stored_path = db_record.stored_path
        engine_job_id = db_record.engine_job_id
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
                                db=db,
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

        # 4. Delete physical file from backend disk
        if stored_path:
            file_path = _resolve_stored_path(stored_path) or Path(stored_path)
            if file_path.exists():
                try:
                    file_path.unlink()
                    result_info["file_deleted"] = True
                except Exception as e:
                    logger.warning("Failed to delete physical file: %s", e)

        # 5. Tell evidence engine to clean up its processing copy
        if engine_job_id:
            try:
                await evidence_engine_client.delete_file(case_id, engine_job_id)
            except Exception as e:
                logger.warning("Failed to delete file from evidence engine: %s", e)

        # 6. Delete evidence record from Postgres
        EvidenceDBStorage.delete_record(db, db_record.id)
        db.commit()

        return result_info

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{evidence_id}/file")
async def get_evidence_file(
    evidence_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
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
        record = EvidenceDBStorage.get(db, UUID(evidence_id))
    except (ValueError, AttributeError):
        record = EvidenceDBStorage.get_by_legacy_id(db, evidence_id)
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
async def get_video_frame_image(
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


class EntityLinkRequest(BaseModel):
    case_id: str
    evidence_ids: List[str]
    entity_ids: List[str]


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
async def set_evidence_relevance(
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


@router.put("/relevance/from-theory")
async def set_relevance_from_theory(
    case_id: str = Query(..., description="Case ID"),
    theory_id: str = Query(..., description="Theory ID"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Mark all evidence files linked to a theory as relevant.
    Collects IDs from attached_evidence_ids, attached_document_ids,
    and any evidence files referenced by graph nodes in the theory's snapshot.
    """
    from services.workspace_service import workspace_service
    from services.evidence_db_storage import EvidenceDBStorage
    from uuid import UUID

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
                all_files = EvidenceDBStorage.list_files(db, case_id=UUID(case_id))
                filename_to_id = {
                    (f.original_filename or "").lower(): str(f.id) for f in all_files
                }
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
        file_uuids = []
        for eid in evidence_ids:
            try:
                file_uuids.append(UUID(eid))
            except ValueError:
                rec = EvidenceDBStorage.get_by_legacy_id(db, eid)
                if rec:
                    file_uuids.append(rec.id)
        if file_uuids:
            updated = EvidenceDBStorage.set_relevance(db, file_uuids, True)
            db.commit()

    return {"updated": updated, "theory_id": theory_id, "evidence_ids_marked": list(evidence_ids)}


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


@router.post("/entity-links/add")
def add_entity_links(
    body: EntityLinkRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Link evidence records to case/entity profile IDs."""
    _verify_evidence_case_access(body.case_id, current_user, db)
    updated = EvidenceDBStorage.link_entities(db, body.evidence_ids, body.entity_ids)
    db.commit()
    return {"updated": updated, "entity_ids": body.entity_ids}


@router.post("/entity-links/remove")
def remove_entity_links(
    body: EntityLinkRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Unlink evidence records from case/entity profile IDs."""
    _verify_evidence_case_access(body.case_id, current_user, db)
    updated = EvidenceDBStorage.unlink_entities(db, body.evidence_ids, body.entity_ids)
    db.commit()
    return {"updated": updated, "entity_ids": body.entity_ids}


@router.get("/by-entity")
def list_evidence_by_entity(
    case_id: str = Query(...),
    entity_id: str = Query(...),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Return evidence records in a case linked to a case/entity profile."""
    case_uuid = _verify_evidence_case_access(case_id, current_user, db, ("case", "view"))
    files = EvidenceDBStorage.list_by_entity(db, case_uuid, entity_id)
    return {"files": files, "total": len(files)}


@router.get("/wiretap/processed")
async def list_wiretap_processed(
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


@router.get("/by-filename/{filename}")
async def get_evidence_by_filename(
    filename: str,
    case_id: str = Query(..., description="Case ID"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Find evidence by original filename and return file info.

    This endpoint helps the frontend locate evidence IDs from document names
    stored in entity citations.
    """
    from services.evidence_db_storage import EvidenceDBStorage
    from uuid import UUID

    try:
        case_uuid = UUID(case_id)
        record = EvidenceDBStorage.find_by_filename(db, filename, case_id=case_uuid)
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary/{filename}")
async def get_document_summary(
    filename: str,
    case_id: str = Query(..., description="Case ID"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get the AI-generated summary for a document.

    Returns the summary stored on the EvidenceFile record in Postgres.
    """
    from services.evidence_db_storage import EvidenceDBStorage
    from uuid import UUID

    try:
        case_uuid = UUID(case_id)
        record = EvidenceDBStorage.find_by_filename(db, filename, case_id=case_uuid)
        summary = record.summary if record else None
        return {
            "filename": filename,
            "case_id": case_id,
            "summary": summary,
            "has_summary": summary is not None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/folder-summary/{folder_name}")
async def get_folder_summary(
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
async def get_transcription_translation(
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
async def list_folder_files(
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
async def test_folder_profile(
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
async def get_file_entities(
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
    RETURN coalesce(n.id, n.key) AS id, n.key AS node_key, n.name AS name, labels(n) AS labels,
           n.specific_type AS specific_type, n.confidence AS confidence,
           n.latitude AS latitude, n.longitude AS longitude,
           n.location_raw AS location_raw,
           n.location_formatted AS location_formatted,
           n.location_name AS location_name,
           n.geocoding_confidence AS geocoding_confidence,
           n.location_source AS location_source,
           n.location_corrected_at AS location_corrected_at,
           n.location_corrected_by AS location_corrected_by,
           n.location_correction_source AS location_correction_source,
           n.location_correction_address AS location_correction_address,
           n.last_location_relocation_key AS last_location_relocation_key
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
            "key": r["node_key"],
            "node_key": r["node_key"],
            "name": r["name"],
            "category": category,
            "specific_type": r["specific_type"],
            "confidence": r["confidence"],
            "latitude": r["latitude"],
            "longitude": r["longitude"],
            "location_raw": r["location_raw"],
            "location_formatted": r["location_formatted"],
            "location_name": r["location_name"],
            "geocoding_confidence": r["geocoding_confidence"],
            "location_source": r["location_source"],
            "location_corrected_at": r["location_corrected_at"],
            "location_corrected_by": r["location_corrected_by"],
            "location_correction_source": r["location_correction_source"],
            "location_correction_address": r["location_correction_address"],
            "last_location_relocation_key": r["last_location_relocation_key"],
        })
    return entities


@router.get("/{evidence_id}/relationships")
async def get_file_relationships(
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
