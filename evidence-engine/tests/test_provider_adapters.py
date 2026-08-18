from __future__ import annotations

import json
from types import SimpleNamespace
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


def _sequence_async_client(
    response_payloads: list[dict[str, Any]],
    captured: list[dict[str, Any]],
) -> type:
    class FakeAsyncClient:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self._responses = iter(response_payloads)

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
            captured.append({"url": url, **kwargs})
            return _FakeResponse(next(self._responses))

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

ARRAY_SCHEMA_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "items",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                        "required": ["name"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["items"],
            "additionalProperties": False,
        },
    },
}


@pytest.mark.asyncio
async def test_openai_adapter_applies_output_token_limit(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeCompletions:
        async def create(self, **kwargs: Any) -> Any:
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="bounded"))],
                usage={"prompt_tokens": 5, "completion_tokens": 2},
            )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions())
    )
    monkeypatch.setattr(openai_client, "get_openai_client", lambda: fake_client)

    content, usage = await openai_client._openai_chat_completion(
        [{"role": "user", "content": "Summarize."}],
        model="gpt-5.6-sol",
        response_format=None,
        temperature=None,
        max_output_tokens=1234,
    )

    assert content == "bounded"
    assert usage == {"prompt_tokens": 5, "completion_tokens": 2}
    assert captured["max_completion_tokens"] == 1234


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
        max_output_tokens=1234,
    )

    assert content == '{"ok":true}'
    assert usage == {"input_tokens": 7, "output_tokens": 3}
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    payload = captured["json"]
    assert payload["system"] == "Return a health result."
    assert payload["output_config"]["format"]["type"] == "json_schema"
    assert payload["output_config"]["format"]["schema"] == SCHEMA_FORMAT["json_schema"]["schema"]
    assert payload["max_tokens"] == 1234
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
        max_output_tokens=1234,
    )

    assert content == '{"ok":true}'
    assert usage == {"input_tokens": 8, "output_tokens": 2, "total_tokens": 10}
    assert captured["url"].endswith("/gemini-3.5-flash:generateContent")
    payload = captured["json"]
    assert payload["systemInstruction"]["parts"][0]["text"] == "Return a health result."
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert payload["generationConfig"]["responseJsonSchema"] == SCHEMA_FORMAT["json_schema"]["schema"]
    assert payload["generationConfig"]["maxOutputTokens"] == 1234
    assert "temperature" not in payload["generationConfig"]


@pytest.mark.asyncio
async def test_deepseek_adapter_uses_json_output_and_normalizes_usage(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(openai_client.settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(
        openai_client.httpx,
        "AsyncClient",
        _fake_async_client(
            {
                "choices": [{"message": {"content": '{"ok":true}'}}],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 2,
                    "total_tokens": 13,
                },
            },
            captured,
        ),
    )

    content, usage = await openai_client._deepseek_chat_completion(
        [{"role": "user", "content": "Check."}],
        model="deepseek-v4-flash",
        response_format=SCHEMA_FORMAT,
        temperature=0.2,
        max_output_tokens=1234,
    )

    assert content == '{"ok":true}'
    assert usage == {"prompt_tokens": 11, "completion_tokens": 2, "total_tokens": 13}
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    payload = captured["json"]
    assert payload["model"] == "deepseek-v4-flash"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["max_tokens"] == 1234
    assert "valid JSON" in payload["messages"][0]["content"]
    assert "JSON SCHEMA" in payload["messages"][0]["content"]
    assert '"required":["ok"]' in payload["messages"][0]["content"]


@pytest.mark.asyncio
async def test_deepseek_adapter_does_not_invent_an_output_token_limit(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(openai_client.settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(
        openai_client.httpx,
        "AsyncClient",
        _fake_async_client(
            {"choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}]},
            captured,
        ),
    )

    await openai_client._deepseek_chat_completion(
        [{"role": "user", "content": "Check."}],
        model="deepseek-v4-flash",
        response_format=SCHEMA_FORMAT,
        temperature=None,
    )

    assert "max_tokens" not in captured["json"]


@pytest.mark.asyncio
async def test_deepseek_adapter_wraps_an_unambiguous_top_level_array(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(openai_client.settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(
        openai_client.httpx,
        "AsyncClient",
        _fake_async_client(
            {
                "choices": [
                    {"finish_reason": "stop", "message": {"content": '[{"name":"alpha"}]'}}
                ]
            },
            captured,
        ),
    )

    content, _usage = await openai_client._deepseek_chat_completion(
        [{"role": "user", "content": "Extract."}],
        model="deepseek-v4-flash",
        response_format=ARRAY_SCHEMA_FORMAT,
        temperature=None,
    )

    assert json.loads(content) == {"items": [{"name": "alpha"}]}


@pytest.mark.asyncio
async def test_deepseek_adapter_retries_truncated_and_malformed_json(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(openai_client.settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(
        openai_client.httpx,
        "AsyncClient",
        _sequence_async_client(
            [
                {
                    "choices": [
                        {"finish_reason": "length", "message": {"content": '{"ok":'}}
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                },
                {
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": '{"ok":'}}
                    ],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 21, "total_tokens": 32},
                },
                {
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": '{"ok":true}'}}
                    ],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 2, "total_tokens": 14},
                },
            ],
            captured,
        ),
    )

    content, usage = await openai_client._deepseek_chat_completion(
        [{"role": "user", "content": "Check."}],
        model="deepseek-v4-flash",
        response_format=SCHEMA_FORMAT,
        temperature=None,
    )

    assert json.loads(content) == {"ok": True}
    assert usage == {"prompt_tokens": 33, "completion_tokens": 43, "total_tokens": 76}
    assert len(captured) == 3
    assert "max_tokens" not in captured[0]["json"]
    assert captured[1]["json"]["max_tokens"] == 384_000
    assert captured[2]["json"]["max_tokens"] == 384_000
    assert "previous attempt was invalid" in captured[1]["json"]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_deepseek_adapter_rejects_schema_wrong_json_after_retries(monkeypatch) -> None:
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(openai_client.settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(
        openai_client.httpx,
        "AsyncClient",
        _sequence_async_client(
            [
                {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
                for _ in range(3)
            ],
            captured,
        ),
    )

    with pytest.raises(ValueError, match="missing required property 'ok'"):
        await openai_client._deepseek_chat_completion(
            [{"role": "user", "content": "Check."}],
            model="deepseek-v4-flash",
            response_format=SCHEMA_FORMAT,
            temperature=None,
        )

    assert len(captured) == 3
