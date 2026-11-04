"""cb-mapdrafts: AI mapping drafts for the phone registry (02 section 6.8 step 2).

B: the ``phone_mapping_draft`` workload (DeepSeek's strongest model by default, thinking at max).
C: ``POST /api/phones/registry/mapping-drafts`` builds its input from the registry's structure only; the answer is
   validated against the mapping schema and the registry; a valid answer is a ``draft`` proposal, an invalid one a
   ``rejected`` proposal with the reason, no answer a ``failed`` run with the reason.
D: the export of an AI draft is a ``status: draft`` file whose basis says "Drafted by <model> · not reviewed".
"""
from __future__ import annotations

import glob
import json
import os
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import sessionmaker

from tests.phone_pg import fld, fresh_engine, make_case, make_extraction, model, needs_template

DATA = os.path.join(os.path.dirname(__file__), "..", "services", "phone", "mappings", "data")
CASE_WORD = "Zqxsyntheticcaseword"


def _shipped(kind, name):
    with open(os.path.join(DATA, kind, "%s.json" % name), encoding="utf-8") as fh:
        return json.load(fh)


# ---- B: the workload -------------------------------------------------------------------------------------------

def test_the_draft_workload_is_registered_and_runs_on_deepseeks_strongest_model_by_default():
    from services import ai_model_policy as p
    assert p.WORKLOADS["phone_mapping_draft"]["group"] == "Phones"
    assert p.DEFAULT_POLICY["phone_mapping_draft"] == {"provider": "deepseek", "model_id": "deepseek-v4-pro"}
    for provider, profile in p.PROVIDER_DEFAULTS.items():
        assert profile["phone_mapping_draft"]["provider"] == provider


def test_deepseek_thinks_at_max_only_when_asked():
    from services.llm_service import LLMExecutionContext
    sent = []

    class Answer:
        def raise_for_status(self):
            return None

        def json(self):
            return {"model": "deepseek-v4-pro", "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}}

    def post(url, **kw):
        sent.append(kw["json"])
        return Answer()

    with patch("services.llm_service.requests.post", side_effect=post):
        llm = LLMExecutionContext(provider="deepseek", model_id="deepseek-v4-pro", api_key="k")
        llm.call("p", json_mode=True, reasoning_effort="max")
        llm.call("p", json_mode=True)
    assert sent[0]["thinking"] == {"type": "enabled"} and sent[0]["reasoning_effort"] == "max"
    assert "temperature" not in sent[0] and sent[0]["max_tokens"] >= 32000
    assert sent[1]["thinking"] == {"type": "disabled"} and "reasoning_effort" not in sent[1]
    assert llm.last_usage["completion_tokens"] == 20


def test_an_incomplete_thinking_answer_is_an_error_not_a_draft():
    from services.llm_service import LLMExecutionContext

    class Answer:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "{\"body\":"}, "finish_reason": "length"}], "usage": {}}

    with patch("services.llm_service.requests.post", return_value=Answer()):
        llm = LLMExecutionContext(provider="deepseek", model_id="deepseek-v4-pro", api_key="k")
        with pytest.raises(ValueError, match="incomplete"):
            llm.call("p", json_mode=True, reasoning_effort="max")


# ---- C: input, validation, runs --------------------------------------------------------------------------------

def _registry_with_a_phone(c):
    """The seed registry, and one synthetic phone in a case whose records carry a word only a case could hold."""
    from services.phone import registry
    registry.apply_seed(c)
    case = make_case(c)
    call = model("Call", [fld("Account", ("String", CASE_WORD)), fld("TimeStamp", ("TimeStamp", "2026-01-01T10:00:00Z")),
                          fld("Direction", ("ModelDirections", "Incoming"))])
    ext = make_extraction(c, case, [(1, None, 1, call)])
    registry.observe_extraction(c, ext)
    return case, ext


@needs_template
def test_the_input_is_registry_structure_only_no_record_case_or_evidence_value():
    from services.phone import mapping_drafts as md
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, ext = _registry_with_a_phone(c)
        seen = []
        event.listen(engine, "before_cursor_execute", lambda *a: seen.append(a[2]))
        with engine.connect() as c:
            texts = []
            for name in ("Call", "InstantMessage", "DecodingSourceOptions"):
                inp = md.build_input(c, name)
                texts.append(md.prompt(inp))
        for p in texts:
            assert CASE_WORD not in p
            assert str(case) not in p and str(ext) not in p
            assert "extraction_id" not in p and "case_id" not in p and "evidence_file" not in p and "record_uid" not in p
        tables = set()
        for s in seen:
            for word in s.replace("(", " ").replace(",", " ").split():
                if word.startswith(("phone_", "cases", "evidence", "users")):
                    tables.add(word)
        assert tables and all(t.startswith("phone_schema_") for t in tables), tables
        call = md.build_input(engine.connect(), "Call")
        names = {f["field"] for f in call["subject"]["fields"]}
        assert {"TimeStamp", "Direction", "Duration"} <= names
        assert any(n["field"] == "Parties" and n["child_type"] == "Party" for n in call["subject"]["nested"])
        assert call["existing_mapping"]["name"] == "Call"


