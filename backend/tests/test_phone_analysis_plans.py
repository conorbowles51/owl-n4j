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
    # a bound before the start (seen on live: a repeating entry after the phone's last record) keeps the start
    assert P.occurrences(s, "Daily", 1, at(2022, 12, 1)) == [s]
    assert P.occurrences(s, "Daily", 1, None, horizon=at(2022, 12, 1)) == [s]
    # a weekly rule on other days still counts its start (Monday) first
    assert P.occurrences(s, "Weekly", 1, at(2023, 1, 8, 23), "Wednesday")[0] == s


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


@needs_template
def test_a_person_placed_text_place_is_compared_and_named_as_theirs(engine):
    """Fails on 10.2, which called every placement "the phone's own coordinates" and graded it strong: a calendar
    entry whose written place a person set on the map (04 6.5 text places, source person_placed) is compared, its
    placement is named as that person's, and it is at most moderate. A phone-placed entry beside it is unchanged."""
    import uuid
    t = at(2023, 3, 6, 10)
    dec = uuid.uuid4()
    with engine.begin() as c:
        case = make_case(c)
        x, _ = phone(c, case, label="C1", events=[])
        e1 = record(c, case, x, 100, "CalendarEntry", fields=[("Location", "String", "Market Square")],
                    times=[("StartDate", t), ("EndDate", t + timedelta(hours=1))])
        e2 = record(c, case, x, 101, "CalendarEntry", fields=[("Subject", "String", "Meeting")],
                    times=[("StartDate", t), ("EndDate", t + timedelta(hours=1))])
        c.execute(text(
            "INSERT INTO pol_text_place (id, case_id, extraction_id, record_uid, field_path, model_type, place_text, "
            "lat, lon, radius_m, reason, decision_id, actor_name, actor_email) VALUES (:i, :c, :e, :u, 'Location', "
            "'CalendarEntry', 'Market Square', 40.0, -75.0, 200, 'test', :d, 'Test Person', 'test@loupe.invalid')"),
            {"i": uuid.uuid4(), "c": case, "e": x, "u": e1, "d": dec})
        c.execute(text(
            "INSERT INTO pol_place_observation (case_id, extraction_id, record_uid, record_type, kind, source_kind, lat, "
            "lon, radius_m, radius_basis, start_utc, end_utc, offset_status, time_semantics, decision_id) VALUES (:c, "
            ":e, :u, 'CalendarEntry', 'planned', 'person_placed', 40.0, -75.0, 200, 'manual', :t, :t, 'explicit', "
            "'event_instant', :d)"), {"c": case, "e": x, "u": e1, "t": t, "d": dec})
        _obs(c, case, x, e2, "planned", 40.0, -75.0, 25.0, t)
        _obs(c, case, x, None, "presence", 40.0002, -75.0, 30.0, t + timedelta(minutes=10))
    with engine.connect() as c:
        res, counts = P.analyse(c, case, PARAMS)
    by_uid = {str(r["records"][0]["record_uid"]): r for r in res}
    person, own = by_uid[str(e1)], by_uid[str(e2)]
    assert (person["kind"], person["strength"]) == ("consistent", "moderate")
    assert person["measures"]["placed_by"] == "person" and person["measures"]["placed_by_name"] == "Test Person"
    assert [s["code"] for s in person["directions"]["supports"]][0] == "placed_by_person"
    assert "Test Person" in person["directions"]["supports"][0]["detail"]
    assert "phone's own" not in person["directions"]["supports"][0]["detail"]
    assert "person_placed" in [u["code"] for u in person["directions"]["undercuts"]]
    assert (own["kind"], own["strength"]) == ("consistent", "strong") and own["measures"]["placed_by"] == "phone"
    assert counts["calendar_placed"] == 2 and counts["calendar_placed_by_person"] == 1


@needs_template
def test_a_placement_is_a_new_input_and_a_rerun_compares_again(engine):
    """Fails on 10.3, whose manifest left placements out: placing or removing a written place changes the run's input
    revision, so Run does not return the earlier run."""
    import uuid
    t = at(2023, 3, 6, 10)
    with engine.begin() as c:
        case = make_case(c)
        x, _ = phone(c, case, label="C1", events=[])
        e = record(c, case, x, 100, "CalendarEntry", fields=[("Location", "String", "Market Square")],
                   times=[("StartDate", t)])
    with engine.connect() as c:
        before = F.input_manifest(c, case, P)
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO pol_text_place (id, case_id, extraction_id, record_uid, field_path, model_type, place_text, "
            "lat, lon, radius_m, reason, decision_id, actor_name, actor_email) VALUES (:i, :c, :e, :u, 'Location', "
            "'CalendarEntry', 'Market Square', 40.0, -75.0, 200, 'test', :d, 'Test Person', 'test@loupe.invalid')"),
            {"i": uuid.uuid4(), "c": case, "e": x, "u": e, "d": uuid.uuid4()})
    with engine.connect() as c:
        placed = F.input_manifest(c, case, P)
    with engine.begin() as c:
        c.execute(text("UPDATE pol_text_place SET removed_decision_id = :d"), {"d": uuid.uuid4()})
    with engine.connect() as c:
        removed = F.input_manifest(c, case, P)
    assert before["person_placements"] == [] and len(placed["person_placements"]) == 1
    assert F.sha256(before) != F.sha256(placed) and F.sha256(placed) != F.sha256(removed)


@needs_template
def test_an_undated_entry_is_listed_not_dropped(engine):
    """Fails on 10.3, which only counted it: a calendar entry with no date and a written place, and one with neither,
    are in the results with the reason, and the stated total counts them."""
    with engine.begin() as c:
        case = make_case(c)
        x, _ = phone(c, case, label="C1", events=[])
        record(c, case, x, 100, "CalendarEntry", fields=[("Location", "String", "Market Square")])
        record(c, case, x, 101, "CalendarEntry", fields=[("Subject", "String", "No date")])
    with engine.connect() as c:
        res, counts = P.analyse(c, case, PARAMS)
    assert sorted(r["kind"] for r in res) == ["no_place", "place_as_text"]
    assert all(r["measures"]["undated"] and r["measures"]["reasons"]["match"][0].startswith("No date") for r in res)
    assert counts["calendar_undated"] == 2 and counts["by_strength_faint"] == 2
