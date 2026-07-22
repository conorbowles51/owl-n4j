from __future__ import annotations

from typing import Any

import pytest

from app.services import openai_client


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


def _fake_async_client(
    response_payload: dict[str, Any],
    captured: dict[str, Any],
) -> type:
    class FakeAsyncClient:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
            captured.update({"url": url, **kwargs})
            return _FakeResponse(response_payload)

    return FakeAsyncClient


SCHEMA_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "health",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
    },
}


@pytest.mark.asyncio
async def test_anthropic_adapter_translates_structured_output(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(openai_client.settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(
        openai_client.httpx,
        "AsyncClient",
        _fake_async_client(
            {
                "content": [{"type": "text", "text": '{"ok":true}'}],
                "usage": {"input_tokens": 7, "output_tokens": 3},
            },
            captured,
        ),
    )

    content, usage = await openai_client._anthropic_chat_completion(
        [
            {"role": "system", "content": "Return a health result."},
            {"role": "user", "content": "Check."},
        ],
        model="claude-sonnet-5",
        response_format=SCHEMA_FORMAT,
        temperature=0.2,
    )

    assert content == '{"ok":true}'
    assert usage == {"input_tokens": 7, "output_tokens": 3}
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    payload = captured["json"]
    assert payload["system"] == "Return a health result."
    assert payload["output_config"]["format"]["type"] == "json_schema"
    assert payload["output_config"]["format"]["schema"] == SCHEMA_FORMAT["json_schema"]["schema"]
    assert "temperature" not in payload


@pytest.mark.asyncio
async def test_gemini_adapter_translates_structured_output_and_usage(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(openai_client.settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(
        openai_client.httpx,
        "AsyncClient",
        _fake_async_client(
            {
                "candidates": [
                    {"content": {"parts": [{"text": '{"ok":true}'}]}}
                ],
                "usageMetadata": {
                    "promptTokenCount": 8,
                    "candidatesTokenCount": 2,
                    "totalTokenCount": 10,
                },
            },
            captured,
        ),
    )

    content, usage = await openai_client._gemini_chat_completion(
        [
            {"role": "system", "content": "Return a health result."},
            {"role": "user", "content": "Check."},
        ],
        model="gemini-3.5-flash",
        response_format=SCHEMA_FORMAT,
        temperature=0.2,
    )

    assert content == '{"ok":true}'
    assert usage == {"input_tokens": 8, "output_tokens": 2, "total_tokens": 10}
    assert captured["url"].endswith("/gemini-3.5-flash:generateContent")
    payload = captured["json"]
    assert payload["systemInstruction"]["parts"][0]["text"] == "Return a health result."
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert payload["generationConfig"]["responseJsonSchema"] == SCHEMA_FORMAT["json_schema"]["schema"]
    assert "temperature" not in payload["generationConfig"]
