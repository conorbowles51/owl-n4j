"""07 J-8 and J-15 through the HTTP routes: Looks right for every row of a kind, a second person's re-check of a
sample of confirmations with its disagreement counts, the preview of a correction that would leave something empty,
the position of an assigned review on its task link, Hand over, and Continue reading. Synthetic phones and people."""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from services import manual_changes
from services.phone import reading_recheck, readings, registry, sweep
from tests.phone_pg import fresh_engine, make_case, make_extraction, needs_template
from tests.test_phone_mappings import CALL, call_extraction, fld, hooks, model, refs, stamp, write  # noqa: F401
from tests.test_phone_review_share import api, key_of, mark, split, threads  # noqa: F401 (fixture)

pytestmark = needs_template


@pytest.fixture
def rv(hooks, tmp_path, monkeypatch):  # noqa: F811
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from postgres.models.enums import GlobalRole
    from postgres.models.user import User
    from postgres.permissions import EDITOR_PERMISSIONS
    from postgres.session import get_db
    from routers.phones import router
    from routers.users import get_current_db_user
    from services.phone import resolvers

    write(str(hooks), CALL)
    readings.install()
    monkeypatch.setattr(manual_changes, "INBOX", tmp_path / "inbox.jsonl")
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = call_extraction(c, case, label="C1")
            sibling = call_extraction(c, case, label="C2")
            owner = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar()
            email = c.execute(text("SELECT email FROM users WHERE id = :u"), {"u": owner}).scalar()
            bea = uuid.uuid4()
            c.execute(text("INSERT INTO users (id,email,name,password_hash,global_role,is_active,created_at,updated_at) "
                           "VALUES (:u, :e, 'Bea Second', 'x', 'user', true, now(), now())"),
                      {"u": bea, "e": "b%s@x.test" % bea.hex[:8]})
            c.execute(text("INSERT INTO case_memberships (case_id, user_id, membership_role, permissions, "
                           "added_by_user_id, created_at, updated_at) VALUES (:c, :u, 'collaborator', "
                           "CAST(:p AS jsonb), :o, now(), now())"),
                      {"c": case, "u": bea, "o": owner, "p": json.dumps(EDITOR_PERMISSIONS)})
        assert sweep.interpret_one(engine, ext)["status"] == "done"
        assert sweep.interpret_one(engine, sibling)["status"] == "done"
        Session = sessionmaker(bind=engine)
        resolvers.register()
        app = FastAPI()
        app.include_router(router)
        people = {"owner": User(id=owner, email=email, name="Ann Owner", global_role=GlobalRole.user),
                  "bea": User(id=bea, email="bea@x.test", name="Bea Second", global_role=GlobalRole.user)}
        who = {"now": people["owner"]}

        def db():
            s = Session()
            try:
                yield s
            finally:
                s.close()

        app.dependency_overrides[get_db] = db
        app.dependency_overrides[get_current_db_user] = lambda: who["now"]
        with TestClient(app, raise_server_exceptions=True) as client:
            yield {"client": client, "case": str(case), "ext": str(ext), "sibling": str(sibling), "engine": engine,
                   "who": who, "people": people, "bea": str(bea), "owner": str(owner)}


def items(rv):
    r = rv["client"].get("/api/phones/readings", params={"case_id": rv["case"]})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def reading(rv, rule, ext=None):
    return next(i for i in items(rv) if i["rule_id"] == rule and i["extraction_id"] == (ext or rv["ext"]))


def row(rv, item):
    r = rv["client"].get("/api/phones/readings/%s/examples" % item["id"], params={"case_id": rv["case"]})
    assert r.status_code == 200, r.text
    kinds = [k["id"] for k in r.json()["kinds"]]
    return {"id": item["id"], "viewed": kinds, "opened": kinds}


def confirm_kind(rv, rows, **kw):
    return rv["client"].post("/api/phones/readings/confirm-kind", json={"case_id": rv["case"], "rows": rows, **kw})


def scalar(rv, sql, **p):
    with rv["engine"].connect() as c:
        return c.execute(text(sql), p).scalar()


# ---- A: Looks right for all rows of a kind ---------------------------------------------------------------------------

