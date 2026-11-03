"""Approach 9: intent and research, the term-matching view (docs/cellebrite/05 section 12; unit 05-S12).

Per phone, the searches and visited pages whose search text, page title or page address path words match the case
vocabulary (``vocabulary.py``), each with the time it carries and what that time means (04): a search's own time
when recorded; for a page, its last visit only, with the visit count as the total (12.3 step 2). A page last visited
after a key date is never shown as visited before it (12.8 test 1); a search with no time is listed under "time not
recorded" and never placed on a timeline (12.8 test 2). The full list of searches and pages is the phone's own
record lists; this view is the vocabulary matches.

Gate (12.6) passed: see 05 section 12.6 for M-9b (intent m9.3).

Decisions (05 section 19):

- 19.S12-a A term matching 3 or more records of the case is a common term (a business or site name); its results
  have strength ``common_term``, the others ``specific_term``. Nothing is dropped. Reverse if investigators' reviews
  show common-term hits confirmed as often as specific ones.
- 19.S12-b Page addresses are matched on their path words only (not the host, query or digits shorter than a phone
  number); a hit only in the address says so. Reverse if address hits are rejected on review far more than title
  hits.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from urllib.parse import unquote, urlsplit

from sqlalchemy import text

from services.phone_analysis import fields as FV
from services.phone_analysis import vocabulary as V

CODE = "intent"
VERSION = "9.1"
PARAMETERS: dict = {}
KINDS = ("search_hit", "page_hit")
SUPPORTS = ("vocabulary_match", "searched_at", "last_visited")
UNDERCUTS = ("time_not_recorded", "last_visit_only", "suggested_or_prefetched", "synced_history", "common_term",
             "address_only", "vocabulary_partial", "deleted_or_carved")
DIRECTION_CODES = SUPPORTS + UNDERCUTS
SIGNALS = [
    {"code": "searches", "label": "Searches"},
    {"code": "pages", "label": "Visited pages"},
]
COMMON_AT = 3
_last = {"counts": {}}


def _d(code, detail, locators=()):
    return {"code": code, "detail": detail, "locators": [str(x) for x in locators]}


def input_manifest(conn, case_id) -> dict:
    from services.phone_analysis import typed_words
    return typed_words.input_manifest(conn, case_id)


def coverage(conn, case_id) -> dict:
    counts = defaultdict(dict)
    for r in conn.execute(text(
            "SELECT extraction_id, model_type, count(*) FROM pv_record WHERE case_id = :c AND model_type IN "
            "('SearchedItem', 'VisitedPage') GROUP BY 1, 2"), {"c": str(case_id)}):
        counts[str(r[0])][r[1]] = int(r[2])
    phones = {}
    for ext, label in FV.active_phones(conn, case_id).items():
        s, p = counts[ext].get("SearchedItem", 0), counts[ext].get("VisitedPage", 0)
        phones[ext] = {"label": label, "signals": {"searches": {"carries_signal": s > 0, "records": s},
                                                   "pages": {"carries_signal": p > 0, "records": p}}}
    return {"phones": phones, "signals": SIGNALS}


def url_words(url) -> str:
    """The path of a page address as words (19.S12-b)."""
    try:
        path = urlsplit(url or "").path
    except ValueError:
        return ""
    return re.sub(r"[\W_]+", " ", unquote(path))


def _read(conn, ext, vocab):
    """``{record_uid: {"model_type", "text", "matches": {(kind, token)}, "matched_in": {...}}}`` of the hits."""
    hits = {}
    for r in conn.execute(text(
            "SELECT record_uid, model_type, field_path, value FROM pv_text WHERE extraction_id = :e AND "
            "NOT coalesce(is_sensitive, false) AND ((model_type = 'SearchedItem' AND field_path = 'Value') OR "
            "(model_type = 'VisitedPage' AND field_path IN ('Title', 'Url'))) ORDER BY record_uid, value_index"),
            {"e": ext}):
        uid = str(r.record_uid)
        h = hits.setdefault(uid, {"model_type": r.model_type, "text": None, "url": None, "matches": set(),
                                  "matched_in": set()})
        if r.field_path == "Url":
            h["url"] = h["url"] or r.value
            m = V.matches(url_words(r.value), vocab)
            where = "address"
        else:
            h["text"] = h["text"] or r.value
            m = V.matches(r.value, vocab)
            where = "search" if r.model_type == "SearchedItem" else "title"
        if m:
            h["matches"].update(m)
            h["matched_in"].add(where)
    return {u: h for u, h in hits.items() if h["matches"]}


def analyse(conn, case_id, params, ctx=None) -> tuple:
    counts = defaultdict(int)
    vocab = V.build(conn, case_id)
    phones = FV.active_phones(conn, case_id)
    per_phone = {}
    term_records = Counter()
    for i, (ext, label) in enumerate(phones.items()):
        if ctx is not None:
            ctx.progress(i, len(phones), label)
            if ctx.cancelled():
                break
        hits = _read(conn, ext, vocab)
        per_phone[ext] = hits
        for h in hits.values():
            term_records.update({t for _, t in h["matches"]})
    counts["distinct_terms"] = len(term_records)
    counts["specific_terms"] = sum(1 for n in term_records.values() if n < COMMON_AT)
    out = []
    for ext, hits in per_phone.items():
        label = phones[ext]
        if not hits:
            continue
        uids = list(hits)
        times = FV.times_for(conn, ext, uids, ("TimeStamp", "LastVisited"))
        meta = FV.field_values(conn, ext, ("SearchedItem", "VisitedPage"), ("VisitCount", "Origin", "Source"))
        deleted = {str(r[0]): r[1] for r in conn.execute(text(
            "SELECT record_uid, deleted_state FROM pv_record WHERE extraction_id = :e AND record_uid = ANY(CAST(:u AS "
            "uuid[]))"), {"e": ext, "u": uids})}
        for uid in sorted(uids):
            h = hits[uid]
            search = h["model_type"] == "SearchedItem"
            kind = "search_hit" if search else "page_hit"
            vals = meta.get(uid, {}).get("values", {})
            when = times.get(uid, {}).get("TimeStamp" if search else "LastVisited")
            kinds = sorted({k for k, _ in h["matches"]})
            toks = {t for _, t in h["matches"]}
            common = all(term_records[t] >= COMMON_AT for t in toks)
            matched_in = sorted(h["matched_in"])
            visits = (vals.get("VisitCount") or [None])[0]
            counts[kind] += 1
            counts[kind + ("_timed" if when else "_untimed")] += 1
            supports = [_d("vocabulary_match", "The %s matches %s." % (
                " and ".join({"search": "search text", "title": "page title", "address": "page address"}[w]
                             for w in matched_in), ", ".join(V.KIND_WORDS[k] for k in kinds)), [uid])]
            undercuts = [_d("vocabulary_partial", "The comparison does not yet include: %s." %
                            ", ".join(V.NOT_INCLUDED))]
            if search and when:
                supports.append(_d("searched_at", "The search records its time.", [uid]))
            elif not search and when:
                supports.append(_d("last_visited", "The page records its last visit.", [uid]))
                undercuts.append(_d("last_visit_only", "Only the most recent visit carries a time%s; earlier visits "
                                    "are not dated." % ((" (%s visits in all)" % visits) if visits else "")))
            if not when:
                undercuts.append(_d("time_not_recorded", "The record carries no time."))
            if search:
                undercuts.append(_d("suggested_or_prefetched", "A suggested search or a prefetched page creates a "
                                    "record without typing%s." % (
                                        "" if not vals.get("Origin") else "; the record gives its origin")))
            undercuts.append(_d("synced_history", "History can be synced from another device signed in to the same "
                                "account."))
            if common:
                undercuts.append(_d("common_term", "Every matched term matches %d or more records in the case, so it "
                                    "may be a business or site name rather than a case term." % COMMON_AT))
            if matched_in == ["address"]:
                undercuts.append(_d("address_only", "The match is in the page address only."))
            if deleted.get(uid) in ("Deleted", "Trash"):
                undercuts.append(_d("deleted_or_carved", "The record is a deleted one the phone still held."))
            field = "Value" if search else ("Title" if "title" in matched_in else "Url")
            out.append({
                "kind": kind, "strength": "common_term" if common else "specific_term",
                "measures": {"phone_label": label, "extraction_id": ext, "text": h["text"], "url": h["url"],
                             "matched_in": matched_in, "term_kinds": kinds, "terms_matched": len(toks),
                             "time_meaning": ("searched_at" if search else "last_visit_only") if when else
                             "not_recorded", "instant": when, "visit_count": visits,
                             "origin": (vals.get("Origin") or [None])[0], "source": (vals.get("Source") or [None])[0]},
                "directions": {"supports": supports, "undercuts": undercuts},
                "period_start": when, "period_end": when,
                "records": [{"extraction_id": ext, "record_uid": uid, "field_path": field, "role": kind}]})
    if ctx is not None:
        ctx.progress(len(phones), len(phones))
    return out, dict(counts)


def run(conn, case_id, params, ctx) -> list:
    results, counts = analyse(conn, case_id, params, ctx)
    _last["counts"] = counts
    return results


def last_counts() -> dict:
    return _last["counts"]
