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