def test_every_listed_row_of_a_kind_is_its_own_decision_by_that_person(rv):
    a, b = reading(rv, "Call.role.From"), reading(rv, "Call.role.To")
    r = confirm_kind(rv, [row(rv, a), row(rv, b)], note="both sides read right")
    assert r.status_code == 200, r.text
    out = r.json()
    assert [x["id"] for x in out["confirmed"]] == [a["id"], b["id"]] and out["refused"] == []
    assert out["words"] == "Confirmed 2 rows under your name, each as its own decision."
    with rv["engine"].connect() as c:
        rows = c.execute(text("SELECT actor_name, actor_user_id::text AS uid, reason_kind, reason, after FROM "
                              "adjudications WHERE case_id = :c AND decision = 'confirm_phone_reading'"),
                         {"c": rv["case"]}).fetchall()
        assert c.execute(text("SELECT count(*) FROM manual_changes WHERE case_id = :c"), {"c": rv["case"]}).scalar() == 2
    assert len(rows) == 2
    assert {(x.actor_name, x.uid, x.reason_kind) for x in rows} == {("Ann Owner", rv["owner"], "standard")}
    assert all(x.after["listed_with_rows"] == 2 and x.after["note"] == "both sides read right" for x in rows)
    assert all(x.reason.startswith("Confirmed on the review screen after viewing") for x in rows)
    assert {reading(rv, "Call.role.From")["status"], reading(rv, "Call.role.To")["status"]} == {"confirmed"}


def test_a_row_not_listed_stays_open_and_is_counted_and_refused_rows_are_stated(rv):
    a, b = reading(rv, "Call.role.From"), reading(rv, "Call.role.To")
    r = confirm_kind(rv, [row(rv, a)])
    assert r.json()["not_listed"] == 1 and "1 row was not listed and stayed open." in r.json()["words"]
    assert reading(rv, "Call.role.To")["status"] == "open"
    # the kind's examples were not shown for this row, and another row is of another kind: both refused, nothing lost
    other = reading(rv, "Call.event_time")
    b2 = reading(rv, "Call.role.To")
    a2 = reading(rv, "Call.role.From", rv["sibling"])
    r = confirm_kind(rv, [{"id": b2["id"], "viewed": []}, row(rv, other)])
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["confirmed"] == [] and {x["id"] for x in out["refused"]} == {b2["id"], other["id"]}
    assert "Open every kind of example first" in next(x["reason"] for x in out["refused"] if x["id"] == b2["id"])
    assert "not of this kind" in next(x["reason"] for x in out["refused"] if x["id"] == other["id"])
    assert "2 rows were refused." in out["words"]
    # a reading a colleague already decided is refused with who did it; the rest of the list still lands
    rv["who"]["now"] = rv["people"]["bea"]
    assert confirm_kind(rv, [row(rv, a2)]).status_code == 200
    rv["who"]["now"] = rv["people"]["owner"]
    b3 = reading(rv, "Call.role.To", rv["sibling"])
    r = confirm_kind(rv, [{"id": a2["id"], "viewed": []}, row(rv, b3)]).json()
    assert [x["id"] for x in r["confirmed"]] == [b3["id"]]
    assert r["refused"][0]["reason"].startswith("Bea Second confirmed this")


def test_a_reading_of_another_phone_is_never_confirmed_with_the_kind(rv):
    a, other_phone = reading(rv, "Call.role.From"), reading(rv, "Call.role.From", rv["sibling"])
    out = confirm_kind(rv, [row(rv, a), row(rv, other_phone)]).json()
    assert [x["id"] for x in out["confirmed"]] == [a["id"]] and out["refused"][0]["id"] == other_phone["id"]
    assert reading(rv, "Call.role.From", rv["sibling"])["status"] == "open"


# ---- B: a second person's sample -------------------------------------------------------------------------------------

def confirm_all(rv, who="owner"):
    rv["who"]["now"] = rv["people"][who]
    for ext in (rv["ext"], rv["sibling"]):
        for i in items(rv):
            if i["status"] == "open" and i["extraction_id"] == ext:
                assert rv["client"].post("/api/phones/readings/%s/confirm" % i["id"], json={
                    "case_id": rv["case"], "viewed": row(rv, i)["viewed"]}).status_code == 200
    rv["who"]["now"] = rv["people"]["owner"]


def draw(rv, reviewer, **kw):
    return rv["client"].post("/api/phones/readings/rechecks", json={"case_id": rv["case"], "reviewer": reviewer, **kw})


