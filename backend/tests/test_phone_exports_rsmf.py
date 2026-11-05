"""03 section 12.4 and E-6: the RSMF export, checked against Relativity's published RSMF 2.0.0 schema
(``services/phone/exports/rsmf_spec``). Synthetic data only; needs the PostgreSQL template."""
from __future__ import annotations

import hashlib
import json

import pytest
from sqlalchemy import text

from services.phone.exports import rsmf
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

pytest.importorskip("jsonschema")
OWNER, ANA, BEN = "phone:+12025550100", "phone:+12025550143", "phone:+12025550188"


def msg(instant, sender, recips, body="hello", **kw):
    parties = [(sender, "sender", sender == OWNER, None, None)] + [(r, "recipient", r == OWNER, None, None)
                                                                    for r in recips]
    return dict(kind="message", instant=instant, body=body, parties=parties,
                direction="outgoing" if sender == OWNER else "incoming", **kw)


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("LOUPE_PHONE_EXPORT_DIR", str(tmp_path))
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            ext, _ = phone(c, case, device_zone="America/New_York", events=[
                msg(at(2023, 3, 14, 15), ANA, [OWNER], body="first day", thread="t"),
                msg(at(2023, 3, 15, 15), OWNER, [ANA], body="second day", thread="t"),
                msg(at(2023, 3, 16, 12), ANA, [OWNER], body="third day", thread="t"),
                dict(kind="call", instant=at(2023, 3, 16, 13), body=None, thread=None, call_duration_s=42,
                     parties=[(OWNER, "caller", True, None, None), (BEN, "callee", False, None, None)])])
            user = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar()
        yield {"engine": engine, "case": case, "ext": ext, "user": user}


def _rsmf_export(w):
    from services.phone.exports import jobs
    with w["engine"].begin() as c:
        made = jobs.create(c, case_id=w["case"], user_id=w["user"], fmt="rsmf", source="stream",
                           filter_body={"zone": {"mode": "case"}}, options={"title": "Synthetic RSMF"})
    done = jobs.run_pending(w["engine"])
    assert done and done[0]["state"] == "done", done
    with w["engine"].connect() as c:
        state = jobs.get(c, w["case"], made["export_id"])
        path = jobs.file_of(c, w["case"], made["export_id"]).storage_path
    return state, open(path, "rb").read(), path


def test_e6_a_three_day_conversation_is_one_rsmf_file_with_every_event_and_it_validates(world):
    state, data, path = _rsmf_export(world)
    assert path.endswith(".rsmf") and state["file"]["filename"] == "Synthetic RSMF.rsmf"
    assert state["file"]["sha256"] == hashlib.sha256(data).hexdigest()
    headers, manifest, files = rsmf.read(data)
    rsmf.validate(manifest)  # Relativity's schema
    assert headers["X-RSMF-Version"] == "2.0.0" and headers["X-RSMF-EventCount"] == "4"
    assert headers["X-RSMF-BeginDate"] == "2023-03-14T15:00:00Z" and headers["X-RSMF-EndDate"] == "2023-03-16T13:00:00Z"
    events = manifest["events"]
    assert len(events) == 4 == state["counts"]["total"] == state["counts"]["rsmf"]["events"]
    assert [e["body"] for e in events if e["custom"][0]["value"] == "Message"] == ["first day", "second day",
                                                                                   "third day"]
    thread = {e["conversation"] for e in events if e["body"].endswith("day")}
    assert len(thread) == 1  # three days, one conversation, one file
    call = next(e for e in events if {"name": "Kind", "value": "Call"} in e["custom"])
    assert call["conversation"] not in thread and call["timestamp"] == "2023-03-16T13:00:00Z"
    assert {e["direction"] for e in events if e["body"].endswith("day")} == {"incoming", "outgoing"}
    assert all(any(c["name"] == "Record id" for c in e["custom"]) for e in events)
    assert all(c["platform"] for c in manifest["conversations"]) and manifest["participants"]
    assert files == {}


def test_every_attachment_is_listed_with_its_bytes_or_the_reason_it_is_not_included():
    rows = [{"record_uid": "00000000-0000-4000-8000-000000000001", "kind": "message", "app": "SyntheticChat",
             "phone": {"extraction_id": "e1", "label": "C1"}, "thread": {"thread_key": "t1", "title": "Synthetic"},
             "direction": "incoming", "time": {"instant": "2023-03-14T15:00:00+00:00"}, "body": "photo",
             "from": {"identity_key": "k1", "name": "Synthetic Ana", "identifier": None, "is_owner": False},
             "to": [], "flags": ["Deleted"], "copies": {"count": 1},
             "attachments": [{"file_uid": "f1", "filename": "a.jpg"}, {"file_uid": "f2", "filename": "gone.jpg"},
                             {"file_uid": None, "filename": "unresolved.jpg"}]}]
    blobs = {"f1": b"synthetic image bytes"}

    def read_file(uid):
        return (blobs[uid], None) if uid in blobs else (None, "The report refers to a file that is not in the "
                                                              "production.")
    data, counts = rsmf.build(rows, title="Synthetic", contains=["Synthetic."], read_file=read_file)
    headers, manifest, files = rsmf.read(data)
    ev = manifest["events"][0]
    assert len(ev["attachments"]) == 3 and ev["deleted"] is True
    assert counts["attachments"] == 3 and counts["attachments_included"] == 1 and counts["attachments_not_included"] == 2
    included = [a for a in ev["attachments"] if "size" in a]
    assert [files[a["id"]] for a in included] == [b"synthetic image bytes"]
    custom = {c["name"]: c["value"] for c in ev["custom"]}
    assert custom["File a.jpg SHA-256"] == hashlib.sha256(b"synthetic image bytes").hexdigest()
    assert "not in the production" in custom["File gone.jpg not included"]
    assert "unresolved.jpg" in json.dumps(ev)


