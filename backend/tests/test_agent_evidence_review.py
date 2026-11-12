import copy
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from services.agent.evidence_review import packets, read_response, review
from services.agent.deliverables import new_artifact, revise_artifact

SOURCE = '00000000-0000-0000-0000-000000000099'
CITE = f'doc://{SOURCE}/1'


def fixture():
    artifact = new_artifact('report', 'Synthetic review', {'sections': [{'id': 'analysis', 'heading': 'Review status',
        'content': f'The review was completed. [Source]({CITE})'}]})
    results = {'source': {'evidence_id': SOURCE, 'revision': 'v1',
        'pages': [{'page_number': 1, 'text': 'No completion date was recorded.'}]}}
    issue = {'error_type': 'unsupported', 'section_id': 'analysis', 'claim_text': 'The review was completed.', 'reason': 'Completion is not established.',
        'cite': CITE, 'source_quote': 'No completion date was recorded.'}
    return artifact, results, issue


def test_separate_review_caches_exact_inputs_and_rechecks_changed_source():
    artifact, results, issue = fixture()
    requests, checkpoints, receipts = [], [], {}
    def invoke(messages):
        requests.append(messages)
        return AIMessage(content=json.dumps({'issues': [issue]}))
    def check():
        return review([artifact], results, receipts, invoke=invoke, checkpoint=lambda: checkpoints.append(copy.deepcopy(receipts)))
    assert 'Completion is not established' in check()[0]['issues'][0]
    assert len(requests) == len(checkpoints) == 1
    assert check() and len(requests) == 1
    assert len(requests[0]) == 2
    assert 'untrusted' in requests[0][0].content
    assert 'source truth' in next(iter(receipts.values()))['scope']
    results['source']['revision'] = 'v2'
    check()
    assert len(requests) == 2


@pytest.mark.parametrize('mutation', ['claim', 'source', 'id', 'malformed'])
def test_model_review_cannot_invent_a_quoted_diagnosis(mutation):
    artifact, results, issue = fixture()
    if mutation == 'claim': issue['claim_text'] = 'A sentence absent from the draft.'
    if mutation == 'source': issue['source_quote'] = 'Invented source.'
    if mutation == 'id': issue['section_id'] = 'another-section'
    if mutation == 'malformed': issue = 'not an issue record'
    with pytest.raises(ValueError):
        read_response(AIMessage(content=json.dumps({'issues': [issue]})), packets(artifact, results)[0])


def test_oversized_source_is_not_silently_truncated_or_treated_as_reviewed():
    artifact, results, _ = fixture()
    result = review([artifact], results, {}, invoke=lambda _: pytest.fail('Oversized review was sent'),
                    checkpoint=lambda: None, max_chars=50)
    assert 'exceeds the bounded review context' in result[0]['issues'][0]


def test_invalid_review_is_repaired_before_asking_the_author_to_change_the_report():
    artifact, results, issue = fixture()
    requests = []
    def invoke(messages):
        requests.append(list(messages))
        if len(requests) == 1:
            return AIMessage(content=json.dumps({'issues': [{**issue, 'source_quote': 'Invented quotation.'}]}))
        return AIMessage(content='{"issues": []}')
    receipts = {}
    assert review([artifact], results, receipts, invoke=invoke, checkpoint=lambda: None) == []
    assert len(requests) == 2 and len(requests[1]) == 4
    assert 'Correct the review response itself' in requests[1][-1].content
    assert next(iter(receipts.values()))['status'] == 'no_issues_identified'


def test_review_repair_explains_an_invalid_combined_error_type():
    artifact, results, issue = fixture()
    requests = []
    def invoke(messages):
        requests.append(list(messages))
        value = {**issue, 'error_type': 'contradiction or unsupported'} if len(requests) == 1 else issue
        return AIMessage(content=json.dumps({'issues': [value]}))
    problems = review([artifact], results, {}, invoke=invoke, checkpoint=lambda: None)
    assert len(requests) == 2 and len(problems) == 1
    assert 'must be exactly "contradiction" or exactly "unsupported"' in requests[1][-1].content
    assert 'Completion is not established' in problems[0]['issues'][0]


def test_identical_inputs_share_one_review_attempt_even_when_the_review_is_incomplete():
    artifact, results, _ = fixture()
    duplicate = new_artifact('report', 'Separate requested copy', copy.deepcopy(artifact['data']))
    requests, progress, receipts = [], [], {}
    def invoke(messages):
        requests.append(messages)
        return AIMessage(content='{}')
    def check():
        return review([artifact, duplicate], results, receipts, invoke=invoke, checkpoint=lambda: None,
                      on_progress=lambda current, total: progress.append((current, total)))
    problems = check()
    assert len(requests) == 2  # One initial response and one repair, shared by both outputs.
    assert len(problems) == 2 and problems[0]['issues'] == problems[1]['issues']
    assert all(current == total == 1 for current, total in progress)
    check()
    assert len(requests) == 4  # A later pass may retry the incomplete review.


