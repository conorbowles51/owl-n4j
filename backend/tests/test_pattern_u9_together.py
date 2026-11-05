"""04-U9 (cb-pol item H): together and apart. No cap, no SSID, one verdict function (C10).

Synthetic phones only. Opt-in PostgreSQL through ``LOUPE_TEST_PHONE_PG_TEMPLATE_URL``.
"""
from __future__ import annotations

import json
import time
from datetime import timedelta

from services.pattern_of_life import colocation
from services.pattern_of_life.places import haversine_m
from services.phone import registry
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.test_pattern_u4_availability import DAY, setup
from tests.test_pattern_u5_places import LAT, LON, PlacePhone, build
from tests.test_phone_mappings import hooks  # noqa: F401 (fixture)

M_PER_DEG_LAT = 111195.0


def obs(north_m=0.0, radius=None, at=DAY, end=None, offset="explicit"):
    return {"lat": LAT + north_m / M_PER_DEG_LAT, "lon": LON, "radius_m": radius, "start": at, "end": end or at,
            "offset_status": offset}


def test_the_verdict_rules():
    v = colocation.verdict(obs(0, 50), obs(120, 100))
    assert v["verdict"] == "compatible" and v["tight"] is True and abs(v["distance_m"] - 120) < 1
    v = colocation.verdict(obs(0, 100), obs(5000, 100))
    assert v["verdict"] == "separated" and v["dt_s"] == 0
    # 5 km apart but 4 minutes between them: 40 m/s allows 9.6 km, so not provably apart
    v = colocation.verdict(obs(0, 100), obs(5000, 100, at=DAY + timedelta(minutes=4)))
    assert v["verdict"] == "undetermined"
    # unknown radius: the stated assumed radius, marked
    v = colocation.verdict(obs(0, None), obs(1000, 100))
    assert v["verdict"] == "compatible" and v["assumed"] is True and v["tight"] is False
    assert v["radii_sum_m"] == 1100.0
    # an offset-less time never makes a pair separated, and is flagged
    v = colocation.verdict(obs(0, 100, offset="absent"), obs(5000, 100))
    assert v["verdict"] == "undetermined" and "offset_absent" in v["flags"]
    # intervals compared by overlap: dt is 0 inside, and a pair outside the window is not compared
    assert colocation.verdict(obs(0, 10, end=DAY + timedelta(hours=1)), obs(0, 10, at=DAY + timedelta(minutes=30)))[
        "dt_s"] == 0
    assert colocation.verdict(obs(0, 10), obs(0, 10, at=DAY + timedelta(minutes=8))) is None


def test_v1_contrast_cases():
    # v1 (origin/main cellebrite_intersection_service.py:105, :153): a fixed 250 m radius, accuracy ignored, so two
    # fixes 200 m apart with 10 m accuracy were "together". Here their areas (radius 20 m each) do not overlap and,
    # with no time between them, they could not have been in one place.
    assert colocation.verdict(obs(0, 20), obs(200, 20))["verdict"] == "separated"
    # v1 used a 600 s window (:106): fixes 8 minutes apart were compared; here the default window is 5 minutes.
    assert colocation.verdict(obs(0, 20), obs(0, 20, at=DAY + timedelta(minutes=8))) is None
    # v1 had only "together"; here apart and undetermined are verdicts with their basis
    assert {colocation.verdict(obs(0, 20), obs(d, 20))["verdict"] for d in (10, 5000)} == {"compatible", "separated"}


def test_the_sweep_keeps_every_pair():
    A = [obs(0, 10, at=DAY + timedelta(milliseconds=100 * i)) for i in range(500)]  # 50 s; B spans 245 s
    B = [obs(30, 10, at=DAY + timedelta(seconds=5 * j)) for j in range(50)]
    pairs = colocation.sweep_pairs(A, B)
    assert len(pairs) == 25000  # no cap (v1 loaded at most 20,000 events, :89)
    assert haversine_m(A[0]["lat"], A[0]["lon"], B[0]["lat"], B[0]["lon"]) < 31


def _phones(c, case, n_a, n_b, b_north=15, ssid_only=False):
    # accuracy 5 m doubles to a 10 m radius per fix (decision 20), so 15 m apart overlaps: every pair compatible
    a, b = PlacePhone(), PlacePhone()
    if ssid_only:
        a.wifi(DAY, ssid="SyntheticNet")
        b.wifi(DAY, ssid="SyntheticNet")
    for i in range(n_a):
        a.location(DAY + timedelta(milliseconds=100 * i), accuracy=5)
    for j in range(n_b):
        b.location(DAY + timedelta(seconds=5 * j), lat=LAT + b_north / M_PER_DEG_LAT, accuracy=5)
    return a.make(c, case), b.make(c, case)


