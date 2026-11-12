"""Durable execution acceptance with synthetic tools; no model or case network access."""
import copy
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from services.agent.graph import AgentGraphRunner

CASE = "00000000-0000-0000-0000-000000000001"


class Model:
    def __init__(self, batches=()):
        self.batches = list(batches)
        self.final_messages = []

    def bind_tools(self, tools):
        model = self

        class Bound:
            def invoke(self, messages):
                if model.batches:
                    return AIMessage(content="", tool_calls=model.batches.pop(0))
                return AIMessage(content="The requested review is ready.")
        return Bound()

    def invoke(self, messages):
        self.final_messages = messages
        return AIMessage(content="The requested review is ready.")


def runner(batches=()):
    r = object.__new__(AgentGraphRunner)
    r.base_model = Model(batches)
    r.model_id = "deepseek-v4-pro"
    return r


def call(number, name="read_test"):
    return dict(id=f"call-{number}", name=name, args={"number": number})


@pytest.fixture
def tool(monkeypatch):
    seen = []

    class Tool:
        name = "read_test"

        def invoke(self, args):
            seen.append(args["number"])
            return {"summary": "Read a synthetic record", "data": {"number": args["number"]},
                    "result_id": f"result-{args['number']}"}

    monkeypatch.setattr("services.agent.graph.make_agent_tools", lambda context: [Tool()])
    monkeypatch.setattr("services.agent.graph.tools_for_binding", lambda model, tools: tools)
    return seen


def test_completed_tool_survives_process_loss_inside_batch(tool):
    saved = {}

    class ProcessKilled(BaseException):
        pass

    def checkpoint(payload):
        saved.clear()
        saved.update(json.loads(json.dumps(payload)))
        if (payload.get("inflight") or {}).get("id") == "call-2":
            raise ProcessKilled()

    with pytest.raises(ProcessKilled):
        list(runner([[call(1), call(2)]]).stream(case_id=CASE,
             messages=[HumanMessage(content="Read both records")], checkpoint_callback=checkpoint))
    assert tool == [1]
    events = list(runner().stream(case_id=CASE, messages=[], resume_checkpoint=saved,
                                 checkpoint_callback=lambda p: None))
    assert tool == [1, 2]  # the first call was not rerun
    assert len(events[-1]["result"]["tool_trace"]) == 2


def test_windows_continue_automatically_and_keep_all_results(tool):
    saved = []
    events = list(runner([[call(1)], [call(2)], [call(3)]]).stream(case_id=CASE,
        messages=[HumanMessage(content="Read all three")], checkpoint_callback=lambda p: saved.append(copy.deepcopy(p)),
        max_tool_calls=1, automatic_windows=3))
    assert tool == [1, 2, 3]
    assert events[-1]["result"]["clarification"] is None
    assert set(saved[-1]["model_views"]) == {"result-1", "result-2", "result-3"}


def test_budget_mid_batch_supplies_every_tool_response_to_finalizer(tool):
    r = runner([[call(1), call(2)]])
    events = list(r.stream(case_id=CASE, messages=[HumanMessage(content="Read both")],
        checkpoint_callback=lambda p: None, max_tool_calls=1, automatic_windows=1))
    assert tool == [1]
    requested = {c["id"] for m in r.base_model.final_messages if isinstance(m, AIMessage) for c in m.tool_calls}
    answered = {m.tool_call_id for m in r.base_model.final_messages if isinstance(m, ToolMessage)}
    assert requested <= answered
    assert events[-1]["result"]["clarification"]["context"]["reason"] == "tool_budget_exhausted"


def test_malformed_model_tool_json_recovers_without_finalizing_or_executing_it(tool):
    r = runner()
    r.base_model.bind_tools = lambda tools: r.base_model
    responses = iter([AIMessage(content='', invalid_tool_calls=[{'id': 'bad', 'name': 'read_test', 'args': '{', 'error': 'Invalid JSON'}]),
                      AIMessage(content='', tool_calls=[call(1)]), AIMessage(content='Source read.')])
    requests = []
    def invoke(messages):
        requests.append(messages)
        return next(responses, AIMessage(content='Completed the synthetic review.'))
    r.base_model.invoke = invoke
    events = list(r.stream(case_id=CASE, messages=[HumanMessage(content='Read the source')], checkpoint_callback=lambda p: None))
    assert tool == [1]
    assert events[-1]['result']['clarification'] is None
    assert any('not executed' in str(message.content) for message in requests[1])
    assert not any(message.invalid_tool_calls for message in requests[1] if isinstance(message, AIMessage))


