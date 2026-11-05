"""Replies, quotes and forwards on stream rows (03 section 6.6, 07 section 4.4). Synthetic phones in a throwaway
PostgreSQL database. Children are written as the interpreter writes them: a child record of the message in
``phone_record_summaries``, its id in ``phone_texts``, its people and times in their own tables."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from services.phone import fold as Fold
from services.phone import streams as S
from services.phone.filters import StreamFilter
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import GEN, at, phone

OWNER, ANA, BEN = "phone:+12025550100", "phone:+12025550143", "phone:+12025550188"
pytestmark = needs_template


@pytest.fixture
def db():
    with fresh_engine() as engine:
        with engine.begin() as c:
            yield c


def msg(instant, sender, recips, body="hello", **kw):
    parties = [(sender, "sender", sender == OWNER, None, None)] + [(r, "recipient", r == OWNER, None, None)
                                                                    for r in recips]
    return dict(kind="message", instant=instant, body=body, parties=parties,
                direction="outgoing" if sender == OWNER else "incoming", **kw)


def child(c, case, ext, parent, model_type, ordinal):
    """A child record of a message, at the generation the fixture interpreted."""
    uid = uuid.uuid5(uuid.UUID(parent["record_uid"]), "child-%s-%d" % (model_type, ordinal))
    c.execute(text(
        "INSERT INTO phone_record_summaries (case_id, extraction_id, document_index, ordinal, record_uid, "
        "root_record_uid, parent_record_uid, locator, model_type, generation, is_top_level, title, has_time, "
        "has_point) VALUES (:c, :e, 0, :o, :u, :p, :p, :loc, :mt, :g, false, 'synthetic', false, false)"),
        {"c": case, "e": ext, "o": ordinal, "u": uid, "p": parent["record_uid"], "loc": "child/%d" % ordinal,
         "mt": model_type, "g": GEN})
    return uid


def field(c, case, ext, record, model_type, name, value, ordinal):
    c.execute(text(
        "INSERT INTO phone_texts (case_id, extraction_id, document_index, ordinal, record_uid, root_record_uid, "
        "locator, model_type, generation, text_uid, body_path, field_name, field_path, value_index, value, "
        "value_folded, effective_value) VALUES (:c, :e, 0, :o, :u, :u, 'x', :mt, :g, :t, '0', :f, :fp, 0, :v, :vf, :ve)"),
        {"c": case, "e": ext, "o": ordinal, "u": record, "mt": model_type, "g": GEN, "t": uuid.uuid4(), "f": name,
         "fp": name, "v": value, "vf": Fold.fold(value), "ve": value})


def rows_of(c, case):
    f = StreamFilter(case_id=str(case))
    idx = S.index_comm_events(c, f)
    out = []
    for d in idx["items"]:
        out += S.window_comm_events(c, f, snapshot_token=idx["snapshot"], day=d["day"], offset=0, limit=200)["items"]
    return {r["body"]: r for r in out}


def test_a_reply_links_to_the_message_its_id_names_and_says_when_it_is_not_there(db):
    case = make_case(db)
    ext, evs = phone(db, case, contacts={ANA: "Ana Rivera"}, events=[
        msg(at(2023, 3, 14, 9), ANA, [OWNER], body="the original", thread="t1"),
        msg(at(2023, 3, 14, 10), OWNER, [ANA], body="a reply", thread="t1"),
        msg(at(2023, 3, 14, 11), OWNER, [ANA], body="a reply to nothing here", thread="t1"),
        msg(at(2023, 3, 14, 12), OWNER, [ANA], body="a reply with no id", thread="t1"),
        msg(at(2023, 3, 14, 13), OWNER, [ANA], body="a plain message", thread="t1"),
    ])
    field(db, case, ext, evs[0]["record_uid"], "InstantMessage", "Identifier", "AAA111", 0)
    field(db, case, ext, child(db, case, ext, evs[1], "ReplyMessageData", 90), "ReplyMessageData",
          "OriginalMessageID", "AAA111", 90)
    field(db, case, ext, child(db, case, ext, evs[2], "ReplyMessageData", 91), "ReplyMessageData",
          "OriginalMessageID", "GONE222", 91)
    child(db, case, ext, evs[3], "ReplyMessageData", 92)
    rows = rows_of(db, case)
    link = rows["a reply"]["replies"]
    assert len(link) == 1 and link[0]["state"] == "found" and link[0]["kind"] == "reply"
    target = link[0]["target"]
    assert target["event_uid"] == evs[0]["event_uid"] and target["excerpt"] == "the original"
    assert target["same_thread"] is True and target["from"]["name"] == "Ana Rivera"
    missing = rows["a reply to nothing here"]["replies"][0]
    assert missing["state"] == "not_in_extraction" and missing["original_id"] == "GONE222" and missing["target"] is None
    assert rows["a reply with no id"]["replies"][0]["state"] == "not_recorded"
    assert rows["a plain message"]["replies"] == [] and rows["a plain message"]["forward"] is None


def test_a_quote_and_a_message_in_another_conversation(db):
    case = make_case(db)
    ext, evs = phone(db, case, events=[
        msg(at(2023, 3, 14, 9), ANA, [OWNER], body="in a group", thread="group"),
        msg(at(2023, 3, 14, 10), OWNER, [ANA], body="in private", thread="private"),
    ], threads={"group": {"title": "Family"}})
    field(db, case, ext, evs[0]["record_uid"], "InstantMessage", "Identifier", "AAA111", 0)
    field(db, case, ext, child(db, case, ext, evs[1], "QuotedMessageData", 90), "QuotedMessageData",
          "OriginalMessageID", "AAA111", 90)
    got = rows_of(db, case)["in private"]["replies"][0]
    assert got["kind"] == "quote" and got["target"]["same_thread"] is False
    assert got["target"]["thread_title"] == "Family" and got["target"]["thread_key"] == evs[0]["thread_key"]


def test_the_same_identifier_on_another_phone_is_not_the_original(db):
    """A link is the report's own, inside one extraction: ids are only unique on the phone that wrote them."""
    case = make_case(db)
    ext_a, a = phone(db, case, label="C1", events=[msg(at(2023, 3, 14, 9), ANA, [OWNER], body="on phone one")])
    ext_b, b = phone(db, case, label="C2", events=[msg(at(2023, 3, 14, 10), OWNER, [ANA], body="on phone two")])
    field(db, case, ext_a, a[0]["record_uid"], "InstantMessage", "Identifier", "SAME", 0)
    field(db, case, ext_b, child(db, case, ext_b, b[0], "ReplyMessageData", 90), "ReplyMessageData",
          "OriginalMessageID", "SAME", 90)
    assert rows_of(db, case)["on phone two"]["replies"][0]["state"] == "not_in_extraction"


