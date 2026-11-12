"""A DeepSeek answer keeps its items through small faults (11 Nov, CHAT JARZ EMPRESA.pdf chunk 0).

The first answer held 9 entities with one property its category lacks; the whole answer was rejected and the retry
answered {"entities": []}, which passes the schema, so the chunk lost every entity. One ConnectTimeout also failed
a whole batch, with an empty stored reason.
"""
from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.pipeline.batch_orchestrator import failure_reason
from app.services import openai_client

_PERSON = {"type": "object", "properties": {"category": {"enum": ["Person"]}, "name": {"type": "string"}},
           "required": ["category", "name"], "additionalProperties": False}
_PLACE = {"type": "object", "properties": {"category": {"enum": ["Location"]}, "name": {"type": "string"},
                                           "location_raw": {"type": "string"}},
          "required": ["category", "name"], "additionalProperties": False}
SCHEMA = {"type": "object", "properties": {"entities": {"type": "array", "items": {"anyOf": [_PERSON, _PLACE]}}},
          "required": ["entities"], "additionalProperties": False}
FORMAT = {"type": "json_schema", "json_schema": {"name": "entities", "strict": True, "schema": SCHEMA}}


def _reply(content: Any) -> dict[str, Any]:
    text = content if isinstance(content, str) else json.dumps(content)
    return {"choices": [{"finish_reason": "stop", "message": {"content": text}}]}


def _client(steps: list[Any], sent: list[dict[str, Any]]) -> type:
    class FakeAsyncClient:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self._steps = iter(steps)

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        async def post(self, url: str, **kwargs: Any) -> Any:
            sent.append(kwargs)
            step = next(self._steps)
            if isinstance(step, BaseException):
                raise step

            class Response:
                def raise_for_status(self) -> None:
                    return None

                def json(self) -> dict[str, Any]:
                    return step
            return Response()
    return FakeAsyncClient


async def _ask(monkeypatch, steps: list[Any]) -> tuple[str, list[dict[str, Any]]]:
    sent: list[dict[str, Any]] = []
    monkeypatch.setattr(openai_client.settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(openai_client.httpx, "AsyncClient", _client(steps, sent))
    monkeypatch.setattr(openai_client, "_DEEPSEEK_CONNECT_RETRY_DELAYS_S", (0.0, 0.0), raising=False)
    content, _usage = await openai_client._deepseek_chat_completion(
        [{"role": "user", "content": "Extract."}], model="deepseek-v4-pro", response_format=FORMAT, temperature=None)
    return content, sent


@pytest.mark.asyncio
async def test_a_property_the_category_lacks_is_dropped_and_the_entities_kept(monkeypatch) -> None:
    answer = {"entities": [{"category": "Person", "name": "Azucena", "location_raw": "CDMX"},
                           {"category": "Location", "name": "CDMX", "location_raw": "Mexico City"}]}
    content, sent = await _ask(monkeypatch, [_reply(answer)])
    assert json.loads(content) == {"entities": [{"category": "Person", "name": "Azucena"},
                                                {"category": "Location", "name": "CDMX",
                                                 "location_raw": "Mexico City"}]}
    assert len(sent) == 1


_ENTITY = {"type": "object", "properties": {"category": {"type": "string"}, "name": {"type": "string"},
                                           "properties": {"type": "object"}},
           "required": ["category", "name"], "additionalProperties": False}
BAG_FORMAT = {"type": "json_schema", "json_schema": {"name": "entities", "strict": True, "schema": {
    "type": "object", "properties": {"entities": {"type": "array", "items": _ENTITY}},
    "required": ["entities"], "additionalProperties": False}}}


@pytest.mark.asyncio
async def test_an_attribute_beside_the_fields_moves_into_properties(monkeypatch) -> None:
    # The live answer: location fields written next to name instead of inside properties.
    answer = {"entities": [{"category": "Person", "name": "Lic. R", "location_raw": "CDMX", "city": "CDMX",
                            "properties": {"role": "lawyer", "city": "Mexico City"}},
                           {"category": "Person", "name": "Azucena", "properties": {"role": "sender"}}]}
    sent: list[dict[str, Any]] = []
    monkeypatch.setattr(openai_client.settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(openai_client.httpx, "AsyncClient", _client([_reply(answer)], sent))
    content, _usage = await openai_client._deepseek_chat_completion(
        [{"role": "user", "content": "Extract."}], model="deepseek-v4-pro", response_format=BAG_FORMAT,
        temperature=None)
    # The value already inside properties is kept; the one beside it, which disagrees, is not written over it.
    assert json.loads(content) == {"entities": [
        {"category": "Person", "name": "Lic. R",
         "properties": {"role": "lawyer", "city": "Mexico City", "location_raw": "CDMX"}},
        {"category": "Person", "name": "Azucena", "properties": {"role": "sender"}}]}
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_an_empty_retry_after_an_answer_with_items_is_not_accepted(monkeypatch) -> None:
    wrong = {"entities": [{"category": "Person", "name": 7}, {"category": "Person", "name": "B"}]}
    right = {"entities": [{"category": "Person", "name": "A"}, {"category": "Person", "name": "B"}]}
    content, sent = await _ask(monkeypatch, [_reply(wrong), _reply({"entities": []}), _reply(right)])
    assert json.loads(content) == right
    assert len(sent) == 3
    assert "held 2 items and this one holds none" in sent[2]["json"]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_only_empty_retries_fail_the_call_instead_of_losing_the_items(monkeypatch) -> None:
    wrong = {"entities": [{"category": "Person", "name": 7}]}
    with pytest.raises(ValueError, match="holds none"):
        await _ask(monkeypatch, [_reply(wrong), _reply({"entities": []}), _reply({"entities": []})])


@pytest.mark.asyncio
async def test_an_empty_first_answer_is_still_accepted(monkeypatch) -> None:
    content, sent = await _ask(monkeypatch, [_reply({"entities": []})])
    assert json.loads(content) == {"entities": []} and len(sent) == 1


@pytest.mark.asyncio
async def test_a_request_that_never_reached_deepseek_is_sent_again(monkeypatch) -> None:
    ok = {"entities": [{"category": "Person", "name": "A"}]}
    content, sent = await _ask(monkeypatch, [httpx.ConnectTimeout(""), httpx.ConnectError("refused"), _reply(ok)])
    assert json.loads(content) == ok and len(sent) == 3


@pytest.mark.asyncio
async def test_connection_failures_end_after_three_tries(monkeypatch) -> None:
    with pytest.raises(httpx.ConnectTimeout):
        await _ask(monkeypatch, [httpx.ConnectTimeout("") for _ in range(3)] + [_reply({"entities": []})])


def test_a_failure_without_text_is_stored_with_its_name() -> None:
    assert failure_reason(httpx.ConnectTimeout("")) == "ConnectTimeout"
    assert failure_reason(ValueError("bad page")) == "bad page"
