"""
Evidence WebSocket Router — forwards job progress from the evidence-engine
to the frontend via WebSocket, replacing the 3-second polling pattern.

The evidence-engine publishes progress to Redis pub/sub on channel
`job:{job_id}:progress`. This endpoint subscribes and relays messages.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from config import REDIS_URL

logger = logging.getLogger(__name__)

router = APIRouter(tags=["evidence-ws"])

_redis = None


async def _get_redis():
    """Lazy-init an async Redis connection."""
    global _redis
    if _redis is None:
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


async def close_redis():
    """Close Redis connection (call on app shutdown)."""
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None


@router.websocket("/api/evidence/ws/jobs/{job_id}")
async def job_progress_ws(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint that streams job progress from the evidence-engine.

    The frontend connects here instead of polling GET /api/background-tasks.
    Messages are JSON objects: {status, progress, message, ...}

    The connection closes automatically when the job reaches "completed" or "failed".
    """
    await websocket.accept()

    try:
        redis = await _get_redis()
        pubsub = redis.pubsub()
        channel = f"job:{job_id}:progress"
        await pubsub.subscribe(channel)

        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )
            if message and message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                except (json.JSONDecodeError, TypeError):
                    data = {"raw": message["data"]}

                await websocket.send_json(data)

                # Close when job is terminal
                status = data.get("status", "")
                if status in ("completed", "failed"):
                    break

            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        logger.debug("Client disconnected from job progress WS: %s", job_id)
    except Exception as e:
        logger.error("Error in job progress WS for %s: %s", job_id, e)
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
        except Exception:
            pass
