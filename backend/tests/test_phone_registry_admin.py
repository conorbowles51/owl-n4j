"""cb-registry-admin B and D: the admin list of registry flags and mapping proposals (02 sections 3.4 and 6.8), and
the per-phone mapping backlog (3.4 "the backlog shown in the coverage map")."""
from __future__ import annotations

import json
import os
import uuid

import pytest
from sqlalchemy import text

from services.phone import proposals, registry
from tests.phone_pg import fresh_engine, make_case, make_extraction, model, needs_template

CALL_JSON = os.path.join(os.path.dirname(__file__), "..", "services", "phone", "mappings", "data", "type", "Call.json")


def _version(c, content):
    vid = uuid.uuid4()
    c.execute(text(
        "INSERT INTO phone_mapping_versions (id, kind, name, version, content_sha256, content, status, origin) VALUES "
        "(:i, :k, :n, :v, :sha, CAST(:c AS jsonb), 'applied_unconfirmed', 'ai_draft')"),
        {"i": vid, "k": content["kind"], "n": content["name"], "v": content["version"], "sha": "0" * 64,
         "c": json.dumps(content)})
    return vid


def _decision(c, case):
    did = uuid.uuid4()
    c.execute(text(
        "INSERT INTO adjudications (id, case_id, subject_type, subject_id, subject_sequence, decision, reason, "
        "actor_name, actor_email, created_at, before, after) VALUES (:d, :c, 'phone_extraction', gen_random_uuid(), 1, "
        "'correct_phone_reading', 'the other time is when it happened', 'Deciding Person', 'decider@x.test', now(), "
        "'{}', '{}')"), {"d": did, "c": case})
    return did


def _proposal(c, case, vid, rule_id, frm, to, label="When it happened is its other time"):
    """The row ``readings.correct`` writes (same columns and content keys)."""
    pid = uuid.uuid4()
    c.execute(text(
        "INSERT INTO phone_mapping_proposals (id, kind, name, content, origin, decision_id, state, case_id) VALUES "
        "(:id, 'type', 'Call', CAST(:c AS jsonb), 'case_correction', :d, 'draft', :case)"),
        {"id": pid, "d": _decision(c, case), "case": case,
         "c": json.dumps({"rule_id": rule_id, "mapping_version_id": str(vid), "from": frm, "to": to,
                          "label": label})})
    return pid


def _setup(c):
    with open(CALL_JSON, encoding="utf-8") as fh:
        call = json.load(fh)
    case = make_case(c)
    vid = _version(c, call)
    return case, vid, call


@needs_template
def test_proposals_list_is_paged_with_true_totals_and_shows_original_beside_correction():
    with fresh_engine() as engine, engine.begin() as c:
        case, vid, _ = _setup(c)
        ids = [_proposal(c, case, vid, "Call.event_time", "TimeStamp", "Zz%d" % i) for i in range(5)]
        page = proposals.list_proposals(c, limit=2, offset=0)
        assert page["total"] == 5 and len(page["proposals"]) == 2 and page["counts"]["draft"] == 5
        page3 = proposals.list_proposals(c, limit=2, offset=4)
        assert page3["total"] == 5 and len(page3["proposals"]) == 1
        p = proposals.list_proposals(c, origin="case_correction", state="draft", limit=50)["proposals"][0]
        assert p["original"] == "TimeStamp" and p["correction"].startswith("Zz")
        assert p["case"]["title"] == "synthetic phone test"
        assert p["decided_by"]["name"] == "Deciding Person" and p["decided_by"]["reason"]
        assert p["file_path"] == "backend/services/phone/mappings/data/type/Call.json"
        assert proposals.list_proposals(c, origin="ai_draft")["total"] == 0
        assert {x["id"] for x in proposals.list_proposals(c, limit=200)["proposals"]} == {str(i) for i in ids}


