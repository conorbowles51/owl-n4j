"""Approach 10, plans and self-reported places (05 section 13.8 tests 1 and 2; cb-gated-spread G). Invented data
only."""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import text

from services.phone_analysis import approaches
from services.phone_analysis import framework as F
from services.phone_analysis import plans as P
from tests.phone_analysis_fixture import record
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

PARAMS = {k: v["default"] for k, v in P.PARAMETERS.items()}


@pytest.fixture
def engine():
    with fresh_engine() as e:
        yield e


def _obs(c, case, ext, uid, kind, lat, lon, radius, t, end=None):
    c.execute(text(
        "INSERT INTO pol_place_observation (case_id, extraction_id, record_uid, record_type, kind, source_kind, lat, "
        "lon, radius_m, radius_basis, start_utc, end_utc, offset_status, time_semantics) VALUES (:c, :e, :u, 'x', :k, "
        "'gps', :la, :lo, :r, 'gps_accuracy_x2', :t, :en, 'explicit', 'event_instant')"),
        {"c": case, "e": ext, "u": uid, "k": kind, "la": lat, "lo": lon, "r": radius, "t": t, "en": end or t})


def test_weekly_entry_with_repeat_until_expands_to_the_right_count():
    """13.8.1: weekly from Monday 2 January to 30 January 2023 is 5 occurrences; every two weeks 3; on two named
    days 9 (Mondays 5 and Wednesdays 4); a monthly rule skips 31 April; with no RepeatUntil the phone's last record
    bounds it."""
    s = at(2023, 1, 2, 9)
    assert P.occurrences(s, "Weekly", None, at(2023, 1, 30, 23)) == [s + timedelta(weeks=k) for k in range(5)]
    assert len(P.occurrences(s, "Weekly", 2, at(2023, 1, 30, 23))) == 3
    assert len(P.occurrences(s, "Weekly", 1, at(2023, 1, 30, 23), "Monday, Wednesday")) == 9
    m = P.occurrences(at(2023, 1, 31, 9), "Monthly", 1, at(2023, 6, 30, 23))
    assert [o.month for o in m] == [1, 3, 5]
    assert len(P.occurrences(s, "Daily", 1, None, horizon=at(2023, 1, 4, 10))) == 3
    assert P.occurrences(s, None, None, None) == [s] and P.occurrences(s, "Weekly", None, None) == [s]


def test_compare_by_hand():
    """13.8.2 by hand: a check-in 50 km from a GPS fix of 20 m accuracy (radius 40 m) is inconsistent; its own
    radius is not stated, so a radius is assumed and the strength is moderate."""
    item = {"lat": 51.5, "lon": -0.1, "radius_m": None}
    far = {"lat": 51.5 + 50 / 111.2, "lon": -0.1, "radius_m": 40.0}
    c = P.compare(item, [far], 1000)
    assert c["kind"] == "inconsistent" and c["strength"] == "moderate" and c["nearest_m"] > 49000
    near = {"lat": 51.5001, "lon": -0.1, "radius_m": 40.0}
    assert P.compare(dict(item, radius_m=30.0), [near], 1000)["strength"] == "strong"
    assert P.compare(item, [near, far], 1000)["kind"] == "mixed"
    assert P.compare(item, [], 1000)["kind"] == "no_data"


@needs_template
def test_checkin_fifty_km_from_a_gps_fix_is_inconsistent(engine):
    """13.8.2 end to end."""
    t = at(2023, 3, 4, 15)
    with engine.begin() as c:
        case = make_case(c)
        x, _ = phone(c, case, label="C1", events=[])
        ci = record(c, case, x, 100, "SocialMediaActivity",
                    fields=[("SocialActivityType", "SocialMediaActivityType", "CheckIn")], times=[("TimeStamp", t)])
        _obs(c, case, x, ci, "declared", 51.5, -0.1, None, t)
        _obs(c, case, x, None, "presence", 51.5 + 50 / 111.2, -0.1, 40.0, t + timedelta(minutes=20))
    with engine.connect() as c:
        res, counts = P.analyse(c, case, PARAMS)
    (r,) = [r for r in res if r["measures"]["source"] == "checkin"] if res else [None]
    assert r["kind"] == "inconsistent" and r["strength"] == "moderate"
    assert r["measures"]["reasons"]["match"] and counts["checkins_placed"] == 1


@needs_template
def test_one_placed_calendar_entry_yields_a_comparison(engine):
    """G (fails on the old code, which built no comparison under 20 placed items): one calendar entry with its own
    coordinates and a fix in its hour gives one consistent comparison; an entry with a text place and one with none
    are still listed, not compared."""
    t = at(2023, 3, 6, 10)
    with engine.begin() as c:
        case = make_case(c)
        x, _ = phone(c, case, label="C1", events=[])
        e1 = record(c, case, x, 100, "CalendarEntry", fields=[("Subject", "String", "Meeting")],
                    times=[("StartDate", t), ("EndDate", t + timedelta(hours=1))])
        _obs(c, case, x, e1, "planned", 40.0, -75.0, 25.0, t)
        _obs(c, case, x, None, "presence", 40.0002, -75.0, 30.0, t + timedelta(minutes=10))
        record(c, case, x, 101, "CalendarEntry", fields=[("Location", "String", "Somewhere street")],
               times=[("StartDate", t)])
        record(c, case, x, 102, "CalendarEntry", times=[("StartDate", t)])
    with engine.connect() as c:
        res, counts = P.analyse(c, case, PARAMS)
    kinds = sorted((r["kind"], r["strength"]) for r in res)
    assert kinds == [("consistent", "strong"), ("no_place", "faint"), ("place_as_text", "faint")]
    assert counts["calendar_placed"] == 1 and counts["calendar_entries"] == 3


@needs_template
def test_runs_through_the_framework(engine):
    approaches.install()
    t = at(2023, 3, 6, 10)
    with engine.begin() as c:
        case = make_case(c)
        x, _ = phone(c, case, label="C1", events=[])
        record(c, case, x, 100, "CalendarEntry", fields=[("RepeatRule", "RepeatRule", "Weekly")],
               times=[("StartDate", t), ("RepeatUntil", t + timedelta(weeks=2))])
        e = record(c, case, x, 101, "CalendarEntry", fields=[("RepeatRule", "RepeatRule", "Daily")],
                   times=[("StartDate", t), ("RepeatUntil", t + timedelta(days=2))])
        _obs(c, case, x, e, "planned", 40.0, -75.0, 25.0, t)
        run, _ = F.request_run(c, case, "plans", {}, "tester@example.com")
    assert F.execute(engine, run["id"])["status"] == "completed"
    with engine.connect() as c:
        page = F.results(c, case, run["id"])
    # the unplaced weekly entry once (3 occurrences counted), the placed daily entry once per occurrence (3)
    assert page["total"] == 4
    assert sorted(i["kind"] for i in page["items"]) == ["no_data", "no_data", "no_data", "no_place"]
