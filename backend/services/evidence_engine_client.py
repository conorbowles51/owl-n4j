"""
Evidence Engine Client — async HTTP client for the evidence-engine microservice.

The evidence-engine handles file storage, processing (text extraction, entity
extraction, deduplication, graph writing), and file serving. This client proxies
requests from the owl-n4j backend so the frontend API surface remains unchanged.
"""

import logging
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from services import request_speed
from config import EVIDENCE_ENGINE_API_KEY, EVIDENCE_ENGINE_URL, EVIDENCE_ENGINE_TIMEOUT

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


class _TimedClient(httpx.AsyncClient):
    """Records each engine call's time (sent to the whole answer read; for a streamed answer, to its headers) on the request being served, for the
    Server-Timing "engine" part and the slow-request log line. The call itself is unchanged."""

    async def send(self, request, **kwargs):
        started = time.perf_counter()
        try:
            return await super().send(request, **kwargs)
        finally:
            request_speed.note_engine(time.perf_counter() - started)


def _get_client() -> httpx.AsyncClient:
    """Lazy-init a shared async HTTP client."""
    global _client
    if _client is None:
        headers = (
            {"X-Evidence-Engine-Key": EVIDENCE_ENGINE_API_KEY}
            if EVIDENCE_ENGINE_API_KEY
            else None
        )
        _client = _TimedClient(
            base_url=EVIDENCE_ENGINE_URL,
            timeout=httpx.Timeout(EVIDENCE_ENGINE_TIMEOUT, connect=10.0),
            headers=headers,
        )
    return _client


async def close():
    """Close the HTTP client (call on app shutdown)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def audio_review_capabilities():
    response = await _get_client().get('/capabilities', timeout=3.0)
    response.raise_for_status()
    return response.json()


async def control_job(job_id: str, case_id: str, action: str):
    """pause, resume, or cancel (phone readings only; the engine refuses it for an extraction already in the case)."""
    if action not in {"pause", "resume", "cancel"}:
        raise ValueError("Invalid ingestion action")
    response = await _get_client().post(f"/jobs/{job_id}/{action}", params={"case_id": case_id})
    response.raise_for_status()
    return response.json()


async def is_available() -> bool:
    """Check if the evidence engine is reachable."""
    try:
        result = await health_check()
        return result.get("status") != "unavailable"
    except Exception:
        return False


async def upload_file(
    case_id: str,
    file_name: str,
    file_content: bytes,
    content_type: str = "application/octet-stream",
    processing_metadata: Optional[dict] = None,
) -> List[Dict[str, Any]]:
    """
    Upload a single file to the evidence-engine for storage and processing.

    Returns:
        List of job response dicts (single element for one file).
    """
    return await upload_files_batch(
        case_id=case_id,
        files=[(file_name, file_content, content_type)],
        processing_metadata=[processing_metadata or {}],
    )


async def upload_files_batch(
    case_id: str,
    files: List[tuple],  # List of (file_name, file_content, content_type)
    processing_metadata: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Upload multiple files to the evidence-engine as a batch.

    All files are extracted in parallel, then deduplicated together in
    a single unified pass.

    Returns:
        List of job response dicts from evidence-engine.
    """
    client = _get_client()

    multipart_files = [
        ("files", (name, content, ctype))
        for name, content, ctype in files
    ]
    data = {}
    if processing_metadata is not None:
        import json

        data["processing_metadata"] = json.dumps(processing_metadata)

    response = await client.post(
        f"/cases/{case_id}/files",
        files=multipart_files,
        data=data,
    )
    response.raise_for_status()
    return response.json()


