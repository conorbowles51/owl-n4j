"""The case search: understand, gather, rerank, remove duplicates, grade, page, whole units (plan R1-R4).

Grades (stated in every result as ``grade_rule``): Strong 7-10, Moderate 4-6, Weak 0-3 by the ranking model's score;
Ungraded when the model could not score. Every candidate found is counted in ``total`` and can be paged with
``offset``; weaker ones come after stronger ones and are never dropped.

The ranked list of one search is kept for ``CACHE_S`` seconds in this process, so paging reads the same order and
does not pay the model again.
"""
from __future__ import annotations

import hashlib
import re
import threading
import time
from typing import Any, Callable, Iterable

from services.case_search import net, rerank as R, units
from services.case_search.net import KIND_LABEL, KINDS
from services.case_search.shape import RESULT_KEYS, why_empty
from services.case_search.understand import understand

GRADE_RULE = ("Strong: the ranking model scored 7-10 (states or rests the answer); Moderate: 4-6 (related "
              "background); Weak: 0-3 (shares words, about something else); Ungraded: not scored.")
DEFAULT_LIMIT = 10
MAX_LIMIT = 50
PAGE_CHARS = 40000
CACHE_S = 600
_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


def grade(score: float | None) -> str:
    if score is None:
        return "ungraded"
    return "strong" if score >= 7 else "moderate" if score >= 4 else "weak"


def _fingerprint(h: dict) -> str:
    body = re.sub(r"\[rec://[^\]]+\]|\[txn://[^\]]+\]", "", h.get("text") or "")
    body = re.sub(r"\W+", " ", body.casefold()).strip()[:400]
    return hashlib.sha1(("%s|%s" % (net.AREA_KIND.get(h["area"], h["area"]), body)).encode()).hexdigest()


def dedupe(cands: list[dict]) -> tuple[list[dict], int]:
    """Same citation, or the same text in the same kind of material (one message on two phones, one statement
    page read twice): kept once, the other places listed in ``also_at``."""
    out: list[dict] = []
    by_cite: dict[str, dict] = {}
    by_text: dict[str, dict] = {}
    removed = 0
    for h in cands:
        cite = h.get("cite") or ""
        fp = _fingerprint(h) if (h.get("text") or "").strip() else None
        first = by_cite.get(cite) if cite else None
        if first is None and fp:
            first = by_text.get(fp)
        if first is not None:
            removed += 1
            if cite and cite != first.get("cite") and cite not in first.setdefault("also_at", []):
                first["also_at"].append(cite)
            first["sources"] = sorted(set(first.get("sources") or []) | set(h.get("sources") or []))
            continue
        if cite:
            by_cite[cite] = h
        if fp:
            by_text[fp] = h
        out.append(h)
    return out, removed


def order(cands: list[dict]) -> list[dict]:
    """Scored first, highest score first; within one whole score, kinds of material take turns (so one source does
    not fill a page with equal results); unscored after them, in search order."""
    scored = [c for c in cands if c.get("score") is not None]
    rest = [c for c in cands if c.get("score") is None]
    out: list[dict] = []
    for s in sorted({int(c["score"]) for c in scored}, reverse=True):
        bucket = sorted([c for c in scored if int(c["score"]) == s], key=lambda c: (-c["score"], -c.get("fused", 0)))
        queues: dict[str, list[dict]] = {}
        for c in bucket:
            queues.setdefault(net.AREA_KIND.get(c["area"], c["area"]), []).append(c)
        while any(queues.values()):
            for k in list(queues):
                if queues[k]:
                    out.append(queues[k].pop(0))
    return out + rest


def _key(case_id, question, kinds, areas, phone, person, date_from, date_to, rank, phrase) -> str:
    return "|".join(str(x) for x in (case_id, question.strip(), ",".join(kinds), ",".join(areas or ()), phone, person,
                                     date_from, date_to, rank, phrase))


