"""02-U8: name folding (02 section 8.4) against the fixture shared with the frontend (03 section 11.3)."""
from __future__ import annotations

import json
import os
import unicodedata

import pytest

from services.phone import fold as F

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "fold_cases.json")
CASES = json.load(open(FIXTURE, encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_fold_vectors(case):
    if "fold" in case:
        assert F.fold(case["input"]) == case["fold"]
    if "exact" in case:
        assert F.fold(case["input"], exact=True) == case["exact"]


def test_tables_are_loaded_and_exist_in_unicode_13():
    assert len(F.STYLED) == 102 and len(F.CONFUSABLE) == 73
    for ch in list(F.STYLED) + list(F.CONFUSABLE):
        assert unicodedata.name(ch, "")  # every code point has a name in this Python's Unicode
    header = json.load(open(os.path.join(os.path.dirname(F.__file__), "data", "confusables_latin.json")))
    assert header["version"] == "13.0.0" and len(header["sha256"]) == 64


def test_the_unicode_of_python_3_10_is_what_the_tables_assume():
    if unicodedata.unidata_version != "13.0.0":
        pytest.skip("this interpreter's Unicode is %s; the deploy runs 3.10 or 3.11 (13.0, 14.0)"
                    % unicodedata.unidata_version)


def _check_map(text, exact=False):
    folded, starts = F.fold_with_map(text, exact=exact)
    assert len(starts) == len(folded)
    assert starts == sorted(starts) and all(0 <= i < len(text) for i in starts)
    packed = F.pack_map(starts)
    for a in range(len(folded)):
        for b in range(a + 1, min(len(folded), a + 6) + 1):
            s, e = F.original_span(packed, a, b)
            assert (s, e) == (starts[a], starts[b - 1] + 1)
    return folded


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_fold_with_map_equals_fold_on_every_vector_and_maps_back(case):
    """S-5: the mapped fold gives fold()'s result on every shared vector, and each folded span maps to the
    original characters that produced it, including where folding changed the string's length."""
    if "fold" in case:
        assert _check_map(case["input"]) == case["fold"]
    if "exact" in case:
        assert _check_map(case["input"], exact=True) == case["exact"]


def test_a_match_after_length_changing_folds_highlights_the_original_characters():
    text = "Paid  ﬁne to José \U0001D4D9\U0001D4F8\U0001D4FC\U0001D4EE, Straße 5"
    folded, starts = F.fold_with_map(text)
    assert folded == F.fold(text)
    packed = F.pack_map(starts)
    for needle, original in (("fine", "ﬁne"), ("jose jose", "José \U0001D4D9\U0001D4F8\U0001D4FC\U0001D4EE"),
                             ("strasse", "Straße")):
        a = folded.index(needle)
        s, e = F.original_span(packed, a, a + len(needle))
        assert text[s:e] == original


def _pieces(text, exact, chunk):
    folded, starts = "", []
    for piece, at in F.iter_fold_with_map(text, exact, chunk=chunk):
        assert piece and len(piece) == len(at)
        folded += piece
        starts.extend(at)
    return folded, starts


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_folding_in_pieces_gives_the_whole_fold_and_map_at_every_piece_size(case):
    """Search snippets fold long texts piece by piece and stop at the first match; joined, the pieces are the
    whole fold with the same map, wherever the cuts fall (whitespace runs, mixed-script tokens, word breaks)."""
    text = case["input"] + "  \t" + case["input"] + "​ end  "
    for exact in (False, True):
        whole = F.fold_with_map(text, exact=exact)
        for chunk in (1, 2, 3, 5, 8, 64):
            assert _pieces(text, exact, chunk) == whole, (exact, chunk)
        assert whole == _pieces(text, exact, len(text) + 1)


def test_a_snippet_of_a_long_text_folds_only_up_to_its_first_match(monkeypatch):
    """A search page of long emails (65 KB each on average on the largest phone case, 13 MB for one page of 200)
    took 11 s because each snippet folded its whole body; a snippet now folds up to the piece holding the first
    match, and finds the same match as the whole fold, including one that crosses a cut."""
    from services.search import search as S
    filler = "Synthetic paragraph of ordinary words, numbers 12345 and punctuation. " * 3000
    text = "Opening words then the match " + filler + " and a later match"
    seen = []
    real = F._styled.__wrapped__
    monkeypatch.setattr(F, "_styled", lambda ch: seen.append(ch) or real(ch))
    snip = S.snippet(text, "the match")
    assert snip["match"] == "the match" and snip["before"] == "Opening words then "
    assert len(seen) < 2 * F.FOLD_CHUNK < len(text) // 20
    # a match across a cut, and a match only at the end, are found where the whole fold finds them
    for chunk in (7, 16, 4096):
        monkeypatch.setattr(F, "FOLD_CHUNK", chunk)
        for t, q in ((text, "a later match"), ("x" * 13 + " ﬁne  Straße  \U0001D4D9\U0001D4F8\U0001D4FC\U0001D4EE", "strasse jose"),
                     ("word " * 40 + "Té́l​é" + " phone", "tel e phone")):
            folded, starts = F.fold_with_map(t)
            fq = F.fold_with_map(q)[0]
            at = folded.find(fq)
            assert at >= 0, q
            expected = S._cut(t, starts[at], starts[at + len(fq) - 1] + 1)
            assert S.snippet(t, q) == expected, (chunk, q)


ASCII_TEXTS = ["  Plain words, punctuation -- runs!!  and\ttabs\r\nlines  ", "ctrl\x01chars\x7fhere \x00 end",
               "...", " ", "A", "mixed Straße ascii ﬁne  then plain text ... again", "x" * 50 + "  " + "Y" * 50,
               "<html><body style=\"a:b\">Synthetic&nbsp;mail &amp; more</body></html>",
               "plain\u00a0words with\u200cjoiners and\u034fgraphemes, curly\u2019quote end",
               "ascii words p\u0430yp\u0430l mixed-script token among ascii, \U0001D4D9\U0001D4F8\U0001D4FC\U0001D4EE too",
               "a" * 300 + "\u00e9" + "b" * 300 + " tail\x01 \x0bsep\x0cform"]


@pytest.mark.parametrize("text", ASCII_TEXTS)
def test_the_plain_ascii_fast_path_folds_exactly_as_the_character_steps(monkeypatch, text):
    """Plain ASCII pieces are folded by a table taken from the steps themselves; with the table switched off
    every text folds to the same string and map, at every piece size and in both modes."""
    expected = {}
    with monkeypatch.context() as m:
        m.setattr(F, "_ASCII", None)
        for exact in (False, True):
            expected[exact] = F.fold_with_map(text, exact=exact)
            assert expected[exact][0] == (F.fold(text, exact=exact) if not exact else expected[exact][0])
    assert F._ASCII is not None
    for exact in (False, True):
        assert F.fold_with_map(text, exact=exact) == expected[exact]
        for chunk in (1, 2, 3, 5, 8, 64):
            assert _pieces(text, exact, chunk) == expected[exact], (exact, chunk)


def test_a_long_run_without_spaces_folds_in_time_that_grows_with_its_length():
    import time
    text = ("A1b2C3" * 40000) + "\u00e9" + ("x" * 240000)
    started = time.monotonic()
    folded, starts = F.fold_with_map(text)
    assert len(folded) == len(text) and starts[-1] == len(text) - 1
    assert time.monotonic() - started < 5


def test_dense_non_latin_text_looks_up_each_characters_script_once(monkeypatch):
    """Dense Greek, Cyrillic or CJK text goes through the steps one character at a time; the script of a character
    (a Unicode name lookup) was looked up again for every occurrence, which made such text fold 4-13% slower than
    before the ASCII fast path. Each distinct character is now looked up once, and the result is unchanged."""
    words = " ".join(["αβγδε", "ζηθικ", "λμνξο", "абвгд", "жзийк", "东南西北", "Pαypal"] * 400)
    expected = F.fold_with_map(words)
    calls = []
    real = unicodedata.name
    monkeypatch.setattr(F.unicodedata, "name", lambda ch, default=None: calls.append(ch) or real(ch, default))
    F._script.cache_clear()
    assert F.fold_with_map(words) == expected
    assert len(calls) <= len(set(words))
