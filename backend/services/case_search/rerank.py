"""Score every candidate against the question with a model (plan R2c), and suggest other phrasings (R2a).

The model is the ``search_ranking`` workload (DeepSeek's fast model by default; the AI settings page changes it). It
sees the question, the date windows and each candidate's text (up to ``CANDIDATE_CHARS`` around the matched words)
and returns a score 0-10 with a one-line reason per candidate. It never sees an answer key.

When the model cannot be reached the candidates keep their search order, every score is ``None`` and the result says
so (``reranked: False``, a note with the reason). Nothing is dropped either way.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)

WORKLOAD = "search_ranking"
MAX_CANDIDATES = 60     # candidates scored per search; the rest keep their search order below them, counted
CANDIDATE_CHARS = 900
BATCH = 30              # candidates per model call
TIMEOUT_S = 90

RANK_PROMPT = """You score search results for an investigator's question about a case.

Question: {question}
{when}
Score each result from 0 to 10 for how much it helps answer the question:
10 = states the answer or a fact the answer rests on; 7-9 = directly about the question's people, place, time or
event; 4-6 = related background a careful investigator would read; 1-3 = shares words but is about something else;
0 = unrelated. A result about the right people at the wrong time, or the right time with the wrong people, scores 3
or less unless the question asks for that. Judge only from the text shown.

Give each result a reason of at most 15 words saying what it shows, in plain words. Do not quote more than 8 words.

Results:
{items}

Answer with JSON only: {{"scores": [{{"i": <result number>, "score": <0-10>, "reason": "<reason>"}}, ...]}} with one
entry for every result."""

PHRASE_PROMPT = """An investigator searches a case's phones, documents, bank statements and notes with this question:

{question}

Write up to 3 short search phrasings that would find records answering it: other words for the same things
(synonyms, how people write it in texts, how a bank statement or a form would print it). Keep names, numbers and
dates exactly as written. Do not invent facts, names or places that are not in the question.

