"""
Evidence Engine Client — async HTTP client for the evidence-engine microservice.

The evidence-engine handles file storage, processing (text extraction, entity
extraction, deduplication, graph writing), and file serving. This client proxies
requests from the owl-n4j backend so the frontend API surface remains unchanged.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx

from config import EVIDENCE_ENGINE_URL, EVIDENCE_ENGINE_TIMEOUT

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Lazy-init a shared async HTTP client."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=EVIDENCE_ENGINE_URL,
            timeout=httpx.Timeout(EVIDENCE_ENGINE_TIMEOUT, connect=10.0),
        )
    return _client


async def close():
    """Close the HTTP client (call on app shutdown)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


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
