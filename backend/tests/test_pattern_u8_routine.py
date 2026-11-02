"""04-U8 (cb-pol item G): stays, places, routine and deviations, with every parameter echoed.

Synthetic phone only (an invented home and work 3 km apart). Opt-in PostgreSQL through
``LOUPE_TEST_PHONE_PG_TEMPLATE_URL``.
"""
from __future__ import annotations

import json
from datetime import timedelta

from services.pattern_of_life import routine
from services.phone import registry
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.test_pattern_u4_availability import DAY, setup
from tests.test_pattern_u5_places import LAT, LON, PlacePhone, build
from tests.test_phone_mappings import hooks  # noqa: F401 (fixture)

HOME = (LAT, LON)
WORK = (LAT + 0.027, LON)   # about 3 km north
AWAY = (LAT - 0.045, LON)   # about 5 km south
START = DAY - timedelta(days=DAY.weekday())  # a Monday, 00:00 UTC


def routine_phone(away_tuesday_week=None):
    p = PlacePhone()
    for d in range(42):
        day = START + timedelta(days=d)
        for m in range(0, 7 * 60, 30):              # 00:00 to 07:00 at home
            p.location(day + timedelta(minutes=m), *HOME, accuracy=10)
        if day.weekday() < 5:
            for m in range(9 * 60, 17 * 60, 30):    # weekday work 09:00 to 17:00
                p.location(day + timedelta(minutes=m), *WORK, accuracy=10)
        night = AWAY if (away_tuesday_week is not None and d == away_tuesday_week * 7 + 1) else HOME
        for m in range(21 * 60, 24 * 60, 30):       # 21:00 to midnight
            p.location(day + timedelta(minutes=m), *night, accuracy=10)
    return p


@needs_template
def test_home_and_work_are_routine_and_a_tuesday_night_elsewhere_is_flagged(hooks):
    from zoneinfo import ZoneInfo
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = routine_phone(away_tuesday_week=3).make(c, case)
        build(engine, ext)
        utc = ZoneInfo("UTC")
        with engine.connect() as c:
            res = routine.compute(c, [str(ext)], utc)
        assert res["parameters"] == routine.PARAMS  # echoed with the result
        assert len(res["routine_places"]) == 2
        places = {p["cluster_id"]: p for p in res["places"]}
        assert all(places[k]["radius_m"] < 150 for k in res["routine_places"])
        home = min(res["routine_places"], key=lambda k: abs(places[k]["lat"] - HOME[0]))
        assert places[home]["day_count"] == 41  # every date but the away Tuesday starts a home stay
        assert places[home]["profile"][1][22] == 50.0  # Tuesdays 22:00: 5 of 6 weeks at home, 60 min each
        dev = routine.deviations(res, utc)
        tuesday = (START + timedelta(days=22)).date().isoformat()
        flagged = {f["date"]: f for f in dev["flagged"]}
        assert tuesday in flagged
        hours = [h["hour"] for h in flagged[tuesday]["hours"]]
        assert hours == [21, 22, 23]
        assert flagged[tuesday]["hours"][0]["place"] == "elsewhere"
        assert flagged[tuesday]["hours"][0]["expected_place"] == home
        assert "Tuesdays" in flagged[tuesday]["expectation"]
        assert len(flagged) == 1
        assert dev["parameters"]["deviation_min_bits"] == 3.0


@needs_template
def test_routine_over_http_returns_parameters_and_totals(hooks):
    from tests.pattern_pg import api_client
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            p = PlacePhone()
            for m in range(0, 120, 10):
                p.location(DAY + timedelta(minutes=m), *HOME, accuracy=10)
            ext = p.make(c, case)
        build(engine, ext)
        subj = json.dumps({"kind": "extraction", "extraction_id": str(ext)})
        with api_client(engine, case) as client:
            body = client.get("/api/pattern/%s/routine" % case, params={"subject": subj}).json()
            assert body["stays_total"] == 1 and body["parameters"]["eps_m"] == 150.0
            assert body["routine_places"] == []  # one stay is not a place
            dev = client.get("/api/pattern/%s/routine/deviations" % case, params={"subject": subj}).json()
            assert dev["flagged"] == [] and dev["parameters"]["laplace_alpha"] == 1.0
