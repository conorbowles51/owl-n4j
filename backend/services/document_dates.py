"""Read dates from a document's own text, by rules.

Every date found is a *reading*: the kind (written, signed, period, received), the value, the words it came from and
the page. It is shown as "Read by Loupe · not confirmed" until a person confirms it. A bare date with no cue word
(a transaction line, a birth date) is not read. A numeric date such as 03/04/2026 is read only when one part is
above 12, so it has one meaning; otherwise it is skipped, never guessed.
"""
from __future__ import annotations

import re
from datetime import date

RULE_SET = "docdates-rules-1"  # the second pass's readings carry "+2" on their rule; the first pass's are unchanged
MIN_YEAR, MAX_YEAR = 1950, 2030

_MONTHS = {
    "jan": 1, "january": 1, "ene": 1, "enero": 1, "feb": 2, "february": 2, "febrero": 2, "mar": 3, "march": 3,
    "marzo": 3, "mzo": 3, "apr": 4, "april": 4, "abr": 4, "abril": 4, "may": 5, "mayo": 5, "jun": 6, "june": 6,
    "junio": 6, "jul": 7, "july": 7, "julio": 7, "aug": 8, "august": 8, "ago": 8, "agosto": 8, "sep": 9, "sept": 9,
    "september": 9, "septiembre": 9, "oct": 10, "october": 10, "octubre": 10, "nov": 11, "november": 11,
    "noviembre": 11, "dec": 12, "december": 12, "dic": 12, "diciembre": 12,
}
_MON = "|".join(sorted(_MONTHS, key=len, reverse=True))

_ISO = r"(?P<iy>\d{4})-(?P<im>\d{2})-(?P<id>\d{2})"
_DMY_WORD = rf"(?P<dd>\d{{1,2}})(?:st|nd|rd|th)?\s+(?:de\s+)?(?P<dm>{_MON})\.?,?\s+(?:de\s+)?(?P<dy>\d{{4}})"
_MDY_WORD = rf"(?P<mm>{_MON})\.?\s+(?P<md>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<my>\d{{4}})"
_NUM = r"(?P<na>\d{1,2})[/.](?P<nb>\d{1,2})[/.](?P<ny>\d{4})"
_NUM2 = r"(?P<na>\d{1,2})[/.](?P<nb>\d{1,2})[/.](?P<ny>\d{4}|\d{2})"  # second pass: a two-digit year after a cue only
_DATE = re.compile(rf"\b(?:{_ISO}|{_DMY_WORD}|{_MDY_WORD}|{_NUM})\b", re.I)
_DATE2 = re.compile(rf"\b(?:{_ISO}|{_DMY_WORD}|{_MDY_WORD}|{_NUM2})\b", re.I)

# cue words read in the 70 characters before a date (or the two dates of a period)
_CUES = [
    ("period", re.compile(r"(period[oe]?|statement period|billing period|del\b|from\b|desde)\s*(?:[:\-]\s*)?$", re.I)),
    ("received", re.compile(r"(received|recibid[oa]|date received|fecha de recepci[oó]n|fecha de recibo)\s*(?:on|:|-)?\s*$", re.I)),
    ("signed", re.compile(r"(signed|sworn|firmad[oa]|executed|subscribed|notar\w*)\b[^.\n]{0,40}$", re.I)),
    ("written", re.compile(
        r"(dated?|invoice date|date of issue|issued|fecha de (?:corte|expedici[oó]n|emisi[oó]n|elaboraci[oó]n)|"
        r"fecha|sent|date|emitido|statement date)\s*(?:on|:|-)?\s*$", re.I)),
]
# The second pass (17 Nov, CM1's lab, fire and custodian forms) reads only a kind the first pass found nothing for, so
# no reading the first pass makes ever changes: measured over 35,984 live texts, letting these cues compete changed 171
# readings to other dates.
_CUES2 = [
    _CUES[0], _CUES[1],
    ("signed", re.compile(r"((signed|sworn|firmad[oa]|executed|subscribed|notar\w*)\b[^.\n]{0,40}|"
                          r"(?:foregoing|above) is true and correct\.?\s*)$", re.I)),
    ("written", re.compile(
        r"(dated?|invoice date|date of issue|issued|fecha de (?:corte|expedici[oó]n|emisi[oó]n|elaboraci[oó]n)|"
        r"fecha|sent|date|emitido|statement date|date of (?:report|letter)|report date)\s*(?:on|[:=-])?\s*=?\s*$",
        re.I)),
    # an incident report's own date: "Reported Saturday 16 March 2024 at 06:10" (the demo case's police reports, 18 Nov)
    ("written", re.compile(r"\breported\s+(?:on\s+)?(?:(?:mon|tues|wednes|thurs|fri|satur|sun)day,?\s+)?$", re.I)),
]
_PERIOD_TO = re.compile(r"^\s*(?:al|to|through|thru|-|–|a|hasta)\s+$", re.I)
_EMAIL_STAMP = re.compile(r"^\s*(?:at\s+)?\d{1,2}:\d{2}\s*[AP]M", re.I)
# a cue that names a different date ("payment due date", "contract date", "birth date") is not the document's date
_OTHER_DATE = re.compile(r"(due|contract|birth|expir\w*|maturity|opening|effective|payment|start|closing|issue\s+of)\s+$", re.I)
_HEAD_LABELS = {"transcript", "recording", "statement", "for", "time"}
_HEAD = 700


