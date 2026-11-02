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
