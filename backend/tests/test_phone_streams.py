"""03 sections 3.1, 3.3, 3.4, 4.3 to 4.5: the one communication-event query (tests C-2 to C-5, A2, A14 counts,
3.1 rules 2 to 6). Synthetic phones in a throwaway PostgreSQL database."""
from __future__ import annotations

from datetime import timezone

import pytest
from sqlalchemy import event, text

from services.phone import labels as L
from services.phone import streams as S
from services.phone.filters import StreamFilter, canonical_json
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, bulk_events, phone

OWNER, ANA, BEN, CAL = "phone:+12025550100", "phone:+12025550143", "phone:+12025550188", "phone:+12025550199"
pytestmark = needs_template


def F(case, **kw):
    return StreamFilter(case_id=str(case), **kw)


def _all_rows(c, f):
    idx = S.index_comm_events(c, f)
    rows = []
    days = [d["day"] for d in idx["items"]]
    if idx["no_time_position"] == "first" and idx["no_time_count"]:
        days = [None] + days
    elif idx["no_time_count"]:
        days = days + [None]
    for d in days:
        off = 0
        while True:
            w = S.window_comm_events(c, f, snapshot_token=idx["snapshot"], day=d, offset=off, limit=2)
            rows.extend(w["items"])
            if len(w["items"]) < 2:
                break
            off += 2
    return idx, rows


def msg(instant, sender, recips, body="hello", **kw):
    parties = [(sender, "sender", sender == OWNER, None, None)] + [(r, "recipient", r == OWNER, None, None)
                                                                    for r in recips]
    return dict(kind="message", instant=instant, body=body, parties=parties,
                direction="outgoing" if sender == OWNER else "incoming", **kw)


@pytest.fixture
def db():
    with fresh_engine() as engine:
        with engine.begin() as c:
            yield c


def test_total_equals_day_counts_plus_no_time_and_no_row_is_dropped(db):
    """C-2, C-3, 3.1 rule 5."""
    case = make_case(db)
    ext, evs = phone(db, case, device_zone="America/New_York", events=[
        msg(at(2023, 3, 14, 19, 7, 12), ANA, [OWNER], thread="t1"),
        msg(at(2023, 3, 15, 3, 30), OWNER, [ANA], thread="t1"),       # 11:30 PM Eastern on the 14th
        msg(at(2023, 3, 15, 4, 0), ANA, [OWNER], thread="t1"),        # midnight Eastern, the 15th
        msg(None, ANA, [OWNER], thread="t1", body="no time here"),
    ])
    f = F(case, zone={"mode": "phone", "phone": str(ext)})
    idx, rows = _all_rows(db, f)
    assert idx["counts"]["events"] == 4 == sum(d["count"] for d in idx["items"]) + idx["no_time_count"]
    assert [(d["day"], d["count"]) for d in idx["items"]] == [("2023-03-14", 2), ("2023-03-15", 1)]
    assert idx["items"][0]["header"] == "Tuesday, March 14, 2023"
    assert idx["items"][0]["zone_label"] == "Eastern Time (UTC-4)"
    assert idx["no_time_count"] == 1 and idx["no_time_position"] == "last"
    assert len(rows) == 4 and {r["event_uid"] for r in rows} == {e["event_uid"] for e in evs}
    assert rows[1]["time"]["full"] == "Tue, Mar 14, 2023, 11:30:00 PM EDT"
    assert rows[-1]["time"]["row"] == "No time recorded" and "No time recorded" in rows[-1]["flags"]
    newest = F(case, zone={"mode": "phone", "phone": str(ext)}, sort="newest_first")
    idx2, rows2 = _all_rows(db, newest)
    assert idx2["no_time_position"] == "first" and rows2[0]["body"] == "no time here"
    assert [r["event_uid"] for r in rows2[1:]] == [r["event_uid"] for r in rows[:3]][::-1]
    no_time_excluded = F(case, include_no_time=False)
    assert S.index_comm_events(db, no_time_excluded)["counts"]["events"] == 3