@needs_template
def test_25000_pairs_over_http_all_returned_with_totals_and_episodes(hooks):
    from tests.pattern_pg import api_client
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ea, eb = _phones(c, case, 500, 50)
        build(engine, ea)
        build(engine, eb)
        body = {"subjects": [{"kind": "extraction", "extraction_id": str(ea)},
                             {"kind": "extraction", "extraction_id": str(eb)}],
                "start": (DAY - timedelta(hours=1)).isoformat(), "end": (DAY + timedelta(hours=1)).isoformat()}
        with api_client(engine, case) as client:
            r = client.post("/api/pattern/%s/together" % case, json=body)
            assert r.status_code == 200
            out = r.json()
            assert out["total"] == 25000 and out["counts"]["compatible"] == 25000 and out["returned"] == 1000
            assert out["episodes"] == [dict(out["episodes"][0], kind="together", breadth="tight", items=25000)]
            seen, cursor = out["returned"], out["next_cursor"]
            while cursor is not None:
                page = client.get("/api/pattern/%s/together/%s" % (case, out["id"]), params={"cursor": cursor}).json()
                seen += page["returned"]
                cursor = page["next_cursor"]
            assert seen == 25000


@needs_template
def test_an_ssid_alone_never_makes_an_item(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ea, eb = _phones(c, case, 0, 0, ssid_only=True)
        build(engine, ea)
        build(engine, eb)
        with engine.begin() as c:
            rid = colocation.create_run(c, case, {"kind": "extraction", "extraction_id": str(ea)},
                                        {"kind": "extraction", "extraction_id": str(eb)}, [str(ea)], [str(eb)],
                                        DAY - timedelta(hours=1), DAY + timedelta(hours=1), {}, "t@x.test")
            counts = colocation.execute_run(c, rid)
        assert counts["pairs"] == 0


@needs_template
def test_a_large_run_answers_202_and_finishes_in_the_background(hooks, monkeypatch):
    from tests.pattern_pg import api_client
    import postgres.session as ps
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ea, eb = _phones(c, case, 20, 4)
        build(engine, ea)
        build(engine, eb)
        monkeypatch.setattr(colocation, "BACKGROUND_PAIRS", 10)
        monkeypatch.setattr(ps, "_get_background_engine", lambda: engine)
        body = {"subjects": [{"kind": "extraction", "extraction_id": str(ea)},
                             {"kind": "extraction", "extraction_id": str(eb)}],
                "start": (DAY - timedelta(hours=1)).isoformat(), "end": (DAY + timedelta(hours=1)).isoformat()}
        with api_client(engine, case) as client:
            r = client.post("/api/pattern/%s/together" % case, json=body)
            assert r.status_code == 202 and r.json()["estimated_pairs"] == 80
            rid = r.json()["run_id"]
            for _ in range(100):
                page = client.get("/api/pattern/%s/together/%s" % (case, rid)).json()
                if page["status"] == "done":
                    break
                time.sleep(0.1)
            assert page["status"] == "done" and page["total"] == 80


def test_the_radius_and_speed_allowed_decide_a_pair():
    """cb-statements-rest D: the screen's allowances change the verdict; air travel can undo a 'separated'."""
    from datetime import datetime, timedelta, timezone

    from services.pattern_of_life import colocation
    t = datetime(2024, 1, 1, tzinfo=timezone.utc)
    deg_km = 1 / 111.195
    near = {"lat": 51.0, "lon": 0.0, "radius_m": None, "start": t, "end": t, "offset_status": "explicit"}
    a = dict(near)
    b = dict(near, lat=51.0 + 1.5 * deg_km, radius_m=None)
    assert colocation.verdict(a, b)["verdict"] == "compatible"  # 1.5 km apart, 1,000 m assumed on each side
    assert colocation.verdict(a, b, {"assumed_radius_m": 500.0})["verdict"] == "separated"
    far = dict(near, lat=51.0 + 20 * deg_km, radius_m=50.0, start=t + timedelta(seconds=120), end=t + timedelta(seconds=120))
    here = dict(near, radius_m=50.0)
    assert colocation.verdict(here, far)["verdict"] == "separated"  # 20 km in 2 minutes is over 144 km/h
    assert colocation.verdict(here, far, {"max_speed_mps": 250.0})["verdict"] == "undetermined"  # not over 900 km/h