def _to_date(m: re.Match, day_first: bool | None = None) -> date | None:
    g = m.groupdict()
    try:
        if g["iy"]:
            d = date(int(g["iy"]), int(g["im"]), int(g["id"]))
        elif g["dd"]:
            d = date(int(g["dy"]), _MONTHS[g["dm"].lower()], int(g["dd"]))
        elif g["mm"]:
            d = date(int(g["my"]), _MONTHS[g["mm"].lower()], int(g["md"]))
        else:
            a, b, y = int(g["na"]), int(g["nb"]), int(g["ny"])
            if len(g["ny"]) == 2:
                y += 2000 if y < 50 else 1900
            if day_first is not None and a <= 12 and b <= 12:
                d = date(y, b, a) if day_first else date(y, a, b)
            elif a > 12 and b <= 12:
                d = date(y, b, a)
            elif b > 12 and a <= 12:
                d = date(y, a, b)
            else:
                return None
    except ValueError:
        return None
    return d if MIN_YEAR <= d.year <= MAX_YEAR else None


def _bare_head_ok(before: str) -> bool:
    """A date at the head of the page, standing alone or after a label word such as "Transcript"."""
    tail = before.rstrip()
    if not tail or re.search(r"[\d]$", tail):
        return False
    if not tail[-1].isalpha():
        return True
    return re.split(r"\W+", tail)[-1].lower() in _HEAD_LABELS


def _page(locs: list | None, at: int) -> int | None:
    for loc in locs or []:
        try:
            if loc.get("start_char", 0) <= at <= loc.get("end_char", -1):
                return loc.get("page_number")
        except AttributeError:
            return None
    return None


def _words(text: str, start: int, end: int) -> str:
    a, b = max(0, start - 40), min(len(text), end + 20)
    return re.sub(r"\s+", " ", text[a:b]).strip()


def _pair_dates(m1: re.Match, m2: re.Match) -> tuple[date, date] | None:
    """Both ends of a period. Numeric ends that are each ambiguous are read in the order the unambiguous end
    shows (``01/08/2026 AL 31/08/2026`` is day first)."""
    a, b = _to_date(m1), _to_date(m2)
    if a and b:
        return a, b
    order = None
    for m in (m1, m2):
        g = m.groupdict()
        if g["na"]:
            if int(g["na"]) > 12:
                order = True
            elif int(g["nb"]) > 12:
                order = False
    if order is None:
        return None
    a, b = _to_date(m1, order), _to_date(m2, order)
    return (a, b) if a and b else None


def read_dates(text: str, source_locations: list | None = None, limit: int = 6) -> list[dict]:
    """Readings from ``text``: dicts with kind, date_from, date_to, rule, words, page. At most one per kind
    (the first in the document), at most ``limit`` in all. A kind the first pass finds nothing for is then read by the
    second pass's cues (rule ending "+2"), never replacing a first-pass reading."""
    found = _read(text, source_locations, _DATE, _CUES, second=False)
    for kind, reading in _read(text, source_locations, _DATE2, _CUES2, second=True).items():
        if kind not in found:
            found[kind] = {**reading, "rule": reading["rule"] + "+2"}
    return list(found.values())[:limit]


def _read(text: str, source_locations, date_rx, cues, *, second: bool) -> dict:
    found: dict[str, dict] = {}
    hits = list(date_rx.finditer(text or ""))
    i = 0
    while i < len(hits):
        m = hits[i]
        before = text[max(0, m.start() - 70):m.start()]
        pair = None
        if i + 1 < len(hits) and _PERIOD_TO.match(text[m.end():hits[i + 1].start()]):
            pair = _pair_dates(m, hits[i + 1])
        if pair and pair[1] > pair[0]:
            if not second and "period" not in found and re.search(r"period|periodo|per.odo|statement|estado de cuenta|del\s*$|from\s*$", before, re.I):
                found["period"] = {"kind": "period", "date_from": pair[0], "date_to": pair[1], "rule": "period-range",
                                   "words": _words(text, m.start(), hits[i + 1].end()),
                                   "page": _page(source_locations, m.start())}
            i += 2
            continue
        d = _to_date(m)
        i += 1
        if not d:
            continue
        kind = next((k for k, rx in cues if rx.search(before)), None)
        if kind is None and len(m.group("ny") or "") == 2:
            continue  # "3/14/26" alone could be anything; after "Date:" it is a date
        rule = f"cue-{kind}" if kind else ""
        if kind == "written":
            cue = cues[3][1].search(before)
            if cue and _OTHER_DATE.search(before[:cue.start()]):
                continue
        if second:
            if kind is None or kind == "period":
                continue  # the second pass reads by its cues only; the head rules are the first pass's
        elif kind is None and m.start() < _HEAD and _EMAIL_STAMP.match(text[m.end():m.end() + 14]):
            kind, rule = "written", "head-date-with-time"
        elif kind is None and m.start() < 250 and not m.group("iy") and _bare_head_ok(before):
            kind, rule = "written", "head-date"
        if kind and kind != "period" and kind not in found:
            found[kind] = {"kind": kind, "date_from": d, "date_to": d, "rule": rule,
                           "words": _words(text, m.start(), m.end()), "page": _page(source_locations, m.start())}
    return found