def test_three_malformed_replies_stop_with_saved_work_instead_of_spinning(tool):
    r = runner()
    r.base_model.bind_tools = lambda tools: r.base_model
    calls = []
    def invoke(messages):
        calls.append(messages)
        if len(calls) <= 3:
            return AIMessage(content='', invalid_tool_calls=[{'id': f'bad{len(calls)}', 'name': 'read_test', 'args': '{', 'error': 'Invalid JSON'}])
        return AIMessage(content='Work is saved but could not continue.')
    r.base_model.invoke = invoke
    events = list(r.stream(case_id=CASE, messages=[HumanMessage(content='Read the source')], checkpoint_callback=lambda p: None))
    assert not tool
    assert events[-1]['result']['clarification']['context']['reason'] == 'no_progress'
    assert len(calls) == 4


def test_ambiguous_case_action_is_not_replayed(tool):
    saved = dict(version=1, case_id=CASE, all_cases=False, allowed_entity_keys=None, phase="tools",
        messages=[{"type": "ai", "data": AIMessage(content="", tool_calls=[call(1, "propose_finding")]).model_dump()}],
        inflight={"id": "call-1", "name": "propose_finding"})
    with pytest.raises(ValueError, match="has not been executed again"):
        list(runner().stream(case_id=CASE, messages=[], resume_checkpoint=saved, checkpoint_callback=lambda p: None))
    assert tool == []


def test_permission_rechecked_before_tools_or_checkpoint_reuse(tool):
    count = 0

    def check(cases):
        nonlocal count
        count += 1
        if count >= 3:
            raise PermissionError("revoked")

    with pytest.raises(PermissionError):
        list(runner([[call(1)]]).stream(case_id=CASE, messages=[HumanMessage(content="Read")],
            checkpoint_callback=lambda p: None, access_check=check))
    assert tool == []


def test_saved_scope_cannot_be_widened_or_narrowed_silently(tool):
    with pytest.raises(ValueError, match="different source scope"):
        list(runner().stream(case_id=CASE, messages=[], resume_checkpoint={"version": 1, "case_id": CASE,
            "all_cases": True, "allowed_entity_keys": None}, checkpoint_callback=lambda p: None, all_cases=False))


def test_repeated_identical_reads_stop_with_useful_partial_result(tool):
    batches = [[dict(call(n), args={"number": 1})] for n in range(1, 7)]
    events = list(runner(batches).stream(case_id=CASE, messages=[HumanMessage(content="Find the missing record")],
        checkpoint_callback=lambda p: None))
    assert tool == [1, 1, 1]
    assert events[-1]["result"]["clarification"]["context"]["reason"] == "no_progress"
    assert events[-1]["result"]["answer"]


def test_hidden_tool_is_not_dispatchable_even_when_model_names_it(tool):
    events = list(runner([[call(1)]]).stream(case_id=CASE, messages=[HumanMessage(content="Read")],
        checkpoint_callback=lambda p: None, hidden_tools={"read_test"}))
    assert tool == []
    assert events[-1]["result"]["tool_trace"][0]["status"] == "error"


def test_paging_errors_with_different_offsets_do_not_spend_the_whole_budget(monkeypatch):
    class Tool:
        name = 'read_tool_result_page'

        def invoke(self, args):
            return {'status': 'error', 'error': f"Invalid page offset {args['offset']}", 'summary': 'Use the saved paging path.'}

    monkeypatch.setattr('services.agent.graph.make_agent_tools', lambda context: [Tool()])
    monkeypatch.setattr('services.agent.graph.tools_for_binding', lambda model, tools: tools)
    batches = [[dict(id=f'bad-{n}', name='read_tool_result_page', args={'offset': n, 'result_id': 'saved'})] for n in range(8)]
    events = list(runner(batches).stream(case_id=CASE, messages=[HumanMessage(content='Read the document')], checkpoint_callback=lambda p: None))
    assert len(events[-1]['result']['tool_trace']) == 3
    assert events[-1]['result']['clarification']['context']['reason'] == 'no_progress'


