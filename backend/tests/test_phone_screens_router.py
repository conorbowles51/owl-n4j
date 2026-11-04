"""03 sections 3.8, 3.11, 4.4 to 4.6 and A16 through the HTTP routes: the phone list, the case time zone, the stream
index and windows, the thread list, the record panel and the identity picker. Synthetic phones only."""
from __future__ import annotations

import uuid
from urllib.parse import quote

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


def test_the_record_panel_offers_the_open_readings_of_its_type_on_its_phone(api):
    """07 J-8b: the panel lists each unchecked reading beside its mark; a checked one is not offered."""
    c, case, ext = api["client"], api["case"], api["ext"]
    with api["engine"].begin() as conn:
        mv = conn.execute(text(
            "INSERT INTO phone_mapping_versions (id, kind, name, version, content_sha256, content, status, origin) "
            "VALUES (gen_random_uuid(), 'type', 'SyntheticPanelTest', 1, repeat('0', 64), '{}', 'applied_unconfirmed', "
            "'human') RETURNING id")).scalar()
        for status, summary in (("open", "each instant message is read as a message"), ("confirmed", "checked")):
            conn.execute(text(
                "INSERT INTO phone_mapping_judgements (id, case_id, extraction_id, mapping_version_id, mapping_kind, "
                "mapping_name, rule_id, type_name, rule_part, summary, records_touched, status, generation) VALUES "
                "(gen_random_uuid(), :c, :e, :mv, 'type', 'InstantMessage', :r, 'InstantMessage', "
                "'record', :s, 3, :st, 1)"), {"c": case, "e": ext, "mv": mv, "r": "r-" + status, "s": summary,
                                               "st": status})
    uid = api["evs"][0]["record_uid"]
    d = c.get(f"/api/phones/records/{uid}", params={"case_id": case}).json()
    assert [r["sentence"].startswith("On C3") for r in d["readings"]] == [True]
    assert "each instant message is read as a message" in d["readings"][0]["sentence"]


def test_a_whole_result_is_frozen_as_one_selection_with_every_copy_and_resolves_only_in_its_case(api):
    """07 section 6.1 and lx-collect: Add to… on a whole filtered result stores one frozen phone_selection. Every
    record the filter matched is in it, copies included, so nothing is silently missing; it does not follow later
    changes, and another case cannot resolve it."""
    from postgres import link_types
    from services.phone import copies
    from tests.phone_streams_fixture import phone as add_phone
    c, case = api["client"], api["case"]
    t0 = at(2023, 4, 1, 12)
    with api["engine"].begin() as conn:
        ext2, evs2 = add_phone(conn, case, label="C4", events=[msg(t0, ANA, [OWNER], body="same"),
                                                               msg(t0, ANA, [OWNER], body="same"),
                                                               msg(at(2023, 4, 2), OWNER, [ANA], body="later")])
        copies.assign(conn, ext2, 1)
    f = {"case_id": case, "phones": [str(ext2)]}
    assert c.post("/api/phones/selections", json={"filter": f, "words": ""}).status_code == 422
    r = c.post("/api/phones/selections", json={"filter": f, "words": "Everything on C4"})
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["record_count"] == 3 and got["event_count"] == 2
    empty = c.post("/api/phones/selections", json={"filter": {**f, "text": {"query": "nothing like this"}},
                                                   "words": "None"})
    assert empty.status_code == 422 and "Nothing matches" in empty.json()["detail"]
    other = c.post("/api/phones/selections", json={"filter": {"case_id": api["other_case"]}, "words": "x"})
    assert other.status_code in (403, 404)
    from sqlalchemy.orm import Session
    with Session(api["engine"]) as db:
        target = link_types.resolve_phone_target(db, case, "phone_selection", got["id"])
        assert sorted(target.members) == sorted(e["record_uid"] for e in evs2)
        assert target.mapping_versions["phones"][0]["extraction_id"] == str(ext2)
        with pytest.raises(link_types.LinkTargetError):
            link_types.resolve_phone_target(db, api["other_case"], "phone_selection", got["id"])
        with pytest.raises(link_types.LinkTargetError):
            link_types.resolve_phone_target(db, case, "phone_selection", "not-an-id")