def test_an_invalid_manifest_is_refused_before_anything_is_delivered():
    with pytest.raises(rsmf.RsmfInvalid):
        rsmf.validate({"version": "2.0.0", "participants": [], "conversations": [{"id": "c1"}], "events": []})
    with pytest.raises(rsmf.RsmfInvalid):
        rsmf.validate({"version": "2.0.0", "participants": [], "conversations": [],
                       "events": [{"type": "message", "timestamp": "14 March"}]})


def _reply_row(uid, line, *, replies=None, forward=None, thread="t1", sender="Synthetic Sender"):
    return {"record_uid": uid, "kind": "message", "phone": {"extraction_id": "e1", "label": "C1"}, "body": line,
            "thread": {"thread_key": thread, "title": "Synthetic"}, "app": "WhatsApp", "direction": "incoming",
            "time": {"instant": "2023-03-01T10:00:00+00:00"}, "from": {"name": sender, "identifier": None},
            "to": [], "flags": [], "attachments": [], "replies": replies or [], "forward": forward}


def _target(uid, thread="t1"):
    return {"record_uid": uid, "thread_key": thread, "from": {"name": "Synthetic Sender", "identifier": None},
            "time": "1 March 2023, 10:00", "excerpt": "the first message", "chars": 17}


def test_a_reply_points_at_its_parent_and_a_forward_says_who_first_wrote_it():
    from services.phone.exports import rsmf
    rows = [_reply_row("m1", "the first message"),
            _reply_row("m2", "my answer", replies=[{"kind": "reply", "state": "found", "original_id": "x",
                                                    "target": _target("m1")}]),
            _reply_row("m3", "passed on", forward={"original_sender": {"name": "First Author", "identifier": None},
                                                   "time_created": "1 March 2023, 09:00"}),
            _reply_row("m4", "elsewhere", replies=[{"kind": "reply", "state": "found", "original_id": "y",
                                                    "target": _target("gone")}]),
            _reply_row("m5", "missing", replies=[{"kind": "reply", "state": "not_in_extraction", "original_id": "z",
                                                  "target": None}]),
            _reply_row("m6", "quoted", replies=[{"kind": "quote", "state": "found", "original_id": "x",
                                                 "target": _target("m1")}]),
            _reply_row("m7", "across", thread="t2", replies=[{"kind": "reply", "state": "found", "original_id": "x",
                                                              "target": _target("m1")}])]
    data, _ = rsmf.build(rows, title="t", contains=[])
    events = {e["id"]: e for e in rsmf.read(data)[1]["events"]}

    def custom(uid, name):
        return next((c["value"] for c in events[uid]["custom"] if c["name"] == name), None)

    assert events["m2"]["parent"] == "m1"
    assert "Replying to Synthetic Sender" in custom("m2", "Reply")
    assert custom("m3", "Forward").startswith("Forwarded. First written by First Author")
    assert custom("m3", "Forward").endswith(", 1 March 2023, 09:00.")
    # the sender of this copy stays the participant: the first author is never made the sender
    people = {p["id"]: p["display"] for p in rsmf.read(data)[1]["participants"]}
    assert people[events["m3"]["participant"]].startswith("Synthetic Sender")
    assert not any("First Author" in p for p in people.values())
    # the schema allows a parent only in the same conversation of this file; the words carry the rest
    assert "parent" not in events["m4"] and "Replying to" in custom("m4", "Reply")
    assert "parent" not in events["m7"] and "Replying to" in custom("m7", "Reply")
    assert "not in this extraction" in custom("m5", "Reply")
    assert "parent" not in events["m6"] and custom("m6", "Reply").startswith("Quoting")
    assert "parent" not in events["m1"] and custom("m1", "Reply") is None


def test_the_bundled_schema_is_relativitys_unchanged():
    s = rsmf.schema()
    assert s["required"] == ["version", "participants", "conversations", "events"]
    assert s["properties"]["events"]["items"]["properties"]["type"]["enum"] == [
        "message", "disclaimer", "join", "leave", "history", "unknown"]