def test_a_call_with_one_party_edge_keeps_the_owner_side(db):
    """C-4: the record names only the other side; 02 writes an owner_implicit party with no identity key."""
    case = make_case(db)
    ext, evs = phone(db, case, events=[
        dict(kind="call", instant=at(2023, 3, 14, 15), direction="outgoing", app="Phone", call_duration_s=63,
             call_status="Established",
             parties=[(ANA, "callee", False, None, "+12025550143"), (None, "owner_implicit", None, None, None, "caller")]),
    ])
    f = F(case, participants=[OWNER, ANA], participant_mode="between")
    idx, rows = _all_rows(db, f)
    assert idx["counts"]["events"] == 1
    row = rows[0]
    assert row["from"]["is_owner"] and row["from"]["identity_key"] == OWNER
    assert L.label_text(row["from"]) == "Owner of C3 (+1 202-555-0100)"
    assert row["line"] == "Owner of C3 (+1 202-555-0100) -> (no name on this phone) (+1 202-555-0143)"
    assert row["call"]["words"] == "Call, 1 min 3 s, answered"
    assert S.index_comm_events(db, F(case, participants=[OWNER], participant_mode="sent_by"))["counts"]["events"] == 1
    assert S.index_comm_events(db, F(case, participants=[OWNER], participant_mode="sent_to"))["counts"]["events"] == 0


def test_seven_thousand_threads_in_one_response(db):
    """C-5: 7,584 threads (the largest case) come back in one call, complete."""
    case = make_case(db)
    ext, _ = phone(db, case, events=[msg(at(2023, 1, 1), ANA, [OWNER], thread="seed")])
    db.execute(text(
        "INSERT INTO phone_threads (case_id, extraction_id, interpretation_level, generation, thread_key, app, "
        "thread_kind, chat_type, party_identity_keys, event_count) SELECT :c, :e, 'reviewed', 1, 'chat:' || :e || ':' "
        "|| i, 'WhatsApp', 'chat', 'OneOnOne', ARRAY[:o, :a], 1 FROM generate_series(1, 7583) i"),
        {"c": case, "e": ext, "o": OWNER, "a": ANA})
    db.execute(text(
        "INSERT INTO phone_comm_events (case_id, extraction_id, interpretation_level, generation, event_uid, record_uid, "
        "document_index, ordinal, locator, model_type, kind, thread_key, app, direction, sort_instant, body) SELECT :c, "
        ":e, 'reviewed', 1, md5('t' || i)::uuid, md5('tr' || i)::uuid, 0, 1000 + i, 'x', 'InstantMessage', 'message', "
        "'chat:' || :e || ':' || i, 'WhatsApp', 'incoming', now() - i * interval '1 minute', 'm' FROM "
        "generate_series(1, 7583) i"), {"c": case, "e": ext})
    out = S.thread_list(db, F(case))
    assert out["complete"] is True and out["counts"]["threads"] == 7584 == len(out["items"])
    assert out["counts"]["threads_total"] == 7584
    titled = [t for t in out["items"] if t["thread_key"].endswith(":seed")][0]
    assert titled["title"] == "(no name on this phone)" or titled["title"].startswith("+1")


def test_a_correction_mid_scroll_makes_the_snapshot_stale(db):
    """3.1 rule 3: a window under an older snapshot is refused."""
    case = make_case(db)
    ext, evs = phone(db, case, events=[msg(at(2023, 3, 14), ANA, [OWNER])])
    f = F(case)
    idx = S.index_comm_events(db, f)
    S.window_comm_events(db, f, snapshot_token=idx["snapshot"], day="2023-03-14")
    db.execute(text(
        "INSERT INTO adjudications (id, case_id, subject_type, subject_id, decision, reason, actor_name, actor_email, "
        "subject_sequence) VALUES (gen_random_uuid(), :c, 'phone_extraction', :e, 'set_phone_label', 'synthetic', "
        "'x', 'x@x.test', 1)"), {"c": case, "e": ext})
    with pytest.raises(S.StaleSnapshot):
        S.window_comm_events(db, f, snapshot_token=idx["snapshot"], day="2023-03-14")
    assert S.index_comm_events(db, f)["snapshot"] != idx["snapshot"]


