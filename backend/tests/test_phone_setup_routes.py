"""The routes behind the Needs a decision box, the blur default and the Significant toggle (07 sections 4.11, 5, 7.3
XF-11). Synthetic phones only."""
from __future__ import annotations

import uuid

from sqlalchemy import text

from tests.phone_pg import needs_template
from tests.test_phone_screens_router import ANA, BEN, api  # noqa: F401 (fixture)

pytestmark = needs_template


def _significant(engine, case, key):
    with engine.begin() as c:
        c.execute(text("INSERT INTO significant_entities (id, case_id, entity_key) VALUES (:i, :c, :k)"),
                  {"i": uuid.uuid4(), "c": case, "k": key})


def _index(c, case, **more):
    r = c.post("/api/phones/streams/index", json=dict({"case_id": case}, **more))
    assert r.status_code == 200, r.text
    return r.json()


def test_setup_state_and_describe_read_true_counts(api):
    c, case, ext = api["client"], api["case"], api["ext"]
    r = c.get("/api/phones/%s/setup" % ext, params={"case_id": case})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["region"]["assumed"] is True and s["zone"]["zone"] == "America/New_York"
    assert {"code": "MX", "name": "Mexico"} in s["regions"]
    r = c.post("/api/phones/%s/setup/describe" % ext, json={"case_id": case, "kind": "clock_offset", "offset_seconds": 60})
    assert r.status_code == 200, r.text
    assert c.post("/api/phones/%s/setup/describe" % ext, json={"case_id": case, "kind": "device_zone",
                                                               "value": "Mars/Olympus"}).status_code == 422
    assert c.get("/api/phones/%s/setup" % uuid.uuid4(), params={"case_id": case}).status_code == 404


def test_each_setting_needs_a_reason_and_a_known_value(api):
    c, case, ext = api["client"], api["case"], api["ext"]
    assert c.post("/api/phones/%s/default-region" % ext, json={"case_id": case, "value": "MX", "reason": ""}).status_code == 422
    assert c.post("/api/phones/%s/default-region" % ext, json={"case_id": case, "value": "ZZ", "reason": "x"}).status_code == 422
    assert c.post("/api/phones/%s/device-zone" % ext, json={"case_id": case, "value": "nowhere", "reason": "x"}).status_code == 422
    r = c.post("/api/phones/%s/default-region" % ext, json={"case_id": case, "value": "MX", "reason": "a Mexican phone"})
    assert r.status_code == 200, r.text
    with api["engine"].connect() as conn:
        row = conn.execute(text("SELECT decision, actor_name, reason, before, after FROM adjudications WHERE subject_id = :e "
                                "AND decision = 'set_phone_default_region'"), {"e": ext}).one()
    assert row.reason == "a Mexican phone" and row.before["default_region"] is None and row.after["default_region"] == "MX"
    # the same value again changes nothing and is refused
    assert c.post("/api/phones/%s/default-region" % ext, json={"case_id": case, "value": "MX", "reason": "x"}).status_code == 422


def test_a_persons_own_blur_choice_is_theirs_and_can_be_cleared(api):
    c, case = api["client"], api["case"]
    assert c.get("/api/phones/settings", params={"case_id": case}).json()["own_media_blur"] is None
    r = c.put("/api/phones/settings/my-blur", json={"case_id": case, "blur": False})
    assert r.status_code == 200 and r.json()["own_media_blur"] is False
    assert r.json()["media_blur"]["default_on"] is False  # the case default is untouched
    r = c.put("/api/phones/settings/my-blur", json={"case_id": case, "blur": None})
    assert r.json()["own_media_blur"] is None


def test_significant_counts_agree_with_the_records_the_toggle_shows(api):
    c, case, engine = api["client"], api["case"], api["engine"]
    s = c.get("/api/phones/significant", params={"case_id": case}).json()
    assert s["significant"] == 0 and s["total"] >= 2 and s["words"].startswith("Phone screens show all records. 0 of ")
    everything = _index(c, case)
    assert everything["counts"]["events"] == 3
    assert _index(c, case, significant_only=True)["counts"]["events"] == 0  # nothing marked: an empty list, not all

    _significant(engine, case, "phone-identity:" + ANA)
    s = c.get("/api/phones/significant", params={"case_id": case}).json()
    assert s["significant"] == 1 and s["words"].endswith("1 of %d phone identities is significant." % s["total"])
    only = _index(c, case, significant_only=True)
    assert only["counts"]["events"] == 2  # the two messages with ANA; BEN's is left out and the total says so
    threads = c.post("/api/phones/conversations/threads", json={"case_id": case, "significant_only": True}).json()
    assert sum(t["event_count"] if "event_count" in t else t["events"] for t in threads["items"]) == 2
    assert _index(c, case)["counts"]["events"] == 3  # the screen without the toggle is unchanged


def test_a_snapshot_under_the_toggle_is_refused_after_the_manifest_changes(api):
    c, case, engine = api["client"], api["case"], api["engine"]
    _significant(engine, case, "phone-identity:" + ANA)
    first = _index(c, case, significant_only=True)["snapshot"]
    _significant(engine, case, "phone-identity:" + BEN)
    assert _index(c, case, significant_only=True)["snapshot"] != first
    assert _index(c, case)["snapshot"] == _index(c, case)["snapshot"]
