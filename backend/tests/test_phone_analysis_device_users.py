"""05-S8, approach 5 complementary-use part (05 section 8.8 tests 3 and 4). Invented data only."""
from __future__ import annotations

import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text

from services.phone_analysis import device_users as U
from services.phone_analysis import framework as F
from tests.phone_analysis_fixture import record
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

PARAMS = {k: v["default"] for k, v in U.PARAMETERS.items()}


@pytest.fixture
def engine():
    with fresh_engine() as e:
        yield e


def _iccid(c, ext, value):
    skel = ["project", {"reportVersion": "7.70"}, None, [
        ["metadata", {"section": "Additional Fields"}, None, [["item", {"name": "ICCID"}, value, None]]]]]
    c.execute(text("UPDATE phone_extraction_documents SET skeleton = CAST(:s AS jsonb) WHERE extraction_id = :e"),
              {"e": ext, "s": json.dumps(skel)})


def _use(c, case, ext, start_hour, end_hour, days, base):
    """Owner interaction every 15 minutes from start_hour to end_hour on each day."""
    rows = []
    for d in range(days):
        t = base + timedelta(days=d, hours=start_hour)
        while t < base + timedelta(days=d, hours=end_hour):
            rows.append(t)
            t += timedelta(minutes=15)
    for i, t in enumerate(rows):
        rec = record(c, case, ext, 900 + i, "DeviceEvent")
        c.execute(text(
            "INSERT INTO pol_activity_event (case_id, extraction_id, record_uid, root_record_uid, record_type, "
            "time_field, field_path, instant_utc, offset_status, instant_basis, original, time_semantics, stream_key, "
            "family, activity_class, class_basis, class_level, actor) VALUES (:c, :e, :r, :r, 'DeviceEvent', 'StartTime', "
            "'StartTime', :t, 'explicit', 'synthetic', :o, 'event_instant', 'synthetic', 'device_events', "
            "'interaction', 'reviewed_mapping', 'applied_unconfirmed', 'owner')"), {"c": case, "e": ext, "r": rec, "t": t, "o": t.isoformat()})


def test_complementary_use_by_hand():
    """8.8.3: X used 09:00 to 12:00 and Y 12:00 to 15:00 daily: phi negative, one switch a day."""
    days = {at(2023, 1, d).date() for d in range(1, 15)}
    bx = {d: set(range(36, 48)) for d in days}
    by = {d: set(range(48, 60)) for d in days}
    c = U.complementary(bx, by)
    assert c["days"] == 14 and c["both"] == 0 and c["only_x"] == 12 * 14 and c["only_y"] == 12 * 14
    assert c["phi"] < 0 and c["switches_per_day"] == 1.0


@needs_template
def test_pair_with_the_same_iccid_and_alternating_use(engine):
    """8.8.3 and 8.8.4 end to end: same ICCID in both reports' metadata is a strong marker; alternating use over 14
    days through an applied mapping is strong on the one scale; values are never in the result."""
    base = at(2023, 1, 2, 0)
    with engine.begin() as c:
        case = make_case(c)
        x, _ = phone(c, case, label="C1", events=[])
        y, _ = phone(c, case, label="C2", owner="phone:+12025550111", events=[])
        _iccid(c, x, "8944 1000 0000 0000 0001")
        _iccid(c, y, "89441000000000000001")
        _use(c, case, x, 9, 12, 14, base)
        _use(c, case, y, 12, 15, 14, base)
    with engine.connect() as c:
        res, counts = U.analyse(c, case, PARAMS)
    (m,) = [r for r in res if r["kind"] == "shared_markers"]
    assert m["strength"] == "strong" and m["measures"]["by_kind"] == {"iccid": 1}
    assert "8944" not in json.dumps(m, default=str)
    (u,) = [r for r in res if r["kind"] == "complementary_use"]
    assert u["measures"]["days"] == 14 and u["measures"]["phi"] < 0 and u["measures"]["switches_per_day"] == 1.0
    assert u["measures"]["phones"] == ["C1", "C2"]
    assert u["strength"] == "strong" and u["measures"]["strength_basis"] == {"count": 14, "substantiation": 2, "fit": 2}
    assert counts["complementary_use_strong"] == 1 and counts["shared_markers_strong"] == 1
    F.register(U)
    with engine.begin() as c:
        with pytest.raises(F.AnalysisError):  # no cutoff is left to set (19.S8-b)
            F.request_run(c, case, "device_users", {"min_days": 15}, "synthetic@example.org")
    with engine.begin() as c:
        run, _ = F.request_run(c, case, "device_users", {}, "synthetic@example.org")
    assert F.execute(engine, uuid.UUID(run["id"]))["status"] == "completed"
    with engine.connect() as c:
        page = F.results(c, case, run["id"])
    assert {i["kind"] for i in page["items"]} == {"shared_markers", "complementary_use"}


