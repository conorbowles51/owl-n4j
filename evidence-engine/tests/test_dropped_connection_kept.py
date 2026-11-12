"""A dropped DeepSeek connection is sent again once, and a file that still fails says why (12 Nov, Thomas Keyes).

One httpx.ReadError in entity summaries failed 6 PDFs after 25 minutes of work, and one in entity extraction failed
ReportThomasKeyes.pdf with an empty reason, which the app showed as "stopped without giving a reason".
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest

from app.pipeline import batch_orchestrator
from app.services import openai_client
from tests.test_deepseek_answer_kept import FORMAT, _ask, _reply

_OK = {"entities": [{"category": "Person", "name": "A"}]}


@pytest.fixture(autouse=True)
def _no_pause(monkeypatch):
    monkeypatch.setattr(openai_client, "_DEEPSEEK_DROPPED_RETRY_DELAYS_S", (0.0,), raising=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("dropped", [httpx.ReadError(""), httpx.WriteError(""),
                                     httpx.RemoteProtocolError("Server disconnected without sending a response.")])
async def test_a_dropped_connection_is_sent_again_once(monkeypatch, dropped) -> None:
    content, sent = await _ask(monkeypatch, [dropped, _reply(_OK)])
    assert json.loads(content) == _OK and len(sent) == 2


@pytest.mark.asyncio
async def test_a_second_drop_fails_the_call(monkeypatch) -> None:
    with pytest.raises(httpx.ReadError):
        await _ask(monkeypatch, [httpx.ReadError(""), httpx.ReadError(""), _reply(_OK)])


@pytest.mark.asyncio
async def test_a_file_failure_without_text_is_stored_with_its_name(monkeypatch) -> None:
    written: dict[str, Any] = {}

    async def fake_update(job_id, status, progress, message, **fields):
        written.update(status=status, message=message, **fields)

    monkeypatch.setattr(batch_orchestrator, "_update_job_status", fake_update)
    await batch_orchestrator._report_file_failure({"id": uuid.uuid4(), "file_name": "ReportThomasKeyes.pdf"},
                                                  httpx.ReadError(""))
    assert written["error_message"] == "ReadError"
    assert written["message"] == "Extraction failed: ReadError"
