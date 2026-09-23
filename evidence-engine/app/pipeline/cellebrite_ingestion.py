import asyncio
import logging
import os
import re
import sys
import threading
import time
from contextlib import suppress
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


def _ensure_backend_imports() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    candidates = [
        repo_root / "backend",
        Path("/backend"),
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
    pause_check=None,
) -> dict[str, Any]:
    _ensure_backend_imports()

    from postgres.session import get_background_session
    from services.evidence_db_storage import EvidenceDBStorage
    from app.pipeline.cellebrite.detection import check_cellebrite_report
    from app.pipeline.cellebrite.ingestion import ingest_cellebrite_report

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

    from app.pipeline.cellebrite.ingestion import detect_cellebrite_xml
    from app.pipeline.cellebrite.recovery import Recovery, report_lock
    boundary = pause_check or (lambda: None)
    xml_path = detect_cellebrite_xml(folder_path)
    if xml_path is None:
        return {'status': 'error', 'reason': 'No Cellebrite XML report was found'}
    recovery = Recovery(xml_path, boundary)
    if recovery.state.get('phase') == 'completed':
        return recovery.state['result']
    precheck = check_cellebrite_report(folder_path, case_id=case_id)
    if not precheck.get('suitable'):
        return {'status': 'error', 'reason': precheck.get('message', 'Not a valid Cellebrite report')}
    report_key = precheck.get('report_key')
    if not report_key:
        return {'status': 'error', 'reason': 'The phone report has no stable report identity'}
    with report_lock(case_id, report_key, boundary):
        # Recheck while holding the shared report lock: two separately queued
        # uploads must not both pass duplicate detection before either writes.
        if not recovery.state.get('phase'):
            precheck = check_cellebrite_report(folder_path, case_id=case_id)
            if precheck.get('duplicate') and not force:
                return {'status': 'error', 'reason': 'duplicate', 'existing': precheck.get('existing')}
            existing = precheck.get('existing') or {}
            recovery.save(phase='cleanup_started', report_key=report_key,
                replace_key=existing.get('report_key') if force and precheck.get('duplicate') else None)
        if recovery.state['phase'] == 'cleanup_started':
            existing_key = recovery.state.get('replace_key')
            if existing_key:
                from services.neo4j_service import neo4j_service
                neo4j_service.delete_phone_report(case_id, existing_key)
                with get_background_session() as db:
                    EvidenceDBStorage.delete_by_cellebrite_report_key(db, case_uuid, existing_key)
                _log(f'Replacement prepared for phone report {existing_key}.')
            # Repeating cleanup after an interruption is safe only before any
            # new graph writes. Resume never deletes its own completed work.
            recovery.save(phase='cleanup_complete')
        boundary()
        with get_background_session() as db:
            result = ingest_cellebrite_report(
                report_dir=folder_path, case_id=case_id, log_callback=_log,
                owner=owner, evidence_db=db, created_by_id=created_by_uuid,
                evidence_root_folder_id=evidence_folder_uuid,
                pause_check=boundary, recovery=recovery,
            )
        if result.get('status') == 'success':
            recovery.save(phase='completed', result=result)
        return result


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
    stop = threading.Event()
    from app.services.ingestion_checkpoints import IngestionPaused, pause_boundary
    last_check = 0.0

    def boundary():
        nonlocal last_check
        if stop.is_set(): raise IngestionPaused()
        now = time.monotonic()
        if now - last_check >= .25:
            asyncio.run_coroutine_threadsafe(pause_boundary(), loop).result()
            last_check = now

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
            pause_check=boundary,
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

        ingestion_result = await asyncio.shield(worker)
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
        # to_thread cannot be cancelled safely. Stop cooperatively and retain
        # the exclusive checkpoint lock until the actual writer has exited.
        stop.set()
        with suppress(IngestionPaused, Exception):
            await asyncio.shield(worker)
        job.pause_requested = True
        job.paused = True
        job.resumable = True
        await _update_job(job, JobStatus.PENDING, job.progress or 0.0, db,
            'Paused after worker interruption. Resume to continue from saved work.',
            error_message='Processing paused after an interruption; saved work is retained.')
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
