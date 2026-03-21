from fastapi import APIRouter
from sqlalchemy import text

from app.dependencies import async_session
from app.services import neo4j_client, chroma_client, redis_client

router = APIRouter()


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

    all_ok = all(checks.values())
    return {"status": "ok" if all_ok else "degraded", "checks": checks}