def test_phone_summary_numbers_equal_their_count_queries_and_the_lists_they_open(api):
    """P-1, P-5, P-7 and 07 J-2: each number is a count over the read views; a top person's count equals the list
    the link opens; the selection flags read "not stated" when the report does not state them; the verdict follows
    the reconciliation result."""
    c, case, ext = api["client"], api["case"], api["ext"]
    r = c.get(f"/api/phones/{ext}/profile", params={"case_id": case})
    assert r.status_code == 200, r.text
    p = r.json()
    with api["engine"].connect() as conn:
        msgs = conn.execute(text("SELECT count(*) FROM pv_comm_event WHERE extraction_id::text = :e AND kind = "
                                 "'message'"), {"e": ext}).scalar()
        recs = conn.execute(text("SELECT coalesce(e.record_count, (SELECT count(*) FROM phone_records r WHERE "
                                 "r.extraction_id = e.id)) FROM phone_extractions e WHERE e.id::text = :e"),
                            {"e": ext}).scalar()
    assert {d["signal"]: d["records"] for d in p["data_periods"]}["messages"] == msgs
    assert p["verdict"]["records"] == recs
    assert p["verdict"]["sentence"].startswith("Read, counts not checked: %s records, " % "{:,}".format(recs))
    assert p["verdict"]["sentence"].endswith("Nothing needs a decision.")
    with api["engine"].begin() as conn:
        conn.execute(text(
            "INSERT INTO phone_reconciliations (id, extraction_id, document_index, ran_at, counter_version, result, "
            "source_totals, captured_totals, differences, difference_count) VALUES (gen_random_uuid(), CAST(:e AS uuid), "
            "0, now() - interval '1 hour', 'synthetic', 'exact', CAST('{}' AS jsonb), CAST('{}' AS jsonb), "
            "CAST('[]' AS jsonb), 0)"), {"e": ext})
    p = c.get(f"/api/phones/{ext}/profile", params={"case_id": case}).json()
    assert p["verdict"]["sentence"].startswith("Read in full: %s records, " % "{:,}".format(recs))
    assert [s["verbatim"] for s in p["selection"]] == ["not stated"] * 4
    top = p["top_people"][0]
    key = top["label"]["identity_key"]
    idx = c.post("/api/phones/streams/index", json={"case_id": case, "phones": [ext], "participants": [key],
                                                    "participant_mode": "any"}).json()
    assert idx["counts"]["events"] == top["events"]
    assert f"people={quote(key, safe='')}" in top["link"]
    assert sum(m["messages"] for m in p["months"]) == msgs - 1  # the undated message has no month
    with api["engine"].begin() as conn:
        conn.execute(text(
            "INSERT INTO phone_reconciliations (id, extraction_id, document_index, ran_at, counter_version, result, "
            "source_totals, captured_totals, differences, difference_count) VALUES (gen_random_uuid(), CAST(:e AS uuid), "
            "0, now(), 'synthetic', 'differs', CAST('{\"files\": 9}' AS jsonb), CAST('{\"files\": 7}' AS jsonb), "
            "CAST('[]' AS jsonb), 1)"), {"e": ext})
    p = c.get(f"/api/phones/{ext}/profile", params={"case_id": case}).json()
    assert p["verdict"]["word"] == "Partly read" and p["verdict"]["sentence"].startswith("Partly read: ")
    assert p["completeness"]["documents"][0]["stated_vs_read"] == [
        {"what": "files", "stated": 9, "read": 7, "words": "Files: the report states 9, Loupe read 7."}]
    assert any(n["kind"] == "reconciliation" for n in p["needs"])
    assert c.get(f"/api/phones/{ext}/profile", params={"case_id": api["other_case"]}).status_code in (403, 404)