@needs_template
def test_a_named_set_draws_attribution_rows_and_every_set_limit_is_stated():
    from services.phone import mapping_drafts as md
    with fresh_engine() as engine, engine.begin() as c:
        from services.phone import registry
        registry.apply_seed(c)
        for i in range(md.SET_VALUES_SHOWN + 5):
            c.execute(text("INSERT INTO phone_schema_set_values (set_name, value, origin) VALUES "
                           "('DecodingSourceOptions', :v, 'observed')"), {"v": "Extra %03d" % i})
        inp = md.build_input(c, "DecodingSourceOptions")
        assert inp["kind"] == "attribution"
        s = inp["named_sets"]["DecodingSourceOptions"]
        assert s["values_shown"] == md.SET_VALUES_SHOWN and s["total_values"] > md.SET_VALUES_SHOWN
        assert '"total_values":%d' % s["total_values"] in md.prompt(inp)
        assert any(x["field"] == "UserMapping" and "TimeStamp" in x["type_time_fields"]
                   for x in inp["subject"]["carried_by"] if x["type"] == "Call")
        with pytest.raises(md.DraftRefused) as no:
            md.subject_kind(c, "NoSuchTypeAnywhere")
        assert no.value.status == 404


@needs_template
def test_every_shipped_type_mapping_passes_the_draft_validator():
    """The validator accepts what a person already committed (no false refusals on the real shape)."""
    from services.phone import mapping_drafts as md
    from services.phone import registry
    with fresh_engine() as engine, engine.begin() as c:
        registry.apply_seed(c)
        types = set(c.execute(text("SELECT type_name FROM phone_schema_types")).scalars())
        checked = 0
        for path in sorted(glob.glob(os.path.join(DATA, "type", "*.json"))):
            with open(path, encoding="utf-8") as fh:
                m = json.load(fh)
            if m["body"]["applies_to"] not in types:
                continue
            assert md.type_body_problems(c, m["body"]) == [], m["name"]
            checked += 1
        assert checked >= 18


def _ask(answer, model_id="deepseek-v4-pro"):
    def ask(db, prompt_text):
        ask.prompts.append(prompt_text)
        if isinstance(answer, Exception):
            raise answer
        raw = answer if isinstance(answer, str) else json.dumps(answer)
        return raw, "deepseek", model_id, {"prompt_tokens": 1200, "completion_tokens": 3400, "total_tokens": 4600}, \
            "deepseek-v4-pro"
    ask.prompts = []
    return ask


def _run(engine, name, ask):
    from services.phone import mapping_drafts as md
    Session = sessionmaker(bind=engine)
    with engine.begin() as c:
        rid = md.create_run(c, name, actor_name="Admin Person", actor_email="admin@x.test")
    s = Session()
    try:
        return md.execute_run(s, rid, ask)
    finally:
        s.close()


