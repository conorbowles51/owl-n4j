import asyncio

import pytesseract
from fastapi import APIRouter
from sqlalchemy import text

from app.config import settings
from app.dependencies import async_session
from app.services import neo4j_client, chroma_client, redis_client

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


@router.get("/health")
async def health_check():
    checks = {}

    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        checks["postgres"] = True
    except Exception:
        checks["postgres"] = False

    checks["neo4j"] = await neo4j_client.check_connection()
    checks["chromadb"] = chroma_client.check_connection()
    checks["redis"] = await redis_client.check_connection()
    checks["ocr"] = await asyncio.to_thread(_ocr_runtime_available)

    all_ok = all(checks.values())
    return {"status": "ok" if all_ok else "degraded", "checks": checks}