def test_phone_summary_counts_match_the_collapsed_lists_and_people_links_survive_the_url(api):
    """Review of item D: the deleted and app counts equal what the linked list shows with copies collapsed; a top
    person's link keeps the plus sign of a phone number through URL decoding; a phone whose report counts were never
    checked is not called read in full."""
    from urllib.parse import parse_qs, urlsplit
    c, case = api["client"], api["case"]
    with api["engine"].begin() as conn:
        ext, _ = phone(conn, uuid.UUID(case), label="C4", events=[
            msg(at(2023, 4, 1), ANA, [OWNER], thread="d", deleted_state="Deleted", dup="g1"),
            msg(at(2023, 4, 1), ANA, [OWNER], thread="d", deleted_state="Deleted", dup="g1"),
            msg(at(2023, 4, 2), ANA, [OWNER], thread="d", app="Signal")])
    p = c.get(f"/api/phones/{ext}/profile", params={"case_id": case}).json()

    def listed(**kw):
        return c.post("/api/phones/streams/index", json={"case_id": case, "phones": [str(ext)], **kw}).json()[
            "counts"]["events"]
    assert p["deleted"]["comm_events"] == listed(deleted_states=["Deleted", "Trash"]) == 1
    assert {a["app"]: a["events"] for a in p["apps"]} == {"WhatsApp": listed(apps=["WhatsApp"]),
                                                          "Signal": listed(apps=["Signal"])} == {"WhatsApp": 1,
                                                                                                 "Signal": 1}
    link = p["top_people"][0]["link"]
    assert parse_qs(urlsplit(link).query)["people"] == [ANA]  # "+" would otherwise decode to a space
    assert p["verdict"]["word"] == "Read, counts not checked"
    assert not p["verdict"]["sentence"].startswith("Read in full")


def test_setting_a_phones_owner_is_a_decision_with_its_reason_and_the_summary_shows_it(api):
    """03 section 7.3: Set the owner writes a set_phone_owner decision and a manual change; a number the phone
    does not show is refused; another case cannot set it; the summary's owner then reads as set by a person."""
    from services.phone import identities, readings
    saved = identities._hooks["owner_decision"]
    identities.register_owner_decision(readings.owner_decision)  # main.py installs it at start-up
    try:
        _set_owner(api)
    finally:
        identities._hooks["owner_decision"] = saved


def _set_owner(api):
    c, case, ext = api["client"], api["case"], api["ext"]
    url = f"/api/phones/{ext}/owner"
    assert c.post(url, json={"case_id": case, "identity_key": "phone:+12025550999", "reason": "synthetic"}
                  ).status_code == 422
    assert c.post(url, json={"case_id": case, "identity_key": ANA, "reason": " "}).status_code == 422
    assert c.post(url, json={"case_id": api["other_case"], "identity_key": ANA, "reason": "synthetic"}
                  ).status_code in (403, 404, 422)
    r = c.post(url, json={"case_id": case, "identity_key": ANA, "reason": "synthetic: owner's own statement"})
    assert r.status_code == 200, r.text
    with api["engine"].connect() as conn:
        d = conn.execute(text("SELECT before, after, reason FROM adjudications WHERE subject_id::text = :e AND "
                              "decision = 'set_phone_owner'"), {"e": ext}).one()
        mc = conn.execute(text("SELECT count(*) FROM manual_changes WHERE kind = 'phone_owner' AND case_id::text = "
                               ":c"), {"c": case}).scalar()
    assert d.after == {"owner_identity_keys": [ANA]} and d.before == {"owner_identity_keys": [OWNER]}
    assert mc == 1
    p = c.get(f"/api/phones/{ext}/profile", params={"case_id": case}).json()
    assert p["owner"]["decided"] and p["owner"]["keys"] == [ANA]
    assert p["owner"]["words"].startswith("Set by a person")


