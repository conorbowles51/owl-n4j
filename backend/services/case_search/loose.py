"""Loose words (lx-searchfix A): a question's words matched the way records are written, not only as typed.

Each search term becomes a group of forms, and a record holds the term when it holds any form:
- the word as typed, and its stem, so a plural or another ending finds the word ("deposits" finds "deposit",
  "towing" finds "tow");
- the abbreviations bank statements print for it ("checks" finds "CHK", "branch" finds "BR", "transfer" finds
  "TFR"). An abbreviation matches only as a whole word: "br" does not match "brown";
- a possessive is read as the name ("Penn's" finds "PENN'S", folded "penn s").

Words every ledger row holds as a matter of course ("payment", "money", "transaction") are dropped when the question
has other words: on their own they would rank every row of the ledger alike. Measured on the demo case, 17 Nov:
"cash deposits at a branch" found 0 of 3 rows by every word as typed ("CASH DEPOSIT BR 014 FENWICK").

Exact matching stays available: ``exact`` on the agent's tools searches the words as typed.
"""
from __future__ import annotations

import re

from services.phone import fold as F

# word (or its stem) -> what statements print for it; whole-word matches only
ABBREVIATIONS: dict[str, tuple[str, ...]] = {
    "check": ("chk", "chq", "ck", "cheque"),
    "cheque": ("chq", "chk", "check"),
    "deposit": ("dep", "dpst"),
    "branch": ("br", "brch"),
    "payment": ("pmt", "pymt", "paymt"),
    "transfer": ("tfr", "trf", "xfer", "trsf"),
    "withdrawal": ("wd", "wdl", "wthdrwl", "withdraw"),
    "withdraw": ("wd", "wdl", "withdrawal"),
    "purchase": ("pur", "purch", "pos"),
    "mobile": ("mob", "mbl"),
    "account": ("acct", "acc"),
    "international": ("intl",),
    "interest": ("int",),
    "online": ("onl",),
    "service": ("svc", "srv"),
    "hospital": ("hosp",),
    "medical": ("med",),
    "insurance": ("ins",),
    "refund": ("rfnd",),
    "direct": ("dir",),
    "debit": ("dbt", "dr"),
    "credit": ("cr", "cdt"),
    "reversal": ("rev",),
    "rent": ("rnt",),
    "storage": ("stor", "stg"),
    "invoice": ("inv",),
    "towing": ("tow",),
    "tow": ("towing",),
    "street": ("st",),
    "company": ("co",),
    "corporation": ("corp",),
    "incorporated": ("inc",),
    "limited": ("ltd",),
    "wire": ("wt",),
    "cash": ("csh",),
}

# Every ledger row's text says it is a payment of money; on their own these words rank every row alike.
GENERIC = frozenset({"payment", "payments", "paid", "pay", "paying", "transaction", "transactions", "money",
                     "amount", "amounts"})

_SUFFIXES = (("ies", "y"), ("sses", "ss"), ("ches", "ch"), ("shes", "sh"), ("xes", "x"), ("ing", ""), ("ed", ""),
             ("es", "e"), ("s", ""))


def stem(word: str) -> str:
    """A light English stem: plural and common endings off, never shorter than three letters ("deposits" ->
    "deposit", "copies" -> "copy", "towing" -> "tow"). A word ending in "ss" keeps it ("glass")."""
    w = word.casefold()
    if len(w) <= 3 or any(ch.isdigit() for ch in w):
        return w
    if w.endswith("ss"):
        return w
    for suf, rep in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) + len(rep) >= 3:
            base = w[: len(w) - len(suf)] + rep
            # "-ing"/"-ed" after a doubled letter: "stopped" -> "stop"
            if suf in ("ing", "ed") and len(base) >= 4 and base[-1] == base[-2] and base[-1] not in "lsz":
                base = base[:-1]
            return base
    return w


def forms(term: str) -> dict[str, list[str]]:
    """The forms one term is matched by: ``inside`` (found anywhere in a word or across words: the term and its
    stem) and ``whole`` (whole words only: abbreviations)."""
    t = F.fold(term)
    if not t:
        return {"inside": [], "whole": []}
    inside = [t]
    if " " not in t:
        s = stem(t)
        if s != t:
            inside.append(s)
    whole: list[str] = []
    for key in dict.fromkeys([t] + inside):
        for a in ABBREVIATIONS.get(key, ()):
            # a long abbreviation (cheque, towing) is found inside words like the term itself
            (inside if len(a) >= 5 else whole).append(a)
    return {"inside": list(dict.fromkeys(inside)), "whole": [w for w in dict.fromkeys(whole) if w not in inside]}


def groups(terms: list[str]) -> list[dict]:
    """The question's terms (``chat_retrieval.terms``) as loose groups: generic money words dropped while another
    word remains. Each group: ``term`` (as the question gives it), ``inside`` and ``whole`` forms."""
    kept = [t for t in terms if F.fold(t) not in GENERIC] or list(terms)
    out = []
    for t in kept:
        f = forms(t)
        if f["inside"] or f["whole"]:
            out.append({"term": t, **f})
    return out


def holds(body_folded: str, group: dict) -> bool:
    """Whether folded text holds a group (the same rule the database query applies)."""
    padded = " %s " % (body_folded or "")
    return any(f in padded for f in group["inside"]) or any(" %s " % w in padded for w in group["whole"])


_WORDS = re.compile(r"\S+")


def described(gs: list[dict]) -> str:
    """The forms searched, for the result's notes: "deposits (deposit, dep), branch (br)"."""
    parts = []
    for g in gs:
        extra = [f for f in g["inside"] + g["whole"] if f != F.fold(g["term"])]
        parts.append("%s (%s)" % (g["term"], ", ".join(extra)) if extra else g["term"])
    return ", ".join(parts)
