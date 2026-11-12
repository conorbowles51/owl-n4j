"""Grounded report checks catch fabricated precise details, without claiming truth."""
from types import SimpleNamespace

from services.agent.source_grounding import inspect_source_grounding
from services.agent.claim_validation import apply_claim_validation
from services.agent.completion_checks import assess
from services.agent.deliverables import new_artifact, validate_artifact


FILE = '00000000-0000-0000-0000-000000000007'
CITE = f'doc://{FILE}/1'


def sources():
    return {'source': {'evidence_id': FILE, 'revision': 'v1', 'pages': [
        {'page_number': 1, 'text': 'Record AB12-CD01 dated 2026-02-28 at 09:15. Assignment D12-01 remains pending.'},
        {'page_number': 2, 'text': 'Record AB12-CD02 dated 2026-03-02 at 10:15. Assignment D12-02 remains pending.'}]}}


def report(prose):
    return {'sections': [{'id': 'analysis', 'heading': 'Analysis', 'content': prose}]}


def test_invented_records_dates_and_times_fail_against_the_cited_page():
    result = inspect_source_grounding(report(f'AB12-CD21 dated 2026-03-02 at 10:15; D12-21. {CITE}'), sources())
    assert result['issues']
    absent = result['sections'][0]['unsupported_details']
    assert absent == {'dates': ['2026-03-02'], 'times': ['10:15'], 'identifiers': ['AB12-CD21', 'D12-21']}


def test_supported_details_are_located_without_claiming_entailment_or_truth():
    result = inspect_source_grounding(report(f'ab12-cd01 on 2026-02-28, 9:15. {CITE}'), sources())
    assert result['issues'] == []
    assert result['sections'][0]['status'] == 'precise_details_located'
    assert 'not entailment' in result['scope']


def test_missing_unreadable_and_ambiguous_citations_cannot_pass():
    assert inspect_source_grounding(report(f'D12-01 {CITE}'), {})['issues']
    unreadable = sources()
    unreadable['source']['pages'][0]['text_missing'] = True
    assert inspect_source_grounding(report(f'D12-01 {CITE}'), unreadable)['issues']
    competing = sources()
    competing['changed'] = {**competing['source'], 'revision': 'v2'}
    assert inspect_source_grounding(report(f'D12-01 {CITE}'), competing)['sections'][0]['ambiguous_sources']


def test_removing_citation_does_not_make_known_source_details_pass():
    data = report('Record AB12-CD21 on 2026-03-02.')
    data['sections'].append({'id': 'sources', 'content': CITE})
    assert inspect_source_grounding(data, sources())['issues']
    data['sections'][0]['heading'] = 'Proposed follow-up schedule'
    assert inspect_source_grounding(data, sources())['issues'] == []
    assert inspect_source_grounding(report('An explicitly invented example: AB12-CD21.'), {})['issues'] == []


def test_automatic_claim_and_completion_checks_reject_old_structural_pass(monkeypatch):
    value = new_artifact('report', 'Example', report(f'AB12-CD21, 2026-03-02. {CITE}'))
    context = SimpleNamespace(result_store=sources(), artifact_store={value['id']: value})
    monkeypatch.setattr('services.agent.render_checks.inspect_export', lambda *a, **kw: {'page_count': 40, 'issues': []})
    assert assess(context, [value], {}, {})[0]['issues']
    apply_claim_validation(value, context.result_store, context.artifact_store)
    assert value['metadata']['validation']['status'] == 'needs_revision'
    assert value['metadata']['claim_evidence']['source_grounding']['sections'][0]['unsupported_details']


def test_escaped_paragraphs_and_broken_tables_need_repair_but_code_samples_do_not():
    assert validate_artifact('report', report(r'First\n\nSecond\n\nThird'))['issues']
    table = '| Date | Record |\n| 2026-02-28 | AB12-CD01 |\n| 2026-03-02 | AB12-CD02 |'
    assert validate_artifact('report', report(table))['issues']
    assert validate_artifact('report', report(table.replace('|\n', '|\n| --- | --- |\n', 1)))['issues'] == []
    assert validate_artifact('report', report('```text\n' + table + '\n```'))['issues'] == []