def test_naming_a_phone_is_a_decision_with_its_reason_and_every_screen_uses_the_name(api):
    """02 section 12.3: Name this phone writes a set_phone_label decision (the computed name kept as before) and a
    manual change; a blank name or reason and another case are refused; the phone list then shows the name."""
    c, case, ext = api["client"], api["case"], api["ext"]
    url = f"/api/phones/{ext}/label"
    before = {p["extraction_id"]: p["label"] for p in c.get("/api/phones", params={"case_id": case}).json()["phones"]}
    assert c.post(url, json={"case_id": case, "label": "   ", "reason": "synthetic"}).status_code == 422
    assert c.post(url, json={"case_id": case, "label": "X" * 41, "reason": "synthetic"}).status_code == 422
    assert c.post(url, json={"case_id": case, "label": "C9", "reason": " "}).status_code == 422
    assert c.post(url, json={"case_id": api["other_case"], "label": "C9", "reason": "synthetic"}
                  ).status_code in (403, 404, 422)
    r = c.post(url, json={"case_id": case, "label": "  C9  exhibit ", "reason": "synthetic: the exhibit label"})
    assert r.status_code == 200, r.text
    assert r.json()["label"] == "C9 exhibit"
    with api["engine"].connect() as conn:
        d = conn.execute(text("SELECT before, after, reason FROM adjudications WHERE subject_id::text = :e AND "
                              "decision = 'set_phone_label'"), {"e": ext}).one()
        mc = conn.execute(text("SELECT count(*) FROM manual_changes WHERE kind = 'phone_label' AND case_id::text = "
                               ":c"), {"c": case}).scalar()
    assert d.before == {"label": before[ext]} and d.after == {"label": "C9 exhibit"} and mc == 1
    after = {p["extraction_id"]: p["label"] for p in c.get("/api/phones", params={"case_id": case}).json()["phones"]}
    assert after[ext] == "C9 exhibit"


def test_comparing_two_phones_counts_on_both_and_only_on_each_with_the_reason(api):
    """07 J-16: messages matched across two phones by 05 5.3's keys (family, text, within 2 minutes); copies count
    once; a message outside the other phone's period says so; undated messages are counted, not compared; a person
    narrows both sides; a phone of another case is refused."""
    c, case, ext = api["client"], api["case"], api["ext"]
    with api["engine"].begin() as conn:
        ext2, _ = phone(conn, uuid.UUID(case), label="C5", events=[
            # C3's short "hello", received there, is sent on C5 28 s later (a short text pairs only when one side
            # sent it and the other received it, 05 5.3.3); it is reported twice on C5 (one copy group)
            msg(at(2023, 3, 14, 19, 7, 40), OWNER, [ANA], thread="t", dup="d1"),
            msg(at(2023, 3, 14, 19, 7, 40), OWNER, [ANA], thread="t", dup="d1"),
            msg(at(2023, 3, 14, 20), ANA, [OWNER], body="only here", thread="t"),
            msg(at(2024, 1, 1), BEN, [OWNER], body="later", thread="u")])
    r = c.get("/api/phones/compare", params={"case_id": case, "a": ext, "b": str(ext2)})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["a"]["label"] == "C3" and out["b"]["label"] == "C5" and out["a"]["no_time"] == 1
    assert out["kinds"]["message"] == {"both": 1, "only_a": 1, "only_a_outside": 0, "only_b": 2, "only_b_outside": 1}
    ana = c.get("/api/phones/compare", params={"case_id": case, "a": ext, "b": str(ext2), "person": ANA}).json()
    assert ana["kinds"]["message"] == {"both": 1, "only_a": 1, "only_a_outside": 0, "only_b": 1, "only_b_outside": 0}
    other = api["other_evs"] and c.get("/api/phones/compare", params={
        "case_id": case, "a": ext, "b": _other_ext(api)})
    assert other.status_code == 404
    assert c.get("/api/phones/compare", params={"case_id": case, "a": ext, "b": ext}).status_code == 422