def ranked(conn, case_id, question: str, *, kinds: tuple[str, ...], areas=None, phone=None, person=None,
           date_from=None,
           date_to=None, rank: bool = True, phrase: bool = True, model_call: Callable[[str], str] | None = None,
           embed_query=None, collections=None, use_cache: bool = True) -> dict[str, Any]:
    """The whole ranked list (no units yet), cached for paging."""
    key = _key(case_id, question, kinds, areas, phone, person, date_from, date_to, rank, phrase)
    now = time.time()
    if use_cache:
        with _lock:
            hit = _cache.get(key)
            if hit and now - hit[0] < CACHE_S:
                return hit[1]
    clock = {}
    t0 = time.time()
    u = understand(conn, case_id, question)
    clock["understand"] = round(time.time() - t0, 2)
    notes = list(u["notes"])
    call = model_call
    if (rank or phrase) and call is None:
        call = R.default_model_call()
    if phrase and call is not None:
        t0 = time.time()
        u["phrasings"], why = R.phrasings(question, model_call=call)
        clock["phrasings"] = round(time.time() - t0, 2)
        if why:
            notes.append(why)
    t0 = time.time()
    got = net.gather(conn, case_id, question, u, kinds, areas=areas, phone=phone, person=person, date_from=date_from,
                     date_to=date_to, embed_query=embed_query, collections=collections)
    clock["gather"] = round(time.time() - t0, 2)
    clock.update(got.get("clock") or {})
    notes += got["notes"]
    cands, removed = dedupe(got["candidates"])
    for c in cands:
        c["kind"] = net.AREA_KIND.get(c["area"], c["area"])
        c["kind_label"] = KIND_LABEL.get(c["area"], c["area"])
    ranking = {"reranked": False, "model": None, "note": "Ranking by model was not asked for; results are in search "
               "order and not graded." if not rank else None, "scored": 0, "not_scored": len(cands)}
    if rank:
        if call is None:
            ranking["note"] = "No ranking model is configured, so results are in search order and not graded."
        else:
            t0 = time.time()
            ranking = R.rerank(question, cands, terms=u["terms"] + [e["term"] for e in u["expansions"]],
                               windows=u["windows"], model_call=call)
            clock["rerank"] = round(time.time() - t0, 2)
    if ranking.get("note"):
        notes.append(ranking["note"])
    ordered = order(cands)
    for c in ordered:
        c["grade"] = grade(c.get("score"))
    out = {"understood": u, "candidates": ordered, "duplicates_removed": removed, "ranking": ranking,
           "searched": got["searched"], "not_searched": got["not_searched"], "notes": notes,
           "meaning_search": got["meaning_search"], "seconds": clock}
    with _lock:
        for k in [k for k, v in _cache.items() if now - v[0] >= CACHE_S]:
            _cache.pop(k, None)
        _cache[key] = (now, out)
    return out


def _public(h: dict, n: int) -> dict:
    cite = h.get("cite") or ""
    return {"n": n, "kind": h["kind"], "area": h["area"], "kind_label": h["kind_label"], "title": h.get("title") or "",
            "cite": cite, "rec": cite if cite.startswith("rec://") else None, "text": h.get("text") or "",
            "unit": h.get("unit"), "chars_not_shown": h.get("chars_not_shown", 0), "score": h.get("score"),
            "grade": h["grade"], "reason": h.get("reason"), "matched": h.get("sources") or [],
            "also_at": h.get("also_at") or [], "read_by_a_model": bool(h.get("as_read")),
            **({"unit_note": h["unit_note"]} if h.get("unit_note") else {})}


