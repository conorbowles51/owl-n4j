"""Name folding shared by phone search and identity (02 section 8.4; 03 section 11.3).

``fold(text, exact=False)``:

1. NFKC (mathematical alphanumerics, fullwidth, circled, superscript and modifier letters to plain letters);
2. the styled letters NFKC leaves alone (``data/styled_letters.json``: negative circled and squared capitals,
   regional indicators, Latin small capitals) to A to Z;
3. inside a token that mixes Latin with Cyrillic or Greek letters, Cyrillic and Greek letters that UTS #39
   lists as confusable with one ASCII letter become that letter (``data/confusables_latin.json``); a token
   wholly in Cyrillic or Greek is left alone;
4. format and control characters removed (Cf, Cc), except ZERO WIDTH SPACE, which becomes a space;
5. unless ``exact``: NFD, combining marks (Mn) dropped, NFC;
6. ``casefold()``;
7. anything that is not a letter, digit or mark becomes a space; whitespace collapsed and trimmed.

``exact=True`` applies steps 4 and 6 only. Python 3.10 syntax; every table entry exists in Unicode 13.0.
"""
from __future__ import annotations

import functools
import json
import os
import re
import unicodedata

_DATA = os.path.join(os.path.dirname(__file__), "data")


def _load(name):
    path = os.path.join(_DATA, name)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    return {chr(int(k, 16)): v for k, v in doc["map"].items()}


STYLED = _load("styled_letters.json")
CONFUSABLE = _load("confusables_latin.json")
_WS = re.compile(r"\s+")


def _script(ch):
    if not ch.isalpha():
        return None
    name = unicodedata.name(ch, "")
    if name.startswith("LATIN"):
        return "latin"
    if name.startswith("CYRILLIC"):
        return "cyrillic"
    if name.startswith("GREEK"):
        return "greek"
    return "other"


def _confusables(text):
    if not CONFUSABLE:
        return text
    out = []
    for token in re.split(r"(\s+)", text):
        scripts = {_script(c) for c in token}
        if "latin" in scripts and scripts & {"cyrillic", "greek"}:
            token = "".join(CONFUSABLE.get(c, c) if _script(c) in ("cyrillic", "greek") else c for c in token)
        out.append(token)
    return "".join(out)


WORD_BREAKS = {"\u200b": " "}  # ZERO WIDTH SPACE marks a word break: a space, not nothing (8.4 test vector)


def _strip_format(text):
    return "".join(WORD_BREAKS.get(c, c) for c in text
                   if c in WORD_BREAKS or unicodedata.category(c) not in ("Cf", "Cc") or c in "\t\n\r")


def fold(text, exact=False):
    if text is None:
        return ""
    if exact:
        return _strip_format(text).casefold()
    s = unicodedata.normalize("NFKC", text)
    s = "".join(STYLED.get(c, c) for c in s)
    s = _confusables(s)
    s = _strip_format(s)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = unicodedata.normalize("NFC", s)
    s = s.casefold()
    s = "".join(c if (c.isalnum() or unicodedata.category(c).startswith("M")) else " " for c in s)
    return _WS.sub(" ", s).strip()


@functools.lru_cache(maxsize=65536)
def _styled(ch):
    """Steps 1 and 2 for one character."""
    return "".join(STYLED.get(c, c) for c in unicodedata.normalize("NFKC", ch))


@functools.lru_cache(maxsize=65536)
def _rest(s):
    """Steps 4 to 7 for one character's piece (whitespace collapsing is done over the whole text)."""
    s = _strip_format(s)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = unicodedata.normalize("NFC", s).casefold()
    return "".join(c if (c.isalnum() or unicodedata.category(c).startswith("M")) else " " for c in s)


def fold_with_map(text, exact=False):
    """``fold`` worked one original character at a time, with where each folded character came from.

    Returns ``(folded, starts)``: ``starts[j]`` is the index in ``text`` of the character that produced
    ``folded[j]``, so a match at ``folded[a:b]`` is ``text[starts[a]:starts[b - 1] + 1]`` in the original
    (03 section 11.3: highlights and citations point at the original characters). The steps and their order are
    ``fold``'s; the only difference is that compositions across characters (Hangul conjoining jamo) are not made.
    Document search folds both the query and the text with this function, so the two always agree.
    """
    if not text:
        return "", []
    pieces = []  # (original index, folded piece) before whitespace is collapsed
    if exact:
        for i, ch in enumerate(text):
            pieces.append((i, _strip_format(ch).casefold()))
    else:
        styled = [_styled(ch) for ch in text]
        if CONFUSABLE:  # step 3 by token, a token being a run of characters that are not whitespace after step 2
            i = 0
            while i < len(text):
                if styled[i].isspace() or not styled[i]:
                    i += 1
                    continue
                j = i
                while j < len(text) and not (styled[j].isspace()) and (styled[j] or j == i):
                    j += 1
                scripts = {_script(c) for k in range(i, j) for c in styled[k]}
                if "latin" in scripts and scripts & {"cyrillic", "greek"}:
                    for k in range(i, j):
                        styled[k] = "".join(CONFUSABLE.get(c, c) if _script(c) in ("cyrillic", "greek") else c
                                            for c in styled[k])
                i = j
        for i, s in enumerate(styled):
            pieces.append((i, _rest(s)))
    out, starts = [], []
    for i, s in pieces:
        for c in s:
            if not exact and c.isspace():
                if not out or out[-1] == " ":
                    continue  # leading and repeated whitespace collapse into one space
                c = " "
            out.append(c)
            starts.append(i)
    if not exact and out and out[-1] == " ":
        out.pop()
        starts.pop()
    return "".join(out), starts


def pack_map(starts):
    """``starts`` as breakpoints ``[j0, d0, j1, d1, ...]``: from ``j_k`` on, ``starts[j] = j + d_k``. Plain text
    folds one to one, so a document's map is a small fraction of its length."""
    out, last = [], None
    for j, i in enumerate(starts):
        d = i - j
        if d != last:
            out += [j, d]
            last = d
    return out


def original_span(packed, a, b):
    """The original ``[start, end)`` of the folded span ``[a, b)`` from a packed map."""
    def at(j):
        d = 0
        lo, hi = 0, len(packed) // 2 - 1
        while lo <= hi:  # the last breakpoint at or before j
            mid = (lo + hi) // 2
            if packed[2 * mid] <= j:
                d, lo = packed[2 * mid + 1], mid + 1
            else:
                hi = mid - 1
        return j + d
    return at(a), at(b - 1) + 1