def _other_ext(api):
    with api["engine"].connect() as conn:
        return str(conn.execute(text("SELECT id FROM phone_extractions WHERE case_id = CAST(:c AS uuid)"),
                                {"c": api["other_case"]}).scalar_one())


def test_between_a_person_and_each_phones_owner_and_the_counts_the_sentence_reads(api):
    """07 J-3: with one person, Between A and B takes B as the owner of each phone; the index says how many of the
    rows are messages and calls and on how many phones; the person's other linked identities are listed."""
    from services.phone.streams import PHONE_OWNER
    c, case = api["client"], api["case"]
    f = {"case_id": case, "participants": [ANA, PHONE_OWNER], "participant_mode": "between"}
    idx = c.post("/api/phones/streams/index", json=f)
    assert idx.status_code == 200, idx.text
    counts = idx.json()["counts"]
    assert counts["events"] == 2 and counts["messages"] == 2 and counts["calls"] == 0 and counts["phones"] == 1
    ben = c.post("/api/phones/streams/index", json={**f, "participants": [BEN, PHONE_OWNER]}).json()["counts"]
    assert ben["events"] == 1  # BEN's one message to the owner (undated, so counted with no time)
    linked = c.get("/api/phones/people/linked", params={"case_id": case, "key": ANA})
    assert linked.status_code == 200 and linked.json()["others"] == [] and linked.json()["numbers"] == 0


def test_media_derive_routes_queue_a_reading_and_refuse_in_words(api):
    """M-3 routes: a photo's reading is queued and listed; a text file is refused with words; another case's file
    is not found."""
    uid, txt = "00000000-0000-4000-8000-00000000d001", "00000000-0000-4000-8000-00000000d002"
    with api["engine"].begin() as c:
        for o, u, tag in ((9100, uid, "Image"), (9101, txt, "Text")):
            c.execute(text("INSERT INTO phone_files (extraction_id, document_index, ordinal, file_uid, local_path, "
                           "outcome, tags, body) VALUES (:e, 0, :o, :f, 'synthetic/x', 'no_hash', :t, "
                           "CAST('[]' AS jsonb))"), {"e": api["ext"], "o": o, "f": u, "t": tag})
    cl = api["client"]
    r = cl.post("/api/phones/media/%s/derive" % uid, json={"case_id": api["case"], "kind": "ocr"})
    assert r.status_code == 200 and r.json()["state"] == "queued" and r.json()["machine_generated"]
    listed = cl.get("/api/phones/media/%s/derived" % uid, params={"case_id": api["case"]}).json()["items"]
    assert [x["id"] for x in listed] == [r.json()["id"]]
    bad = cl.post("/api/phones/media/%s/derive" % txt, json={"case_id": api["case"], "kind": "ocr"})
    assert bad.status_code == 422 and "only from photos" in bad.json()["detail"]
    gone = cl.post("/api/phones/media/%s/derive" % uid, json={"case_id": api["other_case"], "kind": "ocr"})
    assert gone.status_code in (403, 404)  # refused either way: no access to that case, or no such file


