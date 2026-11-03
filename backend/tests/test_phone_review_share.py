"""07 J-13 steps 1, 5 and 6 and its failure state through the HTTP routes: Split for review, the second pass, "[name]
is also reviewing this thread." and the coverage summary (searches run, terms, who reviewed what, what is left), and
the coverage on the export cover. Two synthetic people on a synthetic phone; no case material."""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

OWNER, ANA, BEN, CAL = ("phone:+12025550100", "phone:+12025550143", "phone:+12025550188", "phone:+12025550177")
pytestmark = needs_template


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
    from postgres.permissions import EDITOR_PERMISSIONS
    from postgres.session import get_db
    from routers.phones import router
    from routers.search import router as search_router
    from routers.users import get_current_db_user

    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            ext, evs = phone(c, case, contacts={ANA: "Maria Lopez", BEN: "Ben Ode", CAL: "Cal Tan"}, events=[
                msg(at(2023, 3, 14, 9), ANA, [OWNER], thread="t", body="first apple"),
                msg(at(2023, 3, 14, 10), OWNER, [ANA], thread="t"),
                msg(at(2023, 3, 14, 11), ANA, [OWNER], thread="w", app="Signal"),
                msg(at(2023, 3, 15, 9), BEN, [OWNER], thread="u", body="apple pie"),
                msg(at(2023, 3, 15, 10), CAL, [OWNER], thread="v"),
                msg(at(2023, 3, 16, 9), ANA, [OWNER, BEN], thread="g")],
                threads={"g": {"chat_type": "Group", "title": "Trip", "members": [OWNER, ANA, BEN]}})
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
            outsider = uuid.uuid4()
            c.execute(text("INSERT INTO users (id,email,name,password_hash,global_role,is_active,created_at,updated_at) "
                           "VALUES (:u, :e, 'Not a member', 'x', 'user', true, now(), now())"),
                      {"u": outsider, "e": "o%s@x.test" % outsider.hex[:8]})
        Session = sessionmaker(bind=engine)
        from services.phone import resolvers
        resolvers.register()
        app = FastAPI()
        app.include_router(router)
        app.include_router(search_router)
        people = {"owner": User(id=owner, email=email, name="synthetic", global_role=GlobalRole.user),
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
            yield {"client": client, "case": str(case), "ext": str(ext), "engine": engine, "who": who,
                   "people": people, "owner": str(owner), "bea": str(bea), "outsider": str(outsider)}


def threads(api):
    r = api["client"].post("/api/phones/conversations/threads?sort=name", json={"case_id": api["case"]})
    assert r.status_code == 200, r.text
    return r.json()


def key_of(api, title_part):
    return next(t["thread_key"] for t in threads(api)["items"] if title_part in t["title"])


def mark(api, key, who="owner"):
    api["who"]["now"] = api["people"][who]
    r = api["client"].post("/api/phones/conversations/review", json={"case_id": api["case"], "thread_key": key})
    assert r.status_code == 200, r.text
    api["who"]["now"] = api["people"]["owner"]


def coverage(api):
    r = api["client"].get("/api/phones/conversations/review/coverage", params={"case_id": api["case"]})
    assert r.status_code == 200, r.text
    return r.json()


def split(api, by, **kw):
    body = {"filter": {"case_id": api["case"]}, "by": by, "reviewers": [api["owner"], api["bea"]], **kw}
    p = api["client"].post("/api/phones/conversations/review/split/preview", json=body)
    assert p.status_code == 200, p.text
    return p.json(), body


def test_split_by_person_keeps_a_person_together_shows_counts_first_and_makes_assigned_tasks(api):
    c = api["client"]
    tl = threads(api)
    total = tl["counts"]["threads"]
    assert total == 5  # t, w, u, v and g; every event has a thread, so there is no "Not in a conversation" row
    plan, body = split(api, "person")
    assert plan["threads"] == total and sum(p["threads"] for p in plan["parts"]) == total
    assert sum(p["messages"] for p in plan["parts"]) == sum(t["event_count_total"] for t in tl["items"])
    assert "thread_keys" not in plan["parts"][0]  # the preview is counts only
    # nothing is made by the preview
    with api["engine"].connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM case_tasks WHERE case_id = :c"), {"c": api["case"]}).scalar() == 0
    # the split needs the count the person saw; a stale count makes nothing
    assert c.post("/api/phones/conversations/review/split", json=body).status_code == 422
    r = c.post("/api/phones/conversations/review/split", json={**body, "expect_threads": total + 1})
    assert r.status_code == 409 and "changed" in r.json()["detail"]
    r = c.post("/api/phones/conversations/review/split", json={**body, "expect_threads": total})
    assert r.status_code == 200, r.text
    made = r.json()
    assert len(made["tasks"]) == 2 and {t["reviewer"]["user_id"] for t in made["tasks"]} == {api["owner"], api["bea"]}
    with api["engine"].connect() as conn:
        rows = conn.execute(text(
            "SELECT t.assignee_user_id::text AS who, l.target_id, l.source_anchor FROM case_task_links l JOIN "
            "case_tasks t ON t.id = l.task_id WHERE l.case_id = :c"), {"c": api["case"]}).fetchall()
    assert len(rows) == total and len({r.target_id for r in rows}) == total
    by_key = {r.target_id: r.who for r in rows}
    # Maria Lopez's two one-to-one threads (two apps) go to the same reviewer; the group thread is its own unit
    assert by_key[key_of(api, "Maria")] == next(by_key[t["thread_key"]] for t in tl["items"]
                                                  if t["app"] == "Signal")
    # an assignment is not a review: the coverage is unchanged
    assert coverage(api)["counts"]["reviewed"] == 0
    # a reviewer outside the case is refused
    bad = {**body, "reviewers": [api["outsider"]]}
    assert c.post("/api/phones/conversations/review/split/preview", json=bad).status_code == 422


def test_a_mark_in_a_split_task_counts_in_the_one_coverage_and_moves_the_task_on(api):
    c = api["client"]
    plan, body = split(api, "thread")
    made = c.post("/api/phones/conversations/review/split", json={**body, "expect_threads": plan["threads"]}).json()
    bea_task = next(t for t in made["tasks"] if t["reviewer"]["user_id"] == api["bea"])
    with api["engine"].connect() as conn:
        keys = [r[0] for r in conn.execute(text("SELECT target_id FROM case_task_links WHERE task_id = :t"),
                                           {"t": bea_task["task_id"]})]
    mark(api, keys[0], "bea")
    cov = coverage(api)
    assert cov["counts"]["reviewed"] == 1 and threads(api)["counts"]["reviewed"] == 1
    split_row = next(s for s in cov["splits"] if s["task_id"] == bea_task["task_id"])
    assert split_row["reviewed"] == 1 and split_row["threads"] == len(keys)
    with api["engine"].connect() as conn:
        status = lambda: conn.execute(text("SELECT status FROM case_tasks WHERE id = :t"),
                                      {"t": bea_task["task_id"]}).scalar()
        assert status() == ("in_progress" if len(keys) > 1 else "done")
    for k in keys[1:]:
        mark(api, k, "bea")
    with api["engine"].connect() as conn:
        assert conn.execute(text("SELECT status FROM case_tasks WHERE id = :t"),
                            {"t": bea_task["task_id"]}).scalar() == "done"
    # a second split leaves out what is already reviewed, and says so
    plan2, _ = split(api, "thread")
    assert plan2["already_reviewed_left_out"] == len(keys) and plan2["threads"] == 5 - len(keys)


def test_the_coverage_summary_always_equals_the_marks(api):
    """07 J-13 target [S]: after each mark, undo and Replace-like growth, the summary's counts are the marks'."""
    c = api["client"]
    for k, who in ((key_of(api, "Maria"), "owner"), (key_of(api, "Ben"), "bea"), (key_of(api, "Trip"), "bea")):
        mark(api, k, who)
        cov, tl = coverage(api), threads(api)
        for name in ("threads", "reviewed", "partly_reviewed", "not_reviewed"):
            assert cov["counts"][name] == tl["counts"][name], name
        assert len(cov["reviewed"]) == cov["counts"]["reviewed"]
        assert len(cov["not_reviewed"]) + len(cov["partly_reviewed"]) == cov["counts"]["not_reviewed"]
    cov = coverage(api)
    assert {p["name"]: p["reviewed"] for p in cov["reviewers"]} == {"Bea Second": 2, "synthetic": 1}
    assert c.post("/api/phones/conversations/review/undo",
                  json={"case_id": api["case"], "thread_key": key_of(api, "Ben")}).status_code == 200
    assert coverage(api)["counts"]["reviewed"] == threads(api)["counts"]["reviewed"] == 2
    # a message added after the review makes the thread partly reviewed in both (J-13b)
    with api["engine"].begin() as conn:
        conn.execute(text("UPDATE phone_threads SET event_count = event_count + 1 WHERE thread_key = :k"),
                     {"k": key_of(api, "Trip")})
    cov, tl = coverage(api), threads(api)
    assert cov["counts"]["partly_reviewed"] == tl["counts"]["partly_reviewed"] == 1
    assert cov["counts"]["reviewed"] == tl["counts"]["reviewed"] == 1
    assert cov["partly_reviewed"][0]["added_since"] == 1


def test_second_pass_samples_with_a_recorded_seed_for_a_different_person_and_keeps_the_first_mark(api):
    c = api["client"]
    keys = [t["thread_key"] for t in threads(api)["items"]]
    for k in keys[:4]:
        mark(api, k, "owner")
    mark(api, keys[4], "bea")
    before = {t["thread_key"]: t["review"] for t in threads(api)["items"]}
    r = c.post("/api/phones/conversations/review/second-pass",
               json={"case_id": api["case"], "reviewer": api["bea"], "seed": 1234})
    assert r.status_code == 200, r.text
    sp = r.json()
    # Bea reviewed one thread first, so it is not hers to re-check: 4 eligible, 10% rounds up to 1
    assert sp["eligible"] == 4 and sp["sample"] == 1 and sp["seed"] == 1234 and keys[4] not in sp["thread_keys"]
    again = c.post("/api/phones/conversations/review/second-pass",
                   json={"case_id": api["case"], "reviewer": api["bea"], "seed": 1234}).json()
    assert again["thread_keys"] == sp["thread_keys"]  # the seed draws the same sample
    k = sp["thread_keys"][0]
    body = {"case_id": api["case"], "task_id": sp["task_id"], "thread_key": k, "agrees": False}
    # the first reviewer cannot be their own second pass
    assert c.post("/api/phones/conversations/review/second-pass/result", json={**body, "note": "x"}).status_code == 422
    api["who"]["now"] = api["people"]["bea"]
    assert c.post("/api/phones/conversations/review/second-pass/result", json=body).status_code == 422  # needs a note
    r = c.post("/api/phones/conversations/review/second-pass/result", json={**body, "note": "missed the late reply"})
    assert r.status_code == 200, r.text
    assert r.json()["words"].startswith("Second pass by Bea Second: disagrees with synthetic's review.")
    r = c.post("/api/phones/conversations/review/second-pass/result", json={**body, "agrees": True})
    assert r.json()["earlier_results"] == 1  # the earlier result is kept
    api["who"]["now"] = api["people"]["owner"]
    after = {t["thread_key"]: t["review"] for t in threads(api)["items"]}
    assert after == before  # the first marks are never touched
    cov = coverage(api)
    first = next(s for s in cov["second_pass"] if s["task_id"] == sp["task_id"])
    assert first["sampled"] == 1 and first["agrees"] == 1 and first["seed"] == 1234
    st = c.get("/api/phones/conversations/review/thread", params={"case_id": api["case"], "thread_key": k}).json()
    assert len(st["second_pass"]) == 2 and st["second_pass"][0]["first"]["reviewed_by_name"] == "synthetic"
    # nobody else reviewed anything first, so Bea's own threads only: nothing to sample for the owner here
    r = c.post("/api/phones/conversations/review/second-pass", json={"case_id": api["case"], "reviewer": api["owner"]})
    assert r.status_code == 200 and r.json()["eligible"] == 1


def test_also_reviewing_names_the_other_person_only_and_expires(api):
    c = api["client"]
    k = key_of(api, "Maria")
    body = {"case_id": api["case"], "thread_key": k}
    assert c.post("/api/phones/conversations/presence", json=body).json()["others"] == []
    api["who"]["now"] = api["people"]["bea"]
    r = c.post("/api/phones/conversations/presence", json=body).json()
    assert r["words"] == "synthetic is also reviewing this thread." and r["next_in_seconds"] >= 30
    api["who"]["now"] = api["people"]["owner"]
    assert c.post("/api/phones/conversations/presence", json=body).json()["others"] == ["Bea Second"]
    # another thread is not this thread
    other = c.post("/api/phones/conversations/presence", json={**body, "thread_key": key_of(api, "Ben")}).json()
    assert other["others"] == []
    # a beat older than the expiry no longer counts
    with api["engine"].begin() as conn:
        conn.execute(text("UPDATE presence_sessions SET last_active = now() - interval '5 minutes' WHERE user_id = :u"),
                     {"u": api["bea"]})
    assert c.post("/api/phones/conversations/presence", json=body).json()["others"] == []
    # leaving removes the person at once
    api["who"]["now"] = api["people"]["bea"]
    c.post("/api/phones/conversations/presence", json=body)
    c.post("/api/phones/conversations/presence", json={**body, "leaving": True})
    api["who"]["now"] = api["people"]["owner"]
    assert c.post("/api/phones/conversations/presence", json=body).json()["others"] == []


def test_searches_run_and_terms_are_in_the_coverage_summary(api):
    c = api["client"]
    assert coverage(api)["searches"] == []
    f = {"case_id": api["case"], "text": {"query": "apple"}}
    assert c.post("/api/phones/streams/index", json=f).status_code == 200
    assert c.post("/api/phones/streams/index", json=f).status_code == 200
    assert c.post("/api/phones/streams/index", json={"case_id": api["case"]}).status_code == 200  # no text: no row
    assert c.get("/api/search", params={"case_id": api["case"], "q": "pie", "groups": "messages"}).status_code == 200
    cov = coverage(api)
    runs = {s["query"]: s for s in cov["searches"]}
    assert set(runs) == {"apple", "pie"}
    assert runs["apple"]["runs"] == 2 and runs["apple"]["last_hits"] == 2 and runs["apple"]["people"] == ["synthetic"]
    assert runs["pie"]["surfaces"] == ["search"]
    assert cov["terms"] == ["apple", "pie"]
    assert any('"apple"' in line for line in cov["cover"])


def test_the_export_cover_prints_the_review_coverage_of_its_threads(api, monkeypatch):
    from services.phone import review_share
    from services.phone.exports import jobs, pdf
    k = key_of(api, "Maria")
    mark(api, k, "bea")
    api["client"].post("/api/phones/streams/index", json={"case_id": api["case"], "text": {"query": "apple"}})
    seen = {}
    real = pdf.build_html

    def spy(**kw):
        seen.update(kw)
        return real(**kw)

    monkeypatch.setattr(pdf, "build_html", spy)
    monkeypatch.setattr(pdf, "render_isolated", lambda doc: doc.encode())
    monkeypatch.setattr(jobs, "export_dir", lambda: __import__("pathlib").Path("/mnt/owl-data/tmp/cbr-exports"))
    with api["engine"].begin() as conn:
        eid = jobs.create(conn, case_id=api["case"], user_id=api["owner"], fmt="pdf", source="stream",
                          filter_body={"case_id": api["case"], "threads": [k]}, options={})["export_id"]
    out = jobs.draw(api["engine"], eid)
    assert out["counts"]["review"] == {"threads": 1, "reviewed": 1, "partly_reviewed": 0, "not_reviewed": 0,
                                       "never_reviewed": 0}
    lines = seen["review"]
    assert lines[0] == "Not yet reviewed: 0 of 1 thread. Reviewed: 1. Partly reviewed (messages added since): 0."
    assert "Reviewed by: Bea Second, 1 thread." in lines
    doc, _ = real(**seen)
    assert "<h2>Review coverage</h2>" in doc and "Review coverage of these threads" in doc
    with api["engine"].connect() as conn:
        assert review_share.coverage(conn, api["case"], thread_keys={k})["counts"] == out["counts"]["review"]
