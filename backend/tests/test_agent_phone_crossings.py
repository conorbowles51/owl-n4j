"""The agent beside the rest of Loupe (docs/cellebrite/07 sections 6.4 item 15, 7.1 and 8): CO-11 (casework and
dossiers return phone links with citations), SA-7 (financial tools in a phones-only case), XF-3 (the day before a
payment, with its scope sentence), XF-12 (a map says whether phone points are on it), the overview counting phone
records, and asking in one case about a phone of another case. Synthetic data only; needs the PostgreSQL template."""
from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

pytestmark = needs_template
OWNER, ANA, BEN, ZED = "phone:+12025550100", "phone:+12025550143", "phone:+12025550188", "phone:+12025550199"


def msg(instant, sender, recips, body="hello", **kw):
    parties = [(sender, "sender", sender == OWNER, None, None)] + [(r, "recipient", r == OWNER, None, None)
                                                                    for r in recips]
    return dict(kind="message", instant=instant, body=body, parties=parties,
                direction="outgoing" if sender == OWNER else "incoming", **kw)


@pytest.fixture
def world():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, other = make_case(c), make_case(c)
            ext, evs = phone(c, case, label="C3", contacts={ANA: "Maria Lopez", BEN: "Ben Synthetic"}, events=[
                msg(at(2023, 3, 13, 9), ANA, [OWNER], body="the day before the payment", thread="t1"),
                msg(at(2023, 3, 13, 18), OWNER, [BEN], body="ask Ben about the money", thread="t2",
                    level="applied_unconfirmed"),
                msg(at(2023, 3, 14, 10), OWNER, [ANA], body="payment sent", thread="t1")])
            phone(c, other, label="C9", owner="phone:+12025550111", contacts={ZED: "Zed Elsewhere"},
                  events=[msg(at(2023, 3, 14, 9), ZED, ["phone:+12025550111"], body="other case only")])
            other_rec = c.execute(text("SELECT record_uid FROM pv_comm_event WHERE case_id = :c"),
                                  {"c": str(other)}).scalar()
            # casework and a dossier in the case, each linking a phone record; and a dossier in the other case
            entry = uuid.uuid4()
            c.execute(text("INSERT INTO workspace_entries (id, case_id, entry_type, title, body, tags, review_state, "
                           "version, migration_metadata, needs_migration_review, created_at, updated_at) VALUES (:i, "
                           ":c, 'finding', 'Payment agreed by text', 'Maria agreed the payment the day before.', "
                           "'[]', 'accepted', 1, '{}', false, now(), now())"), {"i": entry, "c": case})
            c.execute(text("INSERT INTO workspace_entry_links (id, entry_id, case_id, target_type, target_id, "
                           "target_label, relationship, source_anchor, metadata, created_at, updated_at) VALUES "
                           "(:i, :e, :c, 'phone_record', :r, 'Message from Maria', 'supports', '{}', '{}', now(), "
                           "now())"), {"i": uuid.uuid4(), "e": entry, "c": case, "r": evs[0]["record_uid"]})
            dossier, foreign = uuid.uuid4(), uuid.uuid4()
            for did, cid, name in ((dossier, case, "Maria Lopez"), (foreign, other, "Zed Elsewhere")):
                c.execute(text("INSERT INTO case_profiles (id, case_id, profile_type, display_name, contacts, "
                               "linkage_state, status, needs_link_review, graph_entity_deleted, created_at, "
                               "updated_at) VALUES (:i, :c, 'person', :n, '[]', 'unlinked', 'active', false, false, "
                               "now(), now())"), {"i": did, "c": cid, "n": name})
            c.execute(text("INSERT INTO dossier_links (id, dossier_id, case_id, target_type, target_id, "
                           "relationship_type, label, source_anchor, created_at, updated_at) VALUES (:i, :d, :c, "
                           "'phone_record', :r, 'supports', 'Payment sent', '{}', now(), now())"),
                      {"i": uuid.uuid4(), "d": dossier, "c": case, "r": evs[2]["record_uid"]})
        yield {"engine": engine, "case": case, "other": other, "evs": evs, "other_rec": other_rec,
               "dossier": dossier, "foreign": foreign}


