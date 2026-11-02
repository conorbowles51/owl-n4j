"""03 section 13 (G-1 to G-4): the Case Map phone layer. Invented coordinates only. Needs the PostgreSQL template."""
from __future__ import annotations

import socket
import uuid

import pytest
from sqlalchemy import text

from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import GEN, at, phone

pytestmark = needs_template


def _points(c, case, ext, coords, accuracy=None, start=1000):
    for n, (lat, lon) in enumerate(coords):
        uid = uuid.uuid4()
        c.execute(text(
            "INSERT INTO phone_record_summaries (case_id, extraction_id, document_index, ordinal, record_uid, "
            "root_record_uid, locator, model_type, generation, is_top_level, title, first_instant, has_time, "
            "has_point) VALUES (:c, :e, 0, :o, :u, :u, :l, 'Location', :g, true, 'synthetic', :i, true, true)"),
            {"c": case, "e": ext, "o": start + n, "u": uid, "l": "%s/0/p%d" % (ext, start + n), "g": GEN,
             "i": at(2023, 3, 14, 12)})
        c.execute(text(
            "INSERT INTO phone_location_points (case_id, extraction_id, document_index, ordinal, record_uid, "
            "root_record_uid, locator, model_type, generation, point_uid, coordinate_record_uid, lat, lon, "
            "accuracy_m, accuracy_basis, source_kind, instant) VALUES (:c, :e, 0, :o, :u, :u, :l, 'Location', :g, "
            ":p, :u, :lat, :lon, :a, :b, 'device_location', :i)"),
            {"c": case, "e": ext, "o": start + n, "u": uid, "l": "%s/0/p%d" % (ext, start + n), "g": GEN,
             "p": uuid.uuid4(), "lat": lat, "lon": lon, "a": accuracy, "b": "recorded" if accuracy else "none",
             "i": at(2023, 3, 14, 12)})


def _unplaced(c, case, ext, model, n, start=90000):
    for k in range(n):
        uid = uuid.uuid4()
        c.execute(text(
            "INSERT INTO phone_record_summaries (case_id, extraction_id, document_index, ordinal, record_uid, "
            "root_record_uid, locator, model_type, generation, is_top_level, title, has_time, has_point) VALUES "
            "(:c, :e, 0, :o, :u, :u, :l, :m, :g, true, 'synthetic', false, false)"),
            {"c": case, "e": ext, "o": start + k, "u": uid, "l": "%s/0/x%d" % (ext, start + k), "m": model, "g": GEN})


@pytest.fixture
def world():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, other = make_case(c), make_case(c)
            ext, _ = phone(c, case, label="C1", device_zone="America/New_York")
            _points(c, case, ext, [(40.0 + k * 0.0001, -74.0) for k in range(3)])  # no accuracy
            _points(c, case, ext, [(41.0, -73.0)], accuracy=25, start=2000)
            _unplaced(c, case, ext, "CellTower", 4)
            _unplaced(c, case, ext, "WirelessNetwork", 2, start=95000)
        yield {"engine": engine, "case": case, "other": other, "ext": ext}


def test_g2_a_point_without_accuracy_says_so_and_one_with_accuracy_has_its_radius(world):
    from services.phone import map as M
    with world["engine"].connect() as c:
        out = M.points(c, world["case"], [-180, -90, 180, 90], 3)
    assert out["total"] == 4 and not out["clustered"] and out["limits"] == []
    words = sorted(i["accuracy_words"] for i in out["items"])
    assert words == ["Accuracy not recorded"] * 3 + ["Within 25 m"]
    assert {i["phone_label"] for i in out["items"]} == {"C1"}
    assert all(i["time"]["full"] for i in out["items"])


def test_g1_above_the_cap_clusters_sum_to_the_total_and_say_so(world, monkeypatch):
    from services.phone import map as M
    monkeypatch.setattr(M, "MAP_POINTS_MAX", 2)
    with world["engine"].connect() as c:
        out = M.points(c, world["case"], [-180, -90, 180, 90], 3)
    assert out["clustered"] and sum(i["count"] for i in out["items"]) == out["total"] == 4
    assert out["limits"][0]["message"].startswith("4 positions in this view are grouped into ")


def test_g3_records_without_a_position_are_counted_and_nothing_goes_to_a_network(world, monkeypatch):
    from services.phone import map as M

    def no_network(*a, **k):
        raise AssertionError("the phone map made a network request")
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    with world["engine"].connect() as c:
        s = M.summary(c, world["case"])
    assert s["positioned"] == 4 and s["total"] == 10
    reasons = {m["model_type"]: m["count"] for m in s["not_positionable"]}
    assert reasons == {"CellTower": 4, "WirelessNetwork": 2}
    assert s["by_source"] == {"device_location": 4}


def test_g4_another_case_sees_nothing_and_graph_locations_are_not_used(world):
    from services.phone import map as M
    with world["engine"].connect() as c:
        assert M.points(c, world["other"], [-180, -90, 180, 90], 3)["total"] == 0
        assert M.summary(c, world["other"])["positioned"] == 0
    src = open(M.__file__).read()
    assert "graph" not in src.split('"""', 2)[2]  # the layer reads pv_location_point only
