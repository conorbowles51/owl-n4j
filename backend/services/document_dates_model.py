"""A model reads a document's date where the rules read none (Neil 2026-11-20, followups).

The rules (services.document_dates) read a date only after a cue word or at the head of a page. Where they find no
date at all, the "Document dates" workload's model (DeepSeek's fast model by default, switched on the AI settings
page) reads the start of the text and names the document's date with the words it read it from. Its answer is kept
only when those words are in the text as written and hold a date that reads as the day it names, so a date the
document does not state is never saved. The reading is saved as source ``model``, shown "Read by Loupe · not
confirmed" with its words and page, like a rule's reading; a person confirms or corrects it the same way.

New files: read once after the rules, on a background queue (one model call per undated file; the ingest never waits
for it). Existing files: ``document_date_store.backfill(model=True)``, dry run first (it counts the calls).
``LOUPE_DOC_DATES_MODEL=off`` stops every call (the test suite sets it).
"""
from __future__ import annotations

import json
import logging
import os
import queue
import re
import threading
import time
import uuid
from datetime import date
from typing import Callable, Optional

log = logging.getLogger(__name__)

WORKLOAD = "document_dates"
RULE_PREFIX = "docdates-model-1"
HEAD_CHARS = 6000
TIMEOUT_S = 60
KINDS = ("written", "signed", "received")

PROMPT = """You read the date a document states about itself. Below is the start of one document's text, as read.

Name the date the document was written (or signed, or received) when the text states one: a letterhead date, a
date line, a date beside a signature, a date stamp. Do not give a date the text only mentions (a transaction, a
birth date, a deadline, an incident inside the text). Copy the words exactly as they appear, including the date.

Answer JSON only: {"dates": [{"kind": "written" | "signed" | "received", "date": "YYYY-MM-DD", "words": "<the
words, copied exactly, at most 120 characters, holding the date>"}]}. At most one per kind. {"dates": []} when the
text states no date of its own.

TEXT:
"""


def enabled() -> bool:
    return os.environ.get("LOUPE_DOC_DATES_MODEL", "on").strip().lower() != "off"


def default_model_call() -> Optional[Callable[[str], str]]:
    """The workload's model as ``prompt -> text`` (JSON mode), or None (switched off, or no model configured)."""
    if not enabled():
        return None
    try:
        from postgres.session import get_background_session
        from services.ai_model_policy import get_workload_model
        from services.ai_provider_credentials import get_provider_api_key
        from services.llm_service import LLMExecutionContext
        with get_background_session() as db:
            provider, model_id = get_workload_model(db, WORKLOAD)
            key = get_provider_api_key(db, provider)
    except Exception as exc:  # noqa: BLE001 - no model: the rule readings stand alone
        log.warning("Document dates model unavailable: %s", exc)
        return None

    def call(prompt: str) -> str:
        ctx = LLMExecutionContext(provider, model_id, api_key=key)
        return ctx.call(prompt, temperature=0.0, json_mode=True, timeout=TIMEOUT_S)
    call.model = "%s/%s" % (provider, model_id)  # type: ignore[attr-defined]
    return call


def _fold(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().casefold()


def _holds(words: str, day: date) -> bool:
    """The words hold a date that reads as ``day`` (a numeric date may be read either way round)."""
    from services.document_dates import _DATE2, _to_date
    for m in _DATE2.finditer(words):
        if day in {_to_date(m), _to_date(m, day_first=True), _to_date(m, day_first=False)}:
            return True
    return False


def prompt_for(text: str) -> str:
    from services.writing_standard import reading_prompt
    return reading_prompt(PROMPT + (text or "")[:HEAD_CHARS])


def read(text: str, source_locations, call: Callable[[str], str]) -> list[dict]:
    """The model's readings that pass the check: dicts as ``document_dates.read_dates`` gives them, rule
    ``model``."""
    from services.document_dates import MAX_YEAR, MIN_YEAR, _page
    head = (text or "")[:HEAD_CHARS]
    if not head.strip():
        return []
    raw = call(prompt_for(head))
    m = re.search(r"\{.*\}", raw or "", re.S)
    try:
        answer = json.loads(m.group(0) if m else raw)
    except (TypeError, ValueError):
        log.warning("Document dates model answered no JSON")
        return []
    folded = _fold(head)
    out: dict[str, dict] = {}
    for d in (answer.get("dates") if isinstance(answer, dict) else None) or []:
        if not isinstance(d, dict):
            continue
        kind, words = d.get("kind"), (d.get("words") or "").strip()
        try:
            day = date.fromisoformat(str(d.get("date") or ""))
        except ValueError:
            continue
        if kind not in KINDS or kind in out or not words or not (MIN_YEAR <= day.year <= MAX_YEAR):
            continue
        if _fold(words) not in folded or not _holds(words, day):
            continue  # not in the text as written, or not the day it names: never saved
        at = _locate(head, words)
        out[kind] = {"kind": kind, "date_from": day, "date_to": day, "rule": "model",
                     "words": re.sub(r"\s+", " ", words)[:300], "page": _page(source_locations, at)}
    return list(out.values())


def _locate(text: str, words: str) -> int:
    """Where the words start in the text (whitespace may differ), for the page."""
    pattern = r"\s+".join(re.escape(w) for w in words.split())
    m = re.search(pattern, text, re.I)
    return m.start() if m else 0


def rule_name(call) -> str:
    return "%s:%s" % (RULE_PREFIX, getattr(call, "model", "model"))[:80]


# ---- the background queue for new files ----------------------------------------------------------------------------

_queue: "queue.Queue[str]" = queue.Queue()
_worker: Optional[threading.Thread] = None
_lock = threading.Lock()
WAIT_S = 5


def schedule(file_id) -> None:
    """Read this file's date by model after the ingest commits (a daemon thread per process; one call per file)."""
    global _worker
    if not enabled():
        return
    _queue.put(str(file_id))
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_run, name="document-dates-model", daemon=True)
            _worker.start()


def _run() -> None:
    from postgres.session import get_background_session
    from services.document_date_store import store_model_for_file
    call = None
    while True:
        fid = _queue.get()
        time.sleep(WAIT_S)  # the ingest's own transaction commits first
        try:
            call = call or default_model_call()
            if call is None:
                continue
            with get_background_session() as db:
                store_model_for_file(db, uuid.UUID(fid), call)
                db.commit()
        except Exception:  # noqa: BLE001 - a failure costs this file's model date, never the ingest
            log.exception("Document date not read by model for %s", fid)