def test_three_copies_show_once_and_every_total_states_the_records(db):
    """3.1 rule 6, 3.4, A14: one row 'Found 3 times' listing three sources; two different messages at the same
    second stay apart; the same message on two phones stays two rows; Show every copy lists three rows."""
    case = make_case(db)
    t = at(2023, 3, 14, 15, 0, 0)
    ext, _ = phone(db, case, events=[
        msg(t, ANA, [OWNER], body="same", app="Native Messages", dup="g1"),
        msg(t, ANA, [OWNER], body="same", app="IMS Service", dup="g1"),
        msg(t, ANA, [OWNER], body="same", app="Android CallLog database", dup="g1"),
        msg(t, ANA, [OWNER], body="different", app="Native Messages"),
    ])
    phone(db, case, label="C7", events=[msg(t, ANA, [OWNER], body="same", app="Native Messages", dup="g1")])
    idx, rows = _all_rows(db, F(case))
    assert idx["counts"] == {"events": 3, "records": 5, "collapsed_copies": 2, "no_time": 0, "calls": 0, "messages": 3,
                             "phones": 2}
    found = [r for r in rows if r["copies"]["count"] == 3]
    assert len(found) == 1 and sorted(found[0]["copies"]["apps"]) == ["Android CallLog database", "IMS Service",
                                                                      "Native Messages"]
    every = F(case, collapse_copies=False)
    idx2, rows2 = _all_rows(db, every)
    assert idx2["counts"]["events"] == 5 == len(rows2)


def test_labels_cover_every_row_of_the_table(db):
    """A2 and C-6 over 3.3's table: a name and an identifier, or the explicit forms."""
    case = make_case(db)
    ext, evs = phone(db, case, contacts={ANA: "Maria Lopez"}, events=[
        msg(at(2023, 3, 14), ANA, [OWNER]),
        msg(at(2023, 3, 14, 13), BEN, [OWNER]),
        dict(kind="message", instant=at(2023, 3, 14, 14), body="x", direction="incoming",
             parties=[(None, "sender", False, "Raw Name", "12345"), (OWNER, "recipient", True, None, None)]),
        dict(kind="message", instant=at(2023, 3, 14, 15), body="x", direction="incoming",
             parties=[("app:whatsapp:jid:5521@s.whatsapp.net", "sender", False, "Maria L", None),
                      (OWNER, "recipient", True, None, None)]),
        dict(kind="email", instant=at(2023, 3, 14, 16), body="x", subject="s", direction="incoming",
             parties=[("email:maria@example.com", "sender", False, "Maria Lopez", None),
                      (OWNER, "recipient", True, None, None)]),
    ])
    db.execute(text("UPDATE phone_identities SET subkind = 'whatsapp_jid' WHERE identity_key LIKE 'app:whatsapp%'"))
    idx, rows = _all_rows(db, F(case))
    lines = [r["line"] for r in rows]
    assert lines[0] == "Maria Lopez (+1 202-555-0143) -> Owner of C3 (+1 202-555-0100)"
    assert lines[1] == "(no name on this phone) (+1 202-555-0188) -> Owner of C3 (+1 202-555-0100)"
    assert lines[2].startswith("Raw Name (12345) -> ")
    assert rows[2]["from"]["identifier"]["normalised"] is False
    assert lines[3].startswith("Maria L (WhatsApp id 5521@s.whatsapp.net) -> ")
    assert lines[4].startswith("Maria Lopez (maria@example.com) -> ")
    assert all(" -> " in ln for ln in lines)


def test_an_owner_set_by_a_person_is_labelled_and_an_owner_without_a_number_says_so(db):
    """P-3 and the owner rows of 3.3."""
    case = make_case(db)
    ext, _ = phone(db, case, owner=None, events=[
        dict(kind="message", instant=at(2023, 3, 14), body="x", direction="outgoing",
             parties=[(None, "sender", True, None, None), (ANA, "recipient", False, None, None)])])
    _, rows = _all_rows(db, F(case))
    assert rows[0]["line"].startswith("Owner of C3 (number not in the extraction) -> ")
    label = {"is_owner": True, "phone_label": "C3", "owner_basis": "manual", "name": "N",
             "identifier": {"kind": "phone", "display": "+1 202-555-0100"}}
    assert L.label_text(label) == "Owner of C3 [Owner set by a person]: N (+1 202-555-0100)"


