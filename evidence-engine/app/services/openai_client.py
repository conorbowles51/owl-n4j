import asyncio
from typing import Any

from openai import AsyncOpenAI

from app.config import settings

_client: AsyncOpenAI | None = None
_semaphore = asyncio.Semaphore(10)


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
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
    return resp.choices[0].message.content or ""


async def embed_texts(
    texts: list[str], model: str | None = None
) -> list[list[float]]:
    client = get_openai_client()
    results: list[list[float]] = []
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        async with _semaphore:
            resp = await client.embeddings.create(
                model=model or settings.openai_embedding_model,
                input=batch,
            )
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
    return resp.text
