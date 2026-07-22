import asyncio
import os

import pytesseract
from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import text

from app.config import settings
from app.dependencies import async_session
from app.services import neo4j_client, chroma_client, redis_client
from app.services.projection_reconciliation import audit_case_projection

router = APIRouter()


def _ocr_runtime_available() -> bool:
    try:
        installed_languages = set(pytesseract.get_languages(config=""))
    except Exception:
        return False
    configured_languages = {
        language.strip()
        for language in settings.tesseract_lang.split("+")
        if language.strip()
    }
    return configured_languages.issubset(installed_languages) and "osd" in installed_languages


def _storage_available() -> bool:
    return os.path.isdir(settings.storage_path) and os.access(
        settings.storage_path, os.R_OK | os.W_OK
    )


async def _runtime_checks() -> dict[str, bool]:
    checks: dict[str, bool] = {}

    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
            await db.execute(
                text(
                    "SELECT pipeline_version, pipeline_state, quality_report "
                    "FROM jobs LIMIT 0"
                )
            )
            await db.execute(text("SELECT id, source_location FROM evidence_claims LIMIT 0"))
        checks["postgres"] = True
    except Exception:
        checks["postgres"] = False

    neo4j_ok, chroma_ok, redis_ok, ocr_ok, storage_ok = await asyncio.gather(
        neo4j_client.check_connection(),
        asyncio.to_thread(chroma_client.check_connection),
        redis_client.check_connection(),
        asyncio.to_thread(_ocr_runtime_available),
        asyncio.to_thread(_storage_available),
    )
    checks.update(
        {
            "neo4j": neo4j_ok,
            "chromadb": chroma_ok,
            "redis": redis_ok,
            "ocr": ocr_ok,
            "storage": storage_ok,
            "openai": bool(settings.openai_api_key.strip()),
        }
    )
    return checks


@router.get("/health")
async def health_check():
    checks = await _runtime_checks()

    all_ok = all(checks.values())
    return {"status": "ok" if all_ok else "degraded", "checks": checks}


@router.get("/ready")
async def readiness_check(response: Response):
    checks = await _runtime_checks()
    all_ok = all(checks.values())
    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if all_ok else "not_ready", "checks": checks}


@router.get("/cases/{case_id}/projection-health")
async def projection_health(case_id: str):
    try:
        return await audit_case_projection(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="case_id must be a UUID") from exc
