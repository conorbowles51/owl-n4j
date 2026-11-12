"""Completion means the latest output meets explicit requirements, after bounded repair."""
from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from services.agent.completion_checks import delivery_contract, assess
from services.agent.claim_validation import fingerprint
from services.agent.deliverables import new_artifact, revise_artifact
from tests.test_agent_durable_execution import CASE, runner


def test_report_page_contract_preserves_latest_explicit_correction_and_ignores_source_page_locations():
    contract = delivery_contract(['Create a 40–60 page professional report.', 'Make it 20–30 pages instead.'])
    assert (contract['min_pages'], contract['max_pages']) == (20, 30)
    assert delivery_contract(['Read source pages 40–60 for the report.'])['min_pages'] is None
    assert delivery_contract(['Create a report.', 'What does the file say?'])['report_requested'] is False
    assert delivery_contract(['Create a one-page report.'])['max_pages'] == 1
    assert delivery_contract(['Create a four-slide editable presentation.'])['slide_count'] == 4


def test_requested_exhibit_count_counts_families_and_does_not_leak_into_followup_edits():
    old = new_artifact('table', 'Exhibit 1', {'rows': [{'value': 1}]})
    revised = revise_artifact(old, {'rows': [{'value': 2}]}, expected_revision=1)
    context = SimpleNamespace(artifact_store={old['id']: old, revised['id']: revised}, result_store={})
    contract = delivery_contract(['Create twelve separately named exhibits.'])
    assert contract['min_outputs'] == 12
    problems = assess(context, [old, revised], contract, {})
    assert 'only 1' in problems[0]['issues'][0]
    assert delivery_contract(['Create twelve separate exhibits.', 'Revise the first one.'])['min_outputs'] is None


def test_explicit_complete_source_read_requires_delivered_text_not_just_fetched_data():
    contract = delivery_contract(['Read all25 source parts completely from Evidence file 00000000-0000-0000-0000-000000000099.'])
    assert contract['full_source_reads']
    context = SimpleNamespace(artifact_store={}, result_store={})
    assert 'has not been read' in assess(context, [], contract, {})[0]['issues'][0]
    partial = {'evidence_id': contract['source_file_ids'][0], 'name': 'Synthetic', 'complete_pages': 1,
        'total_pages': 25, 'status': 'partial_text_delivered', 'incomplete_pages': []}
    assert 'Only 1 of 25' in assess(context, [], contract, {}, source_receipts=[partial])[0]['issues'][0]
    assert assess(context, [], contract, {}, source_receipts=[{**partial, 'complete_pages': 25, 'status': 'complete_text_delivered'}]) == []


def setup_tools(monkeypatch, *, fix=True):
    values = []

    def tools(context):
        class Tool:
            name = 'synthetic_artifact'

            def invoke(self, args):
                if args['fix'] and fix:
                    value = revise_artifact(values[0], {'sections': [{'id': 'analysis', 'heading': 'Narcotics', 'content': 'Complete supported review.'}],
                        'coverage': [{'item': 'Narcotics', 'status': 'fulfilled', 'section_id': 'analysis', 'excerpt': 'Complete supported review.'}]}, expected_revision=1)
                else:
                    value = new_artifact('report', 'Requested report', {'sections': [{'heading': 'Start', 'content': 'Partial draft.'}]}, requirements=['Narcotics'])
                values.append(value)
                return context.result(self.name, {'artifact_id': value['id']}, summary='Saved synthetic draft', artifact=value)
        return [Tool()]

    monkeypatch.setattr('services.agent.graph.make_agent_tools', tools)
    monkeypatch.setattr('services.agent.graph.tools_for_binding', lambda model, tools: tools)
    def inspect(artifact, **kwargs):
        count = 45 if (artifact['metadata']['revision'] == 2) else 3
        return {'artifact_id': artifact['id'], 'payload_sha256': fingerprint(artifact['data']), 'format': 'pdf',
                'page_count': count, 'issues': [], 'source_truth': 'not_established', 'visual_review': 'not_established'}
    monkeypatch.setattr('services.agent.render_checks.inspect_export', inspect)
    return values


