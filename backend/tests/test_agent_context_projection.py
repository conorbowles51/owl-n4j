import copy
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, messages_to_dict

from services.agent.context_projection import project, size


def batch(index, length=14000):
    return [AIMessage(content='', tool_calls=[{'id': f'call{index}', 'name': 'get_document_text', 'args': {}}]),
            ToolMessage(tool_call_id=f'call{index}', content=json.dumps({
                'result_id': f'res{index}', 'summary': f'Read source {index}', 'data': {'text': 'x' * length}}))]


def assert_pairs(messages):
    pending = set()
    for message in messages:
        if isinstance(message, AIMessage):
            assert not pending
            pending.update(call['id'] for call in message.tool_calls)
        elif isinstance(message, ToolMessage):
            assert message.tool_call_id in pending
            pending.remove(message.tool_call_id)
        else:
            assert not pending
    assert not pending


def test_compaction_preserves_all_instructions_source_handles_and_original_messages():
    original = [HumanMessage(content='Cover all25 subjects without an executive summary.')]
    for index in range(80):
        original.extend(batch(index))
        if index == 40:
            original.append(HumanMessage(content='Use the corrected date of15May.'))
    snapshot = copy.deepcopy(messages_to_dict(original))
    output = project(original, budget_chars=80000)
    assert size(output) <= 80000
    assert messages_to_dict(original) == snapshot
    assert [m.content for m in output if isinstance(m, HumanMessage)] == [m.content for m in original if isinstance(m, HumanMessage)]
    text = json.dumps(messages_to_dict(output))
    for index in range(80):
        assert f'res{index}' in text
    assert_pairs(output)


def test_oversized_current_tool_result_is_retrievable_and_call_pairing_survives():
    original = [HumanMessage(content='Produce the complete report.'), *batch(1, 100000)]
    output = project(original, budget_chars=30000)
    assert size(output) <= 30000
    text = json.dumps(messages_to_dict(output))
    assert 'res1' in text and ('_paging' in text or 'receipt' in text)
    assert_pairs(output)
    assert len(original[-1].content) > 100000


def test_small_context_is_unchanged_and_oversized_instructions_fail_explicitly():
    original = [HumanMessage(content='Short request'), *batch(1, 20)]
    assert messages_to_dict(project(original, budget_chars=20000)) == messages_to_dict(original)
    with pytest.raises(ValueError, match='exact investigator instructions'):
        project([HumanMessage(content='x' * 50000)], budget_chars=15000)


def test_parallel_tool_batches_remain_complete_after_compaction():
    calls = [{'id': f'call{i}', 'name': 'read_artifact', 'args': {}} for i in range(3)]
    original = [HumanMessage(content='All three'), AIMessage(content='', tool_calls=calls)]
    original.extend(ToolMessage(tool_call_id=f'call{i}', content=json.dumps({'result_id': f'res{i}', 'data': {'rows': ['x' * 10000] * 5}})) for i in range(3))
    output = project(original, budget_chars=25000)
    assert size(output) <= 25000
    assert_pairs(output)


def test_unparseable_json_never_reaches_provider_as_an_unanswered_tool_call():
    from langchain_openai.chat_models.base import _convert_message_to_dict
    invalid = AIMessage(content='', invalid_tool_calls=[{'id': 'bad', 'name': 'edit_report_sections', 'args': '{', 'error': 'Invalid JSON'}],
        additional_kwargs={'tool_calls': [{'id': 'bad', 'type': 'function', 'function': {'name': 'edit_report_sections', 'arguments': '{'}}]})
    original = [HumanMessage(content='Finish the report'), invalid, HumanMessage(content='Automated check: repair the draft.')]
    output = project(original, budget_chars=20000)
    wire = [_convert_message_to_dict(message) for message in output]
    assert not wire[1].get('tool_calls')
    assert 'not executed' in wire[1]['content']
    assert invalid.invalid_tool_calls and invalid.additional_kwargs['tool_calls']


def test_valid_calls_in_a_mixed_batch_still_receive_their_real_results():
    invalid = AIMessage(content='', tool_calls=[{'id': 'good', 'name': 'read_artifact', 'args': {}}],
        invalid_tool_calls=[{'id': 'bad', 'name': 'edit_report_sections', 'args': '{', 'error': 'Invalid JSON'}])
    output = project([invalid, ToolMessage(tool_call_id='good', content='Real result')], budget_chars=20000)
    assert_pairs(output)
    assert output[0].tool_calls[0]['id'] == 'good' and not output[0].invalid_tool_calls
