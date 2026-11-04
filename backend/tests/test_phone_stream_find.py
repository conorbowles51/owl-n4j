"""Find in these results (03 section 3.1 rule 4, 07 section 4.8, test UX-2): the server searches the whole result,
not the rows in view, and gives each match's day and offset in exactly the order the windows list, with the true
total; a search with too many matches is refused with its count. Synthetic phones only."""
from __future__ import annotations

import uuid

from sqlalchemy import text

from tests.phone_pg import needs_template
from tests.phone_streams_fixture import GEN, at, bulk_events
from tests.test_phone_screens_router import api  # noqa: F401 - the shared synthetic fixture

pytestmark = needs_template


def _index(cl, f):
    r = cl.post("/api/phones/streams/index", json=f)
    assert r.status_code == 200, r.text
    return r.json()


def _row_at(cl, f, snap, day, offset):
    w = cl.post("/api/phones/streams/window", json={"filter": f, "snapshot": snap, "day": day, "offset": offset,
                                                    "limit": 1})
    assert w.status_code == 200, w.text
    return w.json()["items"][0]


def test_find_lists_every_match_at_the_row_the_window_shows(api):  # noqa: F811
    cl, case = api["client"], api["case"]
    f = {"case_id": case}
    snap = _index(cl, f)["snapshot"]
    r = cl.post("/api/phones/streams/find", json={"filter": f, "snapshot": snap, "query": "HELLO"})
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["total"] == 2 and len(got["matches"]) == 2
    for m in got["matches"]:
        assert _row_at(cl, f, snap, m["day"], m["offset"])["event_uid"] == m["event_uid"]
    undated = cl.post("/api/phones/streams/find", json={"filter": f, "snapshot": snap, "query": "undated"}).json()
    assert undated["total"] == 1 and undated["matches"][0]["day"] is None
    assert cl.post("/api/phones/streams/find", json={"filter": f, "snapshot": snap, "query": "nowhere"}).json() == {
        "query": "nowhere", "exact": False, "total": 0, "matches": []}
    assert cl.post("/api/phones/streams/find", json={"filter": f, "snapshot": "x", "query": "hello"}).status_code == 409
    assert cl.post("/api/phones/streams/find", json={"filter": f, "snapshot": snap, "query": "  "}).status_code == 422


def test_find_covers_rows_far_outside_the_viewport_and_newest_first(api):  # noqa: F811
    """UX-2: 2,000 messages on one day; the match is row 1,733, far past any window in view."""
    cl, case, engine = api["client"], api["case"], api["engine"]
    with engine.begin() as c:
        ext = c.execute(text("SELECT extraction_id FROM phone_comm_events WHERE case_id = :c LIMIT 1"),
                        {"c": case}).scalar()
        bulk_events(c, uuid.UUID(case), ext, 2000, start=at(2023, 4, 2, 0, 0), step_seconds=30)
        c.execute(text(
            "INSERT INTO phone_texts (case_id, extraction_id, document_index, ordinal, record_uid, root_record_uid, "
            "locator, model_type, generation, text_uid, body_path, field_name, field_path, value_index, value, "
            "value_folded, effective_value) SELECT :c, :e, 0, 100000 + i, md5('r' || :e || i)::uuid, "
            "md5('r' || :e || i)::uuid, 'bulk', 'InstantMessage', :g, md5('t' || :e || i)::uuid, '0', 'Body', 'Body', 0, "
            "CASE WHEN i = 1733 THEN 'needle synthetic' ELSE 'synthetic message ' || i END, "
            "CASE WHEN i = 1733 THEN 'needle synthetic' ELSE 'synthetic message ' || i END, "
            "CASE WHEN i = 1733 THEN 'needle synthetic' ELSE 'synthetic message ' || i END "
            "FROM generate_series(1, 2000) i"), {"c": uuid.UUID(case), "e": ext, "g": GEN})
    for sort in ("oldest_first", "newest_first"):
        f = {"case_id": case, "sort": sort}
        snap = _index(cl, f)["snapshot"]
        got = cl.post("/api/phones/streams/find", json={"filter": f, "snapshot": snap, "query": "needle"}).json()
        assert got["total"] == 1, got
        m = got["matches"][0]
        assert m["offset"] > 200  # beyond the first window
        assert _row_at(cl, f, snap, m["day"], m["offset"])["event_uid"] == m["event_uid"]
    # every "synthetic" body matches: the true total is stated and the order is the list's order
    f = {"case_id": case}
    snap = _index(cl, f)["snapshot"]
    all_ = cl.post("/api/phones/streams/find", json={"filter": f, "snapshot": snap, "query": "synthetic"}).json()
    assert all_["total"] == 2000 and len(all_["matches"]) == 2000
    offs = [m["offset"] for m in all_["matches"] if m["day"] == all_["matches"][0]["day"]]
    assert offs == sorted(offs)


def test_too_many_matches_is_refused_with_the_count(api, monkeypatch):  # noqa: F811
    from services.phone import streams
    monkeypatch.setattr(streams, "FIND_MAX", 1)
    cl, case = api["client"], api["case"]
    f = {"case_id": case}
    snap = _index(cl, f)["snapshot"]
    r = cl.post("/api/phones/streams/find", json={"filter": f, "snapshot": snap, "query": "hello"})
    assert r.status_code == 422 and r.json()["detail"].startswith("2 matches is more than one search lists (1).")
