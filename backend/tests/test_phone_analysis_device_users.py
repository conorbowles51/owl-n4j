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
            "family, activity_class, class_basis, actor) VALUES (:c, :e, :r, :r, 'DeviceEvent', 'StartTime', "
            "'StartTime', :t, 'explicit', 'synthetic', :o, 'event_instant', 'synthetic', 'device_events', "
            "'interaction', 'reviewed_mapping', 'owner')"), {"c": case, "e": ext, "r": rec, "t": t, "o": t.isoformat()})


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
    days is measured; values are never in the result."""
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
    F.register(U)
    with engine.begin() as c:
        run, _ = F.request_run(c, case, "device_users", {"min_days": 15}, "synthetic@example.org")
    assert F.execute(engine, uuid.UUID(run["id"]))["status"] == "completed"
    with engine.connect() as c:
        page = F.results(c, case, run["id"])
    assert {i["kind"] for i in page["items"]} == {"shared_markers"}  # 14 days < 15: no use result


@needs_template
def test_signs_of_more_than_one_user_are_listed_not_scored(engine):
    with engine.begin() as c:
        case = make_case(c)
        ext, _ = phone(c, case, events=[])
        c.execute(text("INSERT INTO phone_owner_candidates (case_id, extraction_id, candidate_kind, identity_key, tier, "
                       "occurrences, basis, generation) VALUES (:c, :e, 'number', 'phone:+12025550199', 2, 1, "
                       "'extracted', 1)"), {"c": case, "e": ext})
        record(c, case, ext, 500, "User", [("UserType", "UserType", "Owner")])
        record(c, case, ext, 501, "User", [("UserType", "UserType", "Guest")])
    with engine.connect() as c:
        res, _ = U.analyse(c, case, PARAMS)
    (r,) = [r for r in res if r["kind"] == "more_than_one_user"]
    assert r["measures"]["signs"] == ["2 owner phone numbers", "2 device user records"]
    assert r["strength"] == "indicators"
