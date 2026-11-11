"""How good an agent answer is, counted claim by claim against what the run read (lx-agentfit round 2, R2a).

The counts are a rule check, computed by this code from the answer and the run's tool results; they are never
blended into one number, so a loss on one count is never hidden by a gain on another. What the rules cannot judge
(whether a claim says what its record says in words, which facts the question needed) is the claim-by-claim check a
reader does (Claude in lx-agentfit, labelled as Claude's check) and is kept apart from these counts.

Per answer:
- claims: sentences and table rows that state a figure, a date or a source;
- cited / uncited: claims that carry a source link, and claims with a figure that carry none;
- citations: distinct sources the answer links; ``not_read``: links to a record no tool result in this run
  returned (it may still open, but the run never read it, so nothing in the run supports the claim);
- figures: each figure in a cited claim, ``in_record`` when it appears in a record the claim cites, ``not_in_record``
  when none of the claim's read sources carries it;
- unfinished: whether the run left work undone (stopped at its limit, or a result had more rows not read) and
  whether the answer says so;
- other_side: for a factual question, whether the answer gives an alternative and what the records say about it;
- certainty: words that state more certainty than a record can carry.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable

SCHEMA = "loupe.agent.answer_quality/1"
# Counts where a higher number is worse; the rest (claims, cited, figures in_record) are better higher.
WORSE_HIGHER = ("uncited", "not_read", "not_in_record", "unfinished_unstated", "other_side_missing", "certainty")
BETTER_HIGHER = ("cited", "citations", "in_record")

_LINK = re.compile(r"(?:txn|doc|rec)://[0-9A-Za-z][0-9A-Za-z_\-]*(?:/\d+)?")
_MD_LINK = re.compile(r"\[([^\]\n]*)\]\(\s*<?([^)>\s]*)>?\s*\)")
_MONTHS = {m: i for i, m in enumerate(
    ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
     "december"), 1)}
_MONTH = r"(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|" \
         r"jun|jul|aug|sep|sept|oct|nov|dec)\.?"
_DAY_MONTH_YEAR = re.compile(r"\b(\d{1,2})\s+" + _MONTH + r",?\s+(\d{4})\b", re.I)
_MONTH_DAY_YEAR = re.compile(r"\b" + _MONTH + r"\s+(\d{1,2}),?\s+(\d{4})\b", re.I)
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})")
_NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")
_UNFINISHED = re.compile(
    r"\b(?:not (?:yet )?(?:read|checked|covered|reached|finished|done|searched|looked)|could not|did not (?:read|"
    r"reach|check|get to)|unfinished|remaining|still to|not every|left (?:out|unread)|continue|more (?:rows|records|"
    r"results) (?:than|were not)|of \d[\d,]* (?:were|was) (?:read|shown))\b", re.I)
_OTHER_SIDE = re.compile(
    r"\b(?:contradict\w*|inconsistent|alternative|other (?:side|version|party)|on the other hand|against (?:this|"
    r"that|it)|does not (?:support|show|match)|do not (?:support|show|match)|no record (?:shows|supports|places)|"
    r"tested|consistent with|their version|the (?:defence|defense|state|government)'?s? (?:version|account|"
    r"case|claim))\b", re.I)
_CERTAIN = re.compile(r"\b(?:proves?|proven|proved|conclusively|definitely|certainly|beyond (?:any )?doubt|"
                      r"undoubtedly|without (?:any )?doubt|clearly (?:shows|proves|establishes)|establishes that|"
                      r"confirms that)\b", re.I)
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[(\"“*])|\n+")
MIN_NUMBER_DIGITS = 3  # smaller numbers (counts like "2 calls") are too common to match a record by text


def _iso(day: str, month: str, year: str) -> str | None:
    key = month.lower().rstrip(".")
    number = _MONTHS.get(key) or next((i for name, i in _MONTHS.items() if name.startswith(key[:3])), None)
    if not number or not 1 <= int(day) <= 31:
        return None
    return "%s-%02d-%02d" % (year, number, int(day))


def figures(text: str) -> set[str]:
    """Dates (as YYYY-MM-DD) and numbers of three or more digits (commas dropped) a piece of text states."""
    text = _MD_LINK.sub(lambda m: m.group(1), text)
    text = _LINK.sub(" ", text)
    found: set[str] = set()
    for m in _DAY_MONTH_YEAR.finditer(text):
        found.add(_iso(m.group(1), m.group(2), m.group(3)) or "")
    for m in _MONTH_DAY_YEAR.finditer(text):
        found.add(_iso(m.group(2), m.group(1), m.group(3)) or "")
    dated = _DAY_MONTH_YEAR.sub(" ", _MONTH_DAY_YEAR.sub(" ", text))
    for m in _ISO_DATE.finditer(dated):
        found.add(m.group(0))
    dated = _ISO_DATE.sub(" ", dated)
    for m in _NUMBER.finditer(dated.replace("−", "-")):
        number = m.group(0).lstrip("-").replace(",", "")
        if sum(c.isdigit() for c in number) >= MIN_NUMBER_DIGITS:
            found.add(_canon(number))
    found.discard("")
    return found


def _canon(number: str) -> str:
    """One way of writing a number: 1200000.00, 1200000.0 and 1200000 are the same figure, as are 39.3610 and 39.361."""
    return number.rstrip("0").rstrip(".") if "." in number else number


def _record_figures(value: Any) -> set[str]:
    """Every figure a record carries, written the ways an answer may write it (minor units also as major)."""
    text = json.dumps(value, ensure_ascii=False, default=str)
    found = {m.group(0) for m in _ISO_DATE.finditer(text)} | figures(text.replace("\\n", " "))
    for m in _NUMBER.finditer(_ISO_DATE.sub(" ", text)):
        number = m.group(0).lstrip("-").replace(",", "")
        found.add(_canon(number))
        if "." not in number:
            for exponent in (2, 3):  # an amount in minor units, as an answer writes it in major units
                if len(number) > exponent:
                    found.add(_canon(number[:-exponent] + "." + number[-exponent:]))
    return found


def _rows_by_link(outputs: Iterable[Any]) -> dict[str, list[Any]]:
    """Each source link a run's results carry, with the smallest mappings that carry it (the record's row)."""
    rows: dict[str, list[Any]] = {}

    def walk(value: Any, depth: int = 0) -> set[str]:
        if depth > 40:
            return set()
        here: set[str] = set()
        if isinstance(value, dict):
            for item in value.values():
                here |= walk(item, depth + 1)
            own = {link for item in value.values() if isinstance(item, str) for link in _LINK.findall(item)}
            for link in own:
                rows.setdefault(link, []).append(value)
            return here | own
        if isinstance(value, list):
            for item in value:
                here |= walk(item, depth + 1)
            return here
        if isinstance(value, str):
            return set(_LINK.findall(value))
        return here

    for output in outputs:
        walk(output)
    return rows


def _bare(link: str) -> str:
    return link.split("/", 3)[2] if link.count("/") >= 2 else link


def claims(answer: str) -> list[str]:
    """The answer's sentences and table rows that state a figure, a date or a source."""
    parts = [p.strip() for p in _SENTENCE.split(answer or "") if p and p.strip()]
    return [p for p in parts if not re.fullmatch(r"\|?[\s:\-|]+\|?", p) and (figures(p) or _LINK.search(p))]


