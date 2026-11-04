"""The strength of a count-based phone analysis result (approaches 4 and 5; Neil 2026-11-04: "We don't want to miss
things based on an arbitrary cutoff").

Results that rest on how many timed records back them (read times, reply pairs, quarter hours two phones were placed
in) are graded on the app's one scale, strong, moderate, weak and faint (``money_pairings.LEVELS``), by a stated rule;
no model sets a strength. Two parts, as on every graded match:

- **substantiation**: how many records back the result. 2 at or above the approach's ``well`` count, 1 at or above
  its ``some`` count, else 0. The counts are rules of thumb: no measured error rate stands behind them, and the
  screens say so (``RULE_OF_THUMB``).
- **fit**: how firmly each record says what the result needs. 2 when it does so directly (a reviewed or applied
  mapping, a stated radius), 1 when it rests on an assumption (generic interpretation, an assumed radius), 0 when
  neither.

Level: strong when both are 2; moderate when both are at least 1; weak when either is at least 1; faint otherwise.
A result is never dropped for its level: one record gives a weak or faint result, listed as such.
"""
from __future__ import annotations

from services.phone_analysis.money_pairings import LEVEL_WORDS, LEVELS  # noqa: F401 (the shared scale)

RULE_OF_THUMB = "rule of thumb, no measurement behind it"
MAPPED_LEVELS = ("reviewed", "applied_unconfirmed")


def substantiation(n: int, some: int, well: int) -> int:
    return 2 if n >= well else 1 if n >= some else 0


def level(subst: int, fit: int) -> str:
    if subst >= 2 and fit >= 2:
        return "strong"
    if subst >= 1 and fit >= 1:
        return "moderate"
    if subst >= 1 or fit >= 1:
        return "weak"
    return "faint"


def fit_of_levels(levels) -> int:
    """2 when every record was read through a reviewed or applied mapping, 1 when any was read generically, 0 when
    none was interpreted."""
    levels = [x for x in levels if x]
    if not levels:
        return 0
    if all(x in MAPPED_LEVELS for x in levels):
        return 2
    return 1 if any(x in MAPPED_LEVELS or x == "generic" for x in levels) else 0


def reasons(n: int, noun: tuple, some: int, well: int, fit: int, fit_words: dict) -> str:
    """The plain reason for a grade: the count against the rule-of-thumb counts, and the fit."""
    s = substantiation(n, some, well)
    count = "%d %s" % (n, noun[0] if n == 1 else noun[1])
    against = ("at least %d" % well if s == 2 else "at least %d, under %d" % (some, well) if s == 1
               else "under %d" % some)
    return "%s: %s. %s (%s counts: %d some, %d well; %s)." % (
        LEVEL_WORDS[level(s, fit)], count, fit_words[fit], against, some, well, RULE_OF_THUMB)


def counts(items) -> dict:
    """``{level: n}`` over every level, zeros included."""
    out = {lv: 0 for lv in LEVELS}
    for it in items:
        if it in out:
            out[it] += 1
    return out
