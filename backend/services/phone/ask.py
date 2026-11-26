"""Ask the phones a question in plain English (phones redesign, screen 7).

One question over every phone in scope: the case search's phone areas (messages, contacts, transcripts) find the
records, the records dated inside a time the question names are added (every record kind: positions, calls, app
use), and one model call writes the answer as separate statements. Each statement cites the records it rests on.
Rules, not the model, then decide what is shown:

- a statement with no citation, or citing a record the model was not shown, is not shown (and counted);
- a quotation in a statement must be in a record it cites, word for word after folding; one that is not is not
  shown (and counted);
- under each statement, what the rest of the case says comes from the "elsewhere in the case" service
  (lx-elsewhere), never from this model;
- next steps are computed from the answer: phones that should hold a record and do not, people to test together,
  dates the timeline lacks, conversations longer than the part quoted, parts of the question not found, phones left
  out.

Model permission (COMMON rule 6): a phone whose Outside services decision is "not allowed" is left out, and the
answer says so. A phone with no decision is read as chat and the agent read phones today, through the case's model
policy (Neil, 2026-11-01, ``external_processing`` module docstring); the header says which phones were read.
"""
from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from datetime import date, datetime, timezone
from typing import Any, Callable

from sqlalchemy import text

logger = logging.getLogger(__name__)

WORKLOAD = "chat"
MAX_SOURCES = 24          # message windows passed to the model
MAX_WINDOW_RECORDS = 40   # records dated inside the question's time, per answer
PROMPT_CHARS = 60000      # all sources together; a unit is never cut here (the case search cuts a long one around
                          # its match and says so), it is left out whole and counted
MAX_STATEMENTS = 8
MODEL_TIMEOUT_S = 180
REC = re.compile(r"rec://([0-9a-fA-F-]{36})")
QUOTE = re.compile(r"[\"“]([^\"“”]{4,})[\"”]")

# record kinds in plain words: (one, many)
KIND_WORDS = {
    "InstantMessage": ("message", "messages"), "Call": ("call", "calls"), "Email": ("email", "emails"),
    "Note": ("note", "notes"), "Contact": ("contact", "contacts"), "Location": ("place", "places"),
    "Coordinate": ("position", "positions"), "VisitedPage": ("web page visited", "web pages visited"),
    "SearchedItem": ("search typed", "searches typed"), "Notification": ("notification", "notifications"),
    "CalendarEntry": ("calendar entry", "calendar entries"), "Chat": ("conversation", "conversations"),
    "Attachment": ("attachment", "attachments"), "AppsUsageLog": ("app use", "app uses"),
    "DeviceEvent": ("device event", "device events"), "DeviceConnectivity": ("connection", "connections"),
    "Password": ("saved password", "saved passwords"), "LogEntry": ("log entry", "log entries"),
    "SocialMediaActivity": ("social media post", "social media posts"),
    "ActivitySensorDataSample": ("activity reading", "activity readings"),
    "ActivitySensorDataMeasurement": ("activity reading", "activity readings"),
    "ActivitySensorData": ("activity record", "activity records"),
    "ApplicationUsage": ("app use", "app uses"), "Party": ("participant", "participants"),
}
# kinds named in the "Searched ..." line, in this order (text the search reads)
SEARCHED_KINDS = ("InstantMessage", "Call", "Email", "Note", "Contact", "SearchedItem", "VisitedPage",
                  "Notification", "CalendarEntry", "SocialMediaActivity")


def kind_words(model_type: str | None, n: int = 1) -> str:
    one, many = KIND_WORDS.get(model_type or "", (None, None))
    if one is None:
        w = re.sub(r"(?<!^)(?=[A-Z])", " ", model_type or "record").lower()
        one, many = w, w + "s"
    return one if n == 1 else many


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("’", "'").replace("‘", "'").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w'$.,:%/-]+", " ", s)).strip()


# ---- the phones in scope --------------------------------------------------------------------------------------------
def phones_in_scope(conn, case_id, wanted: list[str] | None = None) -> list[dict]:
    """Every current phone of the case (or those asked for), with label, owner and its Outside services decision:
    ``allowed`` True / False, or None when no decision is recorded."""
    from services.phone import external_processing, readings
    labels = readings.phone_labels(conn, case_id)
    rows = conn.execute(text(
        "SELECT id FROM phone_extractions WHERE case_id = :c AND superseded_at IS NULL ORDER BY created_at, id"),
        {"c": str(case_id)}).fetchall()
    want = {str(w) for w in wanted} if wanted else None
    out = []
    for (ext,) in rows:
        e = str(ext)
        if want is not None and e not in want:
            continue
        st = external_processing.state(conn, case_id, e)
        decided = st["decided_at"] is not None
        out.append({"extraction_id": e, "label": labels.get(e, "Phone"), "owner": _owner_name(conn, e),
                    "allowed": st["external_processing"] if decided else None})
    return out