async def upload_file_paths_batch(
    case_id: str,
    files: List[tuple[str, Path, str]],
    processing_metadata: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Stream evidence files from disk to the engine without buffering them in RAM."""
    client = _get_client()
    data = {}
    if processing_metadata is not None:
        import json

        data["processing_metadata"] = json.dumps(processing_metadata)

    with ExitStack() as opened:
        multipart_files = [
            (
                "files",
                (name, opened.enter_context(Path(path).open("rb")), content_type),
            )
            for name, path, content_type in files
        ]
        response = await client.post(
            f"/cases/{case_id}/files",
            files=multipart_files,
            data=data,
        )
        response.raise_for_status()
        return response.json()


async def detect_phone_container(case_id: str, path: str) -> Dict[str, Any]:
    """Classify a staged upload as a phone report (01 section 2.5). Detection never writes and never extracts."""
    client = _get_client()
    response = await client.post(f"/cases/{case_id}/phone/detect", json={"path": path})
    response.raise_for_status()
    return response.json()


async def create_phone_capture_job(
    case_id: str,
    *,
    request_id: str,
    container_path: str,
    root_path: str,
    container_evidence_id: str,
    evidence_folder_id: str | None = None,
    requested_by_user_id: str | None = None,
    original_name: str | None = None,
    upload_sha256: str | None = None,
    upload_group_id: str | None = None,
) -> Dict[str, Any]:
    """Create (or return, on a repeated ``request_id``) the phone capture job for one report root."""
    client = _get_client()
    response = await client.post(
        f"/cases/{case_id}/phone/jobs",
        json={
            "request_id": request_id,
            "container_path": container_path,
            "root_path": root_path,
            "container_evidence_id": container_evidence_id,
            "evidence_folder_id": evidence_folder_id,
            "requested_by_user_id": requested_by_user_id,
            "original_name": original_name,
            "upload_sha256": upload_sha256,
            "upload_group_id": upload_group_id,
        },
    )
    response.raise_for_status()
    return response.json()


async def get_job(job_id: str) -> Dict[str, Any]:
    """Get the status of a processing job."""
    client = _get_client()
    response = await client.get(f"/jobs/{job_id}")
    response.raise_for_status()
    return response.json()


async def list_jobs(case_id: str) -> List[Dict[str, Any]]:
    """List all processing jobs for a case, ordered by created_at desc."""
    client = _get_client()
    response = await client.get(f"/cases/{case_id}/jobs")
    response.raise_for_status()
    return response.json()


async def delete_job(job_id: str) -> None:
    """Delete a single terminal job from the evidence engine."""
    client = _get_client()
    response = await client.delete(f"/jobs/{job_id}")
    response.raise_for_status()


async def clear_case_jobs(case_id: str, terminal_only: bool = True) -> Dict[str, Any]:
    """Delete terminal jobs for a case from the evidence engine."""
    client = _get_client()
    response = await client.delete(
        f"/cases/{case_id}/jobs",
        params={"terminal_only": str(terminal_only).lower()},
    )
    response.raise_for_status()
    return response.json()


async def list_files(case_id: str) -> List[Dict[str, Any]]:
    """List all files for a case from evidence engine."""
    client = _get_client()
    response = await client.get(f"/cases/{case_id}/files")
    response.raise_for_status()
    return response.json()


async def download_file(case_id: str, job_id: str) -> httpx.Response:
    """
    Download a file from evidence engine. Returns the raw httpx Response
    so the caller can stream it back to the client.
    """
    client = _get_client()
    response = await client.get(
        f"/cases/{case_id}/files/{job_id}",
        follow_redirects=True,
    )
    response.raise_for_status()
    return response


async def delete_file(case_id: str, job_id: str) -> None:
    """Delete a file from evidence engine storage."""
    client = _get_client()
    response = await client.delete(f"/cases/{case_id}/files/{job_id}")
    response.raise_for_status()


async def merge_entities(case_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send entities to the evidence engine for AI-powered merging.

    Returns:
        Job response dict from evidence-engine (includes job id for tracking).
    """
    client = _get_client()
    response = await client.post(
        f"/cases/{case_id}/merge-entities",
        json=payload,
    )
    response.raise_for_status()
    return response.json()


async def health_check() -> Dict[str, Any]:
    """Check evidence-engine health."""
    client = _get_client()
    try:
        response = await client.get("/health")
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        logger.warning("Evidence engine health check failed: %s", e)
        return {"status": "unavailable", "error": str(e)}


async def source_database(case_id: str, extraction_id: str, document_index: int, ordinal: int,
                          params: Dict[str, Any]) -> Dict[str, Any]:
    """A verified app database named as a record's source, read by the engine from a read-only scratch copy
    (05 section 17.2). A refusal comes back as ``{"refused": "<words>"}``."""
    client = _get_client()
    response = await client.get(
        f"/cases/{case_id}/phone/extractions/{extraction_id}/files/{document_index}/{ordinal}/database",
        params={k: v for k, v in params.items() if v is not None}, timeout=httpx.Timeout(60.0, connect=10.0))
    if response.status_code == 409:
        return {"refused": response.json().get("detail") or "The database could not be opened."}
    response.raise_for_status()
    return response.json()


async def request_reparse(case_id: str, extraction_id: str, os_family: str, requested_by: str) -> Dict[str, Any]:
    """Queue (or return the open) re-parse run of one phone with the tool pinned for its OS (05 section 17.3).
    A refusal (no tool for this OS, none installed) comes back as ``{"refused": "<words>"}``."""
    client = _get_client()
    response = await client.post(f"/cases/{case_id}/phone/extractions/{extraction_id}/reparse",
                                 json={"os_family": os_family, "requested_by": requested_by})
    if response.status_code in (404, 409):
        return {"refused": response.json().get("detail") or "The re-parse could not be queued."}
    response.raise_for_status()
    return response.json()
