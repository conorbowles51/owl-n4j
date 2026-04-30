import asyncio
import json
import logging
import subprocess
from typing import Any

import httpx
from openai import AsyncOpenAI

from app.config import settings
from app.services.cost_tracking import CostOperationKind, record_openai_cost

_client: AsyncOpenAI | None = None
_semaphore = asyncio.Semaphore(10)
logger = logging.getLogger(__name__)

# Explicit per-request timeouts so a half-open TCP connection can't wedge a call
# indefinitely. Without this, a dropped response read sits forever, only reaped
# by arq's job_timeout (4h) and leaving DB rows in a stuck non-terminal state.
_OPENAI_TIMEOUT = httpx.Timeout(connect=30.0, read=300.0, write=60.0, pool=60.0)


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=_OPENAI_TIMEOUT,
            max_retries=3,
        )
    return _client


async def chat_completion(
    messages: list[dict[str, str]],
    model: str | None = None,
    response_format: Any = None,
    temperature: float | None = None,
) -> str:
    client = get_openai_client()
    async with _semaphore:
        kwargs: dict[str, Any] = {
            "model": model or settings.openai_model,
            "messages": messages,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if response_format is not None:
            kwargs["response_format"] = response_format
        resp = await client.chat.completions.create(**kwargs)
    resolved_model = kwargs["model"]
    operation_kind = CostOperationKind.CHAT_COMPLETION
    if any(
        isinstance(message.get("content"), list)
        and any(isinstance(item, dict) and item.get("type") == "image_url" for item in message.get("content", []))
        for message in messages
    ):
        operation_kind = CostOperationKind.VISION
    try:
        await record_openai_cost(
            model_id=resolved_model,
            operation_kind=operation_kind,
            usage=getattr(resp, "usage", None),
        )
    except Exception as exc:
        logger.warning("Failed to record %s cost: %s", operation_kind, exc)
    return resp.choices[0].message.content or ""


async def embed_texts(
    texts: list[str], model: str | None = None
) -> list[list[float]]:
    client = get_openai_client()
    results: list[list[float]] = []
    batch_size = 100
    resolved_model = model or settings.openai_embedding_model
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        async with _semaphore:
            resp = await client.embeddings.create(
                model=resolved_model,
                input=batch,
            )
        try:
            await record_openai_cost(
                model_id=resolved_model,
                operation_kind=CostOperationKind.EMBEDDING,
                usage=getattr(resp, "usage", None),
                extra_metadata={"batch_size": len(batch)},
            )
        except Exception as exc:
            logger.warning("Failed to record embedding cost: %s", exc)
        results.extend([item.embedding for item in resp.data])
    return results


async def transcribe_audio(file_path: str) -> str:
    client = get_openai_client()
    with open(file_path, "rb") as f:
        async with _semaphore:
            resp = await client.audio.transcriptions.create(
                model=settings.openai_transcription_model,
                file=f,
            )
    duration_seconds = None
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout:
            info = json.loads(result.stdout)
            duration = (info.get("format") or {}).get("duration")
            if duration:
                duration_seconds = float(duration)
    except Exception:
        duration_seconds = None
    try:
        await record_openai_cost(
            model_id=settings.openai_transcription_model,
            operation_kind=CostOperationKind.TRANSCRIPTION,
            usage=getattr(resp, "usage", None),
            duration_seconds=duration_seconds,
        )
    except Exception as exc:
        logger.warning("Failed to record transcription cost: %s", exc)
    return resp.text