def test_names_toggle_changes_labels_only(db):
    """C-7, A1: the case view shows the person's name with each phone's name; same rows, order and counts."""
    case = make_case(db)
    ext, _ = phone(db, case, contacts={ANA: "Mom"}, events=[msg(at(2023, 3, 14), ANA, [OWNER]),
                                                            msg(at(2023, 3, 15), OWNER, [ANA])])
    ext2, _ = phone(db, case, label="C7", owner="phone:+12025550111", contacts={ANA: "Maria L"},
                    events=[msg(at(2023, 3, 16), ANA, ["phone:+12025550111"])])
    pid = db.execute(text(
        "INSERT INTO case_profiles (id, case_id, profile_type, display_name, created_at, updated_at) VALUES (gen_random_uuid(), :c, 'person', "
        "'Maria Lopez', now(), now()) RETURNING id"), {"c": case}).scalar()
    db.execute(text("INSERT INTO phone_identity_links (case_id, identity_id, dossier_id, decision_id) SELECT :c, id, "
                    ":p, gen_random_uuid() FROM phone_identities WHERE identity_key = :k"),
               {"c": case, "p": pid, "k": ANA})
    i1, phone_rows = _all_rows(db, F(case))
    i2, case_rows = _all_rows(db, F(case, names={"mode": "case"}))
    assert [r["event_uid"] for r in phone_rows] == [r["event_uid"] for r in case_rows]
    assert i1["counts"] == i2["counts"]
    assert phone_rows[0]["from"]["name"] == "Mom" and phone_rows[2]["from"]["name"] == "Maria L"
    assert case_rows[0]["from"]["name"] == "Maria Lopez" and case_rows[0]["from"]["name_basis"] == "case_person"
    assert sorted(n["name"] for n in case_rows[0]["from"]["case_names"]) == ["Maria L", "Mom"]


def test_participant_modes_and_group_scope(db):
    """4.3: sent by X to Y, sent to, between direct with the group figure, include_groups."""
    case = make_case(db)
    ext, _ = phone(db, case, threads={"g": {"chat_type": "Group", "title": "Team", "members": [OWNER, ANA, BEN]}},
                   events=[msg(at(2023, 3, 1), ANA, [BEN], thread="d"),
                           msg(at(2023, 3, 2), BEN, [ANA], thread="d"),
                           msg(at(2023, 3, 3), ANA, [OWNER, BEN], thread="g"),
                           msg(at(2023, 3, 4), CAL, [OWNER], thread="c")])
    n = lambda **kw: S.index_comm_events(db, F(case, **kw))["counts"]["events"]  # noqa: E731
    assert n(participants=[ANA, BEN], participant_mode="sent_by") == 2
    assert n(participants=[ANA], participant_mode="sent_by") == 2
    assert n(participants=[ANA], participant_mode="sent_to") == 1
    idx = S.index_comm_events(db, F(case, participants=[ANA, BEN], participant_mode="between"))
    assert idx["counts"]["events"] == 2 and idx["group_totals"] == {"threads": 1, "events": 1}
    assert n(participants=[ANA, BEN], participant_mode="between", group_scope="include_groups") == 3
    assert n(participants=[ANA, CAL], participant_mode="any") == 4
    assert n(participants=[ANA, BEN], participant_mode="all") == 3
    with pytest.raises(ValueError):
        F(case, participants=[ANA], participant_mode="between")


def test_filters_narrow_as_the_intersection_of_each_filter(db):
    """reg-comms-combined-filters (17.2): kinds, apps, directions, text, dates, deleted state."""
    case = make_case(db)
    ext, _ = phone(db, case, events=[
        msg(at(2023, 3, 1), ANA, [OWNER], body="Payment sent", app="WhatsApp"),
        msg(at(2023, 3, 2), OWNER, [ANA], body="José called", app="SMS", deleted_state="Deleted"),
        dict(kind="call", instant=at(2023, 3, 3), direction="incoming", app="Phone",
             parties=[(ANA, "caller", False, None, None), (OWNER, "callee", True, None, None)]),
    ])
    n = lambda **kw: S.index_comm_events(db, F(case, **kw))["counts"]["events"]  # noqa: E731
    assert n(kinds=["message"]) == 2 and n(kinds=["call"]) == 1
    assert n(apps=["SMS"]) == 1 and n(directions=["incoming"]) == 2
    assert n(text={"query": "payment"}) == 1 and n(text={"query": "jose"}) == 1
    assert n(text={"query": "jose", "exact_characters": True}) == 0 and n(text={"query": "josé",
                                                                               "exact_characters": True}) == 1
    assert n(deleted_states=["Deleted"]) == 1
    assert n(from_instant=at(2023, 3, 2), to_instant=at(2023, 3, 2, 23)) == 1
    assert n(kinds=["message"], directions=["outgoing"], apps=["SMS"]) == 1
    assert n(kinds=["message"], apps=["Phone"]) == 0


