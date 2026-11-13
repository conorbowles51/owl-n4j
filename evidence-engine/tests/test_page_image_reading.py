"""Scanned pages where OCR finds no words go to the picture-reading model; the text is stored as the model's reading
with its page and its cost (app.pipeline.page_image_reading; OPDMD63's handwritten floor plan, 13 Nov 2026)."""
from pathlib import Path
from typing import Any

import fitz
import pytest

from app.config import settings
from app.pipeline import page_image_reading as R
from app.pipeline.extract_text import extract_text
from app.services import cost_tracking, openai_client
from app.services.evidence_document_text import build_canonical_document_text


class _FakeSession:
    def __init__(self, sink):
        self.sink = sink

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def add(self, row):
        self.sink.append(row)

    async def commit(self):
        return None


def _pdf(path: Path, blank_pages: int = 1) -> Path:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Typed first page of the file", fontsize=12)
    for _ in range(blank_pages):
        drawn = document.new_page()  # a drawing with no characters: OCR finds no words on it
        drawn.draw_rect(fitz.Rect(100, 100, 400, 400), color=(0, 0, 0), width=3)
    document.save(path)
    document.close()
    return path


@pytest.fixture
def model(monkeypatch):
    calls: list[dict[str, Any]] = []
    rows: list[Any] = []
    answers: list[Any] = []

    async def fake_completion(provider, model_id, messages, response_format, temperature, max_output_tokens):
        calls.append(dict(provider=provider, model=model_id, messages=messages))
        answer = answers.pop(0) if answers else "Room A Kitchen\nRoom B Hall"
        if isinstance(answer, Exception):
            raise answer
        return answer, {"prompt_tokens": 2_000, "completion_tokens": 100, "total_tokens": 2_100}

    async def no_rate(*args):
        return None

    monkeypatch.setattr(openai_client, "_provider_completion", fake_completion)
    monkeypatch.setattr(cost_tracking, "_resolve_pricing_rate", no_rate)
    monkeypatch.setattr(cost_tracking, "async_session", lambda: _FakeSession(rows))
    return calls, rows, answers


@pytest.mark.asyncio
async def test_a_wordless_scanned_page_is_read_by_the_model_and_kept_as_its_reading(tmp_path, model) -> None:
    calls, rows, _ = model
    doc = await extract_text(str(_pdf(tmp_path / "plan.pdf")), "plan.pdf")

    spans = doc.metadata["page_spans"]
    first, second = spans
    assert doc.text[first["start_char"]:first["end_char"]].startswith("Typed first page")
    assert doc.text[second["start_char"]:second["end_char"]] == "Room A Kitchen\nRoom B Hall"
    assert first.get("page_image_reading") is None and first["extraction_method"] != R.METHOD
    assert second["extraction_method"] == "vision_model"
    assert second["text_origin"] == "recognised_glyphs"
    assert second["model_origin"]["kind"] == "model"
    assert second["model_origin"]["model"] == "deepseek-flash"
    assert second["model_origin"]["citation"]["page"] == 2
    reading = second["page_image_reading"]
    assert reading["status"] == "read" and reading["provider"] == "deepseek"
    # 2,000 in and 100 out at DeepSeek's flash price (0.14 / 0.28 per million): Loupe's table has no line for it.
    assert reading["cost_usd"] == pytest.approx(0.000308)
    assert doc.metadata["page_image_reading"]["cost_usd"] == pytest.approx(0.000308)
    assert len(calls) == 1 and calls[0]["messages"][0]["content"][1]["type"] == "image_url"
    assert rows[0].cost_usd == pytest.approx(0.000308)
    assert rows[0].operation_kind == "vision"
    assert rows[0].extra_metadata["page"] == 2 and rows[0].extra_metadata["workload"] == "scanned_page_reading"
    assert rows[0].pricing_version == R.FALLBACK_PRICING_VERSION

    stored = build_canonical_document_text(doc)
    assert "Room B Hall" in stored.content
    page_two = [loc for loc in stored.source_locations if loc["page_number"] == 2][0]
    assert page_two["extraction_method"] == "vision_model"
    assert page_two["model_origin"]["kind"] == "model"
    assert stored.content[page_two["start_char"]:page_two["end_char"]] == "Room A Kitchen\nRoom B Hall"


@pytest.mark.asyncio
async def test_no_words_failure_and_cap_leave_the_page_empty_with_the_reason(tmp_path, model, monkeypatch) -> None:
    _, _, answers = model
    answers.extend(["NO WORDS", RuntimeError("DeepSeek is not connected")])
    monkeypatch.setattr(settings, "scanned_page_reading_max_pages", 2)
    doc = await extract_text(str(_pdf(tmp_path / "three.pdf", blank_pages=3)), "three.pdf")
    statuses = [span.get("page_image_reading", {}).get("status") for span in doc.metadata["page_spans"]]
    assert statuses == [None, "no_words", "failed", "not_read"]
    assert "DeepSeek is not connected" in doc.metadata["page_spans"][2]["page_image_reading"]["message"]
    assert "only 2 pages" in doc.metadata["page_spans"][3]["page_image_reading"]["message"]
    assert all(span["start_char"] == span["end_char"] for span in doc.metadata["page_spans"][1:])
    assert all(span["extraction_method"] == "tesseract_ocr" for span in doc.metadata["page_spans"][1:])


@pytest.mark.asyncio
async def test_switch_off_sends_nothing(tmp_path, model, monkeypatch) -> None:
    calls, _, _ = model
    monkeypatch.setattr(settings, "scanned_page_reading_enabled", False)
    doc = await extract_text(str(_pdf(tmp_path / "off.pdf")), "off.pdf")
    assert calls == []
    assert doc.metadata["page_spans"][1]["ocr_status"] == "no_text"
    assert "page_image_reading" not in doc.metadata
