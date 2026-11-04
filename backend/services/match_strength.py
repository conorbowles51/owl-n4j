"""One strength scale for every possible match the app shows (Neil 2026-11-04: "If there are any payment matches at
all they should be mentioned. With a signal strength showing the user how well matched something is and how heavily
substantiated. We don't want to miss things based on an arbitrary cutoff.").

The levels, their words and the level rule are the ones of phone money pairings
(:mod:`services.phone_analysis.money_pairings`, 05 4.3.8), so a payment pair, a matched-payment name and a phone
identity suggestion read on the same scale: strong, moderate, weak, faint. A rule computes each strength from stated
fits; no model sets one. Each candidate carries plain reasons in two parts: how well it is matched, and what
substantiates it.

A candidate is never dropped for falling under a level: a weak match is listed as weak and a faint one as faint. A
search bound kept for cost is stated with the count it leaves out (:func:`left_out_words`).
"""
from __future__ import annotations

from services.phone_analysis.money_pairings import LEVEL_WORDS, LEVELS, level  # noqa: F401 (the shared scale)

SCALE_WORDS = ("Strength is set by a stated rule, never by a model: how well the two sides match (amount, date, "
               "name or identifier) and how many independent sources substantiate it. Strong, moderate, weak and "
               "faint matches are all listed, strongest first; weak and faint ones are possibilities to check, not "
               "findings.")


def rank(lv: str) -> int:
    """0 for strong ... 3 for faint (sort ascending, strongest first)."""
    return LEVELS.index(lv)


def counts(items, key="level") -> dict:
    """``{level: n}`` over every level, zeros included."""
    out = {lv: 0 for lv in LEVELS}
    for it in items:
        out[it[key]] = out.get(it[key], 0) + 1
    return out


def counts_words(by_level: dict) -> str:
    parts = ["%d %s" % (by_level.get(lv, 0), lv) for lv in LEVELS if by_level.get(lv)]
    return ", ".join(parts) if parts else "none"
