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


@functools.lru_cache(maxsize=65536)
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
    out, starts = [], []
    for piece, at in iter_fold_with_map(text, exact):
        out.append(piece)
        starts.extend(at)
    return "".join(out), starts


FOLD_CHUNK = 4096
_TOKEN = re.compile(r"[^ ]+")


def _ascii_tables():
    """Each ASCII character's fold, taken from the steps themselves (no step joins ASCII characters, and step 3
    needs a Cyrillic or Greek letter), as ``str.translate`` tables, with the characters that fold to nothing. None
    when an ASCII character folds to anything but one character or nothing, so the fast path is never wrong."""
    fold_t, exact_t, drops = {}, {}, []
    for i in range(128):
        ch = chr(i)
        f, e = _rest(_styled(ch)), _strip_format(ch).casefold()
        if len(f) > 1 or len(e) > 1 or (f == "") != (e == "") or (f.isspace() and f != " "):
            return None
        if f == "":
            drops.append(ch)
        fold_t[i], exact_t[i] = f, e
    return fold_t, exact_t, re.compile("[%s]" % re.escape("".join(drops))) if drops else None


_ASCII = _ascii_tables()
_SLOW_CHAR = re.compile("[^\\x00-\\x7f]|%s" % _ASCII[2].pattern if _ASCII and _ASCII[2] else "[^\\x00-\\x7f]")
_ASCII_WS = re.compile("[ \\t\\n\\r\\x0b\\x0c]")
_UWS = re.compile(r"\s")  # a cut is only ever made at one of these, and only where steps 1 and 2 keep it whitespace
_DROP_DEL = {i: None for i in range(128) if _ASCII and _ASCII[0][i] == ""}  # deletes the characters that fold to nothing
SLOW_SHARE = 64  # a piece with more than one slow character in this many goes through the steps whole


def _cut_after(text, b):
    """The first index at or after ``b`` whose character is whitespace after steps 1 and 2: no token of step 3
    crosses it, so the text can be folded either side of it separately."""
    while True:
        m = _UWS.search(text, b)
        if m is None:
            return len(text)
        if _styled(m.group()).isspace():
            return m.start()
        b = m.end()


def iter_fold_with_map(text, exact=False, chunk=None):
    """``fold_with_map`` in pieces of about ``chunk`` original characters, each ``(folded piece, starts)``.

    Joined, the pieces are exactly ``fold_with_map(text)``, and a piece once given never changes, so a caller
    looking for the first match can stop at the piece that completes it instead of folding a long text whole
    (search snippets of long emails). Cuts fall on whitespace (any place when ``exact``), where no step joins
    characters; a whitespace run is given as its one space only when a later character follows it, so a trailing
    space is never given. Words of plain ASCII are folded by a table taken from the steps; any other word goes
    through the steps one character at a time.
    """
    if not text:
        return
    chunk = chunk or FOLD_CHUNK
    n, a = len(text), 0
    st = [False, None]  # anything given yet; the index of a collapsed space not yet given
    while a < n:
        b = min(n, a + chunk)
        if not exact:
            b = _cut_after(text, b)
        out, starts = [], []
        seg = text[a:b]
        if _ASCII is None:
            _slow(seg, a, exact, st, out, starts)
        elif seg.isascii() and not (_ASCII[2] and _ASCII[2].search(seg)):
            _fast(seg, a, exact, st, out, starts)
        elif (len(seg) - len(seg.translate(_DROP_DEL).encode("ascii", "ignore"))) * SLOW_SHARE > len(seg):
            _slow(seg, a, exact, st, out, starts)  # mostly accented, non-Latin or dropped characters
        else:
            # words with a character outside the table go through the steps; the rest through the table. A word
            # here runs between ASCII whitespace, so it holds whole tokens of step 3.
            p = 0
            for m in _SLOW_CHAR.finditer(seg):
                if m.start() < p:
                    continue  # inside a word already folded
                s0, e0 = m.start(), m.end()
                if not exact:
                    s0 = max([p] + [seg.rfind(c, p, s0) + 1 for c in " \t\n\r\x0b\x0c"])
                    w = _ASCII_WS.search(seg, e0)
                    e0 = w.start() if w else len(seg)
                if s0 > p:
                    _fast(seg[p:s0], a + p, exact, st, out, starts)
                _slow(seg[s0:e0], a + s0, exact, st, out, starts)
                p = e0
            if p < len(seg):
                _fast(seg[p:], a + p, exact, st, out, starts)
        if out:
            yield "".join(out), starts
        a = b


def _fast(seg, a, exact, st, out, starts):
    """Plain ASCII with no character that folds to nothing: one folded character per original one."""
    tr = seg.translate(_ASCII[1] if exact else _ASCII[0])
    if exact:
        out.append(tr)
        starts.extend(range(a, a + len(tr)))
        return
    prev = 0
    for m in _TOKEN.finditer(tr):
        if m.start() > prev and st[0] and st[1] is None:
            st[1] = a + prev
        if st[1] is not None:
            out.append(" ")
            starts.append(st[1])
            st[1] = None
        out.append(m.group())
        starts.extend(range(a + m.start(), a + m.end()))
        st[0], prev = True, m.end()
    if len(tr) > prev and st[0] and st[1] is None:
        st[1] = a + prev


def _slow(seg, a, exact, st, out, starts):
    """The steps one original character at a time (``seg`` holds whole tokens of step 3)."""
    pieces = []  # (original index, folded piece) before whitespace is collapsed
    if exact:
        for k, ch in enumerate(seg):
            pieces.append((a + k, _strip_format(ch).casefold()))
    else:
        styled = [_styled(ch) for ch in seg]
        m = len(styled)
        if CONFUSABLE:  # step 3 by token, a token being a run of characters that are not whitespace after step 2
            i = 0
            while i < m:
                if styled[i].isspace() or not styled[i]:
                    i += 1
                    continue
                j = i
                while j < m and not (styled[j].isspace()) and (styled[j] or j == i):
                    j += 1
                scripts = {_script(c) for k in range(i, j) for c in styled[k]}
                if "latin" in scripts and scripts & {"cyrillic", "greek"}:
                    for k in range(i, j):
                        styled[k] = "".join(CONFUSABLE.get(c, c) if _script(c) in ("cyrillic", "greek") else c
                                            for c in styled[k])
                i = j
        for k, sty in enumerate(styled):
            pieces.append((a + k, _rest(sty)))
    emitted, pending = st
    put, at = out.append, starts.append
    for i, piece in pieces:
        if len(piece) == 1 and (exact or not piece.isspace()):  # most characters: one folded character, no space
            if pending is not None:
                put(" ")
                at(pending)
                pending = None
            put(piece)
            at(i)
            emitted = True
            continue
        for c in piece:
            if not exact and c.isspace():
                if emitted and pending is None:
                    pending = i  # leading and repeated whitespace collapse into one space
                continue
            if pending is not None:
                put(" ")
                at(pending)
                pending = None
            put(c)
            at(i)
            emitted = True
    st[0], st[1] = emitted, pending


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
