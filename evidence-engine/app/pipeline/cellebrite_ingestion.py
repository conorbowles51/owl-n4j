import asyncio
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus
from app.services.redis_client import publish_progress

logger = logging.getLogger(__name__)

STEP_PROGRESS = {
    "1": (JobStatus.EXTRACTING_TEXT, 0.02),
    "2": (JobStatus.EXTRACTING_TEXT, 0.06),
    "3": (JobStatus.EXTRACTING_TEXT, 0.10),
    "4": (JobStatus.EXTRACTING_TEXT, 0.15),
    "5": (JobStatus.WRITING_GRAPH, 0.20),
    "6": (JobStatus.EXTRACTING_ENTITIES, 0.30),
    "7": (JobStatus.EXTRACTING_ENTITIES, 0.38),
    "8": (JobStatus.WRITING_GRAPH, 0.45),
    "8.5": (JobStatus.WRITING_GRAPH, 0.82),
    "9": (JobStatus.WRITING_GRAPH, 0.90),
}


def _ensure_cellebrite_imports() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    candidates = [
        repo_root / "backend",
        Path("/backend"),
        repo_root / "ingestion" / "scripts",
        Path("/ingestion") / "scripts",
    ]
    for candidate in reversed(candidates):
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))

    database_url = os.getenv("DATABASE_URL", "")
    if database_url.startswith("postgresql+asyncpg://"):
        os.environ["DATABASE_URL"] = database_url.replace(
            "postgresql+asyncpg://",
            "postgresql+psycopg://",
            1,
        )


async def _update_job(
    job: Job,
    status: JobStatus,
    progress: float,
    db: AsyncSession,
    message: str,
    error_message: str | None = None,
) -> None:
    progress = max(0.0, min(progress, 1.0))
    job.status = status
    job.progress = progress
    if error_message is not None:
        job.error_message = error_message
    await db.commit()

    payload: dict[str, Any] = {
        "job_id": str(job.id),
        "status": status.value,
        "progress": progress,
        "message": message,
    }
    if error_message is not None:
        payload["error_message"] = error_message
    await publish_progress(str(job.id), payload)


def _progress_from_log(message: str, previous: float) -> tuple[JobStatus, float]:
    step_match = re.search(r"Step\s+([0-9]+(?:\.5)?)(?:/9)?:", message)
    if step_match:
        return STEP_PROGRESS.get(step_match.group(1), (JobStatus.WRITING_GRAPH, previous))

    written_match = re.search(r"Written\s+([0-9]+)/([0-9]+)\s+models", message)
    if written_match:
        done = int(written_match.group(1))
        total = max(int(written_match.group(2)), 1)
        return JobStatus.WRITING_GRAPH, 0.45 + (0.35 * (done / total))

    registered_match = re.search(r"Registered\s+([0-9]+)/([0-9]+)\s+media files", message)
    if registered_match:
        done = int(registered_match.group(1))
        total = max(int(registered_match.group(2)), 1)
        return JobStatus.WRITING_GRAPH, 0.90 + (0.08 * (done / total))

    if "Ingestion complete" in message or "Cellebrite ingestion completed" in message:
        return JobStatus.COMPLETED, 1.0
    if message.startswith("ERROR") or "failed" in message.lower():
        return JobStatus.FAILED, previous
    return JobStatus.WRITING_GRAPH, previous


