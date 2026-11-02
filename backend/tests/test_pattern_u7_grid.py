"""04-U7 (cb-pol item E): pattern grid, usual quiet hours and the nights that break them.

Synthetic phones only. Opt-in PostgreSQL through ``LOUPE_TEST_PHONE_PG_TEMPLATE_URL``.
"""
from __future__ import annotations

import json
from datetime import timedelta

from services.pattern_of_life import grid
from services.phone import registry
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.test_pattern_u4_availability import DAY, Phone, build, setup
from tests.test_phone_mappings import hooks  # noqa: F401 (fixture)

DAYS = 30


def routine_phone(break_night=None, unseen_night=None):
    """30 days: the screen lights every 20 minutes around the clock (recording), an unlock every hour from 08:00 to
    22:30 (use). ``break_night``: an unlock at 03:00 after that day; ``unseen_night``: no events 23:00 to 08:00."""
    p = Phone()
    for d in range(DAYS):
        day = DAY + timedelta(days=d)
        for m in range(0, 24 * 60, 20):
            t = day + timedelta(minutes=m)
            if unseen_night is not None and (d == unseen_night and t.hour >= 23 or
                                             d == unseen_night + 1 and t.hour < 8):
                continue
            p.device_event(t, "DisplayOnOff")
        for h in range(8, 23):
            p.device_event(day + timedelta(hours=h, minutes=30), "DeviceLockStatus", "Unlocked")
    if break_night is not None:
        p.device_event(DAY + timedelta(days=break_night + 1, hours=3, minutes=5), "DeviceLockStatus", "Unlocked")
    return p


def day_of(n):
    return (DAY + timedelta(days=n)).date()


@needs_template
def test_quiet_hours_from_a_routine_a_break_listed_and_an_unobserved_night_kept_apart(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = routine_phone(break_night=10, unseen_night=20).make(c, case)
        build(engine, ext)
        with engine.connect() as c:
            out = grid.grid(c, [str(ext)], {}, day_of(0), day_of(DAYS - 1), "UTC")
        q = out["quiet_hours"]
        assert (q["start"], q["end"], q["hours"]) == (23, 8, 9)
        assert q["qualifying_days"] == DAYS
        assert [b["date"] for b in out["breaks"]] == [day_of(10).isoformat()]
        item = out["breaks"][0]["items"]
        assert len(item) == 1 and item[0]["instant_utc"].hour == 3 and item[0]["strength"] == "strong"
        assert [n["date"] for n in out["not_observed"]] == [day_of(20).isoformat()]  # not a break
        cell = out["days"][0]["hours"][9]
        assert cell["state"] == "interaction" and cell["match"] == 1 and cell["counts"]["strong"] == 1
        assert out["days"][0]["hours"][2]["state"] == "data_no_interaction"
        assert len(out["days"]) == DAYS and all(len(d["hours"]) == 24 for d in out["days"])


@needs_template
def test_a_phone_observed_but_never_used_has_no_quiet_period_rather_than_a_24_hour_one(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            p = Phone()
            for d in range(14):
                p.every(DAY + timedelta(days=d), DAY + timedelta(days=d + 1), 20, p.device_event, "DisplayOnOff")
            p.device_event(DAY + timedelta(days=3, hours=12), "DeviceLockStatus", "Unlocked")  # 1 use in 14 days
            ext = p.make(c, case)
        build(engine, ext)
        with engine.connect() as c:
            out = grid.grid(c, [str(ext)], {}, day_of(0), day_of(13), "UTC")
        q = out["quiet_hours"]
        assert q["start"] is None and q["reason"] == "rarely_used"
        assert "rarely used" in q["message"] and "14 days" in q["message"]
        assert out["breaks"] == [] and out["not_observed"] == []


def test_quiet_hours_rules_without_a_database():
    def day(active_hours, observed=24):
        return {"hours": [{"hour": h, "state": "interaction" if h in active_hours else
                           ("data_no_interaction" if h < observed else "no_data"), "match": 1 if h in active_hours
                           else 0} for h in range(24)]}
    assert grid.quiet_hours([day(set(range(24)))] * 5)["reason"] == "no_run"
    assert grid.quiet_hours([day({1}, observed=10)] * 5)["reason"] == "no_observed_days"
    q = grid.quiet_hours([day(set(range(6, 22)))] * 10)
    assert (q["start"], q["end"], q["hours"]) == (22, 6, 8)


@needs_template
def test_grid_over_http_states_the_zone_and_refuses_a_bad_filter(hooks):
    from tests.pattern_pg import api_client
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            p = Phone()
            p.every(DAY, DAY + timedelta(hours=3), 20, p.device_event, "DisplayOnOff")
            ext = p.make(c, case)
        build(engine, ext)
        subj = json.dumps({"kind": "extraction", "extraction_id": str(ext)})
        with api_client(engine, case) as client:
            r = client.get("/api/pattern/%s/grid" % case, params={"subject": subj, "start_date": "2023-03-14",
                                                                  "end_date": "2023-03-15"})
            assert r.status_code == 200
            body = r.json()
            assert body["zone"] == "UTC" and body["zone_note"] == "Phone time zone not recorded"
            assert body["days"][0]["hours"][0]["state"] == "data_no_interaction"
            assert body["quiet_hours"]["reason"] == "no_observed_days"
            assert client.get("/api/pattern/%s/grid" % case, params={
                "subject": subj, "start_date": "2023-03-14", "end_date": "2023-03-15",
                "min_strength": "huge"}).status_code == 400
            r = client.get("/api/pattern/%s/grid" % case, params={
                "subject": subj, "start_date": "2023-03-12", "end_date": "2023-03-12", "zone": "America/New_York"})
            assert len(r.json()["days"][0]["hours"]) == 23  # the spring clock change