@needs_template
def test_reject_needs_a_reason_and_writes_the_event_before_the_state():
    with fresh_engine() as engine, engine.begin() as c:
        case, vid, _ = _setup(c)
        pid = _proposal(c, case, vid, "Call.event_time", "TimeStamp", "Other")
        with pytest.raises(proposals.ProposalRefused):
            proposals.reject(c, pid, "  ", actor_name="Admin Person")
        out = proposals.reject(c, pid, "the mapping is right globally", actor_name="Admin Person",
                               actor_email="admin@x.test")
        assert out["from"] == "draft" and out["to"] == "rejected"
        ev = c.execute(text("SELECT from_state, to_state, reason, actor_name FROM phone_mapping_proposal_events "
                            "WHERE proposal_id = :p"), {"p": pid}).fetchall()
        assert [tuple(e) for e in ev] == [("draft", "rejected", "the mapping is right globally", "Admin Person")]
        assert c.execute(text("SELECT state FROM phone_mapping_proposals WHERE id = :p"), {"p": pid}).scalar() == "rejected"
        with pytest.raises(proposals.ProposalRefused):
            proposals.reject(c, pid, "again", actor_name="Admin Person")
        with pytest.raises(proposals.ProposalRefused):
            proposals.export(c, pid, actor_name="Admin Person")
        listed = proposals.list_proposals(c)["proposals"][0]
        assert listed["last_event"]["to"] == "rejected" and listed["last_event"]["by"] == "Admin Person"


@needs_template
def test_export_writes_a_draft_file_with_the_correction_that_loads_once_a_person_reviews_it(tmp_path):
    from services.phone.mappings import loader
    with fresh_engine() as engine, engine.begin() as c:
        case, vid, call = _setup(c)
        pid = _proposal(c, case, vid, "Call.event_time", "TimeStamp", "StartTime")
        role = _proposal(c, case, vid, "Call.role.From", "caller", "callee")
        out = proposals.export(c, pid, actor_name="Admin Person", actor_email="admin@x.test")
        f = json.loads(out["text"])
        assert out["filename"] == "Call.json" and out["path"].endswith("data/type/Call.json")
        assert f["status"] == "draft" and f["origin"] == "human" and f["version"] == call["version"] + 1
        assert f["review"]["reviewed_by"] is None and str(pid) in f["review"]["basis"]
        assert f["body"]["event_time"]["field"] == "StartTime"
        assert f["body"]["participants"] == call["body"]["participants"]  # nothing else changed
        # as downloaded it is never applied; once a person reviews it, it loads with the correction
        p = tmp_path / "Call.json"
        p.write_text(out["text"])
        assert loader._parse(str(p)) is None
        f.update(status="reviewed", review=dict(f["review"], reviewed_by="A Person", reviewed_on="2026-11-04"))
        p.write_text(json.dumps(f))
        assert loader._parse(str(p)).body["event_time"]["field"] == "StartTime"
        # first download records exported (event first); a second download changes nothing
        assert c.execute(text("SELECT state FROM phone_mapping_proposals WHERE id = :p"), {"p": pid}).scalar() == "exported"
        assert proposals.export(c, pid, actor_name="Admin Person")["event_id"] is None
        n = c.execute(text("SELECT count(*) FROM phone_mapping_proposal_events WHERE proposal_id = :p"), {"p": pid}).scalar()
        assert n == 1
        rf = json.loads(proposals.export(c, role, actor_name="Admin Person")["text"])
        assert rf["body"]["participants"]["role_map"] == {"From": "callee", "To": "callee"}
        # an exported proposal can still be rejected
        assert proposals.reject(c, pid, "superseded", actor_name="Admin Person")["from"] == "exported"


@needs_template
def test_export_refuses_a_rule_the_file_cannot_express_and_changes_nothing():
    with fresh_engine() as engine, engine.begin() as c:
        case, vid, _ = _setup(c)
        pid = _proposal(c, case, vid, "Call.text", [], ["Body"])
        with pytest.raises(proposals.ProposalRefused):
            proposals.export(c, pid, actor_name="Admin Person")
        assert c.execute(text("SELECT state FROM phone_mapping_proposals WHERE id = :p"), {"p": pid}).scalar() == "draft"


