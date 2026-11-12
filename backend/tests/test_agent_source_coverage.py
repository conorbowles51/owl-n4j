import json
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from services.agent.source_coverage import document_coverage, source_observations


def source():
    return {'evidence_id': 'synthetic-source', 'revision': 'sha', 'document_name': 'Synthetic', 'page_count': 2,
            'pages': [{'page_number': 1, 'text': 'abcdefghij'}, {'page_number': 2, 'text': 'klmnopqrst'}]}


def message(result, data):
    return ToolMessage(tool_call_id=result, content=json.dumps({'result_id': result, 'data': data}))


def test_fetched_full_document_is_not_misreported_as_fully_delivered():
    results = {'original': source()}
    receipt = document_coverage([message('original', {'pages': [{'page_number': 1, 'text': 'abcd'}]})], results)[0]
    assert receipt['complete_pages'] == 0 and receipt['fetched_pages'] == 2
    assert receipt['incomplete_pages'][0]['next_read'] == {'result_id': 'original', 'path': ['data', 'pages', 0, 'text'], 'offset': 4}
    assert receipt['status'] == 'partial_text_delivered'


def test_exact_character_pages_close_only_contiguous_coverage_and_deduplicate_overlap():
    results = {'original': source(), 'second': {'page_of': 'original'}, 'third': {'page_of': 'second'}}
    messages = [message('original', {'pages': [{'page_number': 1, 'text': 'abcd'}, {'page_number': 2, 'text': 'klmnopqrst'}]}),
        message('second', {'page_of': 'original', 'text': 'efghij', '_paging': [
            {'unit': 'characters', 'path': ['data', 'pages', 0, 'text'], 'offset': 4}]}),
        message('third', {'page_of': 'second', 'text': 'abcd', '_paging': [
            {'unit': 'characters', 'path': ['data', 'pages', 0, 'text'], 'offset': 0}]})]
    result = document_coverage(messages, results)[0]
    assert result['complete_pages'] == 2 and result['status'] == 'complete_text_delivered'
    assert result['incomplete_pages'] == []


def test_missing_middle_or_incorrect_text_never_counts_as_complete():
    results = {'original': source(), 'end': {'page_of': 'original'}}
    messages = [message('original', {'pages': [{'page_number': 1, 'text': 'abc'}]}),
        message('end', {'text': 'fghij', '_paging': [{'unit': 'characters', 'path': ['data', 'pages', 0, 'text'], 'offset': 5}]})]
    result = document_coverage(messages, results)[0]
    assert result['incomplete_pages'][0]['delivered_prefix_chars'] == 3
    messages.append(message('original', {'pages': [{'page_number': 1, 'text': 'WRONG TEXT'}]}))
    assert document_coverage(messages, results)[0]['complete_pages'] == 0


def test_source_trimmed_by_context_projection_is_not_counted_as_delivered_in_full():
    from services.agent.context_projection import project
    data = {**source(), 'page_count': 1, 'pages': [{'page_number': 1, 'text': 'Synthetic source. ' * 6000}]}
    results = {'original': data}
    stored = [HumanMessage(content='Read the entire source.'),
        AIMessage(content='', tool_calls=[{'id': 'original', 'name': 'get_document_text', 'args': {}}]),
        message('original', data)]
    assert document_coverage(stored, results)[0]['complete_pages'] == 1
    projected = project(stored, budget_chars=12000)
    actual = list(source_observations(projected, results))
    receipt = document_coverage(actual, results)[0]
    assert receipt['status'] == 'partial_text_delivered'
    assert receipt['complete_pages'] == 0
    assert receipt['incomplete_pages'][0]['delivered_prefix_chars'] < len(data['pages'][0]['text'])