def _tools(w, case=None, monkeypatch=None):
    from services.agent.tools import AgentToolContext, make_agent_tools

    @contextmanager
    def session():
        with Session(bind=w["engine"]) as s:
            yield s
    ctx = AgentToolContext(case_id=str(case or w["case"]), ledger_session_factory=session)
    return {t.name: t for t in make_agent_tools(ctx)}


def test_co11_casework_returns_its_phone_links_with_rec_citations_and_the_record_in_full(world):
    out = _tools(world)["get_casework"].invoke({})
    assert out["status"] == "success"
    data = out["data"]
    assert data["schema"] == "loupe.agent.casework/1" and data["total_matching"] == 1
    entry = data["items"][0]
    assert entry["kind"] == "finding" and entry["phone_links"] == 1
    link = entry["links"][0]
    assert link["target_type"] == "phone_record" and link["relationship"] == "supports"
    assert link["citation"]["rec"] == "rec://%s" % world["evs"][0]["record_uid"]
    assert "the day before the payment" in link["citation"]["text"]  # full visibility
    assert "case_id" not in _tools(world)["get_casework"].args


def test_co11_dossier_returns_its_phone_links_with_citations_by_name_or_id(world):
    tools = _tools(world)
    for ref in ("Maria", str(world["dossier"])):
        out = tools["get_dossier"].invoke({"dossier": ref})
        item = out["data"]["items"][0]
        assert item["name"] == "Maria Lopez" and item["phone_links"] == 1
        assert item["links"][0]["citation"]["rec"] == "rec://%s" % world["evs"][2]["record_uid"]
        assert "payment sent" in item["links"][0]["citation"]["text"]
        assert "1 to phone material" in out["data"]["coverage"]


def test_a_dossier_or_record_of_another_case_is_not_in_this_case(world):
    tools = _tools(world)
    for ref in (str(world["foreign"]), "Zed Elsewhere"):
        out = tools["get_dossier"].invoke({"dossier": ref})
        assert out["data"]["not_in_case"] is True and out["summary"].startswith("Not in this case.")
        assert "Zed" not in str(out["data"]["items"])
    rec = tools["phone_record"].invoke({"record": str(world["other_rec"])})
    assert rec["data"]["not_in_case"] is True and "other case only" not in str(rec)
    gone = tools["phone_find_people"].invoke({"query": "Zed Elsewhere"})
    assert gone["summary"].startswith("Not in this case.")


def test_sa7_financial_tools_in_a_phones_only_case_say_there_is_no_financial_evidence(world):
    tools = _tools(world)
    for name in ("get_financial_transactions", "analyze_financial_transactions", "get_financial_coverage"):
        out = tools[name].invoke({})
        assert out["data"]["no_financial_evidence"] is True, name
        assert out["summary"].startswith("No financial evidence in this case."), out["summary"]
        assert "0 payments" not in str(out) and "0 transactions" not in str(out)
    # the phone tools answer in the same case, with full visibility
    msgs = tools["phone_messages"].invoke({"people": ["Maria Lopez"], "mode": "any"})
    assert msgs["data"]["total_matching"] == 2 and "payment sent" in str(msgs["data"]["items"])