def test_locate_returns_the_day_and_offset_of_an_event(db):
    case = make_case(db)
    ext, evs = phone(db, case, events=[msg(at(2023, 3, 14, 10 + i), ANA, [OWNER]) for i in range(4)])
    f = F(case)
    idx = S.index_comm_events(db, f)
    loc = S.locate_comm_event(db, f, snapshot_token=idx["snapshot"], event_uid=evs[2]["event_uid"])
    assert loc == {"day": "2023-03-14", "offset": 2}
    w = S.window_comm_events(db, f, snapshot_token=idx["snapshot"], day=loc["day"], offset=loc["offset"], limit=1)
    assert w["items"][0]["event_uid"] == evs[2]["event_uid"]


def test_a_phone_still_being_read_marks_every_result_incomplete(db):
    """3.8 'still being read' and 4.2 complete false."""
    case = make_case(db)
    phone(db, case, interpreted=False, events=[msg(at(2023, 3, 14), ANA, [OWNER])])
    idx = S.index_comm_events(db, F(case))
    assert idx["complete"] is False and idx["limits"][0]["kind"] == "phone_incomplete"
    assert "still being read" in idx["limits"][0]["message"]


def test_case_zone_default_and_the_canonical_filter(db):
    case = make_case(db)
    phone(db, case, device_zone="America/New_York", events=[msg(at(2023, 3, 14), ANA, [OWNER])])
    phone(db, case, label="C9", device_zone="America/Chicago", events=[msg(at(2023, 3, 14), ANA, [OWNER])])
    z = S.case_zone(db, case)
    assert z["name"] == "UTC" and "different or unknown time zones" in z["note"]
    a = F(case, apps=["b", "a"], kinds=["call", "message"])
    b = F(case, apps=["a", "b"], kinds=["message", "call"])
    assert canonical_json(a) == canonical_json(b)
    assert canonical_json(F(case, participants=[ANA, BEN], participant_mode="sent_by")) != \
        canonical_json(F(case, participants=[BEN, ANA], participant_mode="sent_by"))


def test_a_large_day_windows_by_offset_with_no_gap_or_overlap(db):
    """3.1 rule 2 and the day-bounded offset of 4.7 over 2,000 events in one day."""
    case = make_case(db)
    ext, _ = phone(db, case, events=[])
    bulk_events(db, case, ext, 2000, start=at(2023, 5, 1, 4, 0, 0), step_seconds=30)
    f = F(case, phones=[str(ext)])
    idx = S.index_comm_events(db, f)
    assert idx["counts"]["events"] == 2000
    seen = []
    for d in idx["items"]:
        for off in range(0, d["count"], 1000):
            w = S.window_comm_events(db, f, snapshot_token=idx["snapshot"], day=d["day"], offset=off, limit=1000)
            seen.extend(r["event_uid"] for r in w["items"])
    assert len(seen) == 2000 == len(set(seen))
    instants = [r for r in seen]
    assert instants  # order is checked by the window's ORDER BY; uniqueness and count prove no gap or overlap
    assert timezone.utc


def test_a_record_kept_from_the_previous_reading_does_not_list_an_attachment_twice(db):
    """Review of 03-1: while a phone is re-read, phone_record_summaries holds the earlier generation's rows too; an
    attachment on a child record is listed once, from the current generation."""
    case = make_case(db)
    ext, evs = phone(db, case, events=[msg(at(2023, 3, 14), ANA, [OWNER])])
    parent = evs[0]["record_uid"]
    for gen in (0, 1):  # 1 is the current generation in the fixture; 0 is left from the earlier reading
        db.execute(text(
            "INSERT INTO phone_record_summaries (case_id, extraction_id, document_index, ordinal, record_uid, "
            "root_record_uid, parent_record_uid, locator, model_type, generation, is_top_level, title, has_time, "
            "has_point) VALUES (:c, :e, 0, 900, '00000000-0000-0000-0000-0000000000a1', :p, :p, 'x/0/r900', "
            "'Attachment', :g, false, 'synthetic', false, false)"), {"c": case, "e": ext, "p": parent, "g": gen})
    db.execute(text(
        "INSERT INTO phone_file_references (extraction_id, document_index, record_ordinal, body_path, mechanism, "
        "reference_text, resolution) VALUES (:e, 0, 900, 'f', 'file_id_attribute', 'chat/a.jpg', 'unresolved')"),
        {"e": ext})
    _, rows = _all_rows(db, F(case))
    assert [a["filename"] for a in rows[0]["attachments"]] == ["a.jpg"]