def test_detected_structural_and_page_count_failures_trigger_automatic_repair(monkeypatch):
    values = setup_tools(monkeypatch)
    calls = [[{'id': 'create', 'name': 'synthetic_artifact', 'args': {'fix': False}}], [],
             [{'id': 'repair', 'name': 'synthetic_artifact', 'args': {'fix': True}}]]
    checkpoints = []
    events = list(runner(calls).stream(case_id=CASE, messages=[HumanMessage(content='Create a 40–60 page report.')],
                                      checkpoint_callback=lambda payload: checkpoints.append(payload)))
    result = events[-1]['result']
    assert len(values) == 2 and result['repair_attempts'] == 1
    assert result['completion_issues'] == []
    assert result['render_receipts'][values[-1]['id']]['page_count'] == 45
    assert checkpoints[-1]['delivery_contract']['min_pages'] == 40
    assert checkpoints[-1]['repair_attempts'] == 1


def test_unrepaired_artifact_stops_after_three_attempts_with_explicit_issues(monkeypatch):
    setup_tools(monkeypatch)
    events = list(runner([[{'id': 'create', 'name': 'synthetic_artifact', 'args': {'fix': False}}]]).stream(
        case_id=CASE, messages=[HumanMessage(content='Create a 40–60 page report.')], checkpoint_callback=lambda payload: None))
    result = events[-1]['result']
    assert result['repair_attempts'] == 3
    assert any('minimum is 40' in issue for item in result['completion_issues'] for issue in item['issues'])
    assert 'still needs revision' in result['answer']
    assert 'minimum is 40' in result['answer']
    assert all('The requested review is ready.' not in event.get('answer', '') for event in events)


def test_old_render_failure_does_not_block_a_new_revision(monkeypatch):
    values = setup_tools(monkeypatch)
    old = new_artifact('report', 'Report', {'sections': [{'heading': 'Old', 'content': 'Old content'}]})
    new = revise_artifact(old, {'sections': [{'heading': 'New', 'content': 'New content'}]}, expected_revision=1)
    context = SimpleNamespace(artifact_store={old['id']: old, new['id']: new}, result_store={
        'old-render': {'artifact_id': old['id'], 'payload_sha256': fingerprint(old['data']), 'format': 'pdf',
                       'page_count': 1, 'issues': ['Old broken export']}})
    receipts = {}
    assert assess(context, [old, new], delivery_contract(['Create a 40–60 page report.']), receipts) == []
    assert set(receipts) == {new['id']}


def test_checker_upgrade_grants_a_fresh_bounded_repair_window_but_ordinary_resume_does_not(monkeypatch):
    import copy
    setup_tools(monkeypatch)
    checkpoints = []
    list(runner([[{'id': 'create', 'name': 'synthetic_artifact', 'args': {'fix': False}}]]).stream(
        case_id=CASE, messages=[HumanMessage(content='Create a 40–60 page report.')],
        checkpoint_callback=lambda value: checkpoints.append(copy.deepcopy(value))))
    saved = checkpoints[-1]
    assert saved['repair_attempts'] == 3
    saved['phase'] = 'finalize'
    same = list(runner().stream(case_id=CASE, messages=[], resume_checkpoint=saved, checkpoint_callback=lambda _: None))
    assert not [event for event in same if event.get('stage') == 'repairing']
    saved['completion_check_version'] = 1
    upgraded = list(runner().stream(case_id=CASE, messages=[], resume_checkpoint=saved, checkpoint_callback=lambda _: None))
    assert len([event for event in upgraded if event.get('stage') == 'repairing']) == 3
    assert upgraded[-1]['result']['repair_attempts'] == 3
