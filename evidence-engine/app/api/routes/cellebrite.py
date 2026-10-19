import uuid
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.dependencies import get_db
from app.models.job import Job
from app.pipeline.cellebrite.detection import check_cellebrite_report
from app.schemas.job import JobResponse

router = APIRouter()


class CellebriteJobRequest(BaseModel):
    request_id: uuid.UUID | None = None
    folder_path: str
    evidence_folder_id: uuid.UUID | None = None
    report_name: str | None = None
    report_key: str | None = None
    owner: str | None = None
    force: bool = False
    requested_by_user_id: uuid.UUID | None = None


def _repo_data_root() -> Path:
    configured = Path(settings.cellebrite_data_root)
    if configured.is_absolute():
        return configured
    return Path(__file__).resolve().parents[4] / configured


def _safe_report_folder(case_id: str, raw_path: str) -> tuple[str, Path]:
    cleaned = (raw_path or "").replace("\\", "/").lstrip("/")
    if cleaned in ("", "."):
        root = (_repo_data_root() / case_id).resolve()
        return ".", root

    if not cleaned:
        raise HTTPException(status_code=400, detail="folder_path is required")

    relative = PurePosixPath(cleaned)
    if any(part in ("", ".", "..") for part in relative.parts):
        raise HTTPException(status_code=403, detail="Path outside case directory")

    root = (_repo_data_root() / case_id).resolve()
    full_path = (root / relative).resolve()
    try:
        full_path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Path outside case directory") from exc

    return str(relative), full_path


@router.post("/cases/{case_id}/cellebrite/jobs", response_model=JobResponse, status_code=201)
async def create_cellebrite_job(
    case_id: str,
    body: CellebriteJobRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create and enqueue a Cellebrite ingestion job for a staged report folder."""
    relative_path, full_path = _safe_report_folder(case_id, body.folder_path)
    if not full_path.exists() or not full_path.is_dir():
        raise HTTPException(status_code=404, detail="Cellebrite report folder not found")

    payload = {
        "folder_path": relative_path,
        "evidence_folder_id": str(body.evidence_folder_id) if body.evidence_folder_id else None,
        "report_name": body.report_name,
        "report_key": body.report_key,
        "owner": body.owner,
        "force": body.force,
        "requested_by_user_id": str(body.requested_by_user_id) if body.requested_by_user_id else None,
    }
    identity = body.request_id or uuid.uuid4()
    job = await db.get(Job, identity)
    if job is None:
        from app.services.pipeline_run_state import transition_batch_dispatch
        pipeline_state = transition_batch_dispatch({}, dispatch_state="ready", batch_id=str(identity), case_id=case_id)
        pipeline_state['batch_dispatch'].update(function='process_cellebrite', queue_job_id=f'cellebrite:{identity}')
        job = Job(
        id=identity,
        case_id=case_id,
        job_type="cellebrite_ingestion",
        file_name=body.report_name or Path(relative_path).name,
        file_path=str(full_path),
        source_folder_id=str(body.evidence_folder_id) if body.evidence_folder_id else None,
        requested_by_user_id=body.requested_by_user_id,
        merge_payload=payload,
        pipeline_state=pipeline_state,
        )
        db.add(job)
        try:
            await db.commit()
            await db.refresh(job)
        except IntegrityError:
            await db.rollback()
            job = await db.get(Job, identity)
            if job is None: raise
    if job.case_id != case_id or job.job_type != 'cellebrite_ingestion' or job.merge_payload != payload:
        raise HTTPException(409, 'This processing request belongs to another selection')
    from app.services.batch_dispatch import dispatch_ingestion_batch
    if (job.pipeline_state or {}).get('batch_dispatch', {}).get('state') != 'dispatched':
        await dispatch_ingestion_batch(job, db, request.app.state.arq_pool)
    return job


@router.get("/cases/{case_id}/cellebrite/check")
async def check_cellebrite_folder(case_id: str, folder_path: str):
    """Check whether a staged folder is a Cellebrite UFED report."""
    _, full_path = _safe_report_folder(case_id, folder_path)
    return check_cellebrite_report(full_path, case_id=case_id)
