"""Analysis results can be listed for several phones at once (any of them), the phone layer control's server side."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from routers.phone_analysis import _phone_ids
from services.phone_analysis import framework as F

A, B = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"


def test_phones_filter_matches_any_listed_phone():
    where, p = F._filters("c", "r", phones=[A, B])
    assert "x.extraction_id::text = ANY(:phones)" in where
    assert p["phones"] == [A, B]


def test_no_phones_adds_no_clause():
    where, p = F._filters("c", "r")
    assert "phones" not in p and "ANY(:phones)" not in where


def test_phone_ids_parse_and_refuse_junk():
    assert _phone_ids("%s,%s" % (A, B)) == [A, B]
    assert _phone_ids(None) is None
    with pytest.raises(HTTPException):
        _phone_ids("not-a-uuid")
