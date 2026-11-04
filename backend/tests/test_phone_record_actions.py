"""03 section 3.6 items 7 and 8 through the HTTP routes: what the record panel's actions read. Show on Timeline is
offered for a record with a timeline entry and lands on it (the lens locate gives the same day and offset its
window lists); Show on Map only when positioned; Correct this value over exactly the values the correction route
accepts, the original kept. Synthetic phones only."""
from __future__ import annotations

import uuid

from sqlalchemy import text

from tests.phone_pg import needs_template
from tests.test_phone_screens_router import api  # noqa: F401 - the shared synthetic two-phone fixture

pytestmark = needs_template


def _detail(api, uid):  # noqa: F811
    r = api["client"].get(f"/api/phones/records/{uid}", params={"case_id": api["case"]})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_message_is_on_the_timeline_and_not_positioned(api):  # noqa: F811
    d = _detail(api, api["evs"][0]["record_uid"])
    assert d["on_timeline"] is True and d["position"] is None


def test_show_on_timeline_lands_on_the_row_the_lens_window_lists(api):  # noqa: F811
    cl, case = api["client"], api["case"]
    snap = cl.post("/api/phones/timeline/index", json={"case_id": case}).json()["snapshot"]
    for ev in api["evs"]:
        loc = cl.post("/api/phones/timeline/locate", json={"filter": {"case_id": case}, "snapshot": snap,
                                                         "record_uid": ev["record_uid"]})
        assert loc.status_code == 200, loc.text
        got = loc.json()
        w = cl.post("/api/phones/timeline/window", json={"filter": {"case_id": case}, "snapshot": snap,
                                                         "day": got["day"], "offset": got["offset"], "limit": 1}).json()
        assert w["items"][0]["record_uid"] == ev["record_uid"], (got, w["items"][0])
    # a record of another case, a stale result, and a lens whose kinds leave the record out each say so
    other = cl.post("/api/phones/timeline/locate", json={"filter": {"case_id": case}, "snapshot": snap,
                                                       "record_uid": api["other_evs"][0]["record_uid"]})
    assert other.status_code == 404
    assert cl.post("/api/phones/timeline/locate", json={"filter": {"case_id": case}, "snapshot": "x",
                                                        "record_uid": api["evs"][0]["record_uid"]}).status_code == 409
    calls = cl.post("/api/phones/timeline/index", json={"case_id": case, "lens_kinds": ["calls"]}).json()["snapshot"]
    off = cl.post("/api/phones/timeline/locate", json={"filter": {"case_id": case, "lens_kinds": ["calls"]},
                                                     "snapshot": calls, "record_uid": api["evs"][0]["record_uid"]})
    assert off.status_code == 404 and "kinds shown" in off.json()["detail"]


def test_show_on_map_is_offered_only_for_a_positioned_record(api):  # noqa: F811
    uid = api["evs"][1]["record_uid"]
    with api["engine"].begin() as c:
        ext = c.execute(text("SELECT extraction_id FROM pv_comm_event WHERE record_uid = :u"), {"u": uid}).scalar()
        gen = c.execute(text("SELECT generation FROM phone_interpretation_state WHERE extraction_id = :e"),
                        {"e": ext}).scalar()
        # a message that shares a location carries its own position (the Map's layer reads the same view)
        c.execute(text(
            "INSERT INTO phone_location_points (case_id, extraction_id, document_index, ordinal, record_uid, "
            "root_record_uid, locator, model_type, generation, point_uid, coordinate_record_uid, lat, lon, "
            "accuracy_basis, source_kind) VALUES (:c, :e, 0, 9000, :u, :u, :l, 'InstantMessage', :g, :p, :u, 38.9, "
            "-77.03, 'none', 'shared_location')"),
            {"c": api["case"], "e": ext, "u": uid, "l": "%s/0/p9000" % ext, "g": gen, "p": uuid.uuid4()})
    d = _detail(api, uid)
    assert d["position"] and d["position"]["lat"] == 38.9 and d["position"]["lon"] == -77.03


