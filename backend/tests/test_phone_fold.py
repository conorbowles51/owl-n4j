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