def test_a_window_asks_for_its_attachments_by_record_and_each_stays_with_its_message(db):
    """lx-convspeed: the attachments of a window are read by record id. Joined to the records in one statement,
    Postgres read every file reference of every phone for any window (222 ms of a 280 ms window on the largest
    reference phone). A child's attachment is its message's; a row listed itself keeps its own."""
    case = make_case(db)
    ext, evs = phone(db, case, events=[msg(at(2023, 3, 14), ANA, [OWNER]), msg(at(2023, 3, 14), ANA, [OWNER])])
    first, second = evs[0]["record_uid"], evs[1]["record_uid"]
    db.execute(text(
        "INSERT INTO phone_record_summaries (case_id, extraction_id, document_index, ordinal, record_uid, "
        "root_record_uid, parent_record_uid, locator, model_type, generation, is_top_level, title, has_time, "
        "has_point) VALUES (:c, :e, 0, 900, '00000000-0000-0000-0000-0000000000a1', :p, :p, 'x/0/r900', "
        "'Attachment', 1, false, 'synthetic', false, false)"), {"c": case, "e": ext, "p": first})
    db.execute(text("UPDATE phone_record_summaries SET parent_record_uid = :p WHERE record_uid = :r"),
               {"p": first, "r": second})  # a row of the list that is also a child record of another row
    ordinal = {str(r.record_uid): r.ordinal for r in db.execute(text(
        "SELECT record_uid, ordinal FROM phone_record_summaries WHERE record_uid = :r"), {"r": second})}[str(second)]
    db.execute(text(
        "INSERT INTO phone_file_references (extraction_id, document_index, record_ordinal, body_path, mechanism, "
        "reference_text, resolution) VALUES (:e, 0, 900, 'f', 'file_id_attribute', 'chat/child.jpg', 'unresolved'), "
        "(:e, 0, :o, 'f', 'file_id_attribute', 'chat/own.jpg', 'unresolved')"), {"e": ext, "o": ordinal})
    seen = []

    def note(_conn, _cursor, statement, *_rest):
        seen.append(statement)

    event.listen(db.engine, "before_cursor_execute", note)
    try:
        _, rows = _all_rows(db, F(case))
    finally:
        event.remove(db.engine, "before_cursor_execute", note)
    by_uid = {r["record_uid"]: [a["filename"] for a in r["attachments"]] for r in rows}
    assert by_uid == {str(first): ["child.jpg"], str(second): ["own.jpg"]}
    reads = [s for s in seen if "pv_attachment_link" in s]
    assert reads and not any("phone_record_summaries" in s for s in reads)


def test_a_report_zone_that_is_not_a_zone_name_shows_utc_and_says_so(db):
    """Review of 03-1: capture keeps the report's zone text when it is not a zone name; lists still load."""
    case = make_case(db)
    ext, _ = phone(db, case, device_zone="GMT-05:00 Eastern", events=[msg(at(2023, 3, 14), ANA, [OWNER])])
    for mode in ("case", "phone"):
        idx = S.index_comm_events(db, F(case, zone={"mode": mode, "phone": str(ext)}))
        assert idx["zone"]["name"] == "UTC" and "not one Loupe recognises" in idx["zone"]["note"]
        assert idx["counts"]["events"] == 1


def test_saving_the_case_time_zone_makes_an_open_list_stale(db):
    """Review of 03-1: day bounds follow the case zone, so a new zone changes the snapshot (409, then re-read)."""
    case = make_case(db)
    phone(db, case, events=[msg(at(2023, 3, 14, 3), ANA, [OWNER])])
    f = F(case)
    before = S.index_comm_events(db, f)["snapshot"]
    uid = db.execute(text("SELECT created_by_user_id FROM cases WHERE id = :c"), {"c": case}).scalar()
    db.execute(text("INSERT INTO case_display_settings (case_id, time_zone, updated_by) VALUES (:c, "
                    "'America/New_York', :u)"), {"c": case, "u": uid})
    with pytest.raises(S.StaleSnapshot):
        S.window_comm_events(db, f, snapshot_token=before, day="2023-03-14", offset=0, limit=10)


