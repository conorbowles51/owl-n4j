"""Whether each cited source says what the sentence citing it says (lx-citeproof B).

``case_citations.check_text`` says whether a citation's target is in the case. This module reads the target and asks a
second question: does the cited page, payment or phone record carry the specific facts of the sentence that cites it?

For each sentence (or table row, or bullet) with a citation:

1. Code first. The names, figures (three or more digits, amounts), dates and identifiers of the sentence are looked
   for in the cited text, normalised (case, commas, ``$650.00`` = ``650``, ``12 April 2024`` = ``2024-04-12``).
   Every one found, a figure, date, time or identifier among them: the citation supports the sentence (checked by
   code). None of two or more found: it does not mention it.
2. One batched model call per answer for the sentences code cannot settle (some found, or nothing specific to look
   for). The model's verdict is shown as a model's verdict, with the model's name.

Each citation gets one state: ``supports``, ``partly`` (the source carries some of the sentence's facts and the reason
names what it lacks), ``not_mentioned`` or ``unchecked`` (could not check), each with its reason.
A sentence whose citations all fail is marked in the answer itself, so no reader sees it as backed; the answer ends
with a short count of how the citations were checked and each one that failed. Nothing is dropped silently: past the
per-answer limits, the rest are ``unchecked`` with the limit named.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from services import case_citations as C
from services.agent.answer_quality import figures as _figures

logger = logging.getLogger(__name__)

SCHEMA = "loupe.citation_support/1"
SUPPORTS, PARTLY, NOT_MENTIONED, UNCHECKED = "supports", "partly", "not_mentioned", "unchecked"
WORDS = {SUPPORTS: "supports this", PARTLY: "supports part of this", NOT_MENTIONED: "does not mention this",
         UNCHECKED: "could not check"}
MAX_CLAIMS = 80            # sentences with citations checked per answer; the rest are unchecked, with this named
MAX_MODEL_ITEMS = 40       # sentences sent to the model per answer (one call)
MAX_SOURCE_CHARS = 200_000  # text read per cited source
EXCERPT_CHARS = 2_400      # text of one source given to the model for one sentence
MODEL_TIMEOUT_S = 120
JUDGE_MODEL_SETTING = "LOUPE_CITATION_JUDGE_MODEL"
SWITCH = "LOUPE_CITATION_SUPPORT"  # "0" turns the check off (the answer is stored as before, saying so in metadata)
MARK = "*(the cited source does not mention this)*"
SECTION = "**Source check**"
_CHECK_HEADINGS = (SECTION, "**Figures to check")  # the second: services.agent.answer_quality.UNSUPPORTED_HEADING

_LINK = re.compile(r"\[([^\]\n]*)\]\(\s*<?([^)>\s]*)>?(?:\s+\"[^\"]*\")?\s*\)")
_SENTENCE_END = re.compile(r"(?<=[.!?])[\"”')\]]*\s+(?=[A-Z0-9\[(\"“*_])")
_TABLE_RULE = re.compile(r"^\|?[\s:\-|]+\|?$")
_TIME = re.compile(r"(?<![\d:])([01]?\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?\s*(am|pm|a\.m\.|p\.m\.)?(?![\d:])", re.I)
_IDENT = re.compile(r"(?<![\w-])(?=[A-Za-z\d/-]*[A-Za-z])(?=[A-Za-z\d/-]*\d)[A-Za-z\d]+(?:[-/][A-Za-z\d]+)+(?![\w-])")
_CAP_RUN = re.compile(r"(?<![\w'’])((?:[A-Z][\w'’.&-]*|&)(?:\s+(?:[A-Z][\w'’.&-]*|&|of|de|la|van|von|du))*)")
_WORD = re.compile(r"[\w]+", re.U)
_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
           "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec")
_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
# capitalised words that are not names: sentence openers, headings, report words
_NOT_NAMES = set(_MONTHS) | set(_DAYS) | {
    "a", "an", "the", "this", "that", "these", "those", "there", "their", "they", "he", "she", "it", "his", "her",
    "its", "we", "i", "on", "in", "at", "by", "for", "from", "to", "of", "and", "or", "but", "no", "not", "yes",
    "after", "before", "between", "during", "each", "every", "both", "all", "none", "one", "two", "three", "four",
    "five", "six", "seven", "eight", "nine", "ten", "first", "second", "third", "last", "next", "same", "other",
    "phone", "phones", "call", "calls", "message", "messages", "record", "records", "payment", "payments", "page",
    "statement", "statements", "account", "accounts", "source", "sources", "document", "documents", "note",
    "summary", "answer", "key", "findings", "finding", "evidence", "case", "date", "time", "amount", "total",
    "however", "also", "so", "if", "when", "where", "who", "what", "which", "why", "how", "while", "as", "with",
    "utc", "am", "pm", "edt", "est", "usd", "id", "pdf", "sms", "mms", "gps", "ach", "atm", "is", "was", "were",
    "are", "has", "had", "have", "did", "does", "do", "be", "been", "can", "could", "would", "should", "may",
    "might", "must", "will", "shows", "show", "showed", "confirms", "states", "says", "said", "lists", "notes",
    "corroborates", "corroborated", "consistent", "patterns", "pattern", "red", "flags", "flag", "open", "questions",
    "question", "conclusion", "timeline", "here", "only", "about", "around", "within", "under", "over", "via",
    "debit", "credit", "deposit", "transfer", "cash", "check", "cheque", "invoice", "report", "whatsapp",
    "signal", "telegram", "sent", "received", "incoming", "outgoing", "deleted", "recovered", "yes", "nothing",
    "monthly", "weekly", "daily", "night", "nights", "morning", "evening", "afternoon",
}


@dataclass
class Claim:
    """One sentence, bullet or table row and the citations that back it."""
    text: str              # the sentence as written (links included)
    plain: str             # without links or Markdown marks
    start: int             # character range in the answer
    end: int
    hrefs: list[str]
    table: bool = False


@dataclass
class Source:
    text: str = ""
    complete: bool = True
    reason: str | None = None   # set when the source cannot be checked
    label: str = ""


@dataclass
class Verdict:
    state: str
    reason: str
    by: str  # "code" or "model:<model id>" or "none"
    found: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def enabled() -> bool:
    return os.environ.get(SWITCH, "1").strip() != "0"


# ---- the sentences and their citations ---------------------------------------------------------------------------


def _plain(text: str) -> str:
    text = _LINK.sub(" ", text)
    text = re.sub(r"[*_`#>]+", " ", text)
    text = re.sub(r"\(\s*[,;]?\s*\)", " ", text)
    return re.sub(r"\s+", " ", text).strip(" |-•\t")


def claims(answer: str) -> list[Claim]:
    """Sentences, bullets and table rows that carry a citation. A citation standing alone after a sentence (``... at
    01:15. [invoice, p.1](doc://...)``) backs the sentences of its line that carry none of their own."""
    out: list[Claim] = []
    offset = 0
    skipping = False
    for line in (answer or "").splitlines(keepends=True):
        body = line.rstrip("\n")
        start = offset
        offset += len(line)
        if not body.strip():
            skipping = False
            continue
        if body.strip().startswith(_CHECK_HEADINGS):
            skipping = True  # a check's own list (this one, or the figure check's) is not a claim
        if skipping or _TABLE_RULE.match(body.strip()):
            continue
        table = body.strip().startswith("|")
        parts: list[tuple[int, int]] = []
        if table:
            parts = [(0, len(body))]
        else:
            last = 0
            for m in _SENTENCE_END.finditer(body):
                parts.append((last, m.start()))
                last = m.end()
            parts.append((last, len(body)))
        pending: list[Claim] = []
        for a, b in parts:
            piece = body[a:b]
            if not piece.strip():
                continue
            hrefs = list(dict.fromkeys(m.group(2) for m in _LINK.finditer(piece) if C.parse_citation(m.group(2))))
            plain = _plain(piece)
            if hrefs and not _WORD.search(plain or ""):
                # a citation on its own: it backs the uncited sentences before it on this line
                for claim in pending:
                    claim.hrefs = list(hrefs)
                    out.append(claim)
                pending = []
                continue
            claim = Claim(text=piece, plain=plain, start=start + a, end=start + b, hrefs=hrefs, table=table)
            if hrefs:
                pending = []
                out.append(claim)
            else:
                pending.append(claim)
    out.sort(key=lambda c: c.start)
    return out


# ---- what a sentence states ----------------------------------------------------------------------------------------


def _times(text: str) -> set[str]:
    found = set()
    for m in _TIME.finditer(text):
        hour, minute, half = int(m.group(1)), m.group(2), (m.group(3) or "").lower().replace(".", "")
        if half == "pm" and hour < 12:
            hour += 12
        if half == "am" and hour == 12:
            hour = 0
        found.add("%02d:%s" % (hour, minute))
    return found


def _names(text: str) -> set[str]:
    found = set()
    for m in _CAP_RUN.finditer(text):
        words = [w for w in re.split(r"\s+", m.group(1).strip()) if w]
        while words and (words[-1].lower().strip(".'’s") in _NOT_NAMES or words[-1] in ("of", "de", "la", "&")):
            words.pop()
        while words and words[0].lower().strip(".'’") in _NOT_NAMES:
            words.pop(0)
        if not words:
            continue
        name = " ".join(words)
        name = re.sub(r"['’]s$", "", name).strip(".,;:")
        core = [w for w in _WORD.findall(name) if len(w) >= 3 and not w.isdigit()]
        if not core:
            continue
        if len(words) == 1 and m.start() == 0:
            continue  # a single capitalised word opening the sentence is not taken as a name
        found.add(name)
    return found


def specifics(sentence: str) -> dict[str, set[str]]:
    """What the sentence states that a source must carry: names, figures and dates, times, identifiers."""
    plain = _plain(sentence)
    idents = {m.group(0) for m in _IDENT.finditer(plain) if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", m.group(0))}
    no_ident = _IDENT.sub(" ", plain)
    return {"names": _names(no_ident), "figures": _figures(no_ident) | _figures(" ".join(re.findall(
        r"\d{4}-\d{2}-\d{2}", plain))), "times": _times(no_ident), "identifiers": idents}


class _Haystack:
    """A source's text, normalised once for the lookups."""

    def __init__(self, text: str):
        self.folded = re.sub(r"\s+", " ", (text or "").casefold())
        self.words = set(_WORD.findall(self.folded))
        self.figures = _figures(text or "") | _minor_units(text or "")
        self.times = _times(text or "") | {m.group(1) for m in re.finditer(r"T(\d{2}:\d{2})", text or "")}
        self.compact = re.sub(r"[\s\-/.]", "", self.folded)

    def has(self, kind: str, value: str) -> bool:
        if kind == "figures":
            return value in self.figures
        if kind == "times":
            return value in self.times
        if kind == "identifiers":
            return re.sub(r"[\s\-/.]", "", value.casefold()) in self.compact
        words = [w.casefold() for w in _WORD.findall(value) if len(w) >= 3 and not w.isdigit()]
        return bool(words) and all(w in self.words for w in words)


def _minor_units(text: str) -> set[str]:
    """Amounts a record holds in minor units (``65000``) as an answer writes them (``650``)."""
    out = set()
    for m in re.finditer(r"\"amount_minor\":\s*(-?\d+)", text):
        value = m.group(1).lstrip("-")
        if len(value) > 2:
            major = value[:-2] + "." + value[-2:]
            out.add(major.rstrip("0").rstrip(".") if "." in major else major)
    return out


def code_verdict(wanted: dict[str, set[str]], sources: list[_Haystack]) -> Verdict | None:
    """Settled by code, or None for the model: supports when every specific is in the cited text and at least one is a
    figure, date, time or identifier; does not mention when two or more specifics and none of them are."""
    items = [(kind, value) for kind, values in wanted.items() for value in sorted(values)]
    if not items:
        return None
    found = [v for k, v in items if any(s.has(k, v) for s in sources)]
    missing = [v for k, v in items if not any(s.has(k, v) for s in sources)]
    if not missing and any(kind != "names" for kind, _ in items):
        # names alone do not carry a sentence (a page naming a person says nothing of what they did): the model reads it
        return Verdict(SUPPORTS, "Every name, figure and date of the sentence is in the cited source: "
                       + ", ".join(found[:8]) + ".", "code", found=found)
    if not found and len(items) >= 2:
        return Verdict(NOT_MENTIONED, "None of the sentence's names, figures or dates is in the cited source: "
                       + ", ".join(missing[:8]) + ".", "code", missing=missing)
    return None


# ---- the cited sources ---------------------------------------------------------------------------------------------


def _doc_text(session, case_id, resolution) -> Source:
    from postgres.models.evidence import EvidenceFile
    from services.evidence_page_text import MAX_PAGE_LIMIT, document_pages
    record = session.get(EvidenceFile, uuid.UUID(resolution.evidence_file_id))
    if record is None or str(record.case_id) != str(case_id):
        return Source(reason=C.NOT_IN_CASE)
    label = record.original_filename or "document"
    if resolution.page:
        view = document_pages(session, record, path=None, page_offset=resolution.page - 1, page_limit=1)
        if view.get("text_absent"):
            return Source(reason="The document has no readable text: " + str(view["text_absent"]).strip(), label=label)
        pages = view.get("pages") or []
        text = pages[0].get("text") if pages else ""
        if not pages or resolution.page > (view.get("page_count") or 0):
            return Source(reason=f"The document has no page {resolution.page}.", label=label)
        if not (text or "").strip():
            return Source(reason=f"Page {resolution.page} has no readable text.", label=label)
        return Source(text=text[:MAX_SOURCE_CHARS], label=f"{label}, page {resolution.page}")
    view = document_pages(session, record, path=None, page_offset=0, page_limit=MAX_PAGE_LIMIT)
    if view.get("text_absent"):
        return Source(reason="The document has no readable text: " + str(view["text_absent"]).strip(), label=label)
    text = "\n".join(page.get("text") or "" for page in view.get("pages") or [])
    complete = not view.get("has_more") and len(text) <= MAX_SOURCE_CHARS
    return Source(text=text[:MAX_SOURCE_CHARS], complete=complete, label=label + " (page not given)")


def _txn_text(session, case_id, transaction_id: str) -> Source:
    from postgres.models.financial import FinancialAccount, FinancialTransaction
    row = session.get(FinancialTransaction, uuid.UUID(transaction_id))
    if row is None or str(row.case_id) != str(case_id):
        return Source(reason=C.NOT_IN_CASE)
    note = None
    if row.superseded_by_id:
        newer = session.get(FinancialTransaction, row.superseded_by_id)
        if newer is not None and str(newer.case_id) == str(case_id):
            row, note = newer, "The cited payment was replaced by a corrected one; the corrected values are checked."
    account = session.get(FinancialAccount, row.account_id) if row.account_id else None
    fields = {
        "date": str(row.transaction_date or ""), "posted": str(row.posted_date or ""),
        "amount_minor": row.amount_minor, "currency": row.currency, "direction": row.direction,
        "description": row.description, "counterparty": row.counterparty_raw, "type": row.transaction_type,
        "reference": row.bank_reference,
        "account": {key: getattr(account, key, None) for key in
                    ("holder_name", "institution_name", "identifier_as_printed", "account_type")}
        if account is not None else None,
    }
    text = json.dumps(fields, ensure_ascii=False, default=str)
    return Source(text=text, label="payment" + (f" ({note})" if note else ""))


def _rec_text(session, case_id, record_uid: str) -> Source:
    from services.phone import records
    try:
        detail = records.record_detail(session.connection(), case_id, record_uid)
    except Exception as exc:  # noqa: BLE001 - a record that cannot be read is unchecked, with the reason
        if exc.__class__.__name__ == "NotFound":
            return Source(reason=C.NOT_IN_CASE)
        logger.warning("Phone record %s could not be read for the citation check", record_uid, exc_info=True)
        return Source(reason="The phone record could not be read.")
    return Source(text=json.dumps(detail, ensure_ascii=False, default=str)[:MAX_SOURCE_CHARS], label="phone record")


def read_sources(session, case_id, hrefs: Iterable[str]) -> dict[str, Source]:
    """The text each citation names, read once per citation. A target not in the case, or one that cannot be read,
    carries the reason instead of text."""
    hrefs = list(dict.fromkeys(hrefs))
    parsed = [(h, C.parse_citation(h)) for h in hrefs]
    resolutions = {r.href: r for r in C.resolve_citations(session, case_id, [c for _, c in parsed if c])}
    out: dict[str, Source] = {}
    for href, citation in parsed:
        r = resolutions.get(href)
        if citation is None or r is None:
            out[href] = Source(reason="Not a citation Loupe can open.")
            continue
        if r.status != "ok":
            out[href] = Source(reason=r.reason or C.NOT_IN_CASE)
            continue
        try:
            with session.begin_nested():
                if r.scheme == "doc":
                    out[href] = _doc_text(session, case_id, r)
                elif r.scheme == "txn":
                    out[href] = _txn_text(session, case_id, r.transaction_id)
                else:
                    out[href] = _rec_text(session, case_id, r.record_uid)
        except Exception:  # noqa: BLE001
            logger.warning("Cited source %s could not be read for the citation check", href, exc_info=True)
            out[href] = Source(reason="The cited source could not be read.")
    return out


# ---- the model, for what code cannot settle ------------------------------------------------------------------------


JUDGE_INSTRUCTIONS = (
    "You check citations in an investigator's answer. For each item you get one sentence and the text of each "
    "source it cites. For each source decide whether that source states the specific facts of the sentence (names, "
    "amounts, dates, times, places, what happened). A source that mentions the topic but not the sentence's facts "
    "does not support it. Facts the sentence derives (a count, a sum) are supported when the source shows the parts. "
    "Words that give the writer's own reading (suggests, may, consistent with, likely) are not facts and need no "
    "support. When the source carries some of the facts and not others, the state is partly and the reason names "
    "the missing fact. "
    "Do not use outside knowledge. Reply with JSON only: {\"items\": [{\"id\": <item id>, \"sources\": [{\"n\": "
    "<source number>, \"state\": \"supports\", \"partly\" or \"does_not_mention\", \"reason\": \"<one short sentence naming the "
    "fact found or missing>\"}]}]}"
)


def _excerpt(text: str, wanted: dict[str, set[str]]) -> str:
    """The parts of a source around what the sentence states, at most ``EXCERPT_CHARS``."""
    if len(text) <= EXCERPT_CHARS:
        return text
    folded = text.casefold()
    spots = []
    for values in wanted.values():
        for value in values:
            for word in [value] + _WORD.findall(value):
                i = folded.find(word.casefold())
                if i >= 0 and len(word) >= 3:
                    spots.append(i)
                    break
    if not spots:
        return text[:EXCERPT_CHARS]
    width = max(200, EXCERPT_CHARS // (2 * len(spots)))
    windows: list[list[int]] = []
    for i in sorted(spots):
        a, b = max(0, i - width), min(len(text), i + width)
        if windows and a <= windows[-1][1]:
            windows[-1][1] = max(windows[-1][1], b)
        else:
            windows.append([a, b])
    return " … ".join(text[a:b] for a, b in windows)[:EXCERPT_CHARS]


def default_judge(case_id, user_id=None) -> Callable[[str], tuple[str, dict[str, Any], str]]:
    """A call to the configured model (``LOUPE_CITATION_JUDGE_MODEL``, else the default chat model), metered to the
    case: returns (reply, usage, model id)."""
    def call(prompt: str):
        from postgres.models.cost_record import CostJobType
        from services.ai_costs_service import ai_cost_context
        from services.llm_service import llm_service
        context = llm_service.create_context(model_id=os.environ.get(JUDGE_MODEL_SETTING) or None)
        with ai_cost_context(job_type=CostJobType.AI_ASSISTANT, case_id=uuid.UUID(str(case_id)),
                             user_id=uuid.UUID(str(user_id)) if user_id else None,
                             description="Citation check: does each cited source say what its sentence says",
                             meter_calls=True):
            reply = context.call(prompt, temperature=0, json_mode=True, timeout=MODEL_TIMEOUT_S)
        return reply, dict(context.last_usage or {}), context.model_id
    return call


def _ask_model(items: list[dict[str, Any]], judge) -> tuple[dict[tuple[int, int], Verdict], dict[str, Any]]:
    prompt = JUDGE_INSTRUCTIONS + "\n\n" + json.dumps({"items": items}, ensure_ascii=False)
    started = time.monotonic()
    reply, usage, model_id = judge(prompt)
    seconds = round(time.monotonic() - started, 2)
    data = json.loads(reply) if isinstance(reply, str) else reply
    out: dict[tuple[int, int], Verdict] = {}
    for item in (data or {}).get("items") or []:
        try:
            item_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        for src in item.get("sources") or []:
            try:
                n = int(src.get("n"))
            except (TypeError, ValueError):
                continue
            state = {"supports": SUPPORTS, "partly": PARTLY, "does_not_mention": NOT_MENTIONED}.get(src.get("state"))
            if state is None:
                continue
            reason = re.sub(r"\s+", " ", str(src.get("reason") or "")).strip()[:300]
            out[(item_id, n)] = Verdict(state, reason or WORDS[state].capitalize() + ".", f"model:{model_id}")
    return out, {"model": model_id, "usage": usage, "seconds": seconds, "items": len(items)}


# ---- the check -----------------------------------------------------------------------------------------------------


def check(session, case_id, answer: str, *, judge=None, budget: Callable[[], str | None] | None = None
          ) -> dict[str, Any]:
    """Every cited sentence of ``answer`` against the text it cites. ``judge``: the model call for what code cannot
    settle (None: those citations are unchecked, saying so). ``budget``: returns a refusal sentence when the case's AI
    budget does not allow the model call."""
    found = claims(answer)
    over = found[MAX_CLAIMS:]
    found = found[:MAX_CLAIMS]
    sources = read_sources(session, case_id, [h for c in found for h in c.hrefs])
    hay = {h: _Haystack(s.text) for h, s in sources.items() if s.reason is None}
    results: list[dict[str, Any]] = []
    model_items: list[dict[str, Any]] = []
    pending: dict[tuple[int, int], tuple[int, str]] = {}
    for index, claim in enumerate(found):
        wanted = specifics(claim.text)
        verdicts: dict[str, Verdict] = {}
        readable = [h for h in claim.hrefs if h in hay]
        for href in claim.hrefs:
            if sources[href].reason:
                verdicts[href] = Verdict(UNCHECKED, sources[href].reason, "none")
        for href in readable:
            verdict = code_verdict(wanted, [hay[href]])
            if verdict is not None and verdict.state == NOT_MENTIONED and not sources[href].complete:
                verdict = None  # part of a long document was read: the rest may hold it
            if verdict is not None:
                verdicts[href] = verdict
        undecided = [h for h in readable if h not in verdicts]
        if undecided:
            if len(model_items) < MAX_MODEL_ITEMS:
                model_items.append({"id": index, "sentence": claim.plain[:1200], "sources": [
                    {"n": n, "text": _excerpt(sources[h].text, wanted)} for n, h in enumerate(undecided, 1)]})
                for n, h in enumerate(undecided, 1):
                    pending[(index, n)] = (index, h)
            else:
                for h in undecided:
                    verdicts[h] = Verdict(UNCHECKED, f"Over this answer's limit of {MAX_MODEL_ITEMS} sentences read "
                                          "by a model.", "none")
        results.append({"claim": claim, "verdicts": verdicts, "wanted": wanted})
    model_run: dict[str, Any] | None = None
    if model_items:
        refusal = budget() if budget else None
        verdicts_by_model: dict[tuple[int, int], Verdict] = {}
        failure = None
        if refusal:
            failure = refusal
        elif judge is None:
            failure = "No model was available to read this sentence against its source."
        else:
            try:
                verdicts_by_model, model_run = _ask_model(model_items, judge)
            except Exception as exc:  # noqa: BLE001 - the citations stay, unchecked, saying why
                logger.warning("Citation check model call failed", exc_info=True)
                failure = "The model check failed (%s)." % exc.__class__.__name__
                model_run = {"error": exc.__class__.__name__}
        for key, (index, href) in pending.items():
            verdict = verdicts_by_model.get(key) or Verdict(
                UNCHECKED, failure or "The model gave no verdict for this source.", "none")
            results[index]["verdicts"][href] = verdict
    claims_out = []
    counts = {SUPPORTS: 0, PARTLY: 0, NOT_MENTIONED: 0, UNCHECKED: 0}
    by = {"code": 0, "model": 0, "none": 0}
    for result in results:
        claim, verdicts = result["claim"], result["verdicts"]
        cites = []
        for href in claim.hrefs:
            v = verdicts[href]
            counts[v.state] += 1
            by[v.by.split(":", 1)[0]] += 1
            cites.append({"href": href, "state": v.state, "reason": v.reason, "by": v.by,
                          "source": sources[href].label or None})
        states = {c["state"] for c in cites}
        claims_out.append({"text": claim.plain[:400], "start": claim.start, "end": claim.end, "table": claim.table,
                           "citations": cites,
                           "all_fail": bool(cites) and states == {NOT_MENTIONED},
                           "state": SUPPORTS if SUPPORTS in states else PARTLY if PARTLY in states else (
                               NOT_MENTIONED if states == {NOT_MENTIONED} else UNCHECKED)})
    for claim in over:
        for href in claim.hrefs:
            counts[UNCHECKED] += 1
            by["none"] += 1
        claims_out.append({"text": claim.plain[:400], "start": claim.start, "end": claim.end, "table": claim.table,
                           "citations": [{"href": h, "state": UNCHECKED, "by": "none", "reason":
                                          f"Over this answer's limit of {MAX_CLAIMS} cited sentences."}
                                         for h in claim.hrefs], "all_fail": False, "state": UNCHECKED})
    return {"schema": SCHEMA, "available": True, "claims": claims_out, "counts": counts, "by": by,
            "citations": sum(counts.values()), "model": model_run,
            "scope": "Each citation is read against its own page, payment or phone record. Code looks for the "
                     "sentence's names, figures, dates and identifiers; a model reads what code cannot settle. A "
                     "supported citation is not proof the sentence is true."}


# ---- what the reader sees ------------------------------------------------------------------------------------------


def mark(answer: str, result: dict[str, Any]) -> str:
    """The answer with each sentence whose citations all fail marked where it stands, and a short source check at
    the end: the counts, then every citation that does not support its sentence or could not be checked."""
    if not result or not result.get("available") or not result.get("citations"):
        return answer
    text = answer
    for claim in sorted(result["claims"], key=lambda c: c["end"], reverse=True):
        if not claim["all_fail"]:
            continue
        end = claim["end"]
        if claim["table"]:
            line_end = text.rstrip("|").rfind("|", claim["start"], end)
            end = line_end if line_end > claim["start"] else end
        text = text[:end].rstrip() + " " + MARK + text[end:]
    counts = result["counts"]
    total = result["citations"]
    head = f"{counts[SUPPORTS]} of {total} citations support their sentence"
    rest = []
    if counts[PARTLY]:
        rest.append(f"{counts[PARTLY]} support part of it")
    if counts[NOT_MENTIONED]:
        rest.append(f"{counts[NOT_MENTIONED]} do not mention it")
    if counts[UNCHECKED]:
        rest.append(f"{counts[UNCHECKED]} could not be checked")
    model = (result.get("model") or {}).get("model")
    method = ("Code compared names, figures and dates with each cited source"
              + (f"; {result['by']['model']} were read by a model ({model}), not by a person" if result["by"]["model"]
                 else "") + ".")
    lines = [f"{SECTION}: {head}" + ("; " + ", ".join(rest) if rest else "") + ". " + method]
    shown = 0
    for claim in result["claims"]:
        bad = [c for c in claim["citations"] if c["state"] != SUPPORTS]
        if not bad:
            continue
        sentence = claim["text"] if len(claim["text"]) <= 140 else claim["text"][:137].rstrip() + "..."
        for c in bad:
            if shown >= 30:
                break
            shown += 1
            lines.append(f"- \"{sentence}\" [source]({c['href']}): {WORDS[c['state']]}. {c['reason']}")
    hidden = counts[PARTLY] + counts[NOT_MENTIONED] + counts[UNCHECKED] - shown
    if hidden > 0:
        lines.append(f"- {hidden} more citations do not support their sentence or could not be checked.")
    return text.rstrip() + "\n\n" + "\n".join(lines)


def check_and_mark(session, case_id, answer: str, *, user_id=None, judge=None) -> tuple[str, dict[str, Any]]:
    """The stored form of an answer and its check. A check that fails stores the answer unmarked and says so in the
    result; it never shows the answer as checked."""
    if not enabled():
        return answer, {"schema": SCHEMA, "available": False, "reason": "The source check is switched off."}
    if not C.citations_in(answer):
        return answer, {"schema": SCHEMA, "available": True, "citations": 0, "claims": [],
                        "counts": {SUPPORTS: 0, PARTLY: 0, NOT_MENTIONED: 0, UNCHECKED: 0}}
    started = time.monotonic()

    def budget():
        from services import ai_budget
        try:
            with session.begin_nested():  # a failed read must not end the caller's transaction
                ai_budget.check(session, case_id, "the source check")
        except ai_budget.BudgetRefused as exc:
            return str(exc)
        except Exception:  # noqa: BLE001 - spend that cannot be read is not spent on a guess
            logger.warning("AI budget could not be read for the source check of case %s", case_id, exc_info=True)
            return "The case's AI budget could not be read, so no model read these sentences."
        return None
    try:
        result = check(session, case_id, answer, judge=judge if judge is not None else default_judge(case_id, user_id),
                       budget=budget)
    except Exception:  # noqa: BLE001
        logger.exception("Source check failed for case %s", case_id)
        return answer, {"schema": SCHEMA, "available": False,
                        "reason": "The cited sources could not be read against this answer."}
    result["seconds"] = round(time.monotonic() - started, 2)
    return mark(answer, result), result