@needs_template
def test_a_pair_with_one_or_three_shared_days_is_listed_graded_not_hidden(engine):
    """Neil 2026-11-04: no cutoff hides a candidate. One shared day is weak (few records), three are moderate."""
    base = at(2023, 1, 2, 0)
    with engine.begin() as c:
        case = make_case(c)
        x, _ = phone(c, case, label="C1", events=[])
        y, _ = phone(c, case, label="C2", owner="phone:+12025550111", events=[])
        z, _ = phone(c, case, label="C3", owner="phone:+12025550122", events=[])
        _use(c, case, x, 9, 12, 3, base)
        _use(c, case, y, 12, 15, 1, base)
        _use(c, case, z, 12, 15, 3, base)
    with engine.connect() as c:
        res, counts = U.analyse(c, case, PARAMS)
    use = {tuple(r["measures"]["phones"]): r for r in res if r["kind"] == "complementary_use"}
    assert use[("C1", "C2")]["measures"]["days"] == 1 and use[("C1", "C2")]["strength"] == "weak"
    assert "few_records" in {d["code"] for d in use[("C1", "C2")]["directions"]["undercuts"]}
    assert use[("C1", "C3")]["measures"]["days"] == 3 and use[("C1", "C3")]["strength"] == "moderate"
    assert use[("C2", "C3")]["strength"] == "weak"
    assert counts["complementary_use_weak"] == 2 and counts["complementary_use_moderate"] == 1


def test_marker_strength_uses_the_one_scale():
    """19.S8-c: an account or saved login in common is moderate (the scale's word), never medium."""
    from services.phone_analysis.money_pairings import LEVELS
    assert U.STRENGTH["account"] == U.STRENGTH["saved_login"] == "moderate"
    assert set(U.STRENGTH.values()) <= set(LEVELS)
    assert "marker_moderate" in U.DIRECTION_CODES and "marker_medium" not in U.DIRECTION_CODES


@needs_template
def test_signs_of_more_than_one_user_are_listed_not_scored(engine):
    with engine.begin() as c:
        case = make_case(c)
        ext, _ = phone(c, case, events=[])
        c.execute(text("INSERT INTO phone_owner_candidates (case_id, extraction_id, candidate_kind, identity_key, tier, "
                       "occurrences, basis, generation) VALUES (:c, :e, 'number', 'phone:+12025550199', 1, 1, "
                       "'extracted', 1)"), {"c": case, "e": ext})
        record(c, case, ext, 500, "User", [("UserType", "UserType", "Owner")])
        record(c, case, ext, 501, "User", [("UserType", "UserType", "Guest")])
    with engine.connect() as c:
        res, _ = U.analyse(c, case, PARAMS)
    (r,) = [r for r in res if r["kind"] == "more_than_one_user"]
    assert r["measures"]["signs"] == ["2 owner phone numbers", "2 device user records"]
    assert r["strength"] == "indicators"


