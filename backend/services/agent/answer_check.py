"""Completeness check for a normal (not deep) agent run (D18, C2e).

A live sample of 523 stored runs: median 6 tool calls, ``search_case`` found nothing on 109 of 312 calls, and the
answer then said "none found" without saying what was searched. Before a normal run writes its answer, this check
looks at the run's own tool calls. If searches found nothing and no later call found anything, the run goes back once
with the list of what was tried, and is told that a "none found" answer states what was searched.

Decision: one return per run (state["returned"]); a deep run has its own gate and never uses this one. Reverse if a
measured run is made worse by the extra step.
"""
from __future__ import annotations

import re
from typing import Any

SEARCH_NAMES = ("search_", "get_contact_and_money_between", "get_person_phones", "get_account_mentions")
_COUNT_KEYS = ("total_matching", "total", "records_read", "count")


def _is_search(name: str) -> bool:
    return any(name.startswith(p) for p in SEARCH_NAMES)


def _found(preview: Any) -> bool:
    if not isinstance(preview, dict):
        return preview not in (None, "", [], {})
    for k in ("total_matching", "total"):
        if k in preview:
            return bool(preview[k])
    if preview.get("relevant"):
        return True
    if "records_read" in preview:
        return bool(preview["records_read"]) and bool(preview.get("relevant"))
    return any(bool(v) for v in preview.values())


def _empty_search(item: dict) -> bool:
    return (item.get("status") == "success" and _is_search(item.get("name") or "")
            and not _found(item.get("result_preview")))


def check_message(trace: list[dict], state: dict) -> str | None:
    if state.get("returned"):
        return None
    empties = [t for t in trace if _empty_search(t)]
    if not empties:
        return None
    last_empty = max(i for i, t in enumerate(trace) if _empty_search(t))
    # Something found after the last empty search counts as the retry that worked.
    for t in trace[last_empty + 1:]:
        if t.get("status") == "success" and _found(t.get("result_preview")) and t.get("name") not in ("",):
            return None
    state["returned"] = True
    rows = []
    for t in empties[:8]:
        q = (t.get("arguments") or {})
        rows.append("- %s %s" % (t["name"], ", ".join("%s=%s" % (k, str(v)[:60]) for k, v in list(q.items())[:3])))
    return ("Completeness check, not a new instruction from the person. These searches found nothing:\n%s\n"
            "Before you answer, try another route for each: a different tool, other words from the records you "
            "have seen, or read_scope_with_model on the conversation, document or window itself. If you still find "
            "nothing, say what was searched and what was not, never only that none was found." % "\n".join(rows))


# ---- the question's parts (C2e: a normal run plans before it answers) ---------------------------------------------
# The question's own names, numbers, amounts and quoted words are its checklist. The run is shown them before its
# first step, and before it writes, a part no tool call looked for sends it back once with that list. Decision: words
# from the question only (no model call); reverse if a measured run is made worse by the extra step.

_STOP = {"what", "who", "whom", "when", "where", "which", "why", "how", "did", "does", "do", "is", "are", "was", "were",
         "the", "a", "an", "in", "on", "of", "and", "or", "to", "for", "with", "show", "tell", "list", "find", "give",
         "can", "could", "please", "any", "all", "has", "have", "had", "there", "this", "that", "these", "those", "i",
         "we", "you", "it", "my", "our", "between", "from", "after", "before", "during", "about", "case", "phone",
         "phones", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "january", "february",
         "march", "april", "may", "june", "july", "august", "september", "october", "november", "december", "loupe",
         "ok", "yes", "no", "also", "then", "now", "next", "first", "last",
         # a request's own verbs open its sentences capitalised; they are instructions, not names to look up
         "create", "write", "build", "make", "draft", "prepare", "produce", "generate", "summarise", "summarize",
         "compare", "explain", "describe", "check", "look", "search", "read", "review", "analyse", "analyze",
         "identify", "trace", "map", "count", "sum", "total", "chart", "plot", "export", "open", "help", "provide",
         "include", "use", "add", "revise", "update", "rewrite", "edit", "keep", "put", "set", "get", "go", "see",
         "note", "say", "state", "cover", "outline", "break", "group", "sort", "rank", "work", "focus", "start"}
_QUOTED = re.compile(r"[\"“‘']([^\"”’']{3,60})[\"”’']")
_NUMBER = re.compile(r"\+?\d[\d ().-]{5,}\d")
_AMOUNT = re.compile(r"[$£€]\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s?(?:dollars|usd|eur|gbp)\b", re.I)
_NAME = re.compile(r"\b[A-Z][a-zA-Z'’-]+(?:\s+[A-Z][a-zA-Z'’-]+)*")