def test_a_filter_with_a_case_or_phone_id_that_is_not_an_id_is_refused():
    with pytest.raises(ValueError):
        StreamFilter(case_id="not-a-case")
    with pytest.raises(ValueError):
        StreamFilter(case_id="00000000-0000-0000-0000-000000000001", phones=["C3"])
    with pytest.raises(ValueError):
        StreamFilter(case_id="00000000-0000-0000-0000-000000000001", zone={"mode": "phone", "phone": "C3"})


def test_events_in_no_conversation_are_one_more_thread_so_the_list_covers_every_event(db):
    """6.3 completeness: a phone's events with no thread key are listed as "Not in a conversation" and open."""
    case = make_case(db)
    ext, _ = phone(db, case, events=[msg(at(2023, 3, 14), ANA, [OWNER], thread="t"),
                                     msg(at(2023, 3, 15), BEN, [OWNER]), msg(at(2023, 3, 16), CAL, [OWNER])])
    tl = S.thread_list(db, F(case))
    assert sum(t["event_count"] for t in tl["items"]) == S.index_comm_events(db, F(case))["counts"]["events"] == 3
    loose = [t for t in tl["items"] if t["title"] == S.NO_THREAD_TITLE]
    assert len(loose) == 1 and loose[0]["event_count"] == 2 and loose[0]["event_count_total"] == 2
    assert tl["counts"]["threads_total"] == 2
    assert S.index_comm_events(db, F(case, threads=[loose[0]["thread_key"]]))["counts"]["events"] == 2


def test_thread_sorts_and_the_unreadable_flag(db):
    case = make_case(db)
    ext, evs = phone(db, case, events=[msg(at(2023, 3, 1), ANA, [OWNER], thread="a"),
                                       msg(at(2023, 3, 2), ANA, [OWNER], thread="a"),
                                       msg(at(2023, 3, 9), BEN, [OWNER], thread="b")])
    db.execute(text(
        "INSERT INTO phone_record_summaries (case_id, extraction_id, document_index, ordinal, record_uid, "
        "root_record_uid, parent_record_uid, locator, model_type, generation, is_top_level, title, has_time, "
        "has_point) VALUES (:c, :e, 0, 901, '00000000-0000-0000-0000-0000000000b1', :p, :p, 'x/0/r901', "
        "'ScrambledMessageData', 1, false, 'synthetic', false, false)"),
        {"c": case, "e": ext, "p": evs[2]["record_uid"]})
    order = lambda s: [t["thread_key"].rsplit(":", 1)[-1] for t in S.thread_list(db, F(case), sort=s)["items"]]  # noqa: E731
    assert order("recent") == ["b", "a"] and order("first") == ["a", "b"] and order("volume") == ["a", "b"]
    flags = {t["thread_key"].rsplit(":", 1)[-1]: t["has_unreadable"] for t in S.thread_list(db, F(case))["items"]}
    assert flags == {"a": False, "b": True}


def test_people_mode_lists_every_participant_with_counts_including_the_owner(db):
    case = make_case(db)
    phone(db, case, events=[msg(at(2023, 3, 1), ANA, [OWNER]), msg(at(2023, 3, 2), OWNER, [ANA]),
                            msg(at(2023, 3, 3), BEN, [OWNER], app="SMS")])
    pl = S.participant_list(db, F(case))
    by = {p["label"]["identity_key"]: p for p in pl["items"]}
    assert by[ANA]["events"] == 2 and by[BEN]["events"] == 1 and by[OWNER]["events"] == 3
    assert by[BEN]["apps"] == ["SMS"] and by[ANA]["phones"] == ["C3"]
    assert pl["counts"]["participants"] == 3 and pl["complete"] is True