@needs_template
def test_flag_list_is_paged_with_total_counts_subject_and_raising_phone_link():
    with fresh_engine() as engine, engine.begin() as c:
        registry.apply_seed(c)
        case = make_case(c)
        ext = make_extraction(c, case, [(0, None, 0, model("ZzzPageA", [])), (1, None, 1, model("ZzzPageB", [])),
                                        (2, None, 2, model("ZzzPageC", []))])
        fids = registry.observe_extraction(c, ext)["flag_ids"]
        assert len(fids) == 3
        registry.transition_flag(c, fids[0], "mapping_needed", "needs a reading", actor_name="Admin Person")
        everything = registry.list_flags_page(c, None, limit=200)
        page = registry.list_flags_page(c, "open", limit=1, offset=0)
        assert page["total"] == everything["counts"]["open"] and len(page["flags"]) == 1
        assert page["counts"]["mapping_needed"] == 1 and sum(page["counts"].values()) == everything["total"]
        mine = [f for f in everything["flags"] if f["id"] in fids]
        assert sorted(f["subject"]["type"] for f in mine) == ["ZzzPageA", "ZzzPageB", "ZzzPageC"]
        rb = mine[0]["raised_by"]
        assert rb["link"] == "/cases/%s/phones/%s" % (case, ext) and rb["label"] and rb["case_title"]
        moved = [f for f in mine if f["id"] == fids[0]][0]
        assert moved["last_event"]["to"] == "mapping_needed" and moved["last_event"]["by"] == "Admin Person"
        # D: the phone's backlog holds exactly the flag waiting for a mapping
        backlog = registry.mapping_backlog(c, ext)
        assert backlog["total"] == 1 and backlog["items"][0]["flag_id"] == fids[0]
        assert backlog["items"][0]["subject"]["type"] == "ZzzPageA"
        other = make_extraction(c, case, [(0, None, 0, model("ZzzElsewhere", []))])
        assert registry.mapping_backlog(c, other)["total"] == 0


@needs_template
def test_proposal_and_flag_endpoints_are_admin_only():
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
            case, vid, _ = _setup(c)
            pid = _proposal(c, case, vid, "Call.event_time", "TimeStamp", "StartTime")
            pid2 = _proposal(c, case, vid, "Call.event_time", "TimeStamp", "Other")
        Session = sessionmaker(bind=engine)
        app = FastAPI()
        app.include_router(router)
        role = {"r": GlobalRole.user}

        def db():
            s = Session()
            try:
                yield s
            finally:
                s.close()

        app.dependency_overrides[get_db] = db
        app.dependency_overrides[get_current_db_user] = lambda: User(
            id=uuid.uuid4(), email="admin@x.test", name="Admin Person", global_role=role["r"])
        with TestClient(app) as client:
            for call in (lambda: client.get("/api/phones/registry/proposals"),
                         lambda: client.get("/api/phones/registry/proposals/%s/export" % pid),
                         lambda: client.post("/api/phones/registry/proposals/%s/reject" % pid, json={"reason": "x"}),
                         lambda: client.get("/api/phones/registry/flags?state=open")):
                assert call().status_code == 403
            role["r"] = GlobalRole.admin
            listed = client.get("/api/phones/registry/proposals?state=draft&origin=case_correction&limit=1").json()
            assert listed["total"] == 2 and len(listed["proposals"]) == 1
            r = client.get("/api/phones/registry/proposals/%s/export" % pid)
            assert r.status_code == 200 and 'filename="Call.json"' in r.headers["content-disposition"]
            assert r.headers["x-mapping-path"].endswith("data/type/Call.json") and r.json()["status"] == "draft"
            assert client.post("/api/phones/registry/proposals/%s/reject" % pid2, json={"reason": ""}).status_code == 422
            assert client.post("/api/phones/registry/proposals/%s/reject" % pid2,
                               json={"reason": "right globally"}).status_code == 200
            assert client.post("/api/phones/registry/proposals/%s/reject" % pid2,
                               json={"reason": "again"}).status_code == 409
            assert client.get("/api/phones/registry/proposals/%s/export" % pid2).status_code == 409
            assert client.get("/api/phones/registry/proposals/%s/export" % uuid.uuid4()).status_code == 404
            assert client.get("/api/phones/registry/flags?limit=500").status_code == 422
        with engine.connect() as c:
            ev = c.execute(text("SELECT to_state, actor_name, actor_email FROM phone_mapping_proposal_events "
                                "ORDER BY id")).fetchall()
        assert [tuple(e) for e in ev] == [("exported", "Admin Person", "admin@x.test"),
                                          ("rejected", "Admin Person", "admin@x.test")]