def test_translation_routes_queue_a_message_and_a_conversation_list_them_and_refuse_in_words(api):
    """05 17.5 routes: a message is queued for translation (once), a conversation queues the rest with counts, the
    translations are read back by message, and another case's message is refused."""
    cl, ev = api["client"], api["evs"][0]["event_uid"]
    r = cl.post("/api/phones/messages/%s/translate" % ev, json={"case_id": api["case"]})
    assert r.status_code == 200 and r.json()["state"] == "queued" and r.json()["machine_generated"]
    again = cl.post("/api/phones/messages/%s/translate" % ev, json={"case_id": api["case"]})
    assert again.json()["id"] == r.json()["id"]
    thread = api["evs"][0]["thread_key"]
    t = cl.post("/api/phones/threads/translate", json={"case_id": api["case"], "thread_key": thread})
    assert t.status_code == 200 and t.json() == {"in_conversation": 2, "queued": 1, "left_out": {
        "no_text": 0, "already_translated": 0, "already_waiting": 1}}
    got = cl.post("/api/phones/translations", json={"case_id": api["case"], "keys": [e["event_uid"] for e in
                                                                                    api["evs"]]}).json()["items"]
    assert set(got) == {api["evs"][0]["event_uid"], api["evs"][1]["event_uid"]}
    assert {g["state"] for g in got.values()} == {"queued"}
    other = cl.post("/api/phones/messages/%s/translate" % api["other_evs"][0]["event_uid"],
                    json={"case_id": api["case"]})
    assert other.status_code == 404
    missing = cl.post("/api/phones/media/derived/%s/translate" % uuid.uuid4(), json={"case_id": api["case"]})
    assert missing.status_code == 404


def test_timeline_lens_routes_index_window_and_buckets(api):
    cl = api["client"]
    idx = cl.post("/api/phones/timeline/index", json={"case_id": api["case"]})
    assert idx.status_code == 200 and idx.json()["total"] == 3 and idx.json()["no_time_count"] == 1
    snap = idx.json()["snapshot"]
    day = idx.json()["items"][0]["day"]
    w = cl.post("/api/phones/timeline/window", json={"filter": {"case_id": api["case"]}, "snapshot": snap, "day": day})
    assert w.status_code == 200 and w.json()["items"][0]["kind"] == "message"
    b = cl.post("/api/phones/timeline/buckets", json={"filter": {"case_id": api["case"]}, "snapshot": snap,
                                                      "start": "2023-03-13T00:00:00Z", "end": "2023-03-17T00:00:00Z"})
    assert b.status_code == 200 and sum(x["count"] for x in b.json()["lanes"][0]["buckets"]) == 2
    stale = cl.post("/api/phones/timeline/window", json={"filter": {"case_id": api["case"]}, "snapshot": "x", "day": day})
    assert stale.status_code == 409
    bad = cl.post("/api/phones/timeline/index", json={"case_id": api["case"], "lens_kinds": ["nonsense"]})
    assert bad.status_code == 422


