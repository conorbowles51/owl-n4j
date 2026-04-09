import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.dependencies import async_session
from app.models.job import Job
from app.services.redis_client import get_redis

router = APIRouter()


async def _check_job_status(job_id: str) -> dict | None:
    """Check if a job is already in a terminal state."""
    try:
        async with async_session() as db:
            result = await db.execute(select(Job).where(Job.id == job_id))
            job = result.scalar_one_or_none()
            if job and job.status.value in ("completed", "failed"):
                return {
                    "job_id": str(job.id),
                    "status": job.status.value,
                    "progress": job.progress,
                    "message": job.error_message or "Complete",
                    "entity_count": job.entity_count,
                    "relationship_count": job.relationship_count,
                }
    except Exception:
        pass
    return None


@router.websocket("/ws/jobs/{job_id}")
async def job_progress(websocket: WebSocket, job_id: str):
    await websocket.accept()

    # If the job already finished before we connected, send status immediately
    existing = await _check_job_status(job_id)
    if existing:
        await websocket.send_json(existing)
        await websocket.close()
        return

    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"job:{job_id}:progress")

    try:
        # Re-check after subscribing to close the race window
        existing = await _check_job_status(job_id)
        if existing:
            await websocket.send_json(existing)
            return

        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )
            if message and message["type"] == "message":
                data = json.loads(message["data"])
                await websocket.send_json(data)

                if data.get("status") in ("completed", "failed"):
                    break

            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(f"job:{job_id}:progress")
        await pubsub.close()