def test_a_message_is_never_its_own_original(db):
    case = make_case(db)
    ext, evs = phone(db, case, events=[msg(at(2023, 3, 14, 9), ANA, [OWNER], body="points at itself")])
    field(db, case, ext, evs[0]["record_uid"], "InstantMessage", "Identifier", "SELF", 0)
    field(db, case, ext, child(db, case, ext, evs[0], "ReplyMessageData", 90), "ReplyMessageData",
          "OriginalMessageID", "SELF", 90)
    assert rows_of(db, case)["points at itself"]["replies"][0]["state"] == "not_in_extraction"


def test_a_forward_keeps_its_sender_and_names_its_author_apart(db):
    case = make_case(db)
    ext, evs = phone(db, case, contacts={ANA: "Ana Rivera", BEN: "Ben Okafor"}, events=[
        msg(at(2023, 3, 14, 9), ANA, [OWNER], body="forwarded with an author"),
        msg(at(2023, 3, 14, 10), ANA, [OWNER], body="forwarded, label only"),
    ])
    kid = child(db, case, ext, evs[0], "ForwardedMessageData", 90)
    db.execute(text(
        "INSERT INTO phone_participations (case_id, extraction_id, document_index, ordinal, record_uid, "
        "root_record_uid, locator, model_type, generation, participation_uid, role, role_basis, is_phone_owner, "
        "identifier_raw, name_in_record, identity_key) VALUES (:c, :e, 0, 90, :u, :p, 'x', 'ForwardedMessageData', :g, "
        ":pu, 'original_sender', 'container', false, null, 'Ben Okafor', :k)"),
        {"c": case, "e": ext, "u": kid, "p": evs[0]["record_uid"], "g": GEN, "pu": uuid.uuid4(), "k": BEN})
    db.execute(text(
        "INSERT INTO phone_time_values (case_id, extraction_id, document_index, ordinal, record_uid, root_record_uid, "
        "locator, model_type, generation, time_uid, body_path, field_name, field_path, value_index, instant, "
        "effective_instant, original_text, offset_state, offset_present) VALUES (:c, :e, 0, 90, :u, :p, 'x', "
        "'ForwardedMessageData', :g, :t, '0', 'TimeCreated', 'TimeCreated', 0, :i, :i, 'x', 'present', true)"),
        {"c": case, "e": ext, "u": kid, "p": evs[0]["record_uid"], "g": GEN, "t": uuid.uuid4(),
         "i": at(2023, 3, 1, 8)})
    child(db, case, ext, evs[1], "ForwardedMessageData", 91)
    rows = rows_of(db, case)
    full = rows["forwarded with an author"]
    assert full["from"]["name"] == "Ana Rivera", "the sender of this copy stays the sender"
    assert full["forward"]["original_sender"]["name"] == "Ben Okafor"
    assert "2023" in full["forward"]["time_created"]
    only = rows["forwarded, label only"]
    assert only["forward"] == {"original_sender": None, "time_created": None}
    assert only["from"]["name"] == "Ana Rivera"


def test_rows_read_the_links_in_a_fixed_number_of_queries(db):
    """No per-row lookups: 40 replies read as many statements as 2."""
    from sqlalchemy import event

    def statements(n):
        case = make_case(db)
        ext, evs = phone(db, case, events=[msg(at(2023, 3, 14, 9 + i // 60, i % 60), ANA, [OWNER], body="m%d" % i, thread="t")
                                           for i in range(n * 2)])
        for i in range(n):
            field(db, case, ext, evs[i]["record_uid"], "InstantMessage", "Identifier", "ID%d" % i, i)
            field(db, case, ext, child(db, case, ext, evs[n + i], "ReplyMessageData", 900 + i), "ReplyMessageData",
                  "OriginalMessageID", "ID%d" % i, 900 + i)
        f = StreamFilter(case_id=str(case))
        idx = S.index_comm_events(db, f)
        seen = []

        def count(conn, cursor, statement, parameters, context, executemany):
            seen.append(statement)
        event.listen(db.engine, "before_cursor_execute", count)
        try:
            S.window_comm_events(db, f, snapshot_token=idx["snapshot"], day=idx["items"][0]["day"], offset=0, limit=200)
        finally:
            event.remove(db.engine, "before_cursor_execute", count)
        return len(seen)

    assert statements(2) == statements(40)