def test_saving_a_new_revision_resets_earlier_read_failures(monkeypatch):
    from services.agent.deliverables import new_artifact
    class Read:
        name = 'read_tool_result_page'
        def invoke(self, args):
            return {'status': 'error', 'error': f"Invalid page offset {args['offset']}"}
    class Save:
        name = 'create_artifact'
        def invoke(self, args):
            return {'artifact': new_artifact('table', 'Saved progress', {'rows': [{'record': 'Synthetic'}]})}
    monkeypatch.setattr('services.agent.graph.make_agent_tools', lambda context: [Read(), Save()])
    monkeypatch.setattr('services.agent.graph.tools_for_binding', lambda model, tools: tools)
    bad = lambda n: [dict(id=f'bad-{n}', name='read_tool_result_page', args={'offset': n, 'result_id': 'saved'})]
    batches = [bad(0), bad(1), [dict(id='saved', name='create_artifact', args={})], bad(2)]
    result = list(runner(batches).stream(case_id=CASE, messages=[HumanMessage(content='Review saved work.')],
        checkpoint_callback=lambda p: None))[-1]['result']
    assert len(result['tool_trace']) == 4
    assert len(result['artifacts']) == 1
    assert result['clarification'] is None


def test_durable_finalizer_preserves_upstream_source_recovery(monkeypatch):
    from services.agent import graph
    identity = '11111111-2222-3333-4444-555555555555'
    captured = {}
    class Read:
        name = 'read_test'
        def __init__(self, context): self.context = context
        def invoke(self, args):
            result = self.context.result('read_test', {'items': [{'key': identity, 'cite': f'txn://{identity}',
                'amount_minor': '123400', 'currency': 'MXN', 'currency_exponent': 2, 'description': 'Synthetic payment'}]},
                summary='Read one synthetic payment.')
            captured['handle'] = result['result_id']
            return result
    monkeypatch.setenv('LOUPE_AGENT_FIT', 'W')
    monkeypatch.setattr(graph, 'make_agent_tools', lambda context: [Read(context)])
    monkeypatch.setattr(graph, 'tools_for_binding', lambda model, tools: tools)
    monkeypatch.setattr(graph, 'call_facts', lambda *args: {'items': [
        {'kind': 'payment', 'ref': identity, 'alts': [f'txn://{identity}'], 'label': 'Synthetic payment'}]})
    r = runner([[call(1), call(2)]])
    requests = []
    def final(messages):
        requests.append(messages)
        return AIMessage(content=f"Synthetic payment: 1,234.00 MXN [source](doc://{captured['handle']}).")
    r.base_model.invoke = final
    result = list(r.stream(case_id=CASE, messages=[HumanMessage(content='Read both records')],
        checkpoint_callback=lambda p: None, max_tool_calls=1, automatic_windows=1))[-1]['result']
    assert f'(txn://{identity})' in result['answer'] and 'res_' not in result['answer']
    assert 'Records found so far' in requests[-1][-1].content


def test_notes_survive_resume_without_consuming_investigative_budget(monkeypatch):
    from services.agent import graph
    from services.agent.tools import make_agent_tools
    contexts, offered = [], []
    def tools(context):
        contexts.append(context)
        notes = next(t for t in make_agent_tools(context) if t.name == 'record_working_notes')
        class Read:
            name = 'read_test'
            def invoke(self, args):
                return context.result('read_test', {'number': args['number']}, summary='Read synthetic record.')
        return [notes, Read()]
    monkeypatch.setenv('LOUPE_AGENT_FIT', 'B')
    monkeypatch.setattr(graph, 'make_agent_tools', tools)
    monkeypatch.setattr(graph, 'tools_for_binding', lambda model, tools: offered.extend(t.name for t in tools) or tools)
    note = {'id': 'note-1', 'name': 'record_working_notes', 'args': {'facts': [{'fact': 'Synthetic observation.'}]}}
    saved = {}
    class LostWorker(BaseException): pass
    def checkpoint(payload):
        saved.update(copy.deepcopy(payload))
        if (payload.get('inflight') or {}).get('id') == 'call-1': raise LostWorker()
    with pytest.raises(LostWorker):
        list(runner([[note, call(1)]]).stream(case_id=CASE, messages=[HumanMessage(content='Note the fact, then read')],
            checkpoint_callback=checkpoint, max_tool_calls=1, automatic_windows=1))
    result = list(runner().stream(case_id=CASE, messages=[], resume_checkpoint=saved,
        checkpoint_callback=lambda p: None, max_tool_calls=1, automatic_windows=1))[-1]['result']
    assert result['clarification'] is None
    assert len(result['tool_trace']) == 2 and len(contexts[-1].working_notes) == 1
    assert contexts[-1].free_calls == 1
    monkeypatch.setenv('LOUPE_AGENT_FIT', 'W')
    offered.clear()
    list(runner().stream(case_id=CASE, messages=[HumanMessage(content='Review')], checkpoint_callback=lambda p: None))
    assert 'record_working_notes' not in offered and 'read_test' in offered