@needs_template
def test_a_valid_answer_is_stored_as_an_ai_draft_proposal_and_exports_as_a_draft_file_marked_not_reviewed(tmp_path):
    from services.phone import proposals
    from services.phone.mappings import loader
    call = _shipped("type", "Call")
    with fresh_engine() as engine:
        with engine.begin() as c:
            _registry_with_a_phone(c)
        out = _run(engine, "Call", _ask({"body": call["body"], "registry_requirements": call["review"][
            "registry_requirements"], "notes": "Unsure whether Status or Type is the call outcome."}))
        assert out["status"] == "drafted" and out["error"] is None and out["model"] == "deepseek-v4-pro"
        assert out["seconds"] is not None and out["prompt_tokens"] == 1200 and out["completion_tokens"] == 3400
        assert out["input_summary"]["kind"] == "type" and out["input_summary"]["fields"] > 0
        with engine.begin() as c:
            p = c.execute(text("SELECT origin, state, model, model_version, kind, name, content FROM "
                               "phone_mapping_proposals WHERE id = :i"), {"i": out["proposal_id"]}).one()
            assert (p.origin, p.state, p.model, p.kind, p.name) == ("ai_draft", "draft", "deepseek-v4-pro", "type",
                                                                     "Call")
            assert p.content["status"] == "draft" and p.content["review"]["reviewed_by"] is None
            cost = c.execute(text("SELECT provider, model_id, prompt_tokens, completion_tokens, description FROM "
                                  "cost_records")).fetchall()
            assert [tuple(x)[:4] for x in cost] == [("deepseek", "deepseek-v4-pro", 1200, 3400)]
            listed = proposals.list_proposals(c, origin="ai_draft")["proposals"][0]
            assert listed["model"] == "deepseek-v4-pro" and listed["state"] == "draft"
            f = json.loads(proposals.export(c, out["proposal_id"], actor_name="Admin Person")["text"])
        assert f["status"] == "draft" and f["origin"] == "ai_draft" and f["review"]["reviewed_by"] is None
        assert f["review"]["basis"].startswith("Drafted by deepseek-v4-pro · not reviewed.")
        assert "Unsure whether Status" in f["review"]["basis"]
        assert f["version"] == 2  # one above the shipped version 1
        path = tmp_path / "Call.json"
        path.write_text(json.dumps(f))
        assert loader._parse(str(path)) is None  # a draft is never applied
        # a model cannot be named the reviewer
        f.update(status="reviewed", review=dict(f["review"], reviewed_by="deepseek-v4-pro", reviewed_on="2026-11-04"))
        path.write_text(json.dumps(f))
        with pytest.raises(loader.LoadError):
            loader._parse(str(path))


@needs_template
def test_requirements_are_computed_from_the_named_fields_not_taken_from_the_model():
    """Measured on live 4 Nov: deepseek-v4-pro listed nested containers (Call.Parties, multiModelField Party) as
    requirements; they are not value fields, so the old code refused 2 good drafts of 3."""
    call = _shipped("type", "Call")
    with fresh_engine() as engine:
        with engine.begin() as c:
            _registry_with_a_phone(c)
        out = _run(engine, "Call", _ask({"body": call["body"], "registry_requirements": [
            ["Call", "Parties", "multiModelField", "Party"], ["Call", "Nope", "field", "String"]]}))
        assert out["status"] == "drafted", out["error"]
        with engine.begin() as c:
            reqs = c.execute(text("SELECT content->'review'->'registry_requirements' FROM phone_mapping_proposals "
                                  "WHERE id = :i"), {"i": out["proposal_id"]}).scalar()
        reqs = [tuple(r) for r in reqs]
        assert ("Call", "TimeStamp", "field", "TimeStamp") in reqs and ("Call", "Duration", "field", "TimeSpan") in reqs
        assert ("Call", "Direction", "field", "ModelDirections") in reqs and ("Call", "Source", "field", "String") in reqs
        assert not [r for r in reqs if r[1] in ("Parties", "Nope")]
        assert set(tuple(r) for r in call["review"]["registry_requirements"]) <= set(reqs)


@needs_template
def test_an_answer_naming_fields_the_registry_lacks_is_kept_as_a_rejected_proposal_with_the_reason():
    from services.phone import proposals
    call = _shipped("type", "Call")
    body = json.loads(json.dumps(call["body"]))
    body["event_time"]["field"] = "Account"          # a String, not a TimeStamp
    body["text_fields"] = ["NoSuchField"]
    body["participants"]["role_map"] = {"Somebody": "caller"}
    with fresh_engine() as engine:
        with engine.begin() as c:
            _registry_with_a_phone(c)
        out = _run(engine, "Call", _ask({"body": body, "registry_requirements": []}))
        assert out["status"] == "invalid" and out["proposal_id"]
        for words in ("event_time names Call.Account", "NoSuchField", "role_map key Somebody"):
            assert words in out["error"], (words, out["error"])
        with engine.begin() as c:
            assert c.execute(text("SELECT state FROM phone_mapping_proposals WHERE id = :i"),
                             {"i": out["proposal_id"]}).scalar() == "rejected"
            ev = c.execute(text("SELECT from_state, to_state, reason, actor_name FROM phone_mapping_proposal_events "
                                "WHERE proposal_id = :i"), {"i": out["proposal_id"]}).one()
            assert ev.to_state == "rejected" and "NoSuchField" in ev.reason and ev.actor_name.startswith("Loupe")
            with pytest.raises(proposals.ProposalRefused):
                proposals.export(c, out["proposal_id"], actor_name="Admin Person")