def result(rv, who, task, cid, agrees, note=None):
    rv["who"]["now"] = rv["people"][who]
    r = rv["client"].post("/api/phones/readings/rechecks/result", json={
        "case_id": rv["case"], "task_id": task, "confirmation_id": cid, "agrees": agrees, "note": note})
    rv["who"]["now"] = rv["people"]["owner"]
    return r


def test_the_sample_is_five_percent_of_others_confirmations_seeded_and_never_ones_own(rv):
    assert "nothing to sample" in draw(rv, rv["bea"]).json()["detail"]
    confirm_all(rv)
    n = len(items(rv))
    # a person never samples their own
    r = draw(rv, rv["owner"])
    assert r.status_code == 422 and "%d confirmations, %d made by them" % (n, n) in r.json()["detail"]
    r = draw(rv, rv["bea"], seed=4242)
    assert r.status_code == 200, r.text
    made = r.json()
    assert made["percent"] == 5 and made["eligible"] == n and made["sample"] == max(1, -(-n * 5 // 100))
    # the same seed over the same confirmations draws the same sample
    import random
    ids = sorted(reading_recheck._confirmations(rv["engine"].connect(), rv["case"]), key=lambda c: c["confirmation_id"])
    assert [c["confirmation_id"] for c in random.Random(4242).sample(ids, made["sample"])] == made["confirmation_ids"]
    with rv["engine"].connect() as c:
        t = c.execute(text("SELECT assignee_user_id::text, status, description FROM case_tasks WHERE id = :t"),
                      {"t": made["task_id"]}).one()
        link = c.execute(text("SELECT source_anchor FROM case_task_links WHERE task_id = :t"),
                         {"t": made["task_id"]}).scalar()
    assert t[0] == rv["bea"] and t[1] == "todo" and "seed 4242" in t[2]
    assert link["seed"] == 4242 and link["items"][0]["first"]["by_name"] == "Ann Owner" and "mapping_versions" in link
    # a later draw never takes a confirmation twice, so each counts once in the rate
    second = draw(rv, rv["bea"], seed=1).json()
    assert second["eligible"] == n - made["sample"]
    assert not set(second["confirmation_ids"]) & set(made["confirmation_ids"])


def test_the_first_person_cannot_recheck_and_the_counts_are_true_with_no_rate_on_a_small_base(rv):
    confirm_all(rv)
    made = draw(rv, rv["bea"], percent=100).json()
    task, cids = made["task_id"], made["confirmation_ids"]
    before = scalar(rv, "SELECT count(*) FROM adjudications WHERE case_id = :c", c=rv["case"])
    r = result(rv, "owner", task, cids[0], True)
    assert r.status_code == 422 and "someone other than the person who confirmed it" in r.json()["detail"]
    assert result(rv, "bea", task, cids[0], False).status_code == 422  # a disagreement needs a note
    assert result(rv, "bea", task, cids[0], False, "the far end is the caller here").status_code == 200
    assert result(rv, "bea", task, cids[1], True).status_code == 200
    assert result(rv, "bea", task, cids[1], False, "looked again").status_code == 200  # the earlier result is kept
    rv["who"]["now"] = rv["people"]["bea"]
    s = rv["client"].get("/api/phones/readings/rechecks", params={"case_id": rv["case"]}).json()
    rv["who"]["now"] = rv["people"]["owner"]
    assert (s["sampled"], s["agrees"], s["disagrees"], s["pending"]) == (len(cids), 0, 2, len(cids) - 2)
    assert s["rate_percent"] is None and s["too_few"] is True and "%" not in s["words"]
    assert s["words"].startswith("2 of 2 checked confirmations disagree. Too few for a rate")
    assert "%d not yet checked." % (len(cids) - 2) in s["words"]
    row1 = next(i for i in s["items"] if i["confirmation_id"] == cids[1])
    assert row1["earlier_results"] == 1 and row1["mine"] and row1["status_now"] == "confirmed" and row1["reading_id"]
    # the confirmation itself is untouched; a disagreement writes no decision
    assert scalar(rv, "SELECT count(*) FROM adjudications WHERE case_id = :c", c=rv["case"]) == before
    assert {i["status"] for i in items(rv)} == {"confirmed"}
    with rv["engine"].connect() as c:
        from services.phone import review_share
        lines = review_share.cover_lines(review_share.coverage(c, rv["case"]))
    assert any(x.startswith("Re-check of confirmed readings: 2 of 2 checked") for x in lines)


def test_a_rate_shows_only_with_its_base():
    assert reading_recheck.rate_words(0, 0, 0)["words"] == "No confirmation has been sampled for a re-check."
    assert reading_recheck.rate_words(0, 0, 3)["words"] == "3 confirmations sampled; none checked yet."
    few = reading_recheck.rate_words(18, 1, 0)
    assert few["rate_percent"] is None and few["words"].startswith("1 of 19 checked confirmations disagree. Too few")
    ok = reading_recheck.rate_words(15, 5, 2)
    assert ok["rate_percent"] == 25.0
    assert ok["words"] == ("Disagreement rate 25.0%: 5 of 20 checked confirmations disagree. 2 not yet checked.")


def test_a_recheck_finishes_its_task_and_survives_a_re_read(rv):
    confirm_all(rv)
    made = draw(rv, rv["bea"], seed=7).json()
    sweep.interpret_one(rv["engine"], rv["ext"])
    sweep.interpret_one(rv["engine"], rv["sibling"])  # the judgement rows are written again; the decision stands
    s = rv["client"].get("/api/phones/readings/rechecks", params={"case_id": rv["case"]}).json()
    assert all(i["reading_id"] for i in s["items"])
    for cid in made["confirmation_ids"]:
        assert result(rv, "bea", made["task_id"], cid, True).status_code == 200
    assert scalar(rv, "SELECT status FROM case_tasks WHERE id = :t", t=made["task_id"]) == "done"


# ---- C: the preview of a correction ----------------------------------------------------------------------------------

def preview(rv, item, choice, scope="this_phone"):
    r = rv["client"].post("/api/phones/readings/%s/correct/preview" % item["id"],
                          json={"case_id": rv["case"], "choice": choice, "scope": scope})
    assert r.status_code == 200, r.text
    return r.json()


def correct(rv, item, choice, **kw):
    return rv["client"].post("/api/phones/readings/%s/correct" % item["id"], json={
        "case_id": rv["case"], "choice": choice, "reason": "the far end on this handset", **kw})


def no_role(rv, ext, role):
    return scalar(rv, "SELECT count(*) FROM phone_comm_events e JOIN phone_interpretation_state s ON s.extraction_id = "
                      "e.extraction_id AND s.generation = e.generation WHERE e.extraction_id = :e AND NOT EXISTS (SELECT "
                      "1 FROM phone_participations p WHERE p.record_uid = e.record_uid AND p.generation = e.generation "
                      "AND p.role = :r)", e=ext, r=role)


def test_a_correction_that_empties_a_role_is_previewed_with_the_true_count_and_writes_nothing_first(rv):
    item = reading(rv, "Call.role.From")
    assert no_role(rv, rv["ext"], "caller") == 0
    p = preview(rv, item, "role:callee")
    assert p["records"] == 3 and p["words"] == "After this change, 3 calls will have no caller."
    assert p["phones"] == [{"extraction_id": rv["ext"], "phone": "C1", "records": 3}]
    both = preview(rv, item, "role:callee", "same_format")
    assert both["records"] == 6 and both["words"] == "After this change, 6 calls will have no caller."
    assert scalar(rv, "SELECT count(*) FROM adjudications WHERE case_id = :c", c=rv["case"]) == 0
    # without the count the person agreed to, nothing is written and the sentence comes back
    r = correct(rv, item, "role:callee")
    assert r.status_code == 409 and r.json()["detail"] == "After this change, 3 calls will have no caller. Continue or cancel."
    assert scalar(rv, "SELECT count(*) FROM adjudications WHERE case_id = :c", c=rv["case"]) == 0
    assert reading(rv, "Call.role.From")["status"] == "open"
    assert correct(rv, item, "role:callee", expected_empty=3).status_code == 200
    assert sweep.interpret_one(rv["engine"], rv["ext"])["status"] == "done"
    assert no_role(rv, rv["ext"], "caller") == 3  # the count the person saw is what happened


def test_a_correction_that_empties_nothing_needs_no_agreement(rv):
    item = reading(rv, "Call.role.From")
    p = preview(rv, item, "role:unknown")
    assert p["records"] == 3  # nobody else on those calls is the caller
    q = reading(rv, "Call.role.To")
    r = preview(rv, q, "role:unknown")
    assert r["records"] == 3 and "no callee" in r["words"]
    meaning = [i for i in items(rv) if i["part"] == "meaning"]
    for m in meaning[:1]:
        if m["choices"]:
            assert preview(rv, m, m["choices"][0]["id"])["records"] == 0
    assert correct(rv, {"id": item["id"]}, "nonsense").status_code == 422


def test_a_time_correction_counts_the_records_the_chosen_field_does_not_hold(hooks, tmp_path, monkeypatch):  # noqa: F811
    from sqlalchemy.orm import Session
    from services.financial.decisions import Actor
    write(str(hooks), CALL)
    readings.install()
    monkeypatch.setattr(manual_changes, "INBOX", tmp_path / "inbox.jsonl")
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            records, stamps, o = [], [], 0
            for i in range(3):
                extra = [fld("EndTime", ("TimeStamp", "2023-03-14T16:00:00-04:00"))] if i == 0 else []
                call = model("Call", [fld("TimeStamp", ("TimeStamp", "2023-03-14T15:07:12-04:00")),
                                      fld("Direction", ("ModelDirections", "Outgoing"))] + extra +
                             [refs("Parties", o + 1, o + 2)])
                me = model("Party", [fld("Identifier", ("String", "+12025550100")), fld("Role", ("PartyRole", "From")),
                                     fld("IsPhoneOwner", ("Boolean", "True"))])
                them = model("Party", [fld("Identifier", ("String", "+12025550143")), fld("Role", ("PartyRole", "To")),
                                       fld("IsPhoneOwner", ("Boolean", "False"))])
                records += [(o, None, o, call), (o + 1, o, o, me), (o + 2, o, o, them)]
                stamps.append(stamp(o, "0.0", "TimeStamp", "Call"))
                if i == 0:
                    stamps.append(stamp(o, "2.0", "EndTime", "Call"))
                o += 3
            ext = make_extraction(c, case, records, timestamps=stamps, label="C1")
            uid, email = c.execute(text("SELECT u.id, u.email FROM users u JOIN cases k ON k.owner_user_id = u.id WHERE "
                                        "k.id = :c"), {"c": case}).one()
        assert sweep.interpret_one(engine, ext)["status"] == "done"
        with engine.connect() as c:
            jid = c.execute(text("SELECT j.id FROM phone_mapping_judgements j JOIN phone_interpretation_state s ON "
                                 "s.extraction_id = j.extraction_id AND s.generation = j.generation WHERE "
                                 "j.extraction_id = :e AND j.rule_id = 'Call.event_time'"), {"e": ext}).scalar()
            call = readings._call(c, case, jid)
            assert [x["id"] for x in readings.choices(c, call)] == ["field:EndTime"]
            p = readings.correction_preview(c, case, jid, choice_id="field:EndTime")
        assert p["records"] == 2 and p["words"] == "After this change, 2 calls will have no time."
        with Session(engine) as db:
            readings.correct(db, case, jid, choice_id="field:EndTime", reason="the end is what the phone logged",
                             actor=Actor(name="Ann Owner", email=email, user_id=uid), expected_empty=2)
            db.commit()
        assert sweep.interpret_one(engine, ext)["status"] == "done"
        with engine.connect() as c:
            assert c.execute(text(
                "SELECT count(*) FROM phone_comm_events e JOIN phone_interpretation_state s ON s.extraction_id = "
                "e.extraction_id AND s.generation = e.generation WHERE e.extraction_id = :e AND e.sort_instant IS "
                "NULL"), {"e": ext}).scalar() == 2  # the preview is what the re-reading did


# ---- D, E, F: positions, Hand over, Continue reading -----------------------------------------------------------------

def as_who(api, who):  # noqa: F811
    api["who"]["now"] = api["people"][who]


def mine_split(api):  # noqa: F811
    plan, body = split(api, "thread")
    r = api["client"].post("/api/phones/conversations/review/split", json={**body, "expect_threads": plan["threads"]})
    assert r.status_code == 200, r.text
    with api["engine"].connect() as c:
        rows = c.execute(text(
            "SELECT t.id::text, t.assignee_user_id::text AS who, l.target_id FROM case_task_links l JOIN case_tasks t "
            "ON t.id = l.task_id WHERE l.case_id = :c AND l.source_anchor ? 'review_split'"), {"c": api["case"]}).fetchall()
    bea = [x for x in rows if x.who == api["bea"]]
    return bea[0][0], [x.target_id for x in bea], [x.target_id for x in rows if x.who == api["owner"]]


def save_position(api, key, uid="ev-1"):  # noqa: F811
    r = api["client"].post("/api/phones/conversations/review/position", json={
        "case_id": api["case"], "thread_key": key, "position": {"event_uid": uid, "instant": "2023-03-14T09:00:00+00:00"}})
    assert r.status_code == 200, r.text
    return r.json()


def thread_state(api, key):  # noqa: F811
    r = api["client"].get("/api/phones/conversations/review/thread", params={"case_id": api["case"], "thread_key": key})
    assert r.status_code == 200, r.text
    return r.json()


def continue_work(api, threads_=()):  # noqa: F811
    r = api["client"].post("/api/phones/conversations/review/continue",
                           json={"case_id": api["case"], "threads": list(threads_)})
    assert r.status_code == 200, r.text
    return r.json()


def hand_over(api, task, to, note=None):  # noqa: F811
    return api["client"].post("/api/phones/conversations/review/tasks/%s/hand-over" % task,
                              json={"case_id": api["case"], "to_user": to, "note": note})


def test_the_assigned_persons_position_is_on_the_link_and_a_colleagues_reading_does_not_move_it(api):  # noqa: F811
    task, bea_keys, owner_keys = mine_split(api)
    k = bea_keys[0]
    as_who(api, "bea")
    assert save_position(api, k)["saved"] == 1
    assert save_position(api, owner_keys[0])["saved"] == 0  # not assigned to this person; the browser keeps it
    as_who(api, "owner")
    assert save_position(api, k, "ev-other")["saved"] == 0
    t = thread_state(api, k)["tasks"][0]
    assert t["position"]["event_uid"] == "ev-1" and t["position"]["by_name"] == "Bea Second" and not t["mine"]
    with api["engine"].connect() as c:
        a = c.execute(text("SELECT source_anchor FROM case_task_links WHERE task_id = :t AND target_id = :k"),
                      {"t": task, "k": k}).scalar()
    assert a["position"]["event_uid"] == "ev-1" and "review_split" in a  # the rest of the link is unchanged


def test_hand_over_reassigns_attaches_a_linked_note_and_the_colleague_resumes_there(api):  # noqa: F811
    task, bea_keys, _ = mine_split(api)
    k = bea_keys[0]
    as_who(api, "bea")
    save_position(api, k)
    mark(api, bea_keys[1], "bea") if len(bea_keys) > 1 else None
    as_who(api, "bea")
    r = hand_over(api, task, api["owner"], "Started on the first thread; the rest are untouched.")
    assert r.status_code == 200, r.text
    out = r.json()
    n_open = len(bea_keys) - (1 if len(bea_keys) > 1 else 0)
    assert out["positions"] == 1 and out["open_items"] == n_open
    assert out["words"].startswith("Handed over to ")
    with api["engine"].connect() as c:
        assert str(c.execute(text("SELECT assignee_user_id FROM case_tasks WHERE id = :t"), {"t": task}).scalar()) == api["owner"]
        e = c.execute(text("SELECT entry_type, title, body, author_name FROM workspace_entries WHERE id = :e"),
                      {"e": out["note_id"]}).one()
        assert e.entry_type == "note" and e.author_name == "Bea Second" and e.title.startswith("Handover: ")
        assert "**Positions**" in e.body and "stopped at the message of" in e.body and "**Open items**" in e.body
        assert "not yet reviewed" in e.body and "Started on the first thread" in e.body
        assert "made by Loupe at that moment" in e.body
        assert c.execute(text("SELECT count(*) FROM workspace_entry_links WHERE entry_id = :e AND target_type = 'task' "
                              "AND target_id = :t"), {"e": out["note_id"], "t": task}).scalar() == 1
        assert c.execute(text("SELECT count(*) FROM case_task_links WHERE task_id = :t AND target_type = 'entry' AND "
                              "target_id = :e"), {"t": task, "e": out["note_id"]}).scalar() == 1
    as_who(api, "owner")
    t = next(x for x in thread_state(api, k)["tasks"] if x["task_id"] == task)
    assert t["mine"] and t["position"]["event_uid"] == "ev-1" and t["position"]["by_name"] == "Bea Second"
    # the position passed with the task: it is in the colleague's Continue reading, and gone from the first person's
    work = next(x for x in continue_work(api)["assigned"] if x["task_id"] == task)
    assert [i["thread_key"] for i in work["items"]] == [k]
    assert work["items"][0]["position"]["event_uid"] == "ev-1"
    as_who(api, "bea")
    assert all(x["task_id"] != task for x in continue_work(api)["assigned"])
    # now the colleague's reading moves it
    as_who(api, "owner")
    assert save_position(api, k, "ev-2")["saved"] == 1


def test_hand_over_refuses_who_could_not_do_it_and_changes_nothing(api):  # noqa: F811
    from postgres.permissions import VIEWER_PERMISSIONS
    task, bea_keys, _ = mine_split(api)
    assert hand_over(api, task, api["bea"]).status_code == 422  # the task is already theirs
    assert hand_over(api, task, api["outsider"]).status_code == 422  # not a member
    with api["engine"].begin() as c:
        c.execute(text("INSERT INTO case_memberships (case_id, user_id, membership_role, permissions, "
                       "added_by_user_id, created_at, updated_at) VALUES (:c, :u, 'collaborator', CAST(:p AS jsonb), "
                       ":o, now(), now())"),
                  {"c": api["case"], "u": api["outsider"], "o": api["owner"], "p": json.dumps(VIEWER_PERMISSIONS)})
    r = hand_over(api, task, api["outsider"])
    assert r.status_code == 422 and "can only view" in r.json()["detail"]
    assert hand_over(api, uuid.uuid4(), api["owner"]).status_code == 404
    with api["engine"].connect() as c:
        assert str(c.execute(text("SELECT assignee_user_id FROM case_tasks WHERE id = :t"), {"t": task}).scalar()) == api["bea"]
        assert c.execute(text("SELECT count(*) FROM workspace_entries WHERE case_id = :c"), {"c": api["case"]}).scalar() == 0


def test_a_second_pass_is_never_handed_to_its_first_reviewer(api):  # noqa: F811
    k = threads(api)["items"][0]["thread_key"]
    mark(api, k, "bea")
    r = api["client"].post("/api/phones/conversations/review/second-pass",
                           json={"case_id": api["case"], "reviewer": api["owner"], "percent": 100})
    assert r.status_code == 200, r.text
    r2 = hand_over(api, r.json()["task_id"], api["bea"])
    assert r2.status_code == 422 and "never re-checks their own" in r2.json()["detail"]


def test_continue_reading_lists_open_assigned_threads_and_casual_ids_get_their_titles_from_the_server(api):  # noqa: F811
    task, bea_keys, _ = mine_split(api)
    all_keys = [t["thread_key"] for t in threads(api)["items"]]
    as_who(api, "bea")
    work = continue_work(api)
    t = next(x for x in work["assigned"] if x["task_id"] == task)
    assert t["open"] == t["total"] == len(bea_keys) and t["items"] == [] and t["next"]["thread_key"] == bea_keys[0]
    save_position(api, bea_keys[0])
    t = next(x for x in continue_work(api)["assigned"] if x["task_id"] == task)
    assert [i["thread_key"] for i in t["items"]] == [bea_keys[0]] and t["items"][0]["extraction_id"] == api["ext"]
    as_who(api, "owner")
    # a thread reviewed in full leaves the list; a key not in the case is dropped; a title comes from the server
    done, kept = all_keys[0], all_keys[1]
    mark(api, done)
    assign = {i["thread_key"] for x in continue_work(api)["assigned"] for i in x["items"] + ([x["next"]] if x["next"] else [])}
    casual = [{"thread": kept, "record": "ev-9"}, {"thread": done}, {"thread": "not-in-this-case"}]
    out = continue_work(api, casual)["reading"]
    assert [r["thread_key"] for r in out] == ([] if kept in assign else [kept])
    if out:
        assert out[0]["title"] and out[0]["record"] == "ev-9" and out[0]["extraction_id"] == api["ext"]