def test_xf3_the_day_before_a_payment_cites_every_record_with_a_scope_sentence_and_names_unconfirmed(world):
    # "Who did the owner talk to the day before the payment of 2023-03-14?"
    out = _tools(world)["phone_messages"].invoke({"start": "2023-03-13", "end": "2023-03-13"})
    data = out["data"]
    assert data["total_matching"] == 2 and data["has_more"] is False
    assert all(i["rec"].startswith("rec://") for i in data["items"])
    assert data["coverage"].startswith("Read 2 of 2 messages and calls on 1 phone on 2023-03-13")
    assert len(data["unconfirmed"]) == 1 and "not yet confirmed" in out["summary"]
    clipped = _tools(world)["phone_messages"].invoke({"start": "2023-03-13", "end": "2023-03-13", "limit": 1})
    assert "Only 1 of 2 are in this result" in clipped["summary"]


def test_overview_timeline_and_map_count_the_phones_and_xf12_the_map_says_or_shows_phone_points(world, monkeypatch):
    from services.agent import tools as T
    monkeypatch.setattr(T.graph_service, "get_graph_summary", lambda case_id: {
        "total_nodes": 0, "total_relationships": 0, "entity_types": {}, "relationship_types": {}, "entities": []})
    monkeypatch.setattr(T.timeline_service, "get_timeline_page", lambda **kw: {"events": [], "count": 0})
    monkeypatch.setattr(T.geo_service, "get_entities_with_locations", lambda **kw: [])
    from tests.test_phone_map import _points
    with world["engine"].begin() as c:
        ext = c.execute(text("SELECT id FROM phone_extractions WHERE case_id = :c"),
                        {"c": str(world["case"])}).scalar()
        _points(c, world["case"], ext, [(38.9, -77.0)])
    tools = _tools(world)
    ov = tools["get_case_overview"].invoke({})
    assert ov["data"]["phones"] == {"phones": 1, "messages_and_calls": 3, "location_points": 1}
    assert "hold 3 messages and calls" in ov["summary"]
    tl = tools["get_timeline_events"].invoke({})
    assert "Phone messages and calls are not in this result; 3 are on the phones. Use the phone tools." in tl["summary"]
    mp = tools["get_map_locations"].invoke({})
    assert "Phone location points are not in this result; 1 is on the phones." in mp["summary"]
    left = tools["build_map_artifact"].invoke({})
    assert left["data"]["phone_points_included"] is False
    assert left["artifact"]["metadata"]["notes"].startswith("Phone location points are left out of this map; 1 is")
    shown = tools["build_map_artifact"].invoke({"include_phone_points": True})
    assert shown["data"]["phone_points_included"] is True and shown["data"]["phone_point_count"] == 1
    point = shown["artifact"]["data"]["locations"][0]
    assert point["rec"].startswith("rec://") and point["latitude"] == 38.9
    assert shown["artifact"]["metadata"]["notes"].startswith("Includes 1 of 1 phone location points")
    from services.agent import phone_tools

    def broken(*a, **k):
        raise RuntimeError("synthetic read failure")
    monkeypatch.setattr(phone_tools, "places", broken)
    kept = tools["build_map_artifact"].invoke({"include_phone_points": True})
    assert kept["status"] != "error" and kept["data"]["phone_points_included"] is False
    assert "could not be read just now" in kept["artifact"]["metadata"]["notes"]