def test_copy_rule_v1_groups_exact_copies_only_and_the_counts_say_so(db):
    """3.4 / D-9: same phone, kind, direction, sender, recipients, content and instant; nothing else."""
    from services.phone import copies
    case = make_case(db)
    t0 = at(2023, 3, 14, 10)
    ext, evs = phone(db, case, events=[
        msg(t0, ANA, [OWNER], body="Café"), msg(t0, ANA, [OWNER], body="Café"),  # NFC-equal bodies
        msg(t0, ANA, [OWNER], body="Café"),
        msg(at(2023, 3, 14, 10, 0, 1), ANA, [OWNER], body="Café"),  # one second later: not a copy
        msg(t0, ANA, [OWNER], body="other"), msg(t0, BEN, [OWNER], body="Café"),
        msg(None, ANA, [OWNER], body="Café"), msg(None, ANA, [OWNER], body="Café"),  # no instant never matches
        dict(kind="call", instant=t0, direction="incoming", app="Phone", call_duration_s=63, call_status="Established",
             parties=[(ANA, "caller", False, None, None), (OWNER, "callee", True, None, None)]),
        dict(kind="call", instant=t0, direction="incoming", app="Phone", call_duration_s=63, call_status="Established",
             parties=[(ANA, "caller", False, None, None), (OWNER, "callee", True, None, None)]),
    ])
    other, _ = phone(db, case, label="C9", events=[msg(t0, ANA, [OWNER], body="Café")])
    got = copies.assign(db, ext, 1)
    copies.assign(db, other, 1)
    assert got == {"groups": 2, "records": 5}
    idx = S.index_comm_events(db, F(case))
    assert idx["counts"]["records"] == 11 and idx["counts"]["events"] == 8 and idx["counts"]["collapsed_copies"] == 3
    _, rows = _all_rows(db, F(case))
    found = sorted(r["copies"]["count"] for r in rows if r["copies"]["count"] > 1)
    assert found == [2, 3] and len(rows) == idx["counts"]["events"]
    # locating a collapsed copy lands on its group's shown row (review follow-up)
    hidden = next(e["event_uid"] for e in evs[:3] if e["event_uid"] not in {r["event_uid"] for r in rows})
    loc = S.locate_comm_event(db, F(case), snapshot_token=idx["snapshot"], event_uid=hidden)
    w = S.window_comm_events(db, F(case), snapshot_token=idx["snapshot"], day=loc["day"], offset=loc["offset"], limit=1)
    assert w["items"][0]["copies"]["count"] == 3
    assert S.index_comm_events(db, F(case, collapse_copies=False))["counts"]["events"] == 11


def test_two_emails_with_different_header_threads_are_never_copies(db):
    """D-34: copies of one email share its headers; same subject, body, parties and second is not enough."""
    from services.phone import copies
    case = make_case(db)
    t0 = at(2023, 3, 14, 10)
    em = lambda th: dict(kind="email", instant=t0, direction="incoming", app="Mail", subject="Plan", body="x",  # noqa: E731
                         thread=th, parties=[(ANA, "sender", False, None, None), (OWNER, "recipient", True, None, None)])
    ext, _ = phone(db, case, events=[em("hdr-a"), em("hdr-z"), em("hdr-a")])
    assert copies.assign(db, ext, 1) == {"groups": 1, "records": 2}


def test_two_messages_with_different_files_and_no_text_are_never_copies(db):
    """D-37: the files a message refers to are part of its content."""
    from services.phone import copies
    case = make_case(db)
    t0 = at(2023, 3, 14, 10)
    ext, evs = phone(db, case, events=[msg(t0, ANA, [OWNER], body=None), msg(t0, ANA, [OWNER], body=None),
                                       msg(t0, ANA, [OWNER], body=None)])
    for i, ref in ((0, "a.jpg"), (1, "b.jpg"), (2, "a.jpg")):
        ordinal = db.execute(text("SELECT ordinal FROM phone_comm_events WHERE event_uid = :u"),
                             {"u": evs[i]["event_uid"]}).scalar()
        db.execute(text("INSERT INTO phone_file_references (extraction_id, document_index, record_ordinal, body_path, "
                        "mechanism, reference_text, resolution) VALUES (:e, 0, :o, 'f', 'file_id_attribute', :r, "
                        "'unresolved')"), {"e": ext, "o": ordinal, "r": ref})
    assert copies.assign(db, ext, 1) == {"groups": 1, "records": 2}


def test_a_copy_in_another_thread_still_counts_in_its_own_thread(db):
    """Review of 03-3: copies are ranked across the whole result, so a thread whose only message is the hidden copy
    of a message in another thread dropped out of the thread list. Each thread shows its own copy once."""
    from services.phone import copies
    case = make_case(db)
    t0 = at(2023, 3, 14, 10)
    ext, _ = phone(db, case, events=[msg(t0, ANA, [OWNER], body="same", thread="sms"),
                                     msg(t0, ANA, [OWNER], body="same", thread="app")])
    assert copies.assign(db, ext, 1) == {"groups": 1, "records": 2}
    got = S.thread_list(db, F(case))
    assert sorted(i["event_count"] for i in got["items"]) == [1, 1] and got["counts"]["threads"] == 2
    assert S.index_comm_events(db, F(case))["counts"]["events"] == 1  # the stream still shows the message once