def test_a_replace_that_adds_messages_makes_a_reviewed_thread_partly_reviewed(api):
    """07 J-13b with a real Replace: the newer report has its own extraction id, so the same conversation has a new
    thread key. The mark follows it (by key, or by app, kind, chat type, title and people when one to one), keeps the
    count at review time, and the added message shows as "1 added since". An ambiguous match carries nothing."""
    c, case, engine = api["client"], api["case"], api["engine"]
    old_key = next(t["thread_key"] for t in c.post("/api/phones/conversations/threads", json={"case_id": case})
                   .json()["items"] if t["event_count"] == 2)
    assert c.post("/api/phones/conversations/review", json={"case_id": case, "thread_key": old_key}).status_code == 200
    with engine.begin() as conn:
        new_ext, _ = phone(conn, uuid.UUID(case), device_zone="America/New_York",
                           events=[msg(at(2023, 3, 14, 19, 7, 12), ANA, [OWNER], thread="t"),
                                   msg(at(2023, 3, 15, 3, 30), OWNER, [ANA], thread="t"),
                                   msg(at(2023, 3, 16, 9, 0), ANA, [OWNER], thread="t")])
        conn.execute(text("UPDATE phone_extractions SET standing = 'superseded', superseded_at = now() WHERE id = :o"),
                     {"o": api["ext"]})
        conn.execute(text("UPDATE phone_extractions SET supersedes_id = :o WHERE id = :n"),
                     {"o": api["ext"], "n": new_ext})
    new_key = "chat:%s:t" % new_ext

    def listed():
        tl = c.post("/api/phones/conversations/threads", json={"case_id": case}).json()
        return tl, {t["thread_key"]: t for t in tl["items"]}

    tl, rows = listed()
    assert old_key not in rows and rows[new_key]["review"]["added_since"] == 1
    assert "(2 messages); 1 added since" in rows[new_key]["review"]["words"]
    assert tl["counts"]["partly_reviewed"] == 1 and tl["counts"]["reviewed"] == 0

    renamed = "chat:%s:renamed" % new_ext  # a chat key built from a record id: matched by its people instead
    with engine.begin() as conn:
        for table in ("phone_threads", "phone_comm_events"):
            conn.execute(text("UPDATE %s SET thread_key = :r WHERE thread_key = :k" % table), {"r": renamed, "k": new_key})
    tl, rows = listed()
    assert rows[renamed]["review"]["added_since"] == 1

    assert c.post("/api/phones/conversations/review/undo", json={"case_id": case, "thread_key": renamed}).status_code == 200
    tl, rows = listed()
    assert rows[renamed]["review"] is None  # undone where it was made
    c.post("/api/phones/conversations/review", json={"case_id": case, "thread_key": old_key})

    with engine.begin() as conn:  # a second thread in the newer report with the same people: no one-to-one match
        conn.execute(text(
            "INSERT INTO phone_threads (case_id, extraction_id, interpretation_level, generation, thread_key, app, "
            "thread_kind, chat_type, title_in_record, party_identity_keys, event_count) SELECT case_id, extraction_id, "
            "interpretation_level, generation, :d, app, thread_kind, chat_type, title_in_record, party_identity_keys, 1 "
            "FROM phone_threads WHERE thread_key = :r"), {"d": "chat:%s:twin" % new_ext, "r": renamed})
    tl, rows = listed()
    assert rows[renamed]["review"] is None


def test_a_saved_selection_link_opens_its_frozen_records_and_says_what_it_is(api):
    """lx-collect's saved phone_selection links (/phones?selection=<id>) open Conversations on the frozen records:
    the stream filter's selection reads exactly the records frozen, later messages are not added, and the selection
    describes itself; another case's selection is not found."""
    from tests.phone_streams_fixture import phone as add_phone
    c, case = api["client"], api["case"]
    with api["engine"].begin() as conn:
        ext2, evs2 = add_phone(conn, case, label="C4", events=[msg(at(2023, 4, 1, 12), ANA, [OWNER], body="one"),
                                                               msg(at(2023, 4, 2), OWNER, [ANA], body="two")])
    got = c.post("/api/phones/selections", json={"filter": {"case_id": case, "phones": [str(ext2)]},
                                                 "words": "Everything on C4"}).json()
    with api["engine"].begin() as conn:  # a message read later is not in the frozen selection
        conn.execute(text("UPDATE phone_comm_events SET extraction_id = :e WHERE event_uid = :u"),
                     {"e": ext2, "u": api["evs"][0]["event_uid"]})
    idx = c.post("/api/phones/streams/index", json={"case_id": case, "selection": got["id"]}).json()
    assert idx["counts"]["events"] == 2
    whole = c.post("/api/phones/streams/index", json={"case_id": case, "phones": [str(ext2)]}).json()
    assert whole["counts"]["events"] == 3
    d = c.get("/api/phones/selections/%s" % got["id"], params={"case_id": case})
    assert d.status_code == 200 and d.json()["words"] == "Everything on C4" and d.json()["event_count"] == 2
    assert d.json()["replaced"] is None
    assert c.get("/api/phones/selections/%s" % got["id"], params={"case_id": api["other_case"]}).status_code in (403, 404)
    assert c.get("/api/phones/selections/not-an-id", params={"case_id": case}).status_code == 404
    bad = c.post("/api/phones/streams/index", json={"case_id": case, "selection": "not-an-id"})
    assert bad.status_code == 422
