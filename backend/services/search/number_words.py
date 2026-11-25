"""A phone number typed the way a person writes it, matched however the phone stored it (03 section 11.3, D-12).

Folding turns punctuation into spaces, so ``(717) 555-0221`` folds to ``717 555 0221`` and ``+17175550221`` to
``17175550221``: as plain text neither finds the other. A query that is a number (7 or more digits, and mostly
digits) is therefore also matched on its digits:

- the digits searched are the number without a leading country code or trunk zero (``+1 717 555 0221``,
  ``1-717-555-0221`` and ``0717 5550221`` all search ``7175550221``), so a number saved with or without its country
  code is found;
- a stored text matches when those digits appear in it, either together or split only by spaces in its folded
  form (``717 555 0221``); digits split by a letter or a word (``call 717 or 555 0221``) do not join.

``JOINED_SQL`` is the folded text with the spaces between digits removed. The partial trigram index
``ix_phone_texts_digits_joined`` (migration 20261125_phone_texts_digits_joined) holds it for the texts of up to 1,000
characters that have digits split by spaces, so the match reads two indexes and no table scan (measured on live 25
Nov: an optional-space regular expression took 68 s on 6.6 million texts). A longer text (a long email, a log) with
the number split by spaces is found by typing the number as it is written there, not by its bare digits: those 22,382
texts hold 700 MB, and indexing them took the build from 52 s to 4.5 minutes.
"""
from __future__ import annotations

import re

MIN_DIGITS = 7
SPLIT_SQL = "%(col)s ~ '[0-9] [0-9]' AND length(%(col)s) <= 1000"
JOINED_SQL = "regexp_replace(%(col)s, '([0-9]) (?=[0-9])', '\\1', 'g')"


def _like(s: str) -> str:
    return "%" + s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def number_digits(query: str) -> str | None:
    """The digits a number query searches, or None when the query is not a number."""
    q = (query or "").strip()
    if re.search(r"[^\W\d_]", q):  # a letter: a word, an email address or a name, not a number
        return None
    digits = re.sub(r"\D", "", q)
    if len(digits) < MIN_DIGITS or len(digits) < 0.6 * len(re.sub(r"\s", "", q)):
        return None
    national = _national(digits)
    return national if national and len(national) >= MIN_DIGITS else digits


def _national(digits: str) -> str | None:
    """The national number without its country code (by the numbering plan), or without one trunk zero."""
    if digits.startswith("0"):
        return digits.lstrip("0") or None
    if len(digits) <= 10:
        return digits
    try:
        import phonenumbers
        n = phonenumbers.parse("+" + digits, None)
    except Exception:  # not a number any plan knows: searched as typed
        return digits
    if not phonenumbers.is_possible_number(n):
        return digits
    return str(n.national_number)


def sql(col: str, query: str, param) -> str | None:
    """SQL matching a folded column against a number query, or None. ``param(value)`` names a bound parameter."""
    digits = number_digits(query)
    if not digits:
        return None
    p = param(_like(digits))
    c = {"col": col}
    return "(%s LIKE %s OR (%s AND %s LIKE %s))" % (col, p, SPLIT_SQL % c, JOINED_SQL % c, p)


def joined(folded: str) -> str:
    """Python mirror of ``JOINED_SQL`` (tests and snippets)."""
    return re.sub(r"(\d) (?=\d)", r"\1", folded or "")


def span(original: str, digits: str):
    """``(start, end)`` in ``original`` of the first run holding ``digits``, the digits split only by characters that
    are not letters (as folding treats them); None when absent."""
    if not original or not digits:
        return None
    run_digits, run_at = [], []

    def find():
        at = "".join(run_digits).find(digits)
        return (run_at[at], run_at[at + len(digits) - 1] + 1) if at >= 0 else None

    for i, ch in enumerate(original):
        if ch.isdigit():
            run_digits.append(ch)
            run_at.append(i)
        elif ch.isalpha():
            hit = find()
            if hit:
                return hit
            run_digits, run_at = [], []
    return find()
