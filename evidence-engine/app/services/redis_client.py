import json
from typing import Any

from redis.asyncio import Redis

from app.config import settings

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None


async def publish_progress(job_id: str, data: dict[str, Any]) -> None:
    r = get_redis()
    await r.publish(f"job:{job_id}:progress", json.dumps(data))


async def check_connection() -> bool:
    try:
        r = get_redis()
        return await r.ping()
    except Exception:
        return False
