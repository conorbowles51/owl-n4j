"""Incident dates for the preset windows (lx-corrorest E): the dates a theory or finding states in its own words.

Only a date written in the text is read: "2026-05-03", "3 May 2026" or "May 3, 2026", with a time when one follows it
("21:30"). Each comes back with the words it was read from and the entry it is in, so the person sees where a window
comes from. A date with no time cannot anchor a window of hours; the screen says so and offers days and weeks.
"""
from __future__ import annotations

import re
from datetime import date

from sqlalchemy import text

MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"])}
_M = "|".join(MONTHS) + "|" + "|".join(k[:3] for k in MONTHS)
_TIME = r"(?:(?:\s+at|,|\s)\s*([01]?\d|2[0-3]):([0-5]\d))?"
_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b" + _TIME), "ymd"),
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + _M + r")\.?,?\s+(\d{4})\b" + _TIME, re.I), "dmy"),
    (re.compile(r"\b(" + _M + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b" + _TIME, re.I), "mdy"),
]


def dates_in_text(body: str) -> list[dict]:
    """Every distinct stated date (and time) in the text, in the order written, with the words it came from."""
    found: list[tuple[int, dict]] = []
    for pattern, order in _PATTERNS:
        for m in pattern.finditer(body or ""):
            g = m.groups()
            try:
                if order == "ymd":
                    d = date(int(g[0]), int(g[1]), int(g[2]))
                elif order == "dmy":
                    d = date(int(g[2]), MONTHS[_month(g[1])], int(g[0]))
                else:
                    d = date(int(g[2]), MONTHS[_month(g[0])], int(g[1]))
            except (ValueError, KeyError):
                continue
            time = f"{int(g[3]):02d}:{g[4]}" if g[3] is not None else None
            found.append((m.start(), {"date": d.isoformat(), "time": time, "words": m.group(0).strip()}))
    out, seen = [], set()
    for _, hit in sorted(found, key=lambda x: x[0]):
        key = (hit["date"], hit["time"])
        if key not in seen:
            seen.add(key)
            out.append(hit)
    return out


def _month(word: str) -> str:
    w = word.lower()
    return w if w in MONTHS else next(k for k in MONTHS if k.startswith(w[:3]))


def incident_dates(db, case_id) -> list[dict]:
    """Dates stated in this case's live theories and findings. Each: date, time or None, words, entry id, title."""
    rows = db.execute(text(
        "SELECT id, entry_type, title, body FROM workspace_entries "
        "WHERE case_id = :c AND deleted_at IS NULL AND entry_type IN ('theory', 'finding') ORDER BY created_at"),
        {"c": str(case_id)}).mappings().all()
    out = []
    for r in rows:
        for hit in dates_in_text(f"{r['title'] or ''}. {r['body'] or ''}"):
            out.append({**hit, "entry_id": str(r["id"]), "entry_type": r["entry_type"], "title": r["title"] or ""})
    return out