def question_parts(question: str) -> list[str]:
    """Names, numbers, amounts and quoted words in the question, in order, each once."""
    q = question or ""
    out: list[str] = []

    def add(v):
        v = v.strip(" ,.?!:;")
        if v and v.lower() not in {x.lower() for x in out}:
            out.append(v)

    for m in _QUOTED.finditer(q):
        add(m.group(1))
    for m in _NUMBER.finditer(q):
        if len(re.sub(r"\D", "", m.group(0))) >= 7:
            add(m.group(0))
    for m in _AMOUNT.finditer(q):
        add(m.group(0))
    for m in _NAME.finditer(q):
        words = [w for w in m.group(0).split() if w.lower() not in _STOP]
        if words and not all(w.isupper() and len(w) <= 2 for w in words):
            add(" ".join(words))
    return out[:12]


def plan_message(question: str) -> str | None:
    parts = question_parts(question)
    if not parts:
        return None
    return ("Plan check, not a new instruction from the person. The question names: %s. Plan which tool reads each "
            "before you start, look each one up, and in the answer cover each one or say what was searched for it "
            "and found nothing." % "; ".join(parts))


def _looked_for(part: str, trace: list[dict]) -> bool:
    import json
    words = [w.lower() for w in re.findall(r"[\w'’+$£€.,-]+", part) if len(w) >= 3] or [part.lower()]
    digits = re.sub(r"\D", "", part)
    for t in trace:
        seen = json.dumps(t.get("arguments") or {}, ensure_ascii=False, default=str).lower()
        if digits and len(digits) >= 7 and digits[-7:] in re.sub(r"\D", "", seen):
            return True
        if _AMOUNT.fullmatch(part.strip()):
            amount = re.sub(r"[^\d.]", "", part).rstrip(".")
            if amount and re.search(r"(?<![\d.])%s(?:\.0+)?(?![\d])" % re.escape(amount), seen):
                return True
            continue
        if any(w.strip(".,") in seen for w in words):
            return True
    return False


def parts_message(question: str, trace: list[dict], state: dict) -> str | None:
    """Sends the run back once when a part of the question was never looked for."""
    if state.get("parts_returned"):
        return None
    missing = [p for p in question_parts(question) if not _looked_for(p, trace)]
    if not missing:
        return None
    state["parts_returned"] = True
    return ("Completeness check, not a new instruction from the person. The question names %s, and no tool call has "
            "looked for %s yet. Look each up now (by name, number or amount, on the phones, documents and ledger as "
            "fits), or say in the answer that it was not searched and why." % (
                "; ".join(missing), "it" if len(missing) == 1 else "them"))


# ---- the phones around payments the run read (followups 22 Nov 2026) ----------------------------------------------
# Live 22 Nov: after a payments read said the phones hold records in the week before each payment
# (services.agent.phones_around_payments), 2 of 3 runs of 'What comes before each of those checks?' still answered
# from the ledger alone and missed the price list emailed before one check. Before such a run writes, it goes back
# once to read those windows or to say in the answer that it did not. Decision: one return per run, only when no
# phone or whole-case read ran after the payments read; reverse if a measured run is made worse by the extra step.

AROUND_MARK = "around_on_phones.windows"
PHONE_READS = ("phone_", "get_contact_and_money_between", "get_payment_conversation", "get_day_activity",
               "get_period_activity", "search_case", "read_scope_with_model", "search_by_meaning")


def around_message(trace: list[dict], state: dict) -> str | None:
    if state.get("around_returned"):
        return None
    marked = [i for i, t in enumerate(trace) if t.get("status") == "success"
              and t.get("name") == "get_financial_transactions" and AROUND_MARK in str(t.get("summary") or "")]
    if not marked:
        return None
    last = marked[-1]
    if any(str(t.get("name") or "").startswith(PHONE_READS) for t in trace[last + 1:]):
        return None
    state["around_returned"] = True
    said = str(trace[last].get("summary") or "")
    said = said[said.find("The phones hold"):] if "The phones hold" in said else said
    return ("Completeness check, not a new instruction from the person. A payments read said: \"%s\" No phone "
            "record has been read since. If the question asks what came before, after or around these payments, read "
            "the windows it is about now (each window's read_with call in around_on_phones, or search_case with a "
            "name and that start and end) and answer from the phones beside the ledger. Otherwise say in the answer "
            "that the phones around these payments were not read." % said.strip())

