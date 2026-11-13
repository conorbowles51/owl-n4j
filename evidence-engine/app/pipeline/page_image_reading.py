"""Scanned PDF pages where OCR finds no words are read by a picture-reading model (Neil, 13 Nov 2026).

OCR (Tesseract) reads print. It cannot read handwriting, so a handwritten page (OPDMD63's floor plan of a house,
rooms A to L) was stored with no text and could not be searched. Each page OCR ran on and found no words on is now
sent, as an image, to the model of the ``scanned_page_reading`` workload (AI settings; DeepSeek's image model by
default), asked to write out the words on the page exactly. The answer is the page's text.

The reading is the model's and is stored as the model's, never as a person's (run-rule 1): the page's location keeps
``extraction_method = "vision_model"``, the provider, model and cost of the call, and a ``model_origin`` (kind
``model``, the person whose processing it ran under, the page it was read from). The page view names the model and
says no person has confirmed it. The text is the document's text, so search, chunking and entity extraction read it
like any other page. ``text_origin`` stays ``recognised_glyphs``: characters recovered from an image, which every
financial reader treats with its cautious rules.

Only pages OCR read and found nothing on; never a page with text, a timed-out page, or a page of another kind. At most
``scanned_page_reading_max_pages`` pages of one file are sent; pages past the cap are marked unread with the reason,
never dropped silently. A model that fails leaves its page empty with the reason; the file is not failed.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.services.ingestion_checkpoints import checkpointed

logger = logging.getLogger(__name__)

WORKLOAD = "scanned_page_reading"
METHOD = "vision_model"
NO_WORDS = "NO WORDS"
PROMPT_VERSION = "scanned-page-reading-v1"
HOW = "Read from the page image by a picture-reading model after OCR found no words on it"
# USD per million tokens (input, output) when Loupe's pricing table has no line for the model; the backend's page-image
# reader keeps the same table (services/financial/vision_reader.PRICES). An unknown model is priced at the dearest line.
PRICES = {"deepseek-flash": (0.14, 0.28), "deepseek-v4-flash": (0.14, 0.28), "deepseek-v4-pro": (0.435, 0.87),
          "gpt-4o": (2.50, 10.00), "gpt-5.6-terra": (2.50, 15.00), "gpt-5.6-sol": (5.00, 30.00),
          "gpt-5.6-luna": (1.00, 6.00)}
FALLBACK_PRICE = (5.00, 30.00)
FALLBACK_PRICING_VERSION = "page_image_reading_table_2026_11_13"


def prompt(page: int, file_name: str) -> str:
    return (f"This image is page {page} of the evidence file '{file_name}'. It is a scanned page where text "
            "recognition found no words, so it may be handwritten. Write out every word, number and label on the page "
            "exactly as written, in reading order, one line for each line of writing. Write [illegible] for a word "
            "you cannot read. Do not describe the page, explain it or add words that are not on it. If the page "
            f"holds no words at all, answer exactly: {NO_WORDS}")


def table_price(model_id: str) -> tuple[float, float]:
    for prefix in sorted(PRICES, key=len, reverse=True):
        if model_id == prefix or model_id.startswith(prefix + "-"):
            return PRICES[prefix]
    return FALLBACK_PRICE


def _wanted(span: dict) -> bool:
    return (span.get("extraction_method") == "tesseract_ocr" and span.get("ocr_status") == "no_text"
            and span.get("end_char") == span.get("start_char"))


def _render_png(file_path: str, page_number: int) -> bytes:
    import fitz
    with fitz.open(file_path) as document:
        page = document[page_number - 1]
        longest = max(page.rect.width, page.rect.height) or 1
        zoom = min(settings.scanned_page_reading_long_side_px / longest, 300 / 72)
        return page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False).tobytes("png")


@checkpointed("pipeline/page_image_reading.py:read_page_image:v1", ignore=("png",))
async def read_page_image(png_sha256: str, page: int, file_name: str, *, png: bytes) -> dict[str, Any]:
    """One page image read by the workload's model: its text (``NO WORDS`` kept as the answer) and the call's cost.
    A resumed ingestion reuses a stored answer for the same image (``png_sha256``) instead of paying again."""
    from app.services.ai_model_policy import resolve_ai_model
    from app.services.cost_tracking import CostOperationKind, record_ai_cost
    from app.services import openai_client

    provider, model = resolve_ai_model(WORKLOAD)
    messages = [{"role": "user", "content": [
        {"type": "text", "text": prompt(page, file_name)},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode("ascii")}},
    ]}]
    started = time.monotonic()
    async with openai_client._semaphore:
        content, usage = await openai_client._provider_completion(provider, model, messages, None, None, 4000)
    seconds = round(time.monotonic() - started, 1)
    rate_in, rate_out = table_price(model)
    cost = await record_ai_cost(provider=provider, model_id=model, operation_kind=CostOperationKind.VISION,
                                usage=usage, extra_metadata={"workload": WORKLOAD, "page": page},
                                fallback_price=(rate_in, rate_out, FALLBACK_PRICING_VERSION))
    tokens = {key: (usage or {}).get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
    return {"text": str(content or "").strip(), "provider": provider, "model": model, "cost_usd": float(cost or 0),
            "tokens": tokens, "seconds": seconds}


def _origin(page: int, reading: dict) -> dict:
    from app.services.cost_tracking import _current_context
    context = _current_context.get()
    return {"kind": "model", "model": reading["model"], "model_id": reading["model"], "provider": reading["provider"],
            "for": {"name": None, "user_id": context.requested_by_user_id if context else None},
            "at": datetime.now(timezone.utc).isoformat(),
            "citation": {key: value for key, value in (("page", page), ("source_document_id",
                         context.source_evidence_file_id if context else None)) if value},
            "how": HOW, "prompt_version": PROMPT_VERSION}


async def read_wordless_pages(file_path: str, file_name: str, text: str, metadata: dict) -> tuple[str, dict]:
    """The PDF's text and metadata with each wordless scanned page read by the model (see the module note)."""
    spans = [dict(span) for span in metadata.get("page_spans") or []]
    wanted = [span for span in spans if _wanted(span)]
    if not wanted or not settings.scanned_page_reading_enabled:
        return text, metadata
    pages = [text[span["start_char"]:span["end_char"]] for span in spans]
    read = cost = 0
    for index, span in enumerate(spans):
        if not _wanted(span):
            continue
        number = span["page"]
        if read >= settings.scanned_page_reading_max_pages:
            span["page_image_reading"] = {"status": "not_read", "message": (
                f"Not sent to the picture-reading model: only {settings.scanned_page_reading_max_pages} pages of one "
                "file are sent.")}
            continue
        read += 1
        try:
            png = await asyncio.to_thread(_render_png, file_path, number)
            reading = await read_page_image(hashlib.sha256(png).hexdigest(), number, file_name, png=png)
        except Exception as exc:  # noqa: BLE001 - one page's failure leaves it empty with the reason
            logger.warning("Page-image reading failed page=%d: %s", number, exc)
            span["page_image_reading"] = {"status": "failed", "message": str(exc)[:300] or type(exc).__name__,
                                          "at": datetime.now(timezone.utc).isoformat()}
            continue
        cost += reading["cost_usd"]
        record = {"status": "read", "provider": reading["provider"], "model": reading["model"],
                  "cost_usd": reading["cost_usd"], "tokens": reading["tokens"], "seconds": reading["seconds"],
                  "prompt_version": PROMPT_VERSION, "at": datetime.now(timezone.utc).isoformat()}
        words = reading["text"]
        if not words or words.strip().rstrip(".").upper() == NO_WORDS:
            record["status"] = "no_words"
            span["page_image_reading"] = record
            continue
        pages[index] = words
        span["page_image_reading"] = record
        span["extraction_method"] = METHOD
        span["model_origin"] = _origin(number, reading)
    offset = 0
    for index, span in enumerate(spans):
        span["start_char"], span["end_char"] = offset, offset + len(pages[index])
        offset += len(pages[index]) + 2
    out = dict(metadata, page_spans=spans)
    out["page_image_reading"] = {"workload": WORKLOAD, "pages_sent": read,
                                 "pages_read": sum(s.get("extraction_method") == METHOD for s in spans),
                                 "cost_usd": round(cost, 6)}
    return "\n\n".join(pages), out

