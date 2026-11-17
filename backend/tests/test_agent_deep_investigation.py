"""Deep investigation mode (lx-deepinvest C, D, F): plan, checklist enforced before writing, notebook, no case names."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from services.agent import deep_investigation as D
from services.agent.graph import AgentGraphRunner

CASE = "00000000-0000-0000-0000-000000000002"
LABELS = ["Phone 1", "Phone 2", "Phone 3"]


def plan(domain="phones"):
    return D.build_plan(domain, question="q", counts={"phones": 3}, phone_labels=LABELS)


def test_wants_deep_in_so_many_words():
    assert D.wants_deep("Give me a detailed report about the phones in this case")
    assert D.wants_deep("run a deep investigation of the money")
    assert not D.wants_deep("who texted whom on Friday")


def test_domain_follows_question():
    assert D.domain_for("detailed report on the money in this case") == "money"
    assert D.domain_for("a detailed report on the phones") == "phones"
    assert D.domain_for("a detailed report on the documents") == "documents"
    assert D.domain_for("report", {"ledger": 4}) == "money"


def test_plan_has_per_phone_units_and_every_domain_builds():
    p = plan()
    assert D.item_by_id(p, "conversations")["target"] == LABELS
    assert len(D.open_items(p)) == len(p["items"])
    for domain in D.DOMAINS:
        assert D.build_plan(domain, question="q")["items"]


def note(p, item, fact):
    D.notebook_add(p, [{"item": item, "fact": fact, "cite": "rec://x"}])


def test_done_needs_a_note_for_every_unit_and_not_done_needs_a_reason():
    p = plan()
    got = D.mark(p, [{"item": "conversations", "status": "done", "units": LABELS}])
    assert got["applied"] == [] and "Phone 1" in got["refused"][0]["why"]  # naming the units is not evidence
    note(p, "conversations", "Phone 1 read to the end: 200 messages")
    note(p, "conversations", "Phone 2 read to the end")
    got = D.mark(p, [{"item": "conversations", "status": "done", "units": ["phone 1", "Phone 2", "Phone 3"]}])
    assert got["applied"] == [] and "Phone 3" in got["refused"][0]["why"] and "Phone 1" not in got["refused"][0]["why"]
    assert not D.is_closed(D.item_by_id(p, "conversations"))
    note(p, "conversations", "Phone 3 holds nothing in the window")
    got = D.mark(p, [{"item": "conversations", "status": "done", "units": ["Phone 3"]}])
    assert got["applied"] == ["conversations"] and D.is_closed(D.item_by_id(p, "conversations"))
    assert D.mark(p, [{"item": "media", "status": "not_done"}])["refused"]
    assert D.mark(p, [{"item": "media", "status": "not_done", "reason": "no media in the case"}])["applied"] == ["media"]
    assert D.mark(p, [{"item": "nope", "status": "done"}])["refused"]


def test_an_item_without_units_is_done_only_with_a_note():
    p = plan()
    assert D.mark(p, [{"item": "network", "status": "done"}])["refused"]
    D.notebook_add(p, [{"item": "network", "fact": "no alias found", "cite": "searched: identity suggestions"}])
    assert D.mark(p, [{"item": "network", "status": "done"}])["applied"] == ["network"]


def test_notebook_needs_a_citation_and_goes_to_the_writer_once():
    p = plan()
    got = D.notebook_add(p, [{"fact": "a", "cite": ""}, {"item": "windows", "fact": "b", "cite": "rec://1"}])
    assert got["added"] == 1 and len(got["refused"]) == 1
    assert "rec://1" in D.notebook_block(p)
    assert D.notebook_read(p, "windows")["total"] == 1


def test_gate_sends_back_while_open_and_is_bounded():
    p = plan()
    sent = [D.gate_message(p) for _ in range(D.MAX_GATES + 2)]
    assert all(sent[:D.MAX_GATES]) and sent[D.MAX_GATES] is None
    q = plan()
    for i in q["items"]:
        i["status"], i["reason"] = "not_done", "x"
    assert D.gate_message(q) is None


def test_not_done_is_stated_in_the_writer_rules():
    p = plan()
    D.mark(p, [{"item": "media", "status": "not_done", "reason": "no media in the case"}])
    assert "no media in the case" in D.final_rules(p)
    assert "Limits and next steps" in D.final_rules(p)


def test_no_case_names_in_prompts():
    spec = importlib.util.spec_from_file_location(
        "demo_case", Path(__file__).resolve().parents[2] / "evidence-engine/tests/phone/demo_case.py")
    sys.path.insert(0, str(Path(spec.origin).parent))
    try:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001
        pytest.skip("demo case module not importable: %s" % exc)
    finally:
        sys.path.pop(0)
    text = (Path(D.__file__).read_text() + D.render_block(plan()) + D.final_rules(plan())).lower()
    hits = [n for n in list(mod.INVENTED_NAMES) + list(mod.INVENTED_PLACES) if n.lower() in text]
    assert hits == []


# ---- the durable loop enforces the checklist before it writes --------------------------------------------------

class Model:
    def __init__(self, script):
        self.script = list(script)
        self.final_messages = []

    def bind_tools(self, tools):
        model = self

        class Bound:
            def invoke(self, messages):
                model.seen = messages
                nxt = model.script.pop(0) if model.script else None
                return AIMessage(content="", tool_calls=nxt) if nxt else AIMessage(content="Draft report.")
        return Bound()

    def invoke(self, messages):
        self.final_messages = messages
        return AIMessage(content="The report.")


def run_stream(script, deep=True):
    from services.agent import durable_execution
    from services.agent.tools import make_agent_tools  # noqa: F401
    r = object.__new__(AgentGraphRunner)
    r.base_model = Model(script)
    r.model_id = "deepseek-v4-pro"
    events = list(durable_execution.stream(r, case_id=CASE, messages=[], checkpoint_callback=lambda s: None,
                                           deep_plan=plan() if deep else None, final_answer_rules="RULES"))
    return r, events


def test_loop_returns_to_work_until_checklist_is_closed_then_writes():
    marks = [{"id": "c2", "name": "deep_notebook_add", "args": {"notes": [
        {"item": i["id"], "fact": "%s: %s" % (i["id"], " ".join(LABELS)), "cite": "rec://%s" % i["id"]} for i in plan()["items"]]}},
        {"id": "c1", "name": "deep_mark", "args": {"updates": [
            {"item": i["id"], "status": "done", "units": LABELS} for i in plan()["items"]]}}]
    # First the model writes at once (no tool call): the gate sends it back; then it closes every item.
    r, events = run_stream([None, marks])
    final = [e for e in events if e["type"] == "final"][0]["result"]
    prog = [e for e in events if e["type"] == "deep_progress"]
    assert prog and prog[-1]["progress"]["open"] == 0 and prog[-1]["progress"]["notes"] == len(plan()["items"])
    assert final["answer"]
    system = " ".join(str(getattr(m, "content", "")) for m in r.base_model.final_messages)
    assert "rec://windows" in system  # the notebook reaches the writer
    assert "Completeness check" in json.dumps([str(m.content) for m in r.base_model.seen])


def test_loop_writes_with_open_items_stated_when_gate_is_spent():
    r, events = run_stream([None] * (D.MAX_GATES + 1))
    system = " ".join(str(getattr(m, "content", "")) for m in r.base_model.final_messages)
    assert "Limits and next steps" in system or "not done" in system.lower()
    assert [e for e in events if e["type"] == "final"]


def test_normal_run_is_not_gated():
    r, events = run_stream([None], deep=False)
    assert not [e for e in events if e["type"] == "deep_progress"]


def test_method_names_only_tools_this_build_registers():
    import re
    from services.agent import workflows
    have = workflows.registered_tool_names()
    named = {w for text in D.METHOD.values() for w in re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", text)}
    named -= {"has_more", "next_offset", "phone_messages_x"}
    assert named - have == set(), sorted(named - have)


def test_report_artifact_follows_the_answers_own_headings():
    answer = "# Report for the client\n\nOpening.\n\n## Summary\nx\n\n## Inventory\ny\n"
    art = D.report_artifact(answer, plan())
    assert art["type"] == "report" and art["title"] == "Report for the client"
    heads = [s["heading"] for s in art["data"]["sections"]]
    assert heads == ["Report for the client", "Summary", "Inventory"], heads
    assert D.report_artifact("", plan()) is None


def test_deep_run_adds_the_report_as_an_artifact():
    r, events = run_stream([None] * (D.MAX_GATES + 1))
    final = [e for e in events if e["type"] == "final"][0]["result"]
    assert any((a.get("metadata") or {}).get("origin") == "deep_investigation" for a in final["artifacts"])


def test_every_document_is_a_unit_of_the_documents_item_up_to_a_cap():
    docs = ["tow-invoice.pdf", "police-report.pdf"]
    p = D.build_plan("phones", question="q", phone_labels=LABELS, document_labels=docs)
    assert D.item_by_id(p, "documents")["target"] == docs
    D.notebook_add(p, [{"item": "documents", "fact": "tow-invoice.pdf gives the clearing time", "cite": "doc://1"}])
    got = D.mark(p, [{"item": "documents", "status": "done", "units": docs}])
    assert got["applied"] == [] and "police-report.pdf" in got["refused"][0]["why"]
    big = D.build_plan("phones", question="q", phone_labels=LABELS,
                       document_labels=["d%d.pdf" % i for i in range(D.MAX_DOC_UNITS + 1)])
    assert D.item_by_id(big, "documents")["target"] is None
    assert D.build_plan("documents", question="q", document_labels=docs)["items"][0]["target"] == docs


def test_method_tells_the_run_not_to_convert_times_and_to_check_names_against_history():
    block = D.render_block(plan())
    assert "never convert a time" in block and "local_day" in block
    assert "history" in block


def test_one_record_cannot_back_a_run_of_different_facts():
    p = plan()
    notes = [{"item": "windows", "fact": "fact %d" % i, "cite": "rec://same"} for i in range(D.MAX_NOTES_PER_RECORD + 2)]
    got = D.notebook_add(p, notes)
    assert got["added"] == D.MAX_NOTES_PER_RECORD and len(got["refused"]) == 2
    assert "cite the link of the record" in got["refused"][0]["why"]
    assert D.notebook_add(p, [{"fact": "doc fact", "cite": "doc://x/1"}] * 5)["added"] == 5


def test_method_points_to_bulk_reading_for_phones_and_documents():
    from services.agent import deep_investigation as D
    assert "read_scope_with_model" in D.METHOD["phones"] and "read_scope_with_model" in D.METHOD["documents"]


def test_deep_run_gets_longer_work_time_and_the_review_its_own_time():
    from services.agent import durable_execution as X
    normal_work, normal_review = X.time_limits(False)
    deep_work, deep_review = X.time_limits(True)
    assert deep_work > normal_work >= 3600
    assert normal_review - normal_work >= 1800 and deep_review - deep_work >= 1800


def test_deep_run_rereads_and_notes_are_free_without_a_cap(monkeypatch):
    from services.agent import fit, graph as g
    monkeypatch.setattr(fit, "on", lambda key: True)
    from services.agent.tools import AgentToolContext
    ctx = AgentToolContext(case_id="00000000-0000-0000-0000-000000000001")
    ctx.deep_plan = plan()
    for _ in range(g.FREE_CALL_CAP + g.REREAD_CAP + 20):
        assert g._free_call_refusal("read_tool_result_page", ctx) is None
    plain = AgentToolContext(case_id="00000000-0000-0000-0000-000000000001")
    refused = [g._free_call_refusal("read_tool_result_page", plain) for _ in range(40)]
    assert any(r is not None for r in refused)