def _owner_name(conn, ext) -> str | None:
    try:
        r = conn.execute(text(
            "SELECT name FROM pv_owner_candidate WHERE extraction_id = :e AND candidate_kind = 'name' AND name IS NOT "
            "NULL ORDER BY tier NULLS LAST, occurrences DESC, name LIMIT 1"), {"e": ext}).first()
        return r[0] if r else None
    except Exception:  # noqa: BLE001 - a phone without owner views
        return None


def searched_counts(conn, case_id, extraction_ids: list[str]) -> dict[str, int]:
    if not extraction_ids:
        return {}
    rows = conn.execute(text(
        "SELECT model_type, count(*) FROM phone_record_summaries WHERE case_id = :c AND extraction_id = ANY(:e) "
        "AND model_type = ANY(:k) GROUP BY model_type"),
        {"c": str(case_id), "e": [str(x) for x in extraction_ids], "k": list(SEARCHED_KINDS)}).fetchall()
    got = {r[0]: int(r[1]) for r in rows}
    return {k: got[k] for k in SEARCHED_KINDS if got.get(k)}


def searched_sentence(counts: dict[str, int]) -> str:
    parts = ["%s %s" % (format(n, ","), kind_words(k, n)) for k, n in counts.items()]
    if not parts:
        return "The phones in scope hold no messages, calls, emails or notes to search."
    return "Searched " + (", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else parts[0])


# ---- records --------------------------------------------------------------------------------------------------------
def record_facts(conn, case_id, uids: list[str]) -> dict[str, dict]:
    """``{uid: {extraction_id, model_type, at, deleted, parent, title}}`` for record ids of this case."""
    uids = sorted({str(u) for u in uids if u})
    if not uids:
        return {}
    rows = conn.execute(text(
        "SELECT record_uid, extraction_id, model_type, first_instant, deleted_state, parent_record_uid, title FROM "
        "phone_record_summaries WHERE case_id = :c AND record_uid = ANY(CAST(:u AS uuid[]))"),
        {"c": str(case_id), "u": uids}).fetchall()
    return {str(r[0]): {"extraction_id": str(r[1]), "model_type": r[2], "at": r[3],
                        "deleted": (r[4] or "").lower() not in ("", "intact", "unknown", "none"),
                        "parent": str(r[5]) if r[5] else None, "title": r[6]} for r in rows}


def cite_label(fact: dict | None, labels: dict[str, str]) -> str:
    """``Phone 2 · Message 12 Mar 2024 10:20 AM UTC`` (a deleted record says so)."""
    if not fact:
        return "Phone record"
    phone = labels.get(fact["extraction_id"], "Phone")
    kind = kind_words(fact["model_type"]).capitalize()
    at = fact.get("at")
    when = ""
    if isinstance(at, datetime):
        a = at.astimezone(timezone.utc)
        when = " " + a.strftime("%-d %b %Y %-I:%M %p") + " UTC"
    return "%s · %s%s%s" % (phone, kind, when, " · deleted" if fact.get("deleted") else "")


def _window_records(conn, case_id, windows: list[dict], extraction_ids: list[str], seen: set[str]) -> tuple[list[dict], int]:
    """Records of every kind dated inside the times the question names (positions, calls, app use...), as text lines
    citing their records. Returns (sources, how many more were in the time and not passed)."""
    from services.phone import records
    out, more = [], 0
    for w in windows[:3]:
        start, end = w.get("start"), w.get("end")
        if not start or not end:
            continue
        rows = conn.execute(text(
            "SELECT record_uid FROM phone_record_summaries WHERE case_id = :c AND extraction_id = ANY(:e) AND "
            "first_instant >= :s AND first_instant < :t AND model_type <> 'Party' AND is_top_level "
            "ORDER BY first_instant, record_uid"),
            {"c": str(case_id), "e": extraction_ids, "s": start, "t": end}).fetchall()
        fresh = [str(r[0]) for r in rows if str(r[0]) not in seen]
        room = MAX_WINDOW_RECORDS - sum(len(s["records"]) for s in out)
        take, more = fresh[:max(0, room)], more + max(0, len(fresh) - max(0, room))
        lines = []
        for uid in take:
            try:
                d = records.record_detail(conn, case_id, uid)
            except Exception:  # noqa: BLE001 - a record that cannot be read is left out of this source, said below
                more += 1
                continue
            body = re.sub(r"\s+", " ", records.record_text(d))[:400]
            lines.append("%s [rec://%s]" % (body, uid))
            seen.add(uid)
        if lines:
            out.append({"title": "Records dated %s" % (w.get("label") or "in the time asked about"),
                        "text": "\n".join(lines), "records": take, "kind": "time"})
    return out, more


WORDS_PROMPT = """An investigator asks this question about phone messages:
{question}

List up to {n} words or short phrases a message answering it would contain. Mix two kinds: single words for the
things, places and amounts a message would name (for power tools: "drill", "saw"), and phrases exactly as people
type them, with the person in the phrase where people say it that way (for "did anyone lose their job": "let me go",
"let him go", "fired me", "laid off", "lost my job"). A search finds each one as written, so "let go" does not find
"let me go". Add other languages only when the question names them. Leave out the question's own words.
Return JSON only: {{"words": ["..."]}}
"""
MAX_WORDS = 16
MAX_WORD_WINDOWS = 12


def message_words(question: str, model_call) -> list[str]:
    """Words a message answering the question would hold. The model sees the question only, never phone text:
    phone messages have no meaning search while no phone allows outside services (no embeddings), so the words
    the question uses are all a word search would find without this ("lose their job" never finds "they let me
    go today", demo case, 25 Nov)."""
    from services import writing_standard
    if model_call is None:
        return []
    try:
        got = parse(model_call(writing_standard.system_prompt(WORDS_PROMPT.format(question=question.strip(),
                                                                                    n=MAX_WORDS), "data")))
    except Exception:  # noqa: BLE001 - the search goes on with the question's own words, said in the notes
        logger.warning("Message words could not be made", exc_info=True)
        return []
    out = []
    for w in got.get("words") or []:
        w = re.sub(r"\s+", " ", str(w or "")).strip().strip('"').lower()
        if 3 <= len(w) <= 40 and w not in out:
            out.append(w)
    return out[:MAX_WORDS]


def gather(conn, case_id, question: str, phones: list[dict], *, model_call=None, embed_query=None,
           collections=None, rank=True) -> dict[str, Any]:
    """The sources the answer may use: message windows found by the case search (phone areas only) on the phones
    read, then records dated inside a time the question names."""
    from services.case_search import service as S, units
    read = [p["extraction_id"] for p in phones]
    r = S.ranked(conn, case_id, question, kinds=("phones",), rank=rank, phrase=rank, model_call=model_call,
                 embed_query=embed_query, collections=collections)
    terms = r["understood"]["terms"] + [e["term"] for e in r["understood"]["expansions"]]
    sources, seen, left_out_phone, used = [], set(), 0, 0
    facts_all: dict[str, dict] = {}
    for c in r["candidates"]:
        if len(sources) >= MAX_SOURCES or used >= PROMPT_CHARS:
            break
        unit = units.build(conn, case_id, dict(c), terms)
        body = unit.get("text") or ""
        uids = [u.lower() for u in REC.findall(body)]
        facts = record_facts(conn, case_id, uids)
        keep = [u for u in uids if u in facts and facts[u]["extraction_id"] in read]
        if uids and not keep:
            left_out_phone += 1
            continue
        if sources and used + len(body) > PROMPT_CHARS:
            break
        used += len(body)
        facts_all.update(facts)
        seen.update(keep)
        sources.append({"title": unit.get("title") or c.get("title") or "", "text": body, "records": keep,
                        "kind": "search", "grade": c.get("grade")})
    more_found = max(0, len(r["candidates"]) - len(sources) - left_out_phone)
    # the case search made them already when it ranked (one model call, not two)
    words = r["understood"].get("message_words") if "message_words" in r["understood"] else (
        message_words(question, model_call) if rank else [])
    words = words or []
    word_windows = 0
    if words:
        from services.phone import chat_retrieval
        q = " ".join('"%s"' % w if " " in w else w for w in words)
        for w in chat_retrieval.windows(conn, case_id, q, max_windows=MAX_WORD_WINDOWS, extraction_ids=read):
            body = w.get("text") or ""
            uids = [u.lower() for u in REC.findall(body)]
            if not uids or set(uids) <= seen or used + len(body) > PROMPT_CHARS:
                continue
            facts = record_facts(conn, case_id, uids)
            keep = [u for u in uids if u in facts and facts[u]["extraction_id"] in read]
            if not keep:
                continue
            used += len(body)
            word_windows += 1
            facts_all.update(facts)
            seen.update(keep)
            sources.append({"title": (w.get("metadata") or {}).get("doc_name") or "Messages", "text": body,
                            "records": keep, "kind": "words", "grade": None})
    win, more_in_time = _window_records(conn, case_id, r["understood"].get("windows") or [], read, seen)
    for s in win:
        facts_all.update(record_facts(conn, case_id, s["records"]))
    return {"sources": sources + win, "facts": facts_all, "understood": r["understood"], "notes": r["notes"],
            "found": len(r["candidates"]), "more_found": more_found, "more_in_time": more_in_time,
            "words": words, "word_windows": word_windows,
            "ranking_model": r["ranking"].get("model"), "seconds": r.get("seconds") or {}}


# ---- the model ------------------------------------------------------------------------------------------------------
PROMPT = """You answer an investigator's question from phone records. Use only the records below.
Each record line ends with its citation in square brackets, like [rec://...].

Question: {question}

Phones read: {phones}

Records:
{sources}

Return JSON only:
{{"statements": [{{"text": "...", "cites": ["rec://..."], "people": ["..."], "date_from": "YYYY-MM-DD or null", "date_to": "YYYY-MM-DD or null"}}],
 "not_found": [{{"asked": "the part of the question no record answers"}}]}}

Rules:
- Each statement is one finding: who did or said what, when, on which phone. At most {max_statements} statements, the ones that answer the question first.
- Every statement cites every record it rests on, using only citations shown above. Never state anything no record above says.
- Quote a record's words in double quotes only when the exact words matter, copied exactly as written.
- Name people as the records name them. Give dates and times as the records give them, with their time zone.
- Say a record was deleted only when the record says so.
- "people" lists the people the statement names; "date_from" and "date_to" are the dates it covers.
- Put each part of the question the records do not answer in "not_found", in a few words. If nothing answers the question, return no statements.
"""


def default_model_call() -> Callable[[str], str] | None:
    """The chat workload's model as ``prompt -> text`` (JSON mode). ``LOUPE_CASE_SEARCH_MODEL=off`` (the tests): no
    model. The call keeps its usage on ``call.usage`` for the cost line."""
    import os
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
    except Exception as exc:  # noqa: BLE001
        logger.warning("Phone question model unavailable: %s", exc)
        return None

    def call(prompt: str) -> str:
        ctx = LLMExecutionContext(provider, model_id, api_key=key)
        try:
            return ctx.call(prompt, temperature=0.0, json_mode=True, timeout=MODEL_TIMEOUT_S)
        finally:
            call.usage.append(dict(ctx.last_usage or {}))  # type: ignore[attr-defined]
    call.model = "%s/%s" % (provider, model_id)  # type: ignore[attr-defined]
    call.provider, call.model_id, call.usage = provider, model_id, []  # type: ignore[attr-defined]
    return call


def build_prompt(question: str, phones: list[dict], sources: list[dict]) -> str:
    from services import writing_standard
    ph = "; ".join("%s%s" % (p["label"], " (owner: %s)" % p["owner"] if p.get("owner") else "") for p in phones)
    src = "\n\n".join("## %d. %s\n%s" % (i + 1, s["title"], s["text"]) for i, s in enumerate(sources))
    body = PROMPT.format(question=question.strip(), phones=ph or "none", sources=src or "(no records found)",
                         max_statements=MAX_STATEMENTS)
    return writing_standard.system_prompt(body, "data")


def parse(raw: str) -> dict:
    s = (raw or "").strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    try:
        d = json.loads(s)
    except ValueError:
        m = re.search(r"\{.*\}", s, re.S)
        d = json.loads(m.group(0)) if m else {}
    return d if isinstance(d, dict) else {}


def _day(v) -> str | None:
    if not v or not isinstance(v, str):
        return None
    try:
        return date.fromisoformat(v[:10]).isoformat()
    except ValueError:
        return None


def record_texts(sources: list[dict]) -> dict[str, str]:
    """``{uid: its text}``. A record's text is the line holding its citation, the lines without a citation just
    before it, and the indented lines after it (an email's body follows its subject line and citation). Demo case,
    25 Nov: a check reading only the line with the citation refused a word-for-word quotation of an email's body."""
    out: dict[str, str] = {}
    for s in sources:
        pending: list[str] = []
        cur = None
        for line in s["text"].split("\n"):
            uids = [u.lower() for u in REC.findall(line)]
            if uids:
                for u in uids:
                    out[u] = " ".join([out.get(u, "")] + pending + [line])
                pending, cur = [], uids[-1]
            elif cur and line[:1] in (" ", "\t"):
                out[cur] = out[cur] + " " + line
            else:
                pending.append(line)
                cur = None
    return out


def check(parsed: dict, sources: list[dict], facts: dict[str, dict]) -> tuple[list[dict], dict[str, int]]:
    """Keep the statements the rules allow. Returns (kept, why_left_out counts)."""
    shown = {u for s in sources for u in s["records"]}
    text_of = record_texts(sources)
    kept, dropped = [], {"no_citation": 0, "quote_not_in_record": 0, "empty": 0}
    check.left_out = []  # type: ignore[attr-defined]  # what was not shown, kept for audit (never displayed)
    for st in (parsed.get("statements") or [])[:MAX_STATEMENTS * 2]:
        if not isinstance(st, dict):
            continue
        body = re.sub(r"\s*\[?rec://[0-9a-fA-F-]{36}\]?", "", str(st.get("text") or "")).strip()
        if not body:
            dropped["empty"] += 1
            continue
        cites = []
        for c in st.get("cites") or []:
            for u in REC.findall(str(c)) or ([str(c)] if re.fullmatch(r"[0-9a-fA-F-]{36}", str(c)) else []):
                u = u.lower()
                if u in shown and u not in cites:
                    cites.append(u)
        for u in REC.findall(str(st.get("text") or "")):
            if u.lower() in shown and u.lower() not in cites:
                cites.append(u.lower())
        if not cites:
            dropped["no_citation"] += 1
            check.left_out.append({"why": "no_citation", "text": body})  # type: ignore[attr-defined]
            continue
        cited_text = fold(" ".join(text_of.get(u, "") for u in cites))
        bad = [q for q in QUOTE.findall(body) if fold(q) not in cited_text]
        if bad:
            dropped["quote_not_in_record"] += 1
            check.left_out.append({"why": "quote_not_in_record", "text": body, "quotes": bad,  # type: ignore[attr-defined]
                                   "cites": cites})
            continue
        people = [str(p).strip() for p in (st.get("people") or []) if str(p).strip()][:6]
        kept.append({"text": body, "cites": cites, "people": people, "date_from": _day(st.get("date_from")),
                     "date_to": _day(st.get("date_to")) or _day(st.get("date_from"))})
        if len(kept) >= MAX_STATEMENTS:
            break
    return kept, {k: v for k, v in dropped.items() if v}


def dropped_sentence(dropped: dict[str, int]) -> str | None:
    parts = []
    n = dropped.get("no_citation", 0)
    if n:
        parts.append("%d %s cited no record, so %s not shown" % (n, "statement" if n == 1 else "statements",
                                                                 "it is" if n == 1 else "they are"))
    n = dropped.get("quote_not_in_record", 0)
    if n:
        parts.append("%d %s quoted words its records do not hold, so %s not shown" % (
            n, "statement" if n == 1 else "statements", "it is" if n == 1 else "they are"))
    return ("The answer had more: " + "; ".join(parts) + ".") if parts else None


# ---- elsewhere in the case ------------------------------------------------------------------------------------------
def elsewhere_rows(conn, case_id, statement: dict, phones: list[dict], facts: dict[str, dict]) -> dict:
    """What the rest of the case says about one statement: lx-elsewhere's service (``services.elsewhere``), given
    the statement's text, its cited records, its people and its dates. Relations are that service's rules; nothing
    here or in the model decides one. A part that fails says so; a part that finds nothing says what it searched."""
    try:
        from services.elsewhere import service as ES, subject as SU
    except ImportError:
        return {"rows": None, "searched": [], "note": "The rest of the case was not checked for this statement yet."}
    payload = {"text": statement["text"], "record_uids": statement["cites"][:SU.MAX_RECORDS],
               "people": [{"name": n} for n in statement.get("people") or []]}
    if statement.get("date_from") or statement.get("date_to"):
        payload["period"] = {"start": statement.get("date_from"), "end": statement.get("date_to")}
    try:
        subject = SU.from_statement(conn, case_id, payload)
        got = ES.run(conn, case_id, subject)
    except Exception:  # noqa: BLE001 - the answer stands; the block says the check failed
        logger.warning("Elsewhere check failed", exc_info=True)
        return {"rows": None, "searched": [], "note": "The rest of the case could not be checked for this statement "
                                                      "(an error). Ask again to retry."}
    rows, searched, failed = [], [], []
    for part in got.get("parts") or []:
        label = part.get("label") or str(part.get("source") or "").capitalize()
        if part.get("state") != "done":
            failed.append(label)
        if part.get("searched"):
            searched.append("%s: %s" % (label, part["searched"]))
        for it in part.get("items") or []:
            c = it.get("citation") or {}
            href = c.get("href")
            if not href and c.get("kind") in ("timeline_entry", "timeline_event"):
                href = "/cases/%s/timeline" % case_id
            rows.append({"source": (c.get("phone") if part.get("source") == "phones" and c.get("phone") else label),
                         "part": part.get("source"), "text": it.get("text") or "", "relation": it.get("relation"),
                         "relation_label": it.get("relation_label"), "reason": it.get("reason") or "",
                         "cite": href, "cite_label": c.get("label") or ("Open" if href else None)})
    note = ("Not checked, an error: %s. Ask again to retry." % ", ".join(failed)) if failed else None
    return {"rows": rows, "searched": searched, "note": note, "counts": got.get("counts") or {}}


def _as_date(v):
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        return None


# ---- next steps (rules) ---------------------------------------------------------------------------------------------
def _thread_sizes(conn, case_id, parents: list[str]) -> dict[str, int]:
    if not parents:
        return {}
    rows = conn.execute(text(
        "SELECT parent_record_uid, count(*) FROM phone_record_summaries WHERE case_id = :c AND parent_record_uid = "
        "ANY(CAST(:p AS uuid[])) AND model_type = 'InstantMessage' GROUP BY 1"),
        {"c": str(case_id), "p": sorted(set(parents))}).fetchall()
    return {str(r[0]): int(r[1]) for r in rows}


def _same_name(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    fa, fb = fold(a), fold(b)
    return fa == fb or (len(fa) > 2 and len(fb) > 2 and (fa in fb or fb in fa))


def next_steps(conn, case_id, question: str, statements: list[dict], not_found: list[dict], phones: list[dict],
               left_out: list[dict], facts: dict[str, dict]) -> list[dict]:
    """Ranked steps, each with a why built from this answer and one action. Kinds: missing_on_phone, corroborate,
    timeline, thread, not_found, permission, search."""
    labels = {p["extraction_id"]: p["label"] for p in phones}
    steps: list[dict] = []
    # a person in the statement owns a phone in scope that holds none of its records
    for i, st in enumerate(statements):
        on = {facts[u]["extraction_id"] for u in st["cites"] if u in facts}
        for p in phones:
            if p["extraction_id"] in on or not p.get("owner"):
                continue
            if any(_same_name(p["owner"], who) for who in st["people"]):
                where = ", ".join(sorted(labels.get(e, "Phone") for e in on))
                steps.append({"kind": "missing_on_phone", "statement": i, "rank": 1,
                              "title": "Find out why %s does not hold this" % p["label"],
                              "why": "%s is in statement %d, which rests on %s. %s is %s's phone and holds none of "
                                     "its records." % (p["owner"], i + 1, where, p["label"], p["owner"]),
                              "action": {"label": "Open %s" % p["label"], "kind": "open_phone",
                                         "extraction_id": p["extraction_id"], "date": st.get("date_from")}})
                break
    # two or more people: test them against ordinary days
    for i, st in enumerate(statements):
        if len(st["people"]) >= 2:
            when = st.get("date_from") or "the dates cited"
            steps.append({"kind": "corroborate", "statement": i, "rank": 2,
                          "title": "Test %s and %s around %s" % (st["people"][0], st["people"][1], when),
                          "why": "Statement %d puts them together in %d %s. Corroborate weighs that against their "
                                 "ordinary days with fixed rules." % (i + 1, len(st["cites"]),
                                                                       "record" if len(st["cites"]) == 1 else "records"),
                          "action": {"label": "Corroborate", "kind": "corroborate", "statement": i}})
            break
    # a dated statement the timeline does not hold (from the elsewhere rows)
    for i, st in enumerate(statements):
        rows = (st.get("elsewhere") or {}).get("rows") or []
        if st.get("date_from") and any(r.get("part") == "timeline" and r.get("relation") == "nothing_found"
                                       for r in rows):
            steps.append({"kind": "timeline", "statement": i, "rank": 3,
                          "title": "Put %s on the case timeline" % st["date_from"],
                          "why": "Statement %d is dated %s, and the case timeline holds nothing for it." % (
                              i + 1, st["date_from"]),
                          "action": {"label": "Open the timeline", "kind": "open_timeline", "date": st["date_from"]}})
            break
    # a conversation longer than the part cited
    parents = {facts[u]["parent"]: i for i, st in enumerate(statements) for u in st["cites"]
               if u in facts and facts[u].get("parent") and facts[u]["model_type"] == "InstantMessage"}
    sizes = _thread_sizes(conn, case_id, list(parents))
    best = None
    for parent, i in parents.items():
        cited = sum(1 for st in statements for u in st["cites"] if u in facts and facts[u].get("parent") == parent)
        n = sizes.get(parent, 0)
        if n > cited and (best is None or n - cited > best[2] - best[1]):
            best = (parent, cited, n, i)
    if best:
        parent, cited, n, i = best
        rec = next(u for u in statements[i]["cites"] if u in facts and facts[u].get("parent") == parent)
        steps.append({"kind": "thread", "statement": i, "rank": 4, "title": "Read the conversation in full",
                      "why": "The answer cites %d %s from it; the conversation on %s has %d." % (
                          cited, "message" if cited == 1 else "messages", labels.get(facts[rec]["extraction_id"],
                                                                                     "the phone"), n),
                      "action": {"label": "Open the conversation", "kind": "open_record", "record": rec}})
    if not_found:
        asked = "; ".join(nf.get("asked") or question for nf in not_found[:3])
        steps.append({"kind": "not_found", "rank": 5, "title": "Look in the rest of the case",
                      "why": "The phones did not answer this: %s. The case search reads the financial records, the "
                             "documents and the timeline too." % asked[:300].rstrip(" ?.!"),
                      "action": {"label": "Search the case", "kind": "case_search", "q": question[:200]}})
    if left_out:
        names = ", ".join(p["label"] for p in left_out)
        steps.append({"kind": "permission", "rank": 6, "title": "Decide AI reading for %s" % names,
                      "why": "%s %s left out: %s Outside services decision is “not allowed”." % (
                          names, "was" if len(left_out) == 1 else "were", "its" if len(left_out) == 1 else "their"),
                      "action": {"label": "Open Case settings", "kind": "open_settings"}})
    if not statements and not not_found:
        steps.append({"kind": "search", "rank": 5, "title": "Search the words instead",
                      "why": "No record answered the question. A word search lists every record with its words.",
                      "action": {"label": "Search words", "kind": "search", "q": question[:200]}})
    steps.sort(key=lambda s: s["rank"])
    for n, s in enumerate(steps, 1):
        s["n"] = n
    return steps


# ---- the whole answer -----------------------------------------------------------------------------------------------
def ask(conn, case_id, question: str, *, phones: list[str] | None = None, model_call=None, embed_query=None,
        collections=None, elsewhere: Callable | None = None) -> dict[str, Any]:
    """Answer ``question`` over the phones in scope. ``model_call``: ``prompt -> text`` (default: the chat
    workload's model). Nothing is written here; the router stores the result."""
    t0 = time.time()
    question = (question or "").strip()
    scope = phones_in_scope(conn, case_id, phones)
    read = [p for p in scope if p["allowed"] is not False]
    left_out = [p for p in scope if p["allowed"] is False]
    labels = {p["extraction_id"]: p["label"] for p in scope}
    counts = searched_counts(conn, case_id, [p["extraction_id"] for p in read])
    out: dict[str, Any] = {
        "question": question, "phones": scope, "read": [p["extraction_id"] for p in read],
        "left_out": [p["extraction_id"] for p in left_out], "searched_counts": counts,
        "searched": searched_sentence(counts), "statements": [], "not_found": [], "notes": [], "steps": [],
        "label": "Written by AI from the records · not confirmed", "records_used": [], "model": None,
        "usage": {}, "seconds": {}, "error": None,
    }
    if left_out:
        out["notes"].append("%s %s left out: %s Outside services decision is “not allowed” (Case "
                            "settings)." % (", ".join(p["label"] for p in left_out),
                                            "was" if len(left_out) == 1 else "were",
                                            "its" if len(left_out) == 1 else "their"))
    if not question:
        out["error"] = "Write a question first."
        return out
    if not read:
        out["error"] = ("No phone in scope may be read by AI: %s." % out["notes"][0]) if left_out else \
            "There are no phones in scope. Turn a phone on, or add a phone report to the case."
        return out
    call = model_call if model_call is not None else default_model_call()
    if call is None:
        out["error"] = "No AI model is set up for questions, so nothing was asked. Search words instead."
        return out
    out["model"] = getattr(call, "model", None)
    t = time.time()
    got = gather(conn, case_id, question, read, model_call=call, embed_query=embed_query, collections=collections)
    out["seconds"]["search"] = round(time.time() - t, 2)
    sources, facts = got["sources"], got["facts"]
    for n in got["notes"]:
        if n not in out["notes"] and not n.startswith("Words were matched loosely"):
            out["notes"].append(n)
    if got["more_found"]:
        out["notes"].append("The answer read the %d strongest of %d message groups found; the other %d are in a "
                            "word search." % (len(sources) - sum(1 for s in sources if s["kind"] != "search"),
                                              got["found"], got["more_found"]))
    if got.get("words"):
        out["words"] = got["words"]
        out["notes"].append("Also searched the words a message about this might use: %s." % ", ".join(
            "\u201c%s\u201d" % w for w in got["words"]))
    if got["more_in_time"]:
        out["notes"].append("%d more records are dated inside the time asked about and were not read; open the "
                            "phones at that time to see them." % got["more_in_time"])
    raw = None
    if sources:
        t = time.time()
        try:
            raw = call(build_prompt(question, read, sources))
        except Exception as exc:  # noqa: BLE001 - say what happened; nothing is shown as an answer
            logger.warning("Phone question model call failed", exc_info=True)
            out["error"] = "The AI model did not answer (%s). Nothing below was written by it; ask again." % (
                type(exc).__name__)
        out["seconds"]["answer"] = round(time.time() - t, 2)
    parsed = parse(raw) if raw else {}
    kept, dropped = check(parsed, sources, facts)
    out["dropped"] = dropped
    out["left_out_statements"] = list(getattr(check, "left_out", []))
    ds = dropped_sentence(dropped)
    if ds:
        out["notes"].append(ds)
    for st in kept:
        st["cite_labels"] = [{"record": u, "label": cite_label(facts.get(u), labels),
                              "extraction_id": (facts.get(u) or {}).get("extraction_id")} for u in st["cites"]]
        st["elsewhere"] = (elsewhere or elsewhere_rows)(conn, case_id, st, read, facts)
    out["statements"] = kept
    # the sentence is built here from the part asked: a model's own "not found" sentence describes records without
    # citing them (demo case, 25 Nov: "the email only lists drills ... with payment to Travis Kell")
    nf = []
    for x in parsed.get("not_found") or []:
        asked = str((x.get("asked") if isinstance(x, dict) else x) or "").strip().rstrip(" ?.!")[:200]
        if asked and asked.lower() not in [n["asked"].lower() for n in nf]:
            nf.append({"asked": asked, "text": "No record on the phones read answers this: %s." % asked})
    if sources and not kept and not nf and not out["error"]:
        nf = [{"asked": question, "text": "No record on the phones read answers this question."}]
    if not sources and not out["error"]:
        nf = [{"asked": question, "text": "The search found no record on the phones read for this question."}]
    out["not_found"] = nf[:4]
    used = []
    for s in sources:
        for u in s["records"]:
            if u not in used:
                used.append(u)
    cited = {u for st in kept for u in st["cites"]}
    out["records_used"] = [{"record": u, "label": cite_label(facts.get(u), labels), "cited": u in cited,
                            "extraction_id": (facts.get(u) or {}).get("extraction_id")} for u in used]
    out["steps"] = next_steps(conn, case_id, question, kept, out["not_found"], scope, left_out, facts)
    usage = getattr(call, "usage", None) or []
    out["usage"] = _sum_usage(usage, getattr(call, "provider", None), getattr(call, "model_id", None))
    out["seconds"]["total"] = round(time.time() - t0, 2)
    return out


def _sum_usage(usage: list[dict], provider, model_id) -> dict:
    tot = {"calls": len(usage), "prompt_tokens": 0, "completion_tokens": 0, "cache_hit_tokens": 0}
    for u in usage:
        tot["prompt_tokens"] += int(u.get("prompt_tokens") or 0)
        tot["completion_tokens"] += int(u.get("completion_tokens") or 0)
        tot["cache_hit_tokens"] += int(u.get("prompt_cache_hit_tokens") or 0)
    tot["usd"] = None
    if provider == "deepseek" and model_id:
        try:
            from services.ai_costs_service import deepseek_published_cost
            c = deepseek_published_cost(model_id, prompt_tokens=tot["prompt_tokens"],
                                        cache_hit_tokens=tot["cache_hit_tokens"], cache_miss_tokens=None,
                                        completion_tokens=tot["completion_tokens"], at=datetime.now(timezone.utc))
            tot["usd"] = float(c) if c is not None else None
        except Exception:  # noqa: BLE001 - the cost line says unknown
            tot["usd"] = None
    return tot