def score(answer: str, outputs: Iterable[Any], *, question: str = "", stopped_at_limit: bool = False,
          results_with_more: int = 0) -> dict[str, Any]:
    """The counts for one answer; ``outputs`` are the run's tool results as the tools returned them."""
    from services.agent.question_scope import is_factual

    outputs = list(outputs)
    rows = _rows_by_link(outputs)
    read_ids = {_bare(link) for link in rows}
    found = claims(answer)
    cited = [c for c in found if _LINK.search(c)]
    uncited = [c for c in found if not _LINK.search(c) and figures(c)]
    links = set(_LINK.findall(answer or ""))
    not_read = sorted(link for link in links if link not in rows and _bare(link) not in read_ids)
    in_record = not_in_record = 0
    unsupported: list[dict[str, Any]] = []
    for claim in cited:
        claim_links = [link for link in _LINK.findall(claim) if link in rows or _bare(link) in read_ids]
        if not claim_links:
            continue
        carried: set[str] = set()
        for link in claim_links:
            for row in rows.get(link) or [r for k, v in rows.items() if _bare(k) == _bare(link) for r in v]:
                carried |= _record_figures(row)
        missing = sorted(f for f in figures(claim) if f not in carried)
        in_record += len(figures(claim)) - len(missing)
        not_in_record += len(missing)
        if missing:
            unsupported.append({"claim": claim[:300], "figures": missing, "sources": claim_links})
    unfinished = bool(stopped_at_limit or results_with_more)
    unfinished_stated = bool(_UNFINISHED.search(answer or ""))
    factual = is_factual(question)
    other_side = bool(_OTHER_SIDE.search(answer or ""))
    return {
        "schema": SCHEMA, "check": "rule check (code), not a reader's check",
        "claims": len(found), "cited": len(cited), "uncited": len(uncited),
        "citations": len(links), "not_read": len(not_read), "not_read_links": not_read[:20],
        "in_record": in_record, "not_in_record": not_in_record, "unsupported": unsupported[:20],
        "unfinished": unfinished, "unfinished_stated": unfinished_stated,
        "unfinished_unstated": int(unfinished and not unfinished_stated),
        "factual": factual, "other_side": other_side, "other_side_missing": int(factual and not other_side),
        "certainty": len(_CERTAIN.findall(answer or "")),
    }


