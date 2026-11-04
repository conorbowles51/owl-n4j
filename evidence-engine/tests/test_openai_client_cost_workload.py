"""Each AI call's cost record names its workload, so one step's cost per document can be measured (FEAT-002)."""
import asyncio
from typing import Any

from app.services import openai_client


def test_cost_record_carries_the_workload(monkeypatch) -> None:
    recorded: list[dict[str, Any]] = []

    async def fake_deepseek(messages, **kwargs):
        return "summary", {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}

    async def fake_record(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(openai_client, "resolve_ai_model", lambda workload, model=None, provider=None: ("deepseek", "m"))
    monkeypatch.setattr(openai_client, "_deepseek_chat_completion", fake_deepseek)
    monkeypatch.setattr(openai_client, "record_ai_cost", fake_record)

    asyncio.run(openai_client.chat_completion([{"role": "user", "content": "x"}], workload="ingestion_document_summary"))
    asyncio.run(openai_client.chat_completion([{"role": "user", "content": "x"}]))

    assert recorded[0]["extra_metadata"] == {"workload": "ingestion_document_summary"}
    assert recorded[1]["extra_metadata"] is None
