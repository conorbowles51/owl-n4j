"""The agent's answer in plain words, checked by code before it is stored and shown (lx-agentlive C).

The final answer is written for an investigator who is not technical. The finalizer's prompt asks for plain words
(services.agent.graph), but a live answer (run 8df85211, 8 Nov 2026) still opened with "admitted at `proof_class` p3",
"`proof_class_not_included: 27673`", "no p0–p2 verified rows" and "`get_financial_coverage(account_holders=[…])`".
So every answer passes through :func:`checked` on both service paths, next to the citation check.

What it rewrites, always to the words the financial screens use for the same thing (frontend_v2 ledger-format.ts):
proof-class codes p0–p4 (single, ranges and lists), the words "proof class", the verified and working populations,
tool names and tool calls (the names come from the live tool registry, so a new tool is covered without a list here;
each is named by the title the activity panel shows for it), and tool-result field names with a known meaning.

What it never touches: a citation link (label and target), a bare link (rec://, doc://, txn://, http…), a fenced code
block, an inline code span that is not one of the terms above (an account number, a CLABE, a quoted value), an email
address or handle, and any code that is part of a longer token (``p3`` inside ``ABC-p3`` or a record id).

What it cannot rewrite safely it leaves as written and flags in the run's metadata (``plain_check.flagged``): a
snake_case word with no known plain meaning (it may be a handle or a value), and a term inside a link label or code
block. Nothing is dropped: a tool call's arguments are kept, in words.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable

log = logging.getLogger(__name__)

# The screens' words for each check status (frontend_v2/src/features/financial/lib/ledger-format.ts PROOF_CLASS_COPY).
CLASS_WORDS = {
    "0": "checked against the file's own totals",
    "1": "read exactly, with no total in the file to check against",
    "2": "checked against the statement's printed balances",
    "3": "left out of verified totals (read from a PDF statement, which stays out by rule even when it balances, or its checks are incomplete)",
    "4": "mentioned elsewhere, not a financial record, and never counted",
}
VERIFIED_WORDS = "verified"  # p0, p1 and p2 together: the classes that enter verified totals
POPULATION_WORDS = {"verified": "verified payments only", "working": "every usable payment, checked or not"}
POPULATION_NOUN = {"verified": "set of verified payments", "working": "working set (every usable payment, checked or not)"}

# Tool-result fields an answer has been seen to name, or that the prompts name, with what each means.
FIELD_WORDS = {
    "proof_class": "check status",
    "source_proof_class": "source's check status",
    "proof_class_not_included": "left out of verified totals (read from a PDF statement, or not fully checked)",
    "source_not_admitted": "from a source not yet admitted",
    "total_matching": "payments matching",
    "has_more": "more not yet read",
    "next_offset": "next page",
    "next_page": "next page",
    "included_in_totals": "counted in totals",
    "from_name": "payer name",
    "to_name": "payee name",
    "counterparty_raw": "description as printed",
    "open_judgement_calls": "open judgement calls",
    "judgement_calls": "judgement calls",
    "statement_cite": "statement page link",
    "statement_page": "statement page",
    "credit_card": "credit card",
    "ledger_revision": "ledger version",
    "expected_revision": "ledger version",
    "expected_ledger_revision": "ledger version",
    "model_read_names": "names a model read",
    "source_result_ids": "source results",
    "account_holders": "account holders",
    "outside_verified_rows": "rows outside verified totals",
    "included_classes": "check statuses included",
    "exclusion_reason": "reason left out",
    "considered_rows": "rows considered",
    "ledger_status": "ledger status",
    "match_lines": "matches",
    "rank_reason": "reason for its rank",
    "base_rate": "base rate",
    "group_basis": "grouping basis",
    "exact_displayed_label": "the name shown on the row",
    "amount_minor": "amount",
    "account_type": "account type",
    "date_from": "from date",
    "date_to": "to date",
}

# The rule both prompts carry (services.agent.graph: the finalizer's system prompt and the tool loop's).
PROMPT_RULE = (
    "Write the answer in plain words for an investigator who is not technical. Never write a check-status code "
    "(p0, p1, p2, p3, p4, alone or as a range), the words proof class or population, a tool name, a tool call, or a "
    "field name from a tool result (for example proof_class_not_included, total_matching, from_name); say what it "
    "means instead, in the words the screens use: p0 or p2 is checked against the statement's printed balances, p1 "
    "is read exactly with no total in the file to check, p0 to p2 together are verified, p3 is not fully checked and "
    "so left out of verified totals, p4 is mentioned elsewhere, not a financial record, and never counted; the "
    "verified population is the verified payments, the working population is every usable payment, checked or not. "
    "For example, write \"none of these payments could be checked against the statements' printed balances, so I've "
    "used the figures as read and labelled them unverified\", not \"no p0-p2 rows (proof_class_not_included: "
    "27673)\". Say what you looked at, not which tool you called. Keep citation links, account numbers, CLABE "
    "numbers and other quoted evidence exactly as returned. Do not use em dashes."
)

_EDGE_BEFORE = r"(?<![\w@./:#\-‐-―])"
_EDGE_AFTER = r"(?![\w@\-]|\.[A-Za-z0-9])"
_SNAKE = re.compile(_EDGE_BEFORE + r"([a-z][a-z0-9]*(?:_[a-z0-9]+)+)" + _EDGE_AFTER)
_CLASS = r"[pP]([0-4])"
_DASH = r"\s*(?:–|—|-|to|through)\s*"
_CLASS_LIST = re.compile(_EDGE_BEFORE + r"[pP]0,\s*[pP]1,?\s*(?:and|or)\s*[pP]2(?![\w\-])(\s+verified)?")
_CLASS_RANGE = re.compile(_EDGE_BEFORE + r"((?:verified\s+)?)" + _CLASS + _DASH + r"[pP]?([0-4])(?![\w\-])(\s+verified)?")
_CLASS_ONE = re.compile(_EDGE_BEFORE + _CLASS + r"(?![\w\-]|\.\d)")
_PROOF_SCOPE = re.compile(r"(?i)\bproof[-_ ]class\s+scope\b")
_PROOF_WORD = re.compile(r"(?i)(?<![\w.])(source[_ ])?proof[-_ ]class(es)?\b")
_POPULATION_ARG = re.compile(r"(?i)\bpopulation\s*[=:]\s*[\"'`]?(verified|working)[\"'`]?")
_POPULATION_NOUN = re.compile(r"(?i)(?<![\w\"“'])([\"“']?)(verified|working)[\"”']?\s+population\b")
_FENCE = re.compile(r"```.*?(?:```|\Z)", re.S)
_LINK = re.compile(r"!?\[(?:[^\[\]]|\[[^\[\]]*\])*\]\([^()\s]*(?:\([^()\s]*\)[^()\s]*)*(?:\s+\"[^\"]*\")?\)")
_AUTOLINK = re.compile(r"<[a-z][a-z0-9+.\-]*:[^\s>]+>", re.I)
_URI = re.compile(r"\b[a-z][a-z0-9+.\-]*://[^\s)\]>]+", re.I)
_EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+|(?<![\w])@[\w.]+")
_INLINE = re.compile(r"(`+)(.+?)\1", re.S)
_MASK = re.compile("(\\d+)")


def _tool_names() -> frozenset[str]:
    from services.agent.workflows import registered_tool_names
    return registered_tool_names()


def _tool_title(name: str) -> str:
    """The title the activity panel shows for the tool, or its name in words when it has none."""
    from services.agent.graph import activity_for_tool_call
    title = activity_for_tool_call(name, {}, "plain-check")["title"]
    if title == "Used agent tool":
        title = name.replace("_", " ").capitalize()
    return title


def _cap(word: str, like: str) -> str:
    return word[:1].upper() + word[1:] if like[:1].isupper() else word


def _class_words(lo: str, hi: str) -> str:
    lo, hi = sorted((int(lo), int(hi)))
    if (lo, hi) == (0, 2):
        return VERIFIED_WORDS
    return " or ".join(CLASS_WORDS[str(i)] for i in range(lo, hi + 1))


def _split_args(text: str) -> list[str]:
    parts, depth, quote, cur = [], 0, None, ""
    for ch in text:
        if quote:
            quote = None if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
            continue
        cur += ch
    return [p.strip() for p in parts + [cur] if p.strip()]


def _arg_value(value: str) -> str:
    value = value.strip()
    if value[:1] in "[(" and value[-1:] in "])":
        return ", ".join(_arg_value(v) for v in _split_args(value[1:-1]))
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _args_words(args: str) -> str:
    words = []
    for part in _split_args(args):
        m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*[=:]\s*(.*)\Z", part, re.S)
        if not m:
            words.append(_arg_value(part))
            continue
        key, value = m.group(1), _arg_value(m.group(2))
        if key == "population" and value.lower() in POPULATION_WORDS:
            words.append(POPULATION_WORDS[value.lower()])
        else:
            words.append("%s: %s" % (FIELD_WORDS.get(key, key.replace("_", " ")), value))
    return "; ".join(w for w in words if w)


def _close_paren(text: str, start: int, limit: int = 600) -> int | None:
    """Index just after the parenthesis that closes the one at ``start``; None when it does not close nearby."""
    depth, quote = 0, None
    for i in range(start, min(len(text), start + limit)):
        ch = text[i]
        if quote:
            quote = None if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
    return None


class _Check:
    def __init__(self, tools: frozenset[str]):
        self.tools = tools
        self.terms: dict[str, int] = {}
        self.flagged: list[dict[str, str]] = []
        self.masks: list[str] = []
        names = "|".join(sorted(map(re.escape, tools), key=len, reverse=True)) or r"(?!x)x"
        self.tool_re = re.compile(r"(?<![\w@./:#\-])(?:functions\.)?(" + names + r")(?![\w\-])")

    # bookkeeping
    def hit(self, kind: str) -> None:
        self.terms[kind] = self.terms.get(kind, 0) + 1

    def flag(self, text: str, why: str) -> None:
        item = {"text": text[:120], "why": why}
        if item not in self.flagged and len(self.flagged) < 50:
            self.flagged.append(item)

    def mask(self, text: str) -> str:
        self.masks.append(text)
        return "%d" % (len(self.masks) - 1)

    def unmask(self, text: str) -> str:
        while _MASK.search(text):
            text = _MASK.sub(lambda m: self.masks[int(m.group(1))], text)
        return text

    def scan(self, text: str, where: str) -> None:
        """Flag internal terms left as written inside text that is never rewritten."""
        for m in self.tool_re.finditer(text):
            self.flag(m.group(1), "tool name %s, left as written" % where)
        for rx in (_CLASS_RANGE, _CLASS_ONE):
            for m in rx.finditer(text):
                self.flag(m.group(0), "check-status code %s, left as written" % where)
        if _PROOF_WORD.search(text):
            self.flag(_PROOF_WORD.search(text).group(0), "internal term %s, left as written" % where)

    # rewriting
    def calls(self, text: str, lead: str = "") -> str:
        out, pos = [], 0
        for m in self.tool_re.finditer(text):
            if m.start() < pos:
                continue
            name, end = m.group(1), m.end()
            before = (lead + text[:m.start()]).rstrip(" \t*_")
            first = not before or before[-1] in ".!?:\n|"  # a sentence, list item or table cell opens with it
            words = "%s “%s” step" % ("The" if first else "the", _tool_title(name))
            paren = re.compile(r"\s*\(").match(text, end)
            close = _close_paren(text, paren.end() - 1) if paren else None
            if close is not None:
                args = _args_words(text[paren.end():close - 1])
                words += " (%s)" % args if args else ""
                end = close
                self.hit("tool call")
            else:
                self.hit("tool name")
            out += [text[pos:m.start()], words]
            pos = end
        return "".join(out) + text[pos:]

    def words(self, text: str, lead: str = "") -> str:
        """``lead``: the text before ``text`` (an inline span's sentence), so a tool named first is capitalised."""
        text = self.calls(text, lead)

        def sub(rx, kind, fn):
            nonlocal text

            def one(m):
                self.hit(kind)
                return fn(m)
            text = rx.sub(one, text)

        sub(_POPULATION_ARG, "population", lambda m: POPULATION_WORDS[m.group(1).lower()])
        sub(_POPULATION_NOUN, "population",
            lambda m: _cap(POPULATION_NOUN[m.group(2).lower()], m.group(2)))
        sub(_PROOF_SCOPE, "proof class", lambda m: _cap("what could be checked", m.group(0)))
        sub(_CLASS_LIST, "check-status code", lambda m: VERIFIED_WORDS)
        sub(_CLASS_RANGE, "check-status code",
            lambda m: VERIFIED_WORDS if (m.group(1) or m.group(4)) and _class_words(m.group(2), m.group(3)) == VERIFIED_WORDS
            else m.group(1) + _class_words(m.group(2), m.group(3)) + (m.group(4) or ""))
        sub(_CLASS_ONE, "check-status code", lambda m: CLASS_WORDS[m.group(1)])

        def field(m):
            token = m.group(1)
            if token in FIELD_WORDS:
                self.hit("field name")
                return FIELD_WORDS[token]
            self.flag(token, "a word with underscores and no known plain meaning, left as written")
            return token
        text = _SNAKE.sub(field, text)
        sub(_PROOF_WORD, "proof class",
            lambda m: _cap(("source's " if m.group(1) else "") + "check status" + ("es" if m.group(2) else ""),
                           m.group(0)))
        return text

    def inline(self, m: re.Match) -> str:
        """An inline code span: rewritten (without its backticks) when the whole span is an internal term, else kept."""
        body = m.group(2).strip()
        is_call = self.tool_re.fullmatch(body) or (
            self.tool_re.match(body) and body.endswith(")") and "(" in body)
        is_field = re.fullmatch(r"([a-z][a-z0-9]*(?:_[a-z0-9]+)+)(\s*[:=]\s*[\w.,\-\"']+)?", body)
        if is_call or (is_field and is_field.group(1) in FIELD_WORDS) \
                or _CLASS_ONE.fullmatch(body) or _CLASS_RANGE.fullmatch(body) or _POPULATION_ARG.fullmatch(body) \
                or _PROOF_WORD.fullmatch(body):
            return self.words(body, self.unmask(m.string[:m.start()]))
        if is_field:
            self.flag(body, "code with underscores and no known plain meaning, left as written")
        return self.mask(m.group(0))

    def run(self, answer: str) -> str:
        text = answer

        def protect(rx, where=None):
            nonlocal text

            def keep(m):
                if where:
                    self.scan(m.group(0), where)
                return self.mask(m.group(0))
            text = rx.sub(keep, text)

        protect(_FENCE, "in a code block")
        protect(_LINK, "in a link")
        protect(_AUTOLINK)
        protect(_URI)
        protect(_EMAIL)
        text = _INLINE.sub(self.inline, text)
        text = self.words(text)
        return self.unmask(text)


def plain(answer: str, *, tools: frozenset[str] | None = None) -> tuple[str, dict[str, Any]]:
    """The answer in plain words, and what was done: ``rewritten`` (count), ``terms`` (count per kind), ``flagged``."""
    if not answer:
        return answer, {"available": True, "rewritten": 0, "terms": {}, "flagged": []}
    check = _Check(tools if tools is not None else _tool_names())
    out = check.run(answer)
    return out, {"available": True, "rewritten": sum(check.terms.values()), "terms": check.terms,
                 "flagged": check.flagged}


def checked(answer: str, *, tools: Callable[[], frozenset[str]] | None = None) -> tuple[str, dict[str, Any]]:
    """The production call. A check that fails leaves the answer as the model wrote it, and says so."""
    try:
        return plain(answer, tools=tools() if tools else None)
    except Exception:  # noqa: BLE001 - an unchecked answer says so; it is never shown as checked
        log.exception("Plain-words check failed")
        return answer, {"available": False, "reason": "The answer's wording could not be checked for internal terms."}