@needs_template
def test_a_non_json_answer_and_a_schema_breaking_answer_are_kept_never_dropped():
    with fresh_engine() as engine:
        with engine.begin() as c:
            _registry_with_a_phone(c)
        bad = _run(engine, "Call", _ask("I think the event time is TimeStamp."))
        assert bad["status"] == "invalid" and "not JSON" in bad["error"]
        wrong = _run(engine, "Call", _ask({"body": {"applies_to": "Call", "thread": {"strategy": "sometimes"}}}))
        assert wrong["status"] == "invalid" and "thread" in wrong["error"]
        other = _run(engine, "Call", _ask({"body": {"applies_to": "Chat"}}))
        assert other["status"] == "invalid" and "applies_to" in other["error"]
        with engine.begin() as c:
            rows = c.execute(text("SELECT state, content FROM phone_mapping_proposals ORDER BY created_at")).fetchall()
        assert [r.state for r in rows] == ["rejected"] * 3
        assert rows[0].content["unparsed_answer"].startswith("I think")


@needs_template
def test_no_answer_leaves_a_failed_run_with_the_reason_and_no_proposal():
    with fresh_engine() as engine:
        with engine.begin() as c:
            _registry_with_a_phone(c)
        out = _run(engine, "Call", _ask(RuntimeError("DeepSeek is not configured")))
        assert out["status"] == "failed" and "not configured" in out["error"] and out["proposal_id"] is None
        with engine.begin() as c:
            assert c.execute(text("SELECT count(*) FROM phone_mapping_proposals")).scalar() == 0


@needs_template
def test_attribution_rows_for_a_named_set_are_checked_against_its_values():
    row = {"row_id": "attr-call-decoding", "type": "Call", "field": "TimeStamp",
           "predicates": [{"field": "UserMapping", "op": "eq", "value": "Decoding"}], "context": [],
           "outputs": {"flag": "decoded_by_tool", "group": "B"}, "basis": "field_name",
           "reasoning": "The value names the decoding step.", "would_change": "A vendor document says otherwise."}
    with fresh_engine() as engine:
        with engine.begin() as c:
            from services.phone import registry
            registry.apply_seed(c)
        good = _run(engine, "DecodingSourceOptions", _ask({"body": {"rows": [row]}, "registry_requirements": []}))
        assert good["status"] == "drafted", good["error"]
        off = dict(row, row_id="attr-x", predicates=[{"field": "UserMapping", "op": "eq", "value": "NotAValue"}],
                   outputs={"flag": "x"})
        bad = _run(engine, "DecodingSourceOptions", _ask({"body": {"rows": [off]}, "registry_requirements": []}))
        assert bad["status"] == "invalid" and "NotAValue" in bad["error"] and "outputs" in bad["error"]
        with engine.begin() as c:
            k = c.execute(text("SELECT kind, name FROM phone_mapping_proposals WHERE id = :i"),
                          {"i": good["proposal_id"]}).one()
        assert tuple(k) == ("attribution", "DecodingSourceOptions")


@needs_template
def test_draft_endpoints_are_admin_only_and_a_second_draft_of_one_name_waits():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from postgres.models.enums import GlobalRole
    from postgres.models.user import User
    from postgres.session import get_db
    from routers.phones import router
    from routers.users import get_current_db_user
    from services.phone import mapping_drafts as md

    with fresh_engine() as engine:
        with engine.begin() as c:
            from services.phone import registry
            registry.apply_seed(c)
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
        started = []
        with TestClient(app) as client, patch.object(md, "run_in_background",
                                                     side_effect=lambda f, rid, ask=None: started.append(rid)):
            assert client.post("/api/phones/registry/mapping-drafts", json={"type_name": "Call"}).status_code == 403
            assert client.get("/api/phones/registry/mapping-drafts").status_code == 403
            assert client.get("/api/phones/registry/mapping-drafts/%s" % uuid.uuid4()).status_code == 403
            role["r"] = GlobalRole.admin
            r = client.post("/api/phones/registry/mapping-drafts", json={"type_name": "Call"})
            assert r.status_code == 202 and r.json()["status"] == "queued" and len(started) == 1
            assert client.post("/api/phones/registry/mapping-drafts", json={"type_name": "Call"}).status_code == 409
            assert client.post("/api/phones/registry/mapping-drafts",
                               json={"type_name": "NoSuchType"}).status_code == 404
            listed = client.get("/api/phones/registry/mapping-drafts").json()
            assert listed["total"] == 1 and listed["runs"][0]["name"] == "Call"
            assert any(t["name"] == "Call" for t in listed["draftable"]["types"])
            assert any(s["name"] == "DecodingSourceOptions" for s in listed["draftable"]["named_sets"])
            assert client.get("/api/phones/registry/mapping-drafts/%s" % r.json()["id"]).json()["name"] == "Call"
