"""03 section 3.2, test A6: every phone time string, against the fixture the frontend suite also reads."""
from __future__ import annotations

import json
import os
from datetime import datetime

import pytest

from services.phone import time_display as T

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "time_cases.json")
CASES = json.load(open(FIXTURE, encoding="utf-8"))


@pytest.mark.parametrize("case", CASES["instants"], ids=[c["id"] for c in CASES["instants"]])
def test_row_full_and_day_of_each_instant(case):
    assert T.format_row(case["instant"], case["zone"]) == case["row"]
    assert T.format_row(case["instant"], case["zone"], seconds=True) == case["row_seconds"]
    assert T.format_full(case["instant"], case["zone"]) == case["full"]
    day = T.day_of(case["instant"], case["zone"])
    assert (day.isoformat() if day else None) == case["day"]


@pytest.mark.parametrize("case", CASES["days"], ids=["%s %s" % (c["day"], c["zone"]) for c in CASES["days"]])
def test_day_header_and_zone_label(case):
    assert T.format_day_header(case["day"]) == case["header"]
    assert T.zone_label(case["day"], case["zone"]) == case["zone_label"]


def test_a_time_with_no_offset_is_written_as_the_report_wrote_it():
    for case in CASES["walls"]:
        wall = datetime.fromisoformat(case["wall"])
        block = T.time_block(None, "America/New_York", wall=wall, time_field="TimeStamp")
        assert block == {"instant": None, "row": case["row"], "full": case["full"], "offset_present": False,
                         "time_field": "TimeStamp"}


def test_day_bounds_cover_a_23_and_a_25_hour_day():
    s, e = T.day_bounds("2023-03-12", "America/New_York")
    assert (e - s).total_seconds() == 23 * 3600
    s, e = T.day_bounds("2023-11-05", "America/New_York")
    assert (e - s).total_seconds() == 25 * 3600


def test_never_invalid_date_and_a_naive_instant_is_refused():
    assert "Invalid" not in T.format_full(None, "UTC")
    with pytest.raises(ValueError):
        T.format_full("2023-03-14T19:07:12", "UTC")


def test_zone_validation():
    assert T.valid_zone("America/New_York") and T.valid_zone("UTC")
    assert not T.valid_zone("Mars/Olympus") and not T.valid_zone("") and not T.valid_zone(None)
