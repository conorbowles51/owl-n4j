import asyncio
import json
import logging
import subprocess
from typing import Any

import httpx
from openai import AsyncOpenAI

from app.config import settings
from app.services.cost_tracking import CostOperationKind, record_openai_cost
from app.services.provider_resilience import guard_provider_call

_client: AsyncOpenAI | None = None
_semaphore = asyncio.Semaphore(10)
logger = logging.getLogger(__name__)

# Explicit per-request timeouts so a half-open TCP connection can't wedge a call
# indefinitely. Without this, a dropped response read sits forever, only reaped
# by arq's job_timeout (4h) and leaving DB rows in a stuck non-terminal state.
_OPENAI_TIMEOUT = httpx.Timeout(connect=30.0, read=300.0, write=60.0, pool=60.0)
_OVERSIZED_REQUEST_MARKERS = (
    "request_headers_too_large",
    "input_too_large",
    "context_length_exceeded",
    "maximum context length",
    "request too large",
    "too large",
)


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
        resp = await guard_provider_call(
            "openai",
            lambda: client.chat.completions.create(**kwargs),
        )
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


def _embedding_batch_limits() -> tuple[int, int]:
    max_items = max(1, settings.openai_embedding_batch_size)
    max_chars = max(1, settings.openai_embedding_max_batch_chars)
    return max_items, max_chars


def _embedding_batch_char_count(batch: list[str]) -> int:
    return sum(len(text or "") for text in batch)


def _iter_embedding_batches(
    texts: list[str],
    *,
    max_items: int,
    max_chars: int,
) -> list[list[str]]:
    batches: list[list[str]] = []
    batch: list[str] = []
    batch_chars = 0

    for text in texts:
        text_chars = len(text or "")
        if batch and (
            len(batch) >= max_items or batch_chars + text_chars > max_chars
        ):
            batches.append(batch)
            batch = []
            batch_chars = 0

        batch.append(text)
        batch_chars += text_chars

    if batch:
        batches.append(batch)

    return batches


def _openai_error_text(exc: Exception) -> str:
    parts = [str(exc)]
    for attr in ("code", "type", "param", "message"):
        value = getattr(exc, attr, None)
        if value:
            parts.append(str(value))
    response = getattr(exc, "response", None)
    if response is not None:
        try:
            parts.append(json.dumps(response.json()))
        except Exception:
            parts.append(str(response))
    return " ".join(parts)


def _is_oversized_openai_request(exc: Exception) -> bool:
    error_text = _openai_error_text(exc).lower()
    return any(marker in error_text for marker in _OVERSIZED_REQUEST_MARKERS)


async def _request_embedding_batch(
    client: AsyncOpenAI,
    *,
    model: str,
    batch: list[str],
    max_chars: int,
) -> list[list[float]]:
    batch_chars = _embedding_batch_char_count(batch)
    try:
        async with _semaphore:
            resp = await guard_provider_call(
                "openai",
                lambda: client.embeddings.create(
                    model=model,
                    input=batch,
                ),
            )
    except Exception as exc:
        if _is_oversized_openai_request(exc):
            if len(batch) == 1:
                raise RuntimeError(
                    "OpenAI embedding request is too large for a single text "
                    f"item ({batch_chars} chars) using {model}: {exc}"
                ) from exc

            midpoint = max(1, len(batch) // 2)
            logger.warning(
                "OpenAI embedding batch rejected as oversized; retrying as "
                "%d and %d item batches (%d chars total, limit %d): %s",
                midpoint,
                len(batch) - midpoint,
                batch_chars,
                max_chars,
                exc,
            )
            left = await _request_embedding_batch(
                client,
                model=model,
                batch=batch[:midpoint],
                max_chars=max_chars,
            )
            right = await _request_embedding_batch(
                client,
                model=model,
                batch=batch[midpoint:],
                max_chars=max_chars,
            )
            return left + right
        raise

    try:
        await record_openai_cost(
            model_id=model,
            operation_kind=CostOperationKind.EMBEDDING,
            usage=getattr(resp, "usage", None),
            extra_metadata={
                "batch_size": len(batch),
                "batch_char_count": batch_chars,
                "batch_char_limit": max_chars,
            },
        )
    except Exception as exc:
        logger.warning("Failed to record embedding cost: %s", exc)

    return [item.embedding for item in resp.data]


async def embed_texts(
    texts: list[str], model: str | None = None
) -> list[list[float]]:
    client = get_openai_client()
    results: list[list[float]] = []
    resolved_model = model or settings.openai_embedding_model
    max_items, max_chars = _embedding_batch_limits()

    for batch in _iter_embedding_batches(
        texts,
        max_items=max_items,
        max_chars=max_chars,
    ):
        results.extend(
            await _request_embedding_batch(
                client,
                model=resolved_model,
                batch=batch,
                max_chars=max_chars,
            )
        )

    return results


async def transcribe_audio(file_path: str, prompt: str | None = None) -> str:
    client = get_openai_client()
    with open(file_path, "rb") as f:
        async with _semaphore:
            kwargs: dict[str, Any] = {
                "model": settings.openai_transcription_model,
                "file": f,
            }
            if prompt:
                kwargs["prompt"] = prompt
            resp = await guard_provider_call(
                "openai",
                lambda: client.audio.transcriptions.create(**kwargs),
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