@needs_template
def test_two_pairs_resting_on_one_phones_sim_record_keep_their_own_keys(engine):
    """Review finding: X holds the ICCID in a SIM record, Y and Z only in their report headers. Pairs (X,Y) and
    (X,Z) both rested on X's SIM record alone and the run failed. Each pair now carries its own anchor."""
    F.register(U)
    with engine.begin() as c:
        case = make_case(c)
        x, _ = phone(c, case, label="C1", events=[dict(kind="message", instant=at(2023, 1, 2), body="hi", thread="t", parties=[])])
        y, _ = phone(c, case, label="C2", owner="phone:+12025550111", events=[dict(kind="message", instant=at(2023, 1, 2), body="hi", thread="t", parties=[])])
        z, _ = phone(c, case, label="C3", owner="phone:+12025550122", events=[dict(kind="message", instant=at(2023, 1, 2), body="hi", thread="t", parties=[])])
        record(c, case, x, 50, "SIMData", fields=[("Name", "String", "ICCID"),
                                                  ("Value", "String", "89441000000000000001")])
        _iccid(c, y, "89441000000000000001")
        _iccid(c, z, "89441000000000000001")
        run, _ = F.request_run(c, case, "device_users", None, "synthetic@example.org")
    assert F.execute(engine, uuid.UUID(run["id"]))["status"] == "completed"
    with engine.connect() as c:
        page = F.results(c, case, run["id"], kind="shared_markers")
    assert page["total"] == 3


@needs_template
def test_owner_numbers_count_only_the_current_generation_and_extracted_tier(engine):
    """Review finding: owner numbers were read from the table, so an earlier generation's or an inferred (tier 2)
    number counted as an owner number. They are now read from the current-generation view at tier 1."""
    with engine.begin() as c:
        case = make_case(c)
        x, _ = phone(c, case, label="C1", events=[])
        for key, tier, gen in (("phone:+12025550188", 2, 1), ("phone:+12025550199", 1, 0)):
            c.execute(text(
                "INSERT INTO phone_owner_candidates (case_id, extraction_id, candidate_kind, identity_key, tier, "
                "occurrences, basis, generation) VALUES (:c, :e, 'number', :k, :t, 1, 'inferred', :g)"),
                {"c": case, "e": x, "k": key, "t": tier, "g": gen})
    with engine.connect() as c:
        assert U._indicators(c, x)["owner_numbers"] == 1
        assert len([k for k in U.markers(c, x) if k[0] == "owner_number"]) == 1


# ---- steps 2 and 4 (05 8.8 tests 1 and 2; cb-gated-aware F) -------------------------------------------------------

def _obs(t, lat, lon, radius=20.0, synced=False, uid=None):
    return {"id": 1, "record_uid": uid, "lat": lat, "lon": lon, "radius_m": radius, "start": t, "end": t,
            "offset_status": "explicit", "attribution_flags": ["synced_from_account"] if synced else []}


def test_together_and_apart_by_hand():
    """8.8.1: fixes 30 m apart with radii 20 m each in one bin: together; 2 km apart: apart."""
    t = at(2023, 3, 1, 10)
    lat, lon = 38.9, -77.03
    v = U.bin_verdicts([_obs(t, lat, lon, uid="a")], [_obs(t, lat + 30 / 111_320, lon, uid="b")], PARAMS)
    (b,) = v.values()
    assert b["verdict"] == "together" and not b["assumed"] and b["tight"]
    v = U.bin_verdicts([_obs(t, lat, lon, uid="a")], [_obs(t, lat + 2000 / 111_320, lon, uid="b")], PARAMS)
    assert [x["verdict"] for x in v.values()] == ["apart"]


def _place(c, case, ext, ordinal, t, lat, lon, radius=20.0, synced=False):
    uid = record(c, case, ext, ordinal, "Location")
    c.execute(text(
        "INSERT INTO pol_place_observation (case_id, extraction_id, record_uid, kind, source_kind, lat, lon, radius_m, "
        "radius_basis, start_utc, end_utc, offset_status, time_semantics, attribution_flags) VALUES (:c, :e, :r, "
        "'presence', 'gps', :la, :lo, :rad, 'stated', :t, :t, 'explicit', 'observed', CAST(:f AS text[]))"),
        {"c": case, "e": ext, "r": uid, "la": lat, "lo": lon, "rad": radius, "t": t,
         "f": ["synced_from_account"] if synced else []})
    return uid


