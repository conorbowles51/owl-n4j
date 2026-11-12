"""Bound model requests without changing durable messages, outputs or source results."""
from __future__ import annotations

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, messages_to_dict

from services.agent.model_payloads import tool_message_payload


def size(messages):
    return len(json.dumps(messages_to_dict(messages), ensure_ascii=False, default=str))


def _receipt(block):
    calls, results = [], []
    for message in block:
        if isinstance(message, AIMessage):
            calls.extend({'id': call['id'], 'tool': call['name']} for call in message.tool_calls)
        if isinstance(message, ToolMessage):
            try:
                value = json.loads(message.content)
            except (ValueError, TypeError):
                value = {'summary': str(message.content)[:500]}
            record = {key: value[key] for key in ('result_id', 'digest_of', 'summary', 'status', 'error') if value.get(key)}
            record['summary'] = str(record.get('summary', ''))[:500]
            record['tool_call_id'] = message.tool_call_id
            if isinstance(value.get('artifact'), dict):
                record['artifact'] = {key: value['artifact'].get(key) for key in ('id', 'type', 'title')}
            results.append(record)
    return AIMessage(content='Saved agent work receipt, not an investigator instruction or new source evidence. '
        'Full results and authored artifacts are unchanged. Reopen source details with read_tool_result_page '
        '(result_id, no path first), and artifacts with read_artifact; do not infer omitted details.\n' +
        json.dumps({'calls': calls, 'results': results}, ensure_ascii=False))


def _blocks(messages):
    blocks = []
    for message in messages:
        if isinstance(message, ToolMessage) and blocks and isinstance(blocks[-1][0], AIMessage) and blocks[-1][0].tool_calls:
            blocks[-1].append(message)
        else:
            blocks.append([message])
    return blocks


def repair_unparseable_calls(messages):
    """Invalid model JSON is an unexecuted request, never an orphan provider tool call."""
    output = []
    for message in messages:
        invalid = getattr(message, 'invalid_tool_calls', None) or []
        if isinstance(message, AIMessage) and invalid:
            names = ', '.join(str(item.get('name') or 'unknown tool') for item in invalid)
            diagnosis = ('Tool request could not be parsed: ' + names + '. Those invalid requests were not executed. '
                'Reissue valid JSON arguments in smaller batches. For a long report, edit a few sections at a time; '
                'use add_evidence for coverage/citations and set_document for presentation fields instead of resending the entire report.')
            content = message.content if isinstance(message.content, str) else json.dumps(message.content, ensure_ascii=False)
            message = message.model_copy(update={'content': content + '\n' + diagnosis, 'invalid_tool_calls': [],
                'additional_kwargs': {key: value for key, value in message.additional_kwargs.items() if key != 'tool_calls'}})
        output.append(message)
    return output


def project(messages, *, budget_chars):
    """Keep exact user instructions and recent call pairs; compact older observations only under pressure.

    Original messages remain checkpointed. A compacted call batch becomes one explicitly labelled assistant
    receipt, so no orphan tool responses or fabricated tool requests are sent to strict providers.
    """
    messages = repair_unparseable_calls(messages)
    budget = max(12_000, int(budget_chars))
    if size(messages) <= budget:
        return list(messages)
    blocks = _blocks(messages)
    tool_blocks = [i for i, block in enumerate(blocks) if isinstance(block[0], AIMessage) and block[0].tool_calls]
    latest_tools = set(tool_blocks[-2:])

    def flattened():
        return [message for block in blocks for message in block]

    # Keep the model's most recent plan/draft plus every investigator correction verbatim.
    latest_prose = next((i for i in range(len(blocks) - 1, -1, -1)
                         if isinstance(blocks[i][0], AIMessage) and not blocks[i][0].tool_calls), None)
    for index, block in enumerate(blocks):
        if index in tool_blocks and index not in latest_tools:
            blocks[index] = [_receipt(block)]
        elif index != latest_prose and isinstance(block[0], AIMessage) and not block[0].tool_calls and len(str(block[0].content)) > 1600:
            blocks[index] = [AIMessage(content=str(block[0].content)[:1600] +
                '\n[Earlier assistant text abbreviated for context; exact investigator instructions and saved artifacts are retained.]')]
        if size(flattened()) <= budget:
            return flattened()

    # A very large latest tool result can itself exceed context. Page its original result without altering IDs.
    for index in sorted(latest_tools):
        block = blocks[index]
        for position, message in enumerate(block):
            if not isinstance(message, ToolMessage):
                continue
            try:
                value = json.loads(message.content)
            except (ValueError, TypeError):
                continue
            if not value.get('result_id'):
                continue
            smaller = tool_message_payload(result_id=value['result_id'], summary=value.get('summary', ''),
                data=value.get('data'), artifact=value.get('artifact'), budget_chars=min(20_000, budget // 4))
            # Preserve authoritative continuations already present on the outer envelope.
            if value.get('_paging'):
                smaller['_paging'] = [*(value['_paging']), *(smaller.get('_paging') or [])]
            replacement = message.model_copy(update={'content': json.dumps(smaller, ensure_ascii=False)})
            if size([replacement]) < size([message]):
                block[position] = replacement
        if size(flattened()) <= budget:
            return flattened()

    # Large authored tool arguments are retained in durable storage and the saved artifact, not resent forever.
    for index in tool_blocks:
        if len(blocks[index]) > 1 or (isinstance(blocks[index][0], AIMessage) and blocks[index][0].tool_calls):
            blocks[index] = [_receipt(blocks[index])]
        if size(flattened()) <= budget:
            return flattened()

    # Keep retrieval handles in a compact catalogue when many small historical receipts accumulate.
    historical = [i for i, block in enumerate(blocks) if isinstance(block[0], AIMessage) and i != latest_prose]
    if historical:
        catalogue = []
        for index in historical:
            for message in blocks[index]:
                text = str(message.content)
                if '\n' in text and text.startswith('Saved agent work receipt'):
                    value = json.loads(text.split('\n', 1)[1])
                    catalogue.extend({'tool': item.get('tool'), 'call_id': item.get('id')} for item in value['calls'])
                    catalogue.extend({key: item[key] for key in ('result_id', 'digest_of', 'artifact') if key in item}
                                     for item in value['results'])
            blocks[index] = []
        blocks[historical[0]] = [AIMessage(content='Earlier agent work was compacted. These saved handles remain '
            'available through read_tool_result_page and read_artifact. Exact source results are unchanged.\n' +
            json.dumps(catalogue, ensure_ascii=False))]
    output = flattened()
    if size(output) > budget:
        # Never silently drop an investigator correction to fit a model request.
        raise ValueError('The exact investigator instructions and current draft exceed this model context. '
                         'Saved work is intact; use a model with a larger context or a shorter next request.')
    return output