Answer with JSON only: {{"phrasings": ["...", "..."]}}"""


def default_model_call() -> Callable[[str], str] | None:
    """The workload's model as ``prompt -> text`` (JSON mode), or ``None`` when no model is configured.
    ``LOUPE_CASE_SEARCH_MODEL=off`` (the test suite sets it): no model, so a test never pays for a call."""
    if os.environ.get("LOUPE_CASE_SEARCH_MODEL", "").strip().lower() == "off":
        return None
    try:
        from postgres.session import get_background_session
        from services.ai_model_policy import get_workload_model
        from services.ai_provider_credentials import get_provider_api_key
        from services.llm_service import LLMExecutionContext
        with get_background_session() as db:
            provider, model_id = get_workload_model(db, WORKLOAD)
            key = get_provider_api_key(db, provider)
    except Exception as exc:  # noqa: BLE001 - no model: the search still answers, unranked, said so
        logger.warning("Search ranking model unavailable: %s", exc)
        return None

    def call(prompt: str) -> str:
        # one context per call: a context keeps its last prompt and usage for the cost record, and batches run
        # side by side
        ctx = LLMExecutionContext(provider, model_id, api_key=key)
        return ctx.call(prompt, temperature=0.0, json_mode=True, timeout=TIMEOUT_S)
    call.model = "%s/%s" % (provider, model_id)  # type: ignore[attr-defined]
    return call


def _parse(raw: str) -> dict:
    raw = (raw or "").strip()
    m = re.search(r"\{.*\}", raw, re.S)
    return json.loads(m.group(0) if m else raw)


def excerpt(body: str, terms: list[str], limit: int = CANDIDATE_CHARS) -> str:
    body = body or ""
    if len(body) <= limit:
        return body
    low = body.casefold()
    at = next((low.find(t.casefold()) for t in terms if low.find(t.casefold()) >= 0), -1)
    start = max(0, min(len(body) - limit, at - limit // 3)) if at >= 0 else 0
    return ("…" if start else "") + body[start:start + limit] + ("…" if start + limit < len(body) else "")


def rerank(question: str, candidates: list[dict[str, Any]], *, terms: list[str], windows: list[dict] | None = None,
           model_call: Callable[[str], str] | None = None) -> dict[str, Any]:
    """Adds ``score`` (0-10 or None) and ``reason`` to each candidate in place. Returns ``{"reranked", "scored",
    "not_scored", "model", "note"}``."""
    if not candidates:
        return {"reranked": False, "scored": 0, "not_scored": 0, "model": None, "note": None}
    call = model_call if model_call is not None else default_model_call()
    head, tail = candidates[:MAX_CANDIDATES], candidates[MAX_CANDIDATES:]
    for c in candidates:
        c.setdefault("score", None)
        c.setdefault("reason", None)
    if call is None:
        return {"reranked": False, "scored": 0, "not_scored": len(candidates), "model": None,
                "note": "No ranking model is configured, so results are in search order and not graded."}
    when = ""
    if windows:
        when = "Dates in the question (case time zone): %s." % "; ".join(w["days"] for w in windows)
    scored, failures = 0, []
    parts = [head[b:b + BATCH] for b in range(0, len(head), BATCH)]

    def ask(part):
        lines = []
        for n, c in enumerate(part, 1):
            meta = " | ".join(x for x in (c.get("kind_label") or c.get("kind"), c.get("date") or "", c.get("title") or "")
                              if x)
            lines.append("[%d] (%s)\n%s" % (n, meta, excerpt(c.get("text") or "", terms)))
        prompt = RANK_PROMPT.format(question=question.strip(), when=when, items="\n\n".join(lines))
        return _parse(call(prompt)).get("scores") or []

    # the batches are asked side by side: one search waits for the slowest batch, not their sum
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max(1, len(parts))) as pool:
        futures = [pool.submit(ask, part) for part in parts]
        answers = []
        for f in futures:
            try:
                answers.append(f.result())
            except Exception as exc:  # noqa: BLE001 - this batch stays unscored, said so
                failures.append(str(exc)[:160])
                answers.append([])
    for part, got in zip(parts, answers):
        for g in got:
            if not isinstance(g, dict):
                continue
            try:
                i = int(g.get("i")) - 1
                s = max(0.0, min(10.0, float(g.get("score"))))
            except (TypeError, ValueError):
                continue
            if 0 <= i < len(part) and part[i]["score"] is None:
                part[i]["score"] = s
                part[i]["reason"] = str(g.get("reason") or "")[:200]
                scored += 1
    not_scored = len(candidates) - scored
    note = None
    if failures and not scored:
        note = "The ranking model did not answer (%s), so results are in search order and not graded." % failures[0]
    elif not_scored:
        note = ("%d of %d results were not scored by the ranking model%s; they are listed after the scored ones, in "
                "search order." % (not_scored, len(candidates), (" (more than %d found)" % MAX_CANDIDATES)
                                   if tail else ""))
    return {"reranked": scored > 0, "scored": scored, "not_scored": not_scored,
            "model": getattr(call, "model", None), "note": note}


def phrasings(question: str, *, model_call: Callable[[str], str] | None = None, limit: int = 3) -> tuple[list[str], str | None]:
    """Other phrasings of the question (model), or ``([], reason)``."""
    call = model_call if model_call is not None else default_model_call()
    if call is None:
        return [], "No ranking model is configured, so the question was searched as written only."
    try:
        got = _parse(call(PHRASE_PROMPT.format(question=question.strip()))).get("phrasings") or []
    except Exception as exc:  # noqa: BLE001
        return [], "Other phrasings could not be made (%s); the question was searched as written." % str(exc)[:120]
    out = []
    for p in got:
        p = str(p or "").strip()
        if p and p.casefold() != question.strip().casefold() and p not in out:
            out.append(p[:200])
    return out[:limit], None
