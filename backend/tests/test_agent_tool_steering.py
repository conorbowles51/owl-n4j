"""Tool steering (Neil 12 Nov 2026, approved mock-up): tool groups in plain words, per-run switches taken from the
next step, notes the agent reads before its next step, switches in the trail with their step, switched-off groups
under "Not examined", and "step N of up to <budget>". Synthetic tools and a scripted model; no model or case network."""
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from services.agent import tool_groups
from services.agent.graph import AgentGraphRunner, AgentToolContext, make_agent_tools

CASE = "00000000-0000-0000-0000-000000000001"


def test_every_agent_tool_is_in_exactly_one_group():
    names = [tool.name for tool in make_agent_tools(AgentToolContext(case_id=CASE))]
    unmapped = sorted(n for n in names if tool_groups.group_of(n) is None)
    assert unmapped == [], f"tools with no group (add each to services.agent.tool_groups.GROUPS): {unmapped}"
    listed = [t for g in tool_groups.GROUPS for t in g["tools"]]
    assert len(listed) == len(set(listed)), "a tool is listed in two groups"
    stale = sorted(set(listed) - set(names))
    assert stale == [], f"groups name tools the agent no longer has: {stale}"


def test_groups_neil_named_are_there_and_always_on_cannot_be_switched():
    names = {g["name"] for g in tool_groups.GROUPS}
    assert {"Money and ledger", "Phones", "Documents", "People and identities", "Map and places",
            "Graph queries"} <= names
    with pytest.raises(ValueError):
        tool_groups.new_entry(kind="switch", user_id="u", group=tool_groups.ALWAYS_ON, on=False)
    with pytest.raises(ValueError):
        tool_groups.new_entry(kind="note", user_id="u", note="   ")
    with pytest.raises(ValueError):
        tool_groups.new_entry(kind="note", user_id="u", note="x" * (tool_groups.NOTE_MAX_CHARS + 1))


def test_chosen_from_question_marks_groups_without_limiting_them():
    chosen = tool_groups.chosen_from_question("What payments did Lena Marsh receive, and from whom?")
    assert "money" in chosen and "people" in chosen
    assert "places" not in chosen
    assert "places" in tool_groups.chosen_from_question("Where was the glovebox phone on the nights of May 2024?")


class Model:
    """Scripted: each step's tool calls in turn; records the tool names offered to every step."""

    def __init__(self, batches):
        self.batches = list(batches)
        self.offered = []
        self.requests = []

    def bind_tools(self, tools):
        model = self
        names = [t.name for t in tools]

        class Bound:
            def invoke(self, messages):
                model.offered.append(names)
                model.requests.append(list(messages))
                if model.batches:
                    return AIMessage(content="", tool_calls=model.batches.pop(0))
                return AIMessage(content="Lena Marsh received five transfers from Travis Kell.")
        return Bound()

    def invoke(self, messages):
        return AIMessage(content="Lena Marsh received five transfers from Travis Kell.")


def make_tool(name, seen):
    class Tool:
        def invoke(self, args):
            seen.append(name)
            return {"summary": f"{name} read", "data": {"ok": True}, "result_id": f"r-{name}-{len(seen)}"}
    tool = Tool()
    tool.name = name
    return tool


@pytest.fixture
def tools(monkeypatch):
    seen = []
    names = ["get_financial_transactions", "phone_messages", "search_documents", "read_tool_result_page"]
    monkeypatch.setattr("services.agent.graph.make_agent_tools", lambda context: [make_tool(n, seen) for n in names])
    monkeypatch.setattr("services.agent.graph.tools_for_binding", lambda model, tools: tools)
    return seen


def runner(batches):
    r = object.__new__(AgentGraphRunner)
    r.base_model = Model(batches)
    r.model_id = "deepseek-v4-pro"
    return r


def call(n, name):
    return {"id": f"c{n}", "name": name, "args": {}}


def run(r, requests_by_read, progress=None):
    reads = iter(requests_by_read)

    def steering():
        return next(reads, requests_by_read[-1] if requests_by_read else [])
    return list(r.stream(case_id=CASE, messages=[HumanMessage(content="What payments did Lena Marsh receive?")],
                         checkpoint_callback=lambda payload: None, steering=steering,
                         on_progress=(progress.append if progress is not None else None)))


def test_a_switched_off_group_is_not_offered_from_the_next_step_and_its_calls_are_refused(tools):
    off_phones = tool_groups.new_entry(kind="switch", user_id="u", group="phones", on=False)
    # Step 1 asks for the ledger; the person switches phones off while it runs; the model (which planned earlier)
    # still asks for phone messages at step 2: refused. Step 3 is offered no phone tool.
    r = runner([[call(1, "get_financial_transactions")], [call(2, "phone_messages")],
                [call(3, "search_documents")]])
    events = run(r, [[], [off_phones]])
    offered = r.base_model.offered
    assert "phone_messages" in offered[0]
    assert all("phone_messages" not in names for names in offered[1:])
    assert "read_tool_result_page" in offered[-1]  # always on stays
    assert "phone_messages" not in tools  # the call was not run
    final = events[-1]["result"]
    refused = [t for t in final["tool_trace"] if t["name"] == "phone_messages"][0]
    assert refused["status"] == "error" and "switched off Phones after step 1" in refused["error"]
    steering = [e for e in events if e["type"] == "steering"]
    assert len(steering) == 1
    entry = steering[0]["entries"][0]
    assert (entry["title"], entry["step"], entry["applies_from"]) == ("You switched off Phones", 1, 2)
    assert steering[0]["off"] == ["phones"]
    # The model is told, in the conversation, that the group is off.
    told = [m.content for m in r.base_model.requests[1] if isinstance(m, HumanMessage)]
    assert any("Phones: switched off by the investigator after step 1" in text for text in told)
    # The answer names it under Not examined, with the step (rule 1).
    assert "**Not examined**" in final["answer"]
    assert "Phones: switched off by you at step 1, so not examined from step 2 on." in final["answer"]
    assert final["steering"][0]["group"] == "phones"


