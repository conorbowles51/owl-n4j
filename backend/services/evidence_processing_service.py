from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from postgres.models.evidence import EvidenceFile
from services import evidence_engine_client
from services.evidence_db_storage import EvidenceDBStorage
from services.evidence_job_sync import reconcile_case_jobs
from services.folder_context_service import build_processing_snapshot
from services.job_status_subscriber import get_subscriber


def _serialize_profile_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_folder_id": snapshot.get("source_folder_id"),
        "effective_context": snapshot.get("effective_context"),
        "effective_mandatory_instructions": snapshot.get("effective_mandatory_instructions") or [],
        "effective_special_entity_types": snapshot.get("effective_special_entity_types") or [],
        "chain": snapshot.get("chain") or [],
    }


async def process_db_files(
    db: Session,
    *,
    case_id: uuid.UUID,
    file_ids: list[uuid.UUID],
    force_reprocess: bool = False,
) -> dict[str, Any]:
    await reconcile_case_jobs(db, str(case_id))

    files = EvidenceDBStorage.get_files_by_ids(db, file_ids)
    files_by_id = {f.id: f for f in files}

    candidates: list[EvidenceFile] = []
    skipped_processing = 0
    missing_on_disk = 0

    for file_id in file_ids:
        ef = files_by_id.get(file_id)
        if ef is None:
            continue
        if ef.status == "processing":
            skipped_processing += 1
            continue
        if ef.status == "processed" and not ef.processing_stale and not force_reprocess:
            skipped_processing += 1
            continue
        candidates.append(ef)

    if not candidates:
        return {
            "job_ids": [],
            "file_count": 0,
            "skipped_count": skipped_processing,
            "message": "No eligible files to process",
        }

    file_tuples: list[tuple[str, bytes, str]] = []
    per_file_metadata: list[dict[str, Any]] = []
    valid_files: list[EvidenceFile] = []

    for ef in candidates:
        path = Path(ef.stored_path)
        if not path.exists():
            missing_on_disk += 1
            continue

        snapshot = build_processing_snapshot(
            db,
            case_id=case_id,
            folder_id=ef.folder_id,
            file_id=ef.id,
        )

        file_tuples.append(
            (
                ef.original_filename,
                path.read_bytes(),
                _guess_content_type(ef.original_filename),
            )
        )
        per_file_metadata.append(snapshot)
        valid_files.append(ef)

    if not valid_files:
        return {
            "job_ids": [],
            "file_count": 0,
            "skipped_count": skipped_processing,
            "missing_on_disk": missing_on_disk,
            "message": "No files found on disk",
        }

    EvidenceDBStorage.mark_processing(
        db,
        [ef.id for ef in valid_files],
        force=force_reprocess,
    )
    for ef, snapshot in zip(valid_files, per_file_metadata):
        EvidenceDBStorage.set_processing_snapshot(
            db,
            ef.id,
            profile_snapshot=_serialize_profile_snapshot(snapshot),
            folder_id=ef.folder_id,
        )
    db.commit()

    try:
        jobs = await evidence_engine_client.upload_files_batch(
            case_id=str(case_id),
            files=file_tuples,
            processing_metadata=per_file_metadata,
        )
    except Exception as exc:
        EvidenceDBStorage.mark_processed(
            db,
            [ef.id for ef in valid_files],
            error=str(exc),
        )
        db.commit()
        raise

    job_ids_out: list[str] = []
    for ef, job in zip(valid_files, jobs):
        ef.engine_job_id = str(job["id"])
        job_ids_out.append(str(job["id"]))
    db.commit()

    if job_ids_out:
        subscriber = get_subscriber()
        await subscriber.track_jobs(job_ids_out, str(case_id))

    return {
        "job_ids": job_ids_out,
        "file_count": len(valid_files),
        "skipped_count": skipped_processing,
        "missing_on_disk": missing_on_disk,
        "message": f"Processing {len(valid_files)} file(s)",
    }


def _guess_content_type(file_name: str) -> str:
    import mimetypes

    return mimetypes.guess_type(file_name)[0] or "application/octet-stream"