def losses(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Each count on which ``after`` is worse than ``before``: a lost source or a new unsupported figure is a loss
    whatever the other counts gained (rule 2)."""
    lost = [f"{k} {before.get(k, 0)} → {after.get(k, 0)}" for k in WORSE_HIGHER
            if int(after.get(k, 0) or 0) > int(before.get(k, 0) or 0)]
    lost += [f"{k} {before.get(k, 0)} → {after.get(k, 0)}" for k in BETTER_HIGHER
             if int(after.get(k, 0) or 0) < int(before.get(k, 0) or 0)]
    return lost


def gains(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Each count on which ``after`` is better than ``before``, written before → after like ``losses``."""
    won = [f"{k} {before.get(k, 0)} → {after.get(k, 0)}" for k in WORSE_HIGHER
           if int(after.get(k, 0) or 0) < int(before.get(k, 0) or 0)]
    won += [f"{k} {before.get(k, 0)} → {after.get(k, 0)}" for k in BETTER_HIGHER
            if int(after.get(k, 0) or 0) > int(before.get(k, 0) or 0)]
    return won


UNSUPPORTED_HEADING = "**Figures to check: not found in the records cited beside them**"
MAX_MARKED = 20


def mark_unsupported(answer: str, outputs: Iterable[Any]) -> str:
    """``answer`` with each cited claim whose figure none of its cited records carries listed under it (agent-fit
    V). The claim stays as written; the list tells the reader which figures to check against their records."""
    result = score(answer, outputs)
    found = result["unsupported"]
    if not found:
        return answer
    lines = []
    for item in found[:MAX_MARKED]:
        claim = _MD_LINK.sub(lambda m: m.group(1), item["claim"]).strip()
        claim = claim if len(claim) <= 120 else claim[:117].rstrip() + "..."
        sources = ", ".join(f"[source {i}]({link})" for i, link in enumerate(item["sources"][:3], 1))
        lines.append(f"- {', '.join(item['figures'])} in \"{claim}\" ({sources}).")
    if len(found) > MAX_MARKED:
        lines.append(f"- {len(found) - MAX_MARKED} more claims have figures not found in their records.")
    return answer.rstrip() + "\n\n" + UNSUPPORTED_HEADING + "\n" + "\n".join(lines)
