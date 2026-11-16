"""Exact checks of an answer's own shape (lx-deepinvest B). Each finds a defect that was seen in a live report and
that no reader should meet: a sentence with a name missing, a section printed twice, a contents list that does not
match the sections. Deterministic; the writer is asked once to repair what is found, and what remains is said.
"""
from __future__ import annotations

import re

_HEADING = re.compile(r"^\s{0,3}(#{1,4})\s+(.+?)\s*#*\s*$|^\s*\*\*(.+?)\*\*\s*:?\s*$", re.M)
_NUMBER = re.compile(r"^\s*(?:section\s+)?\d+[.)]?\s+")
_CONTENTS = re.compile(r"^\s{0,3}(?:#{1,4}\s+)?\**(contents|table of contents)\**\s*:?\s*$", re.I | re.M)
_ITEM = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.+?)\s*$")

# A gap where a name or label stood: "appear on and .", "between and", "( )", "[]( )", ", ,".
_GAPS = (
    (re.compile(r"\b(?:on|with|from|to|between|by|of|for|at)\s+(?:and|or)\s+(?=[\w.,;])", re.I), "a name is missing before 'and'"),
    (re.compile(r"\b(?:and|or)\s+[.,;:](?=\s|$)", re.I), "a name is missing after 'and'"),
    (re.compile(r"\b(?:on|with|from|to|by|of|for|at)\s+[.,;:](?=\s|$)", re.I), "a name is missing after a preposition"),
    (re.compile(r"\(\s*[,;]?\s*\)"), "empty brackets"),
    (re.compile(r"\[\s*\]\([^)]*\)"), "a link with no text"),
    (re.compile(r",\s*,"), "two commas in a row"),
)


def _norm(title: str) -> str:
    title = re.sub(r"[*_`#]+", "", title)
    title = _NUMBER.sub("", title)
    return re.sub(r"\s+", " ", title).strip(" :.-").casefold()


def headings(text: str) -> list[tuple[int, str]]:
    out = []
    for m in _HEADING.finditer(text or ""):
        level = len(m.group(1)) if m.group(1) else 5
        title = m.group(2) or m.group(3) or ""
        out.append((level, title))
    return out


def dropped_names(text: str) -> list[str]:
    found = []
    body = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", body):
        for rx, why in _GAPS:
            if rx.search(sentence):
                found.append("%s: \"%s\"" % (why, sentence.strip()[:120]))
                break
    return found


def duplicate_sections(text: str) -> list[str]:
    seen: dict[str, int] = {}
    for _, title in headings(text):
        key = _norm(title)
        if key and key not in ("contents", "table of contents"):
            seen[key] = seen.get(key, 0) + 1
    return ["section printed %d times: \"%s\"" % (n, k) for k, n in seen.items() if n > 1]


def contents_mismatch(text: str) -> list[str]:
    """When the answer has a contents list: every entry names a section and every top section is in the list."""
    m = _CONTENTS.search(text or "")
    if not m:
        return []
    entries = []
    for line in (text[m.end():] or "").split("\n")[1:]:
        if not line.strip():
            if entries:
                break
            continue
        item = _ITEM.match(line)
        if not item:
            break
        entries.append(item.group(1))
    if not entries:
        return []
    listed = {_norm(re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", e)) for e in entries}
    tops = [t for lv, t in headings(text) if lv <= 2 and _norm(t) not in ("contents", "table of contents")]
    sections = {_norm(t) for t in tops}
    out = ["contents lists a section that is not in the report: \"%s\"" % e for e in sorted(listed - sections) if e]
    out += ["the report has a section the contents does not list: \"%s\"" % t for t in tops if _norm(t) not in listed]
    return out


def defects(text: str) -> list[str]:
    return dropped_names(text) + duplicate_sections(text) + contents_mismatch(text)


def repair_request(found: list[str]) -> str:
    return ("The answer has these defects. Rewrite the answer in full, repairing each: put the missing name or phone "
            "label back in its sentence (take it from the notes and results already given; if it is not known, "
            "rewrite the sentence so it does not need it), print each section once, and make the contents match the "
            "sections. Keep every citation and every fact.\n- " + "\n- ".join(found[:20]))
