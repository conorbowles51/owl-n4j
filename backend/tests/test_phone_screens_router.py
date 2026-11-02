"""03 sections 3.8, 3.11, 4.4 to 4.6 and A16 through the HTTP routes: the phone list, the case time zone, the stream
index and windows, the thread list, the record panel and the identity picker. Synthetic phones only."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

OWNER, ANA, BEN = "phone:+12025550100", "phone:+12025550143", "phone:+12025550188"
pytestmark = needs_template
RAISE = False


def msg(instant, sender, recips, body="hello", **kw):
    parties = [(sender, "sender", sender == OWNER, None, None)] + [(r, "recipient", r == OWNER, None, None)
                                                                    for r in recips]
    return dict(kind="message", instant=instant, body=body, parties=parties,
                direction="outgoing" if sender == OWNER else "incoming", **kw)


@pytest.fixture
def api():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from postgres.models.enums import GlobalRole
    from postgres.models.user import User
    from postgres.session import get_db
    from routers.phones import router
    from routers.users import get_current_db_user

    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            other_case = make_case(c)
            ext, evs = phone(c, case, device_zone="America/New_York", contacts={ANA: "Maria Lopez"},
                             events=[msg(at(2023, 3, 14, 19, 7, 12), ANA, [OWNER], thread="t"),
                                     msg(at(2023, 3, 15, 3, 30), OWNER, [ANA], thread="t"),
                                     msg(None, BEN, [OWNER], thread="u", body="undated")])
            oext, oevs = phone(c, other_case, label="C9", events=[msg(at(2023, 3, 14), ANA, [OWNER])])
            owner = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar()
            email = c.execute(text("SELECT email FROM users WHERE id = :u"), {"u": owner}).scalar()
        Session = sessionmaker(bind=engine)
        from services.phone import resolvers
        resolvers.register()  # as main.py does at start-up
        app = FastAPI()
        app.include_router(router)

        def db():
            s = Session()
            try:
                yield s
            finally:
                s.close()

        app.dependency_overrides[get_db] = db
        app.dependency_overrides[get_current_db_user] = lambda: User(
            id=owner, email=email, name="synthetic", global_role=GlobalRole.user)
        with TestClient(app, raise_server_exceptions=RAISE) as client:
            yield {"client": client, "case": str(case), "ext": str(ext), "evs": evs, "other_case": str(other_case),
                   "other_evs": oevs, "engine": engine}


def test_phone_list_counts_and_owner(api):
    c = api["client"]
    r = c.get("/api/phones", params={"case_id": api["case"]})
    assert r.status_code == 200, r.text
    p = r.json()["phones"][0]
    assert p["label"] == "C3" and p["counts"]["messages"] == 3 and p["state"] == "ingested"
    assert p["owner"]["is_owner"] and p["owner"]["identifier"]["display"] == "+1 202-555-0100"
    assert p["device_zone"] == "America/New_York"


def test_case_time_zone_is_validated_saved_and_audited(api):
    c = api["client"]
    assert c.put("/api/phones/settings", json={"case_id": api["case"], "time_zone": "Mars/Olympus"}).status_code == 422
    r = c.put("/api/phones/settings", json={"case_id": api["case"], "time_zone": "America/Chicago"})
    assert r.status_code == 200, r.text
    assert r.json()["time_zone"] == "America/Chicago" and r.json()["effective"]["basis"] == "case_setting"
    with api["engine"].connect() as conn:
        logged = conn.execute(text("SELECT details FROM system_logs WHERE action = 'Set phone data time zone'")).fetchall()
    assert len(logged) == 1


def test_stream_index_window_and_a_stale_snapshot(api):
    c = api["client"]
    f = {"case_id": api["case"], "zone": {"mode": "phone", "phone": api["ext"]}}
    idx = c.post("/api/phones/streams/index", json=f).json()
    assert idx["counts"]["events"] == 3 and idx["no_time_count"] == 1
    assert idx["zone"]["label"] == "Eastern Time"
    w = c.post("/api/phones/streams/window", json={"filter": f, "snapshot": idx["snapshot"], "day": "2023-03-14"})
    assert w.status_code == 200 and len(w.json()["items"]) == 2
    assert w.json()["items"][0]["line"] == "Maria Lopez (+1 202-555-0143) -> Owner of C3 (+1 202-555-0100)"
    nt = c.post("/api/phones/streams/window", json={"filter": f, "snapshot": idx["snapshot"], "day": None})
    assert [r["body"] for r in nt.json()["items"]] == ["undated"]
    stale = c.post("/api/phones/streams/window", json={"filter": f, "snapshot": "0" * 64, "day": "2023-03-14"})
    assert stale.status_code == 409 and stale.json()["detail"] == "stale_snapshot"
    loc = c.post("/api/phones/streams/locate", json={"filter": f, "snapshot": idx["snapshot"],
                                                     "event_uid": api["evs"][1]["event_uid"]})
    assert loc.json() == {"day": "2023-03-14", "offset": 1}
    threads = c.post("/api/phones/conversations/threads", json={"case_id": api["case"]}).json()
    assert threads["counts"]["threads"] == 2 and threads["complete"] is True


@pytest.mark.parametrize("participants,mode", [
    ([OWNER], "any"), ([ANA], "sent_by"), ([ANA, OWNER], "between"), (["phone:+19995550000"], "any"),
    (["other:digits:12345"], "sent_to"), (["app:whatsapp:jid:none@s.whatsapp.net"], "any"), ([BEN, ANA], "all"),
])
@pytest.mark.parametrize("expand", [False, True])
def test_every_participant_filter_loads(api, participants, mode, expand):
    """A16: by number, by contact, by identity, by person; identities with no number and numbers with no contact."""
    r = api["client"].post("/api/phones/streams/index", json={"case_id": api["case"], "participants": participants,
                                                              "participant_mode": mode,
                                                              "expand_person_identities": expand})
    assert r.status_code == 200, r.text


def test_a_failure_gives_the_error_wording_with_a_reference(api, monkeypatch):
    """A16 / 3.8: never 'unknown error'."""
    from services.phone import streams

    def boom(*a, **k):
        raise RuntimeError("synthetic")
    monkeypatch.setattr(streams, "index_comm_events", boom)
    r = api["client"].post("/api/phones/streams/index", json={"case_id": api["case"]})
    assert r.status_code == 500
    d = r.json()["detail"]
    assert d["message"] == "The message list could not be loaded." and d["text"].startswith(
        "The message list could not be loaded. Reference: ")


def test_a_record_of_another_case_is_not_found_and_a_filter_on_another_case_is_refused(api):
    """3.11."""
    c = api["client"]
    r = c.get("/api/phones/records/%s" % api["evs"][0]["record_uid"], params={"case_id": api["case"]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["extraction"]["label"] == "C3" and d["model_type"] == "InstantMessage"
    assert d["fields"][0]["name"] == "Body" and d["fields"][0]["values"][0]["text"] == "hello"
    assert d["source_row"]["available"] is False and d["files_absence"] == "This record does not refer to a file."
    assert "Body: hello" in d["as_text"]
    assert c.get("/api/phones/records/%s" % api["other_evs"][0]["record_uid"],
                 params={"case_id": api["case"]}).status_code == 404
    assert c.get("/api/phones/records/%s" % uuid.uuid4(), params={"case_id": api["case"]}).status_code == 404
    assert c.post("/api/phones/streams/index", json={"case_id": api["other_case"]}).status_code in (403, 404)


def test_identity_picker_finds_by_digits_and_by_a_phone_name(api):
    c = api["client"]
    by_digits = c.get("/api/phones/identities", params={"case_id": api["case"], "q": "2025550143"}).json()
    assert [i["identity_key"] for i in by_digits["items"]] == [ANA] and by_digits["total"] == 1
    assert by_digits["items"][0]["names"][0]["name"] == "Maria Lopez"
    by_name = c.get("/api/phones/identities", params={"case_id": api["case"], "q": "maria"}).json()
    assert by_name["total"] == 1
    everyone = c.get("/api/phones/identities", params={"case_id": api["case"], "limit": 2}).json()
    assert everyone["total"] == 3 and len(everyone["items"]) == 2 and everyone["next_cursor"] == 2
    assert everyone["items"][0]["identity_key"] in (ANA, OWNER)  # busiest first
    # review follow-up: folded like Search, and a backslash is text, not a pattern
    assert c.get("/api/phones/identities", params={"case_id": api["case"], "q": "LÓPEZ"}).json()["total"] == 1
    assert c.get("/api/phones/identities", params={"case_id": api["case"], "q": "\\"}).json()["total"] == 0
    assert c.get("/api/phones/identities", params={"case_id": api["case"], "q": "%"}).json()["total"] == 0


def test_marking_a_thread_reviewed_counts_it_keeps_earlier_marks_and_undo_restores(api):
    """07 section 6.1 review marks, J-13, J-13b: who, when, the count then, added since; undo."""
    c, case = api["client"], api["case"]
    tl = c.post("/api/phones/conversations/threads", json={"case_id": case}).json()
    assert tl["counts"]["not_reviewed"] == 2 and tl["counts"]["reviewed"] == 0
    key = next(t["thread_key"] for t in tl["items"] if t["event_count"] == 2)
    r = c.post("/api/phones/conversations/review", json={"case_id": case, "thread_key": key})
    assert r.status_code == 200, r.text
    assert r.json()["review"]["words"].startswith("Reviewed by synthetic on ") and "(2 messages)" in r.json()["review"]["words"]
    tl = c.post("/api/phones/conversations/threads", json={"case_id": case}).json()
    assert tl["counts"]["reviewed"] == 1
    with api["engine"].begin() as conn:  # a Replace that adds a message: the mark stays, "1 added since"
        conn.execute(text("UPDATE phone_threads SET event_count = event_count + 1 WHERE thread_key = :k"), {"k": key})
    row = next(t for t in c.post("/api/phones/conversations/threads", json={"case_id": case}).json()["items"]
               if t["thread_key"] == key)
    assert row["review"]["added_since"] == 1 and row["review"]["words"].endswith("; 1 added since")
    unrev = c.post("/api/phones/conversations/threads?sort=unreviewed", json={"case_id": case}).json()["items"]
    assert all(t["review"] is None or t["review"]["added_since"] > 0 for t in unrev)
    c.post("/api/phones/conversations/review", json={"case_id": case, "thread_key": key})
    with api["engine"].connect() as conn:
        anchor = conn.execute(text("SELECT source_anchor FROM case_task_links WHERE target_id = :k"), {"k": key}).scalar()
        logged = conn.execute(text("SELECT count(*) FROM system_logs WHERE action LIKE '%conversation review%' OR "
                                   "action = 'Marked a phone conversation reviewed'")).scalar()
    assert len(anchor["earlier"]) == 1 and anchor["record_count"] == 3 and "mapping_versions" in anchor
    assert logged == 2
    assert c.post("/api/phones/conversations/review/undo", json={"case_id": case, "thread_key": key}).json()["restored"]
    assert c.post("/api/phones/conversations/review/undo", json={"case_id": case, "thread_key": key}).json()["restored"] is False
    tl = c.post("/api/phones/conversations/threads", json={"case_id": case}).json()
    assert tl["counts"]["reviewed"] == 0
    assert c.post("/api/phones/conversations/review", json={"case_id": api["other_case"], "thread_key": key}).status_code in (403, 404)


def test_people_list_route(api):
    r = api["client"].post("/api/phones/conversations/participants", json={"case_id": api["case"]})
    assert r.status_code == 200 and r.json()["counts"]["participants"] == 3


def test_a_person_s_not_a_copy_decision_shows_the_copy_as_its_own_row_and_can_be_undone(api):
    """C-13: recorded with the person and reason (decision ledger and manual changes), then restorable."""
    from services.phone import copies
    from tests.phone_streams_fixture import phone as add_phone
    c, case = api["client"], api["case"]
    t0 = at(2023, 4, 1, 12)
    with api["engine"].begin() as conn:
        ext2, evs2 = add_phone(conn, case, label="C4", events=[msg(t0, ANA, [OWNER], body="same"),
                                                               msg(t0, ANA, [OWNER], body="same")])
        copies.assign(conn, ext2, 1)
    f = {"case_id": case, "phones": [str(ext2)]}
    assert c.post("/api/phones/streams/index", json=f).json()["counts"]["events"] == 1
    uid = evs2[1]["record_uid"]
    assert c.post(f"/api/phones/records/{uid}/not-a-copy", json={"case_id": case, "reason": ""}).status_code == 422
    r = c.post(f"/api/phones/records/{uid}/not-a-copy", json={"case_id": case, "reason": "Different sends"})
    assert r.status_code == 200, r.text
    assert c.post("/api/phones/streams/index", json=f).json()["counts"]["events"] == 2
    with api["engine"].connect() as conn:
        d = conn.execute(text("SELECT actor_name, reason, decision FROM adjudications WHERE subject_id::text = :r"),
                         {"r": str(uid)}).one()
        mc = conn.execute(text("SELECT count(*) FROM manual_changes WHERE kind = 'phone_copy'")).scalar()
    assert d.reason == "Different sends" and d.decision == "mark_not_duplicate" and d.actor_name and mc == 1
    r = c.post(f"/api/phones/records/{uid}/not-a-copy", json={"case_id": case, "reason": "Was right", "restore": True})
    assert r.status_code == 200, r.text
    assert c.post("/api/phones/streams/index", json=f).json()["counts"]["events"] == 1