def search(conn, case_id, question: str, *, kinds: Iterable[str] | None = None, areas: Iterable[str] | None = None,
           phone: str | None = None,
           person: str | None = None, date_from=None, date_to=None, offset: int = 0, limit: int = DEFAULT_LIMIT,
           min_grade: str | None = None, rank: bool = True, phrase: bool = True,
           model_call: Callable[[str], str] | None = None, embed_query=None, collections=None,
           use_cache: bool = True, page_chars: int = PAGE_CHARS) -> dict[str, Any]:
    """One page of the case search, in the shared result shape (``shape.RESULT_KEYS``).

    ``kinds``: any of ``KINDS`` (default all); ``areas``: only these embedded areas (and ``graph``) inside them.
    ``min_grade``: ``strong`` or ``moderate`` pages only those grades;
    the others are still counted in ``grades`` and ``total``, and the result says how many are below the grade asked
    for. ``rank``/``phrase``: the model reranking and the other phrasings (both on by default)."""
    question = (question or "").strip()
    wanted = tuple(k for k in (kinds or KINDS) if k in KINDS) or KINDS
    unknown = [k for k in (kinds or []) if k not in KINDS]
    offset = max(0, int(offset or 0))
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    if not question:
        res = {"total": 0, "shown": 0, "offset": 0, "next_offset": None, "hits": [], "searched": [],
               "not_searched": list(wanted), "why_empty": "The search was empty: write words, a name, a number or a "
               "question.", "notes": [], "grades": {}, "grade_rule": GRADE_RULE}
        return {**{k: None for k in RESULT_KEYS}, **res}
    r = ranked(conn, case_id, question, kinds=wanted, areas=tuple(areas) if areas else None, phone=phone, person=person, date_from=date_from,
               date_to=date_to, rank=rank, phrase=phrase, model_call=model_call, embed_query=embed_query,
               collections=collections, use_cache=use_cache)
    cands = r["candidates"]
    grades = {g: sum(1 for c in cands if c["grade"] == g) for g in ("strong", "moderate", "weak", "ungraded")}
    pool = cands
    below = 0
    if min_grade in ("strong", "moderate"):
        keep = ("strong",) if min_grade == "strong" else ("strong", "moderate")
        pool = [c for c in cands if c["grade"] in keep]
        below = len(cands) - len(pool)
    page_terms = r["understood"]["terms"] + [e["term"] for e in r["understood"]["expansions"]]
    hits, used = [], 0
    t0 = time.time()
    for i, c in enumerate(pool[offset:offset + limit]):
        unit = units.build(conn, case_id, dict(c), page_terms)
        if hits and used + len(unit["text"]) > page_chars:
            break
        used += len(unit["text"])
        hits.append(_public(unit, offset + i + 1))
    nxt = offset + len(hits) if offset + len(hits) < len(pool) else None
    seconds = dict(r.get("seconds") or {}, units=round(time.time() - t0, 2))
    notes = list(r["notes"])
    if unknown:
        notes.append("Not searched, unknown kind: %s (kinds are %s)." % (", ".join(unknown), ", ".join(KINDS)))
    if len(hits) < min(limit, len(pool) - offset):
        notes.append("%d results shown, fewer than asked for, to keep the page to %d characters; pass offset=%s for "
                     "the next." % (len(hits), page_chars, nxt))
    if below:
        notes.append("%d weaker results are below the grade asked for; they are counted in grades and shown "
                     "without min_grade." % below)
    if r["duplicates_removed"]:
        notes.append("%d duplicates removed (the same record found twice, or the same text in two places; the other "
                     "places are listed in also_at)." % r["duplicates_removed"])
    res = {
        "question": question, "total": len(pool), "shown": len(hits), "offset": offset, "next_offset": nxt,
        "grades": grades, "grade_rule": GRADE_RULE, "below_grade": below, "hits": hits,
        "searched": r["searched"], "not_searched": r["not_searched"], "notes": notes,
        "why_empty": None, "meaning_search": r["meaning_search"], "reranked": bool(r["ranking"].get("reranked")),
        "ranking_model": r["ranking"].get("model"), "duplicates_removed": r["duplicates_removed"],
        "seconds": seconds,
        "understood": {k: r["understood"][k] for k in ("terms", "names", "expansions", "windows", "zone",
                                                       "phrasings")},
    }
    if not pool:
        res["why_empty"] = why_empty(res, below=below)
    return res