def test_co18_an_accepted_agent_answer_is_ai_assisted_names_its_model_and_links_the_records_it_cites(world):
    from services.agent import accept
    from services.phone import resolvers
    from postgres.models.user import User
    resolvers.register()  # as main.py does at start-up
    case, rec = world["case"], world["evs"][0]["record_uid"]
    with world["engine"].begin() as c:
        owner = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar()
        thread, msg_id, question = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        c.execute(text("INSERT INTO agent_threads (id, case_id, owner_user_id, title, status) VALUES (:t, :c, :u, "
                       "'q', 'active')"), {"t": thread, "c": case, "u": owner})
        c.execute(text("INSERT INTO agent_messages (id, thread_id, sequence_number, role, content) VALUES (:m, :t, 1, "
                       "'user', 'Who wrote the day before?')"), {"m": question, "t": thread})
        c.execute(text("INSERT INTO agent_messages (id, thread_id, sequence_number, role, content, model_provider, "
                       "model_id) VALUES (:m, :t, 2, 'assistant', :b, 'openai', 'gpt-synthetic')"),
                  {"m": msg_id, "t": thread, "b": "Maria wrote first ([message](rec://%s)); a record of another case "
                                                    "(rec://%s) is not linked." % (rec, world["other_rec"])})
    with Session(bind=world["engine"]) as db:
        user = db.get(User, owner)
        out = accept.accept_answer_into_assessment(db, case_id=case, message_id=msg_id, dossier_id=world["dossier"],
                                                   category="Contact", user=user)
        assert out["provenance_type"] == "ai_assisted" and out["agent_message_id"] == str(msg_id)
        assert out["read_by"] == "Read by gpt-synthetic, accepted by synthetic"
        assert [l["target_id"] for l in out["supporting_links"]] == [rec]
        assert out["cited_records"]["not_in_case"] == 1
        assert "1 cited record is not in this case and was not linked." == out["cited_records"]["sentence"]
        for bad in (dict(message_id=question, dossier_id=world["dossier"]),       # a question is not an answer
                    dict(message_id=msg_id, dossier_id=world["foreign"])):        # a dossier of another case
            with pytest.raises((ValueError, LookupError)):
                accept.accept_answer_into_assessment(db, case_id=case, category="Contact", user=user, **bad)
        with pytest.raises(LookupError):                                          # asked in the other case
            accept.accept_answer_into_assessment(db, case_id=world["other"], message_id=msg_id,
                                                 dossier_id=world["foreign"], category="Contact", user=user)
        someone_else = User(id=uuid.uuid4(), email="else@synthetic.test", name="Else", password_hash="x")
        with pytest.raises(LookupError):                                          # another person's agent thread
            accept.accept_answer_into_assessment(db, case_id=case, message_id=msg_id, dossier_id=world["dossier"],
                                                 category="Contact", user=someone_else)
        db.rollback()


def test_xf10_ask_about_these_messages_reads_only_the_chosen_records_of_this_case_by_id(world):
    from services.phone import chat_retrieval
    from services.rag_service import RAGService
    chosen = [world["evs"][0]["record_uid"], "rec://%s" % world["evs"][2]["record_uid"], str(world["other_rec"])]
    ctx = {"thread": "t1", "scope_words": "Maria Lopez, 13 to 14 March 2023", "scope_total": 3, "record_ids": chosen}
    with world["engine"].connect() as c:
        got = chat_retrieval.selected_windows(c, world["case"], ctx)
    assert [g["metadata"]["record_uid"] for g in got] == [world["evs"][0]["record_uid"], world["evs"][2]["record_uid"]]
    assert "the day before the payment" in got[0]["text"] and got[0]["text"].endswith("[rec://%s]" % chosen[0])
    assert all("other case only" not in g["text"] for g in got)          # another case's record is never read
    block = RAGService._format_view_context({"label": "Conversations", "phone": ctx})
    assert "Scope: Maria Lopez, 13 to 14 March 2023" in block and "3 selected records of 3 in the scope" in block
    many = {"record_ids": [str(uuid.uuid4()) for _ in range(60)] + [world["evs"][0]["record_uid"]]}
    with world["engine"].connect() as c:
        assert chat_retrieval.selected_windows(c, world["case"], many) == []  # the 51st is past the cap: not read
    assert "Only the first 50 selected records are read with this question; 11 were left out." in \
        RAGService._format_view_context({"phone": many})
    # what was read is said to the model: 2 of the 3 chosen are in this case; a failed read is never silent
    two = RAGService._format_view_context({"phone": dict(ctx, _read=2)})
    assert "Only 2 of them were found in this case" in two and "the other 1 were not found in this case" in two
    failed = RAGService._format_view_context({"phone": dict(ctx, _read=None)})
    assert "could not be read just now" in failed and "appear below" not in failed
