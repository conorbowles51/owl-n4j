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
from decimal import Decimal, InvalidOperation
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


# A record whose page reading was replaced by the ledger amount carries both figures, in either of two forms:
# "9,800.00 USD (the ledger amount; the AI reading was 800.00 USD)" or "9800.0 (the ledger amount; read from the page
# as 800.0)". The model's reason may quote the reading; only the ledger figure is the real one.
_FIG = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_SUPERSEDED = re.compile(r"(?P<ledger>" + _FIG + r")(?:\s?[A-Z]{3})?\s*\(the ledger amount; (?:the AI reading was|read from the "
                         r"page as) [^\d)]*(?P<read>" + _FIG + r")[^)]*\)")
_REASON_FIG = re.compile(r"(?<![\d.,/\-])(?:" + _FIG + r")(?![\d/\-]|[.,]\d)")


def _value(figure: str) -> Decimal | None:
    try:
        return Decimal(figure.replace(",", ""))
    except InvalidOperation:
        return None


def _like(written: str, token: str) -> str:
    """The ledger amount as the record writes it, or with the replaced figure's places when those differ."""
    places = len(token.split(".", 1)[1]) if "." in token else 0
    if places == (len(written.split(".", 1)[1]) if "." in written else 0):
        return written
    return (("{:,.%df}" if "," in written else "{:.%df}") % places).format(_value(written))


def ledger_reason(reason: str, text: str) -> str:
    """``reason`` with any figure that is a superseded page reading in ``text`` written as its ledger amount."""
    if not reason or "(the ledger amount;" not in (text or ""):
        return reason
    swaps, real = {}, set()
    for m in _SUPERSEDED.finditer(text):
        ledger, read = _value(m.group("ledger")), _value(m.group("read"))
        if ledger is not None and read is not None and ledger != read:
            swaps.setdefault(read, m.group("ledger"))
            real.add(ledger)
    if not swaps:
        return reason

    def swap(m):
        v = _value(m.group(0))
        if v in swaps and v not in real:
            return _like(swaps[v], m.group(0))
        return m.group(0)
    return _REASON_FIG.sub(swap, reason)


def _parse(raw: str) -> dict:
    raw = (raw or "").strip()
    m = re.search(r"\{.*\}", raw, re.S)
    return json.loads(m.group(0) if m else raw)


EXCERPT_PLACES = 200


def _forms(term: str) -> list[str]:
    """A question word and its singular ("checks" also finds "CHECK 2202")."""
    t = term.casefold()
    return [t, t[:-1]] if len(t) > 4 and t.endswith("s") and not t.endswith("ss") else [t]


def excerpt(body: str, terms: list[str], limit: int = CANDIDATE_CHARS, title: str | None = None) -> str:
    """The part of ``body`` that holds the most different question words, the first such part when several tie."""
    body = body or ""
    if len(body) <= limit:
        return body
    start = best_start(body, terms, limit, title)
    return ("…" if start else "") + body[start:start + limit] + ("…" if start + limit < len(body) else "")


def best_start(body: str, terms: list[str], limit: int, title: str | None = None) -> int:
    """Where a ``limit``-character cut of ``body`` holds the most different question words (0 when none is there).
    A first line that repeats the hit's ``title`` is not read: the title is shown beside the cut, and a question word
    in a file name ("practice-2024-02.pdf") put every cut of a statement page at its header."""
    low = body.casefold()
    first = low.split("\n", 1)[0]
    head = (title or "").casefold().split()[0] if (title or "").strip() else ""
    skip = len(first) if len(head) >= 4 and head.rstrip(",") in first else 0
    found: list[tuple[int, int]] = []  # (position, which term)
    for i, t in enumerate(terms):
        for f in _forms(t):
            if not f:
                continue
            at, n = low.find(f), 0
            while at >= 0 and n < EXCERPT_PLACES:  # a common word's first places are enough to find the best part
                if at >= skip:
                    found.append((at, i))
                at, n = low.find(f, at + 1), n + 1
    found.sort()
    best, start = 0, 0
    counts: dict[int, int] = {}
    lo = hi = 0
    for at, _ in found:  # window starts only move forward, so one pass of two pointers counts every window
        s0 = max(0, min(len(body) - limit, at - limit // 3))
        while hi < len(found) and found[hi][0] < s0 + limit:
            counts[found[hi][1]] = counts.get(found[hi][1], 0) + 1
            hi += 1
        while found[lo][0] < s0:
            counts[found[lo][1]] -= 1
            if not counts[found[lo][1]]:
                del counts[found[lo][1]]
            lo += 1
        if len(counts) > best:
            best, start = len(counts), s0
    return start


def rerank(question: str, candidates: list[dict[str, Any]], *, terms: list[str], windows: list[dict] | None = None,
           model_call: Callable[[str], str] | None = None, extra: int = 0) -> dict[str, Any]:
    """Adds ``score`` (0-10 or None) and ``reason`` to each candidate in place. Returns ``{"reranked", "scored",
    "not_scored", "model", "note"}``. ``extra``: candidates scored beyond ``MAX_CANDIDATES`` (one per hit of a list
    that joined the search, so no candidate scored without that list goes unscored with it)."""
    if not candidates:
        return {"reranked": False, "scored": 0, "not_scored": 0, "model": None, "note": None}
    call = model_call if model_call is not None else default_model_call()
    limit = MAX_CANDIDATES + max(0, int(extra or 0))
    head, tail = candidates[:limit], candidates[limit:]
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
            lines.append("[%d] (%s)\n%s" % (n, meta, excerpt(c.get("text") or "", terms, title=c.get("title"))))
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
                part[i]["reason"] = ledger_reason(str(g.get("reason") or "")[:200], part[i].get("text") or "")
                scored += 1
    not_scored = len(candidates) - scored
    note = None
    if failures and not scored:
        note = "The ranking model did not answer (%s), so results are in search order and not graded." % failures[0]
    elif not_scored:
        note = ("%d of %d results were not scored by the ranking model%s; they are listed after the scored ones, in "
                "search order." % (not_scored, len(candidates), (" (more than %d found)" % limit)
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
