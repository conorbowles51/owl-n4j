import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.redis_client import get_redis

router = APIRouter()


@router.websocket("/ws/jobs/{job_id}")
async def job_progress(websocket: WebSocket, job_id: str):
    await websocket.accept()

    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"job:{job_id}:progress")

    try:
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