def test_large_cited_page_is_reviewed_in_complete_bounded_source_batches():
    artifact, results, _ = fixture()
    source = ('A long synthetic source paragraph with exact characters.\n' * 1000)
    results['source']['pages'][0]['text'] = source
    values = packets(artifact, results, max_chars=5000)
    assert len(values) > 1
    assert all(not p['too_large'] and p['source_context_partial'] for p in values)
    assert ''.join(p['sources'][CITE]['text'] for p in values) == source
    assert values[0]['sources'][CITE]['start_char'] == 0
    assert values[-1]['sources'][CITE]['end_char'] == len(source)


def test_unsubstantiated_contradiction_is_returned_to_reviewer_not_report_writer():
    artifact, results, issue = fixture()
    requests = []
    def invoke(messages):
        requests.append(list(messages))
        if len(requests) == 1:
            return AIMessage(content=json.dumps({'issues': [{**issue, 'error_type': 'contradiction', 'source_quote': '',
                'reason': 'The statement is consistent with the source. No contradiction found.'}]}))
        return AIMessage(content='{"issues": []}')
    assert review([artifact], results, {}, invoke=invoke, checkpoint=lambda: None) == []
    assert len(requests) == 2
    assert 'requires an exact source quotation' in requests[1][-1].content


def test_partial_source_review_cannot_treat_other_batches_as_missing_evidence():
    artifact, results, issue = fixture()
    packet = {**packets(artifact, results)[0], 'source_context_partial': True}
    with pytest.raises(ValueError, match='other cited text is reviewed separately'):
        read_response(AIMessage(content=json.dumps({'issues': [{**issue, 'error_type': 'unsupported'}]})), packet)


def test_distinct_source_populations_are_reviewed_separately():
    artifact, results, _ = fixture()
    other_cite = CITE.rsplit('/', 1)[0] + '/2'
    results['source']['pages'].append({'page_number': 2, 'text': 'A different subject has a completed review.'})
    artifact['data']['sections'].append({'id': 'other', 'heading': 'Another subject',
        'content': f'A different subject has a completed review. [Source]({other_cite})'})
    values = packets(artifact, results)
    assert len(values) == 2
    assert [list(p['sources']) for p in values] == [[CITE], [other_cite]]


def test_semantic_contradiction_enters_durable_repair_and_accounts_for_review_usage(monkeypatch):
    from tests.test_agent_durable_execution import CASE, runner
    from services.agent import graph
    from services.agent.claim_validation import fingerprint
    from services.agent.render_checks import CHECK_VERSION
    artifact, results, issue = fixture()
    values, reviews, saved = [], [], []
    def tools(context):
        class Tool:
            name = 'synthetic_report'
            def invoke(self, args):
                context.result_store.update(results)
                value = artifact if not values else revise_artifact(artifact, {'sections': [{'id': 'analysis',
                    'heading': 'Review status', 'content': f'No completion date was recorded. [Source]({CITE})'}]}, expected_revision=1)
                values.append(value)
                return context.result(self.name, {}, summary='Saved synthetic report.', artifact=value)
        return [Tool()]
    monkeypatch.setattr(graph, 'make_agent_tools', tools)
    monkeypatch.setattr(graph, 'tools_for_binding', lambda model, tools: tools)
    monkeypatch.setattr('services.agent.render_checks.inspect_export', lambda a, **kw: {
        'artifact_id': a['id'], 'payload_sha256': fingerprint(a['data']), 'check_version': CHECK_VERSION,
        'page_count': 1, 'issues': [], 'format': 'pdf'})
    r = runner([[{'id': 'create', 'name': 'synthetic_report', 'args': {}}], [],
                [{'id': 'repair', 'name': 'synthetic_report', 'args': {}}]])
    original = r.base_model.invoke
    def invoke(messages):
        if messages[0].content.startswith('You are reviewing a saved investigative draft'):
            reviews.append(messages)
            return AIMessage(content=json.dumps({'issues': [issue] if len(reviews) == 1 else []}),
                             usage_metadata={'input_tokens': 10, 'output_tokens': 5, 'total_tokens': 15})
        return original(messages)
    r.base_model.invoke = invoke
    events = list(r.stream(case_id=CASE, messages=[HumanMessage(content='Create a sourced report.')],
                          checkpoint_callback=lambda value: saved.append(value)))
    final = events[-1]['result']
    assert len(values) == len(reviews) == 2
    assert final['repair_attempts'] == 1 and final['completion_issues'] == []
    assert len(saved[-1]['evidence_review_receipts']) == 2
    assert sum((m.usage_metadata or {}).get('total_tokens', 0) for m in final['messages']) == 30
