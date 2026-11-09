"""Every engine request carries Loupe's writing standard (docs/writing-standard.md); page-image readings do not."""
import asyncio
from typing import Any

from app.services import openai_client

MARKER = "Writing standard (Loupe):"


def _run(monkeypatch, messages, response_format=None) -> list[dict[str, Any]]:
    sent: list[list[dict[str, Any]]] = []

    async def fake_deepseek(messages, *args, **kwargs):
        sent.append(messages)
        return "ok", {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}

    async def fake_record(**kwargs):
        return None

    monkeypatch.setattr(openai_client, "resolve_ai_model", lambda workload, model=None, provider=None: ("deepseek", "m"))
    monkeypatch.setattr(openai_client, "_deepseek_chat_completion", fake_deepseek)
    monkeypatch.setattr(openai_client, "record_ai_cost", fake_record)
    asyncio.run(openai_client.chat_completion(messages, response_format=response_format))
    return sent[0]


def test_a_summary_request_gets_the_full_block_in_its_system_message(monkeypatch) -> None:
    sent = _run(monkeypatch, [{"role": "system", "content": "Summarise."}, {"role": "user", "content": "doc"}])
    assert sent[0]["content"].startswith("Summarise.") and MARKER in sent[0]["content"]
    assert "Words never to use" in sent[0]["content"]
    assert sent[1] == {"role": "user", "content": "doc"}


def test_a_json_request_gets_the_short_block_and_a_request_without_system_gets_one(monkeypatch) -> None:
    sent = _run(monkeypatch, [{"role": "user", "content": "x"}], response_format={"type": "json_object"})
    assert sent[0]["role"] == "system" and MARKER in sent[0]["content"] and "Free-text fields" in sent[0]["content"]


def test_a_page_image_reading_is_sent_unchanged(monkeypatch) -> None:
    messages = [{"role": "system", "content": "Read."},
                {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:,"}}]}]
    assert _run(monkeypatch, messages) == messages


def test_the_summary_post_check_keeps_quotes_and_citations() -> None:
    standard = openai_client._writing_standard()
    text = 'Paid 10.00 USD in order to settle [a.pdf, p.2](doc://x/2). "We utilize cash". I hope this helps.'
    assert standard.clean(text) == 'Paid 10.00 USD to settle [a.pdf, p.2](doc://x/2). "We utilize cash".'