def test_correctable_values_are_the_ones_the_correction_route_accepts_and_keep_the_original(api):  # noqa: F811
    cl, case = api["client"], api["case"]
    uid = api["evs"][0]["record_uid"]
    d = _detail(api, uid)
    assert d["correctable"], "a message's body is a text value"
    v = next(x for x in d["correctable"] if x["value_type"] == "String")
    assert v["corrected_text"] is None and v["machine_text"] is not None
    r = cl.post(f"/api/phones/records/{uid}/corrections", json={
        "case_id": case, "field_path": v["field_path"], "value_index": v["value_index"],
        "corrected_text": "synthetic corrected", "reason": "synthetic", "expected_revision": v["revision"]})
    assert r.status_code == 200, r.text
    after = next(x for x in _detail(api, uid)["correctable"]
                 if (x["field_path"], x["value_index"]) == (v["field_path"], v["value_index"]))
    assert after["machine_text"] == v["machine_text"] and after["corrected_text"] == "synthetic corrected"
    assert after["revision"] != v["revision"]
    # the revision it was shown is now stale: a second save on the old revision is refused
    again = cl.post(f"/api/phones/records/{uid}/corrections", json={
        "case_id": case, "field_path": v["field_path"], "value_index": v["value_index"],
        "corrected_text": "other", "reason": "synthetic", "expected_revision": v["revision"]})
    assert again.status_code == 409


def _point(c, case, ext, gen, ordinal, instant, lat=38.9, lon=-77.03):
    c.execute(text(
        "INSERT INTO phone_location_points (case_id, extraction_id, document_index, ordinal, record_uid, "
        "root_record_uid, locator, model_type, generation, point_uid, coordinate_record_uid, lat, lon, "
        "accuracy_basis, source_kind, instant) VALUES (:c, :e, 0, :o, :u, :u, :l, 'Location', :g, :p, :u, :lat, :lon, "
        "'none', 'device_location', :t)"),
        {"c": case, "e": ext, "o": ordinal, "u": uuid.uuid4(), "l": "%s/0/p%d" % (ext, ordinal), "g": gen,
         "p": uuid.uuid4(), "t": instant, "lat": lat, "lon": lon})


def test_show_on_map_from_a_message_lists_the_hour_around_it_or_says_how_far_the_nearest_is(api):  # noqa: F811
    from datetime import timedelta
    cl, case = api["client"], api["case"]
    uid = api["evs"][0]["record_uid"]
    assert _detail(api, uid)["message_dated"] is True
    with api["engine"].begin() as c:
        ext, t = c.execute(text("SELECT extraction_id, sort_instant FROM pv_comm_event WHERE record_uid = :u"),
                           {"u": uid}).first()
        gen = c.execute(text("SELECT generation FROM phone_interpretation_state WHERE extraction_id = :e"),
                        {"e": ext}).scalar()
        _point(c, case, ext, gen, 9100, t - timedelta(hours=3, minutes=12))
    r = cl.get("/api/phones/map/near", params={"case_id": case, "record_uid": uid})
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["within"] == 0 and got["nearest"]["gap_words"] == "3 h 12 min earlier"
    assert got["words"] == "No positioned records within 1 hour of this message. The nearest is 3 h 12 min earlier."
    with api["engine"].begin() as c:
        _point(c, case, ext, gen, 9101, t + timedelta(minutes=59), lat=38.95, lon=-77.0)
        _point(c, case, ext, gen, 9102, t - timedelta(minutes=30), lat=38.85, lon=-77.1)
        _point(c, case, ext, gen, 9103, t + timedelta(minutes=61))  # just outside the hour
    got = cl.get("/api/phones/map/near", params={"case_id": case, "record_uid": uid}).json()
    assert got["within"] == 2 and got["nearest"] is None
    assert got["bbox"] == [-77.1, 38.85, -77.0, 38.95]
    assert got["words"] == "2 positioned records on the same phone within 1 hour of this message."
    # the map layer, given the same phone and hour, counts the same records
    m = cl.post("/api/phones/map/summary", json={"case_id": case, "filter": {
        "phones": [str(ext)], "from_instant": got["from_instant"], "to_instant": got["to_instant"],
        "include_no_time": False}}).json()
    assert m["positioned"] == got["within"]
    other = cl.get("/api/phones/map/near", params={"case_id": case, "record_uid": api["other_evs"][0]["record_uid"]})
    assert other.status_code == 404