def _run_cellebrite_ingestion_sync(
    *,
    folder_path: Path,
    case_id: str,
    owner: str | None,
    force: bool,
    created_by_id: str | None,
    evidence_folder_id: str | None,
    log_callback,
) -> dict[str, Any]:
    _ensure_cellebrite_imports()

    from postgres.session import get_background_session
    from services.cellebrite_service import check_cellebrite_report, _import_cellebrite
    from services.evidence_db_storage import EvidenceDBStorage

    case_uuid = UUID(case_id)
    created_by_uuid = UUID(created_by_id) if created_by_id else None
    evidence_folder_uuid = UUID(evidence_folder_id) if evidence_folder_id else None

    def _log(message: str) -> None:
        log_callback(message)
        with get_background_session() as db:
            EvidenceDBStorage.add_log(
                db,
                case_id=case_uuid,
                evidence_file_id=None,
                filename=None,
                level="info",
                message=message,
            )

    precheck = check_cellebrite_report(folder_path, case_id=case_id)
    if not precheck.get("suitable"):
        reason = precheck.get("message", "Not a valid Cellebrite report")
        _log(f"ERROR: {reason}")
        return {"status": "error", "reason": reason}

    if precheck.get("duplicate") and not force:
        existing = precheck.get("existing") or {}
        _log(
            "ERROR: Refusing to ingest duplicate phone report "
            f"{existing.get('report_key') or precheck.get('report_key')}. "
            "Set replace existing to re-ingest."
        )
        return {"status": "error", "reason": "duplicate", "existing": existing}

    if force and precheck.get("duplicate"):
        existing = precheck.get("existing") or {}
        existing_key = existing.get("report_key")
        if existing_key:
            from services.neo4j_service import neo4j_service

            deleted = neo4j_service.delete_phone_report(case_id, existing_key)
            with get_background_session() as db:
                evidence_deleted = EvidenceDBStorage.delete_by_cellebrite_report_key(
                    db,
                    case_uuid,
                    existing_key,
                )
            _log(
                f"Replaced existing phone report {existing_key}: "
                f"removed {deleted.get('deleted_nodes', 0)} nodes "
                f"+ {deleted.get('deleted_phone_report', 0)} PhoneReport node(s) "
                f"+ {evidence_deleted} evidence row(s)."
            )

    _, ingest_cellebrite_report = _import_cellebrite()
    with get_background_session() as db:
        return ingest_cellebrite_report(
            report_dir=folder_path,
            case_id=case_id,
            log_callback=_log,
            owner=owner,
            evidence_db=db,
            created_by_id=created_by_uuid,
            evidence_root_folder_id=evidence_folder_uuid,
        )


async def run_cellebrite_pipeline(job_id: str, db: AsyncSession) -> None:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one()

    payload = job.merge_payload or {}
    folder_path = Path(job.file_path or "")
    if not folder_path.exists() or not folder_path.is_dir():
        await _update_job(
            job,
            JobStatus.FAILED,
            job.progress or 0.0,
            db,
            "Cellebrite report folder not found",
            error_message=f"Folder not found: {folder_path}",
        )
        return

    queue: asyncio.Queue[str] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def log_from_thread(message: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, message)

    await _update_job(job, JobStatus.PENDING, 0.0, db, "Queued Cellebrite ingestion")

    worker = asyncio.create_task(
        asyncio.to_thread(
            _run_cellebrite_ingestion_sync,
            folder_path=folder_path,
            case_id=job.case_id,
            owner=payload.get("owner"),
            force=bool(payload.get("force")),
            created_by_id=payload.get("requested_by_user_id"),
            evidence_folder_id=payload.get("evidence_folder_id") or job.source_folder_id,
            log_callback=log_from_thread,
        )
    )

    try:
        last_progress = job.progress or 0.0
        while not worker.done():
            try:
                message = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            status, last_progress = _progress_from_log(message, last_progress)
            if status is not JobStatus.FAILED:
                await _update_job(job, status, last_progress, db, message)

        ingestion_result = await worker
        while not queue.empty():
            message = queue.get_nowait()
            status, last_progress = _progress_from_log(message, last_progress)
            if status is not JobStatus.FAILED:
                await _update_job(job, status, last_progress, db, message)

        if ingestion_result.get("status") == "success":
            job.entity_count = int(ingestion_result.get("total_nodes", 0) or 0)
            job.relationship_count = int(ingestion_result.get("total_relationships", 0) or 0)
            await _update_job(
                job,
                JobStatus.COMPLETED,
                1.0,
                db,
                (
                    "Cellebrite ingestion completed: "
                    f"{job.entity_count} nodes, {job.relationship_count} relationships"
                ),
            )
            return

        reason = ingestion_result.get("reason", "Unknown Cellebrite ingestion error")
        await _update_job(
            job,
            JobStatus.FAILED,
            job.progress or last_progress,
            db,
            f"Cellebrite ingestion failed: {reason}",
            error_message=str(reason),
        )
    except asyncio.CancelledError:
        await _update_job(
            job,
            JobStatus.FAILED,
            job.progress or 0.0,
            db,
            "Cancelled (worker timeout or shutdown)",
            error_message="Cellebrite job cancelled during processing.",
        )
        raise
    except Exception as exc:
        logger.exception("Cellebrite pipeline failed for job %s", job_id)
        await _update_job(
            job,
            JobStatus.FAILED,
            job.progress or 0.0,
            db,
            f"Cellebrite ingestion failed: {exc}",
            error_message=str(exc),
        )
        raise
