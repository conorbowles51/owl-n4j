import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import httpx
from openai import APIConnectionError, APITimeoutError, AsyncOpenAI

from app.config import EMBEDDING_MODEL, settings
from app.services.ai_model_policy import resolve_ai_model, resolve_provider_api_key
from app.services.cost_tracking import CostOperationKind, record_ai_cost, record_openai_cost

_client: AsyncOpenAI | None = None
_client_key: str | None = None
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


@dataclass(frozen=True)
class AudioTranscriptionResult:
    """Normalized transcription output used by the ingestion pipeline."""

    text: str
    segments: list[dict[str, Any]]
    duration_seconds: float | None
    model: str


@dataclass(frozen=True)
class AudioTranscriptionProgress:
    """A durable progress/heartbeat update for an audio transcription."""

    message: str
    completed: float
    total: float


AudioProgressCallback = Callable[[AudioTranscriptionProgress], Awaitable[None]]


class AudioTranscriptionRequestError(RuntimeError):
    """A transport failure annotated with whether streaming had begun."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        stream_started: bool,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.stream_started = stream_started


def get_openai_client() -> AsyncOpenAI:
    global _client, _client_key
    api_key = resolve_provider_api_key("openai")
    if not api_key:
        raise ValueError("OpenAI is not connected. Add its API key in Settings → AI settings.")
    if _client is None or _client_key != api_key:
        _client = AsyncOpenAI(
            api_key=api_key,
            timeout=_OPENAI_TIMEOUT,
            max_retries=3,
        )
        _client_key = api_key
    return _client


async def chat_completion(
    messages: list[dict[str, Any]],
    model: str | None = None,
    response_format: Any = None,
    temperature: float | None = None,
    *,
    provider: str | None = None,
    workload: str | None = None,
    max_output_tokens: int | None = None,
) -> str:
    resolved_provider, resolved_model = resolve_ai_model(
        workload,
        model=model,
        provider=provider,
    )
    async with _semaphore:
        if resolved_provider == "openai":
            content, usage = await _openai_chat_completion(
                messages,
                model=resolved_model,
                response_format=response_format,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
        elif resolved_provider == "anthropic":
            content, usage = await _anthropic_chat_completion(
                messages,
                model=resolved_model,
                response_format=response_format,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
        elif resolved_provider == "gemini":
            content, usage = await _gemini_chat_completion(
                messages,
                model=resolved_model,
                response_format=response_format,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
        elif resolved_provider == "deepseek":
            content, usage = await _deepseek_chat_completion(
                messages,
                model=resolved_model,
                response_format=response_format,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
        else:
            raise ValueError(f"Unsupported ingestion AI provider: {resolved_provider}")
    operation_kind = CostOperationKind.CHAT_COMPLETION
    if any(
        isinstance(message.get("content"), list)
        and any(isinstance(item, dict) and item.get("type") == "image_url" for item in message.get("content", []))
        for message in messages
    ):
        operation_kind = CostOperationKind.VISION
    try:
        await record_ai_cost(
            provider=resolved_provider,
            model_id=resolved_model,
            operation_kind=operation_kind,
            usage=usage,
        )
    except Exception as exc:
        logger.warning("Failed to record %s cost: %s", operation_kind, exc)
    return content


def _json_schema_from_response_format(response_format: Any) -> dict[str, Any] | None:
    if not isinstance(response_format, dict):
        return None
    if response_format.get("type") == "json_schema":
        schema = (response_format.get("json_schema") or {}).get("schema")
        return schema if isinstance(schema, dict) else None
    if response_format.get("type") == "json_object":
        return {"type": "object", "additionalProperties": True}
    return None


def _plain_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(item.get("text") or "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
    return str(content or "")


async def _openai_chat_completion(
    messages: list[dict[str, Any]],
    *,
    model: str,
    response_format: Any,
    temperature: float | None,
    max_output_tokens: int | None = None,
) -> tuple[str, Any]:
    client = get_openai_client()
    kwargs: dict[str, Any] = {"model": model, "messages": messages}
    if temperature is not None and not model.startswith(("o1", "o3", "gpt-5")):
        kwargs["temperature"] = temperature
    if response_format is not None:
        kwargs["response_format"] = response_format
    if max_output_tokens is not None:
        kwargs["max_completion_tokens"] = max_output_tokens
    resp = await client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or "", getattr(resp, "usage", None)


async def _anthropic_chat_completion(
    messages: list[dict[str, Any]],
    *,
    model: str,
    response_format: Any,
    temperature: float | None,
    max_output_tokens: int | None = None,
) -> tuple[str, dict[str, Any]]:
    api_key = resolve_provider_api_key("anthropic")
    if not api_key:
        raise ValueError("Anthropic is not connected. Add its API key in Settings → AI settings.")
    system_parts = [
        _plain_text_content(message.get("content"))
        for message in messages
        if message.get("role") == "system"
    ]
    conversation = [
        {
            "role": "assistant" if message.get("role") == "assistant" else "user",
            "content": _plain_text_content(message.get("content")),
        }
        for message in messages
        if message.get("role") != "system"
    ]
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_output_tokens or 16384,
        "messages": conversation,
    }
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)
    if temperature is not None and not model.startswith(
        ("claude-sonnet-5", "claude-opus-4-8", "claude-fable-5")
    ):
        payload["temperature"] = temperature
    schema = _json_schema_from_response_format(response_format)
    if schema:
        payload["output_config"] = {
            "format": {"type": "json_schema", "schema": schema}
        }
    async with httpx.AsyncClient(timeout=_OPENAI_TIMEOUT) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    content = "\n".join(
        str(block.get("text") or "")
        for block in data.get("content", [])
        if block.get("type") == "text"
    ).strip()
    if not content:
        raise ValueError("Anthropic returned an empty response")
    return content, data.get("usage") or {}


async def _gemini_chat_completion(
    messages: list[dict[str, Any]],
    *,
    model: str,
    response_format: Any,
    temperature: float | None,
    max_output_tokens: int | None = None,
) -> tuple[str, dict[str, Any]]:
    api_key = resolve_provider_api_key("gemini")
    if not api_key:
        raise ValueError("Google Gemini is not connected. Add its API key in Settings → AI settings.")
    system_parts = [
        _plain_text_content(message.get("content"))
        for message in messages
        if message.get("role") == "system"
    ]
    contents = [
        {
            "role": "model" if message.get("role") == "assistant" else "user",
            "parts": [{"text": _plain_text_content(message.get("content"))}],
        }
        for message in messages
        if message.get("role") != "system"
    ]
    generation_config: dict[str, Any] = {}
    if max_output_tokens is not None:
        generation_config["maxOutputTokens"] = max_output_tokens
    if temperature is not None and not model.startswith("gemini-3"):
        generation_config["temperature"] = temperature
    schema = _json_schema_from_response_format(response_format)
    if schema:
        generation_config.update(
            {"responseMimeType": "application/json", "responseJsonSchema": schema}
        )
    payload: dict[str, Any] = {"contents": contents}
    if system_parts:
        payload["systemInstruction"] = {
            "parts": [{"text": "\n\n".join(system_parts)}]
        }
    if generation_config:
        payload["generationConfig"] = generation_config
    async with httpx.AsyncClient(timeout=_OPENAI_TIMEOUT) as client:
        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={
                "x-goog-api-key": api_key,
                "content-type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    candidates = data.get("candidates") or []
    parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
    content = "\n".join(str(part.get("text") or "") for part in parts).strip()
    if not content:
        raise ValueError("Gemini returned an empty response")
    usage = data.get("usageMetadata") or {}
    return content, {
        "input_tokens": usage.get("promptTokenCount"),
        "output_tokens": usage.get("candidatesTokenCount"),
        "total_tokens": usage.get("totalTokenCount"),
    }


async def _deepseek_chat_completion(
    messages: list[dict[str, Any]],
    *,
    model: str,
    response_format: Any,
    temperature: float | None,
    max_output_tokens: int | None = None,
) -> tuple[str, dict[str, Any]]:
    api_key = resolve_provider_api_key("deepseek")
    if not api_key:
        raise ValueError("DeepSeek is not connected. Add its API key in Settings → AI settings.")
    normalized_messages = [dict(message) for message in messages]
    payload: dict[str, Any] = {
        "model": model,
        "messages": normalized_messages,
        "thinking": {"type": "disabled"},
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if max_output_tokens is not None:
        payload["max_tokens"] = max_output_tokens
    if _json_schema_from_response_format(response_format):
        payload["response_format"] = {"type": "json_object"}
        payload["messages"] = [
            {
                "role": "system",
                "content": "Return only valid JSON matching the requested structure.",
            },
            *normalized_messages,
        ]
    async with httpx.AsyncClient(timeout=_OPENAI_TIMEOUT) as client:
        response = await client.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "content-type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    choices = data.get("choices") or []
    content = str(((choices[0].get("message") or {}).get("content") or "")).strip() if choices else ""
    if not content:
        raise ValueError("DeepSeek returned an empty response")
    return content, data.get("usage") or {}


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
            resp = await client.embeddings.create(
                model=model,
                input=batch,
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


async def embed_texts(texts: list[str]) -> list[list[float]]:
    client = get_openai_client()
    results: list[list[float]] = []
    max_items, max_chars = _embedding_batch_limits()

    for batch in _iter_embedding_batches(
        texts,
        max_items=max_items,
        max_chars=max_chars,
    ):
        results.extend(
            await _request_embedding_batch(
                client,
                model=EMBEDDING_MODEL,
                batch=batch,
                max_chars=max_chars,
            )
        )

    return results


def _response_payload(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    model_dump = getattr(response, "model_dump", None)
    if callable(model_dump):
        payload = model_dump()
        if isinstance(payload, dict):
            return payload
    return {}


def _normalize_transcript_segments(
    response: Any,
    *,
    time_offset_seconds: float,
    segment_id_prefix: str,
    speaker_id_prefix: str,
) -> list[dict[str, Any]]:
    payload = _response_payload(response)
    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list):
        return []

    segments: list[dict[str, Any]] = []
    for index, raw_segment in enumerate(raw_segments):
        if not isinstance(raw_segment, dict):
            continue
        text = str(raw_segment.get("text") or "").strip()
        speaker = str(raw_segment.get("speaker") or "").strip()
        try:
            start = max(0.0, float(raw_segment.get("start") or 0.0))
            end = max(start, float(raw_segment.get("end") or start))
        except (TypeError, ValueError):
            continue
        if not text:
            continue
        raw_id = str(raw_segment.get("id") or index)
        segments.append(
            {
                "id": f"{segment_id_prefix}{raw_id}",
                "start": round(start + time_offset_seconds, 3),
                "end": round(end + time_offset_seconds, 3),
                "text": text,
                "speaker": f"{speaker_id_prefix}{speaker or 'unknown'}",
            }
        )
    return segments


def _audio_transcription_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=30.0,
        read=float(getattr(settings, "audio_transcription_read_timeout_seconds", 900)),
        write=120.0,
        pool=60.0,
    )


async def _report_audio_progress(
    callback: AudioProgressCallback | None,
    *,
    message: str,
    completed: float,
    total: float,
) -> None:
    if callback is None:
        return
    await callback(
        AudioTranscriptionProgress(
            message=message,
            completed=max(0.0, min(completed, total)) if total > 0 else max(0.0, completed),
            total=max(0.0, total),
        )
    )


async def transcribe_audio(
    file_path: str,
    prompt: str | None = None,
    *,
    time_offset_seconds: float = 0.0,
    segment_id_prefix: str = "",
    speaker_id_prefix: str = "",
    duration_seconds: float | None = None,
    progress_total_seconds: float | None = None,
    progress_callback: AudioProgressCallback | None = None,
    known_speaker_references: dict[str, str] | None = None,
) -> AudioTranscriptionResult:
    client = get_openai_client()
    model = settings.openai_transcription_model
    diarization_enabled = model == "gpt-4o-transcribe-diarize"
    if duration_seconds is None:
        try:
            probe = subprocess.run(
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
            if probe.returncode == 0 and probe.stdout:
                info = json.loads(probe.stdout)
                duration = (info.get("format") or {}).get("duration")
                if duration:
                    duration_seconds = float(duration)
        except Exception:
            duration_seconds = None

    total_seconds = progress_total_seconds or (
        time_offset_seconds + (duration_seconds or 0.0)
    )
    await _report_audio_progress(
        progress_callback,
        message="Uploading audio for transcription...",
        completed=time_offset_seconds,
        total=total_seconds,
    )

    # Audio uploads are non-idempotent work. Do not let the SDK silently submit
    # the same recording again after a read timeout.
    transcription_client = client.with_options(max_retries=0)
    response: Any = None
    usage: Any = None
    streamed_text = ""
    streamed_segments: list[dict[str, Any]] = []
    stream_started = False
    transcription_started_reported = False
    with open(file_path, "rb") as f:
        async with _semaphore:
            kwargs: dict[str, Any] = {
                "model": model,
                "file": f,
                "timeout": _audio_transcription_timeout(),
            }
            if diarization_enabled:
                # Speaker annotations are only returned in diarized_json. Server
                # VAD is required for recordings longer than 30 seconds and also
                # gives cleaner conversational turn boundaries for short files.
                kwargs["response_format"] = "diarized_json"
                kwargs["chunking_strategy"] = "auto"
                kwargs["stream"] = True
                known_speakers = [
                    (name.strip(), reference)
                    for name, reference in (known_speaker_references or {}).items()
                    if name.strip() and reference
                ][:4]
                if known_speakers:
                    kwargs["known_speaker_names"] = [
                        name for name, _reference in known_speakers
                    ]
                    kwargs["known_speaker_references"] = [
                        reference for _name, reference in known_speakers
                    ]
            elif prompt:
                kwargs["prompt"] = prompt
            try:
                response = await transcription_client.audio.transcriptions.create(**kwargs)
            except Exception as exc:
                if not diarization_enabled:
                    raise
                raise AudioTranscriptionRequestError(
                    str(exc),
                    retryable=isinstance(
                        exc,
                        (APITimeoutError, APIConnectionError, httpx.TimeoutException),
                    ),
                    stream_started=False,
                ) from exc

            if diarization_enabled:
                try:
                    async for event in response:
                        stream_started = True
                        payload = _response_payload(event)
                        event_type = payload.get("type")
                        if (
                            event_type == "transcript.text.delta"
                            and not transcription_started_reported
                        ):
                            await _report_audio_progress(
                                progress_callback,
                                message="Audio transcription started",
                                completed=time_offset_seconds,
                                total=total_seconds,
                            )
                            transcription_started_reported = True
                        elif event_type == "transcript.text.segment":
                            streamed_segments.extend(
                                _normalize_transcript_segments(
                                    {"segments": [payload]},
                                    time_offset_seconds=time_offset_seconds,
                                    segment_id_prefix=segment_id_prefix,
                                    speaker_id_prefix=speaker_id_prefix,
                                )
                            )
                            segment_end = float(payload.get("end") or 0.0)
                            await _report_audio_progress(
                                progress_callback,
                                message="Transcribing audio...",
                                completed=time_offset_seconds + segment_end,
                                total=total_seconds,
                            )
                        elif event_type == "transcript.text.done":
                            streamed_text = str(payload.get("text") or "").strip()
                            usage = payload.get("usage")
                except Exception as exc:
                    if isinstance(exc, AudioTranscriptionRequestError):
                        raise
                    raise AudioTranscriptionRequestError(
                        str(exc),
                        retryable=isinstance(
                            exc,
                            (APITimeoutError, APIConnectionError, httpx.TimeoutException),
                        ),
                        stream_started=stream_started,
                    ) from exc
            else:
                usage = getattr(response, "usage", None)

    completed_seconds = time_offset_seconds + (duration_seconds or 0.0)
    await _report_audio_progress(
        progress_callback,
        message="Audio transcription complete",
        completed=completed_seconds,
        total=total_seconds,
    )
    try:
        await record_openai_cost(
            model_id=model,
            operation_kind=CostOperationKind.TRANSCRIPTION,
            usage=usage,
            duration_seconds=duration_seconds,
        )
    except Exception as exc:
        logger.warning("Failed to record transcription cost: %s", exc)

    payload = _response_payload(response)
    text = (
        streamed_text
        if diarization_enabled
        else str(payload.get("text") or getattr(response, "text", "") or "").strip()
    )
    return AudioTranscriptionResult(
        text=text,
        segments=streamed_segments
        if diarization_enabled
        else _normalize_transcript_segments(
            response,
            time_offset_seconds=time_offset_seconds,
            segment_id_prefix=segment_id_prefix,
            speaker_id_prefix=speaker_id_prefix,
        ),
        duration_seconds=duration_seconds,
        model=model,
    )