def _event(c, case, ext, ordinal, t):
    rec = record(c, case, ext, ordinal, "DeviceEvent")
    c.execute(text(
        "INSERT INTO pol_activity_event (case_id, extraction_id, record_uid, root_record_uid, record_type, "
        "time_field, field_path, instant_utc, offset_status, instant_basis, original, time_semantics, stream_key, "
        "family, activity_class, class_basis, actor) VALUES (:c, :e, :r, :r, 'DeviceEvent', 'StartTime', "
        "'StartTime', :t, 'explicit', 'synthetic', :o, 'event_instant', 'synthetic', 'device_events', "
        "'interaction', 'reviewed_mapping', 'owner')"), {"c": case, "e": ext, "r": rec, "t": t, "o": t.isoformat()})


@needs_template
def test_ten_co_placed_bins_give_a_weak_co_location_and_a_synced_point_does_not_place(engine):
    """cb-gated-aware F and 8.8.2: 10 together bins (under the 200 of the plan) are a weak result, not nothing. A bin
    with only a Synced point is not placed by default. Fails on 5.2-use, which gives no co-location result."""
    t = at(2023, 3, 1, 10)
    lat, lon = 38.9, -77.03
    with engine.begin() as c:
        case = make_case(c)
        x, _ = phone(c, case, label="C1", events=[])
        y, _ = phone(c, case, label="C2", owner="phone:+12025550111", events=[])
        for i in range(10):
            _place(c, case, x, 100 + i, t + timedelta(hours=i), lat, lon)
            _place(c, case, y, 100 + i, t + timedelta(hours=i, minutes=2), lat + 30 / 111_320, lon)
        _place(c, case, x, 200, t + timedelta(days=1), lat, lon)
        _place(c, case, y, 200, t + timedelta(days=1), lat, lon, synced=True)
    with engine.connect() as c:
        res, counts = U.analyse(c, case, PARAMS)
        res_synced, _ = U.analyse(c, case, dict(PARAMS, include_synced=True))
        cov = F.coverage(c, case, "device_users")
    (co,) = [r for r in res if r["kind"] == "co_location"]
    m = co["measures"]
    assert m["bins_both_placed"] == 10 and m["together"] == 10 and m["apart"] == 0 and m["C"] == 1.0
    assert co["strength"] == "weak"
    assert any(d["detail"].startswith("Weak: 10 decided quarter hours.") for d in co["directions"]["supports"])
    (co2,) = [r for r in res_synced if r["kind"] == "co_location"]
    assert co2["measures"]["bins_both_placed"] == 11
    assert counts["co_location_weak"] == 1
    assert cov["totals"]["most_co_placed_bins"] == 10
    assert "the most here is 10" in cov["notes"][1] and "Rule of thumb (no measurement behind it)" in cov["notes"][1]


@needs_template
def test_use_while_apart_lists_the_bins_with_both_phones_records(engine):
    """8.3 step 4: an apart bin in which X's owner used X."""
    t = at(2023, 3, 1, 10)
    lat, lon = 38.9, -77.03
    with engine.begin() as c:
        case = make_case(c)
        x, _ = phone(c, case, label="C1", events=[])
        y, _ = phone(c, case, label="C2", owner="phone:+12025550111", events=[])
        px = _place(c, case, x, 100, t, lat, lon)
        py = _place(c, case, y, 100, t, lat + 2000 / 111_320, lon)
        _event(c, case, x, 300, t + timedelta(minutes=5))
    with engine.connect() as c:
        res, _ = U.analyse(c, case, PARAMS)
    (co,) = [r for r in res if r["kind"] == "co_location"]
    assert co["measures"]["apart"] == 1 and co["measures"]["C"] == 0.0 and co["strength"] == "weak"
    (u,) = [r for r in res if r["kind"] == "use_while_apart"]
    assert u["measures"]["used_phone"] == "C1" and len(u["measures"]["bins"]) == 1
    roles = {(r["role"], r["record_uid"]) for r in u["records"]}
    assert ("place_used", px) in roles and ("place_other", py) in roles
    assert any(r == "used" for r, _ in roles)