def test_switching_back_on_offers_the_tools_again_and_the_answer_states_the_span(tools):
    off = tool_groups.new_entry(kind="switch", user_id="u", group="phones", on=False)
    on = tool_groups.new_entry(kind="switch", user_id="u", group="phones", on=True)
    r = runner([[call(1, "get_financial_transactions")], [call(2, "search_documents")],
                [call(3, "phone_messages")]])
    events = run(r, [[], [off], [off, on]])
    offered = r.base_model.offered
    assert "phone_messages" not in offered[1] and "phone_messages" in offered[2]
    assert tools == ["get_financial_transactions", "search_documents", "phone_messages"]
    answer = events[-1]["result"]["answer"]
    assert "Phones: switched off by you at step 1 and on again at step 2, so not examined in steps 2 to 2." in answer


def test_a_note_is_read_before_the_next_step_in_the_persons_words(tools):
    note = tool_groups.new_entry(kind="note", user_id="u", note="Check the May 2024 statement first")
    r = runner([[call(1, "get_financial_transactions")], [call(2, "search_documents")]])
    events = run(r, [[], [note]])
    second = r.base_model.requests[1]
    assert isinstance(second[-1], HumanMessage)
    assert second[-1].content.endswith("Check the May 2024 statement first")
    assert "after step 1" in second[-1].content
    trail = [e for e in events if e["type"] == "steering"][0]["entries"][0]
    assert trail["title"] == "You sent a note to the agent" and trail["note"] == "Check the May 2024 statement first"
    # A note is not a switch: nothing is listed as not examined.
    assert "Not examined" not in events[-1]["result"]["answer"]


def test_an_entry_is_taken_once_and_survives_a_resume(tools):
    off = tool_groups.new_entry(kind="switch", user_id="u", group="phones", on=False)
    saved = {}

    def checkpoint(payload):
        saved.clear()
        saved.update(json.loads(json.dumps(payload)))
    r = runner([[call(1, "get_financial_transactions")], [call(2, "search_documents")]])
    events = list(r.stream(case_id=CASE, messages=[HumanMessage(content="q")], checkpoint_callback=checkpoint,
                           steering=lambda: [off]))
    assert len([e for e in events if e["type"] == "steering"]) == 1
    assert saved["steering_applied"][0]["id"] == off["id"]


def test_progress_carries_the_run_budget(tools):
    progress = []
    r = runner([[call(1, "get_financial_transactions")]])
    run(r, [[]], progress=progress)
    assert progress and all(p.get("budget") == 28 * 8 for p in progress)


def test_existing_not_examined_heading_gets_the_line_under_it():
    applied = [{"kind": "switch", "group": "places", "on": False, "step": 4, "applies_from": 5}]
    answer = "Findings.\n\n**Not examined**\n- The May statement is missing.\n"
    out = tool_groups.with_not_examined(answer, applied, last_step=9)
    assert out.count("Not examined") == 1
    assert "**Not examined**\n- Map and places: switched off by you at step 4" in out
    assert tool_groups.with_not_examined("Findings.", [], last_step=3) == "Findings."


def test_steering_view_marks_pending_until_taken():
    from services.agent.storage import steering_view

    off = tool_groups.new_entry(kind="switch", user_id="u", group="graph", on=False)

    class Run:
        extra_metadata = {"steering": [off], "tool_groups_chosen": ["money"]}
    view = steering_view(Run())
    assert view["pending"][0]["title"] == "You switched off Graph queries" and view["off"] == ["graph"]
    Run.extra_metadata = {**Run.extra_metadata,
                          "steering_applied": [tool_groups.trail_entry({**off, "step": 3, "applies_from": 4})]}
    view = steering_view(Run())
    assert view["pending"] == [] and view["applied"][0]["step"] == 3 and view["chosen"] == ["money"]


def test_run_record_lists_switched_off_groups_and_notes():
    from services.agent.run_record_export import not_examined_rows, steering_rows
    record = {"calls": [], "items": [], "unrun_tool_calls": [], "case_layer": "all", "tool_calls_used": 9,
              "tool_budget": 28, "run_id": "r", "steering": [
                  {"kind": "switch", "group": "phones", "on": False, "step": 5, "applies_from": 6, "at": "t"},
                  {"kind": "note", "note": "Check the May 2024 statement first", "step": 6, "applies_from": 7}]}
    rows = steering_rows(record)
    assert rows[0]["what"] == "Phones switched off" and rows[0]["after step"] == 5
    assert rows[1]["what"] == "Note to the agent: Check the May 2024 statement first"
    from services.agent import run_record_export
    original = run_record_export._header_rows
    run_record_export._header_rows = lambda record: []
    try:
        scope = not_examined_rows(record, material={}, phone_types=[])["scope"]
    finally:
        run_record_export._header_rows = original
    assert scope == [{"#": "", "what": "Phones (switched off by the investigator)",
                      "decision": "Switched off at step 5; not examined from step 6 on."}]
