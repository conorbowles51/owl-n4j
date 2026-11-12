import copy
import uuid

from services.agent import claim_validation as claims
from services.agent.deliverables import new_artifact, dependency_metadata
from services.agent.storage import _checked_artifact_metadata


def test_completion_review_survives_reopening_without_leaking_to_another_revision():
    from types import SimpleNamespace
    from services.agent.storage import to_api_artifact
    artifact = new_artifact('report', 'Synthetic source review', {'sections': [{'heading': 'A', 'content': 'Draft.'}]})
    run = SimpleNamespace(extra_metadata={'completion_checks': {'issues': [
        {'artifact_id': artifact['id'], 'issues': ['The stated sequence contradicts its cited source.']}]}})
    record = SimpleNamespace(id=artifact['id'], type='report', title=artifact['title'], payload=artifact['data'],
        extra_metadata=artifact['metadata'], run=run)
    assert to_api_artifact(record).metadata['completion_review']['status'] == 'needs_revision'
    assert 'completion_review' not in record.extra_metadata
    record.id = str(uuid.uuid4())
    assert 'completion_review' not in to_api_artifact(record).metadata


def test_unchanged_source_checks_are_reused_but_changed_canonical_text_invalidates_them(monkeypatch):
    identity = str(uuid.uuid4())
    source = {'doc': {'evidence_id': identity, 'revision': 'revision1',
        'pages': [{'page_number': 1, 'text': 'Recorded on 2026-02-03.'}]}}
    artifact = new_artifact('report', 'Synthetic view', {'sections': [{'id': 's', 'heading': 'Record',
        'content': f'Recorded on 2026-02-03. [Source](doc://{identity}/1)'}]})
    claims.apply_claim_validation(artifact, source, {})
    original, calls = claims.apply_claim_validation, []
    def apply(*args):
        calls.append(True)
        return original(*args)
    monkeypatch.setattr(claims, 'apply_claim_validation', apply)
    def checked():
        return _checked_artifact_metadata(copy.deepcopy(artifact), source, {}, canonical_digest=claims.canonical_source_fingerprint(source))
    assert checked()['validation']['status'] == 'structural_checks_passed'
    assert not calls
    source['doc']['pages'][0]['text'] = 'Recorded on 2026-02-04.'
    assert checked()['validation']['status'] == 'needs_revision'
    assert len(calls) == 1
    assert checked()['validation']['status'] == 'needs_revision'
    assert len(calls) == 1
    source['unrelated-tool'] = {'summary': 'Unrelated later progress does not invalidate source checks.'}
    assert checked()['validation']['status'] == 'needs_revision' and len(calls) == 1


def test_relevant_calculation_input_mutation_invalidates_signature():
    artifact = new_artifact('table', 'Synthetic values', {'rows': [{'amount': 2}], 'claim_bindings': [
        {'id': 'sum', 'content_path': 'rows.0.amount', 'claim_text': '2', 'source': {'result_id': 'calc'}}]})
    results = {'calc': {'value': 2, 'input_refs': {'rows': {'result_id': 'rows'}}}, 'rows': [{'amount': 2}]}
    old = claims.validation_signature(artifact, results, {})
    results['rows'][0]['amount'] = 3
    assert claims.validation_signature(artifact, results, {}) != old


def test_structural_receipt_is_bound_to_its_actual_payload():
    artifact = new_artifact('workbook', 'Synthetic workbook', {'sheets': [{'name': 'Data', 'rows': [{'amount': 2}]}]})
    assert dependency_metadata(artifact, {})['validation']['status'] == 'structural_checks_passed'
    artifact['data']['sheets'][0]['rows'] = []
    assert dependency_metadata(artifact, {})['validation']['status'] == 'needs_revision'
