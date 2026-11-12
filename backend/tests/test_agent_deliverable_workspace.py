"""Synthetic end-to-end tool journeys for long documents, data and immutable revisions."""
import copy
import uuid
from types import SimpleNamespace

import pytest

from services.agent.calculation_workspace import CalculationError, Workspace, calculate
from services.agent.deliverable_tools import make_deliverable_tools
from services.agent.deliverables import new_artifact, revise_artifact, validate_artifact, interactive_document


@pytest.fixture
def tools():
    context = SimpleNamespace(artifact_store={}, result_store={})
    def result(name, data, *, summary, artifact=None, status="success", error=None):
        key = str(uuid.uuid4())
        context.result_store[key] = data
        if artifact:
            context.artifact_store[artifact["id"]] = artifact
        return {"result_id": key, "data": data, "artifact": artifact, "status": status, "error": error}
    context.result = result
    return {t.name: t for t in make_deliverable_tools(context)}


def test_twelve_exhibits_remain_discoverable_and_earliest_can_be_revised(tools):
    made = []
    for i in range(12):
        a = tools["create_artifact"].invoke({"kind": "matrix", "title": f"Exhibit {i}",
            "data": {"columns": [{"key": "item"}], "rows": [{"item": i}]}})
        made.append(a["artifact"])
    assert tools["list_artifacts"].invoke({})["data"]["total"] == 12
    first = tools["read_artifact"].invoke({"artifact_id": made[0]["id"]})["data"]
    assert first["value"]["rows"] == [{"item": 0}]
    revised = tools["revise_artifact"].invoke({"artifact_id": made[0]["id"], "expected_revision": 1,
        "data": {"rows": [{"item": "corrected"}]}})["artifact"]
    assert revised["metadata"]["deliverable_id"] == made[0]["id"]
    assert revised["metadata"]["revision"] == 2
    assert tools["list_artifacts"].invoke({})["data"]["total"] == 12
    assert tools["list_artifacts"].invoke({"include_versions": True})["data"]["total"] == 13
    stale = tools["revise_artifact"].invoke({"artifact_id": made[0]["id"], "expected_revision": 1, "data": {}})
    assert stale["status"] == "error"


def test_long_report_incremental_edit_retains_unmentioned_sections(tools):
    sections = [{"id": f"s{i}", "heading": f"Subject {i}", "content": f"Full evidence for subject {i}. " * 800}
                for i in range(30)]
    coverage = [{"item": f"Subject {i}", "status": "fulfilled", "section_id": f"s{i}",
                 "excerpt": f"Full evidence for subject {i}."} for i in range(30)]
    created = tools["create_artifact"].invoke({"kind": "report", "title": "Thirty profiles", "data": {"sections": sections, "coverage": coverage},
                                              "required_items": [f"Subject {i}" for i in range(30)]})["artifact"]
    revised = tools["edit_report_sections"].invoke({"artifact_id": created["id"], "expected_revision": 1,
        "operations": [{"action": "replace", "section_id": "s7", "section": {"heading": "Subject 7", "content": "Corrected source. Full evidence for subject 7."}}]})["artifact"]
    assert len(revised["data"]["sections"]) == 30
    assert revised["data"]["sections"][6] == sections[6]
    assert revised["data"]["sections"][7]["content"] == "Corrected source. Full evidence for subject 7."
    assert created["data"]["sections"][7] == sections[7]
    assert revised["metadata"]["validation"]["issues"] == []


def test_correction_cannot_accidentally_create_a_second_same_title_deliverable(tools):
    first = tools['create_artifact'].invoke({'kind': 'report', 'title': 'Synthetic profile',
        'data': {'sections': [{'id': 'profile', 'heading': 'Profile', 'content': 'Original source reading.'}]}})['artifact']
    revised = tools['edit_report_sections'].invoke({'artifact_id': first['id'], 'expected_revision': 1,
        'operations': [{'action': 'replace', 'section_id': 'profile', 'section': {'content': 'Corrected source reading.'}}]})['artifact']
    duplicate = tools['create_artifact'].invoke({'kind': 'report', 'title': 'Synthetic profile', 'data': revised['data']})
    assert duplicate['status'] == 'error' and revised['id'] in duplicate['error']
    assert 'expected_revision=2' in duplicate['error'] and duplicate['artifact'] is None
    assert tools['list_artifacts'].invoke({})['data']['total'] == 1
    requested_copy = tools['create_artifact'].invoke({'kind': 'report', 'title': 'Synthetic profile',
        'data': revised['data'], 'separate_copy_reason': 'The investigator requested an independent comparison copy.'})['artifact']
    assert requested_copy['metadata']['deliverable_id'] != first['metadata']['deliverable_id']
    assert 'independent comparison copy' in requested_copy['metadata']['separate_copy_reason']
    assert tools['list_artifacts'].invoke({})['data']['total'] == 2


def test_complete_dataset_calculation_uses_all_batches_not_a_preview(tools):
    created = tools["create_artifact"].invoke({"kind": "table", "title": "Synthetic 1500 rows", "data": {
        "rows": [{"amount": "0.10", "index": n} for n in range(750)]}})["artifact"]
    revised = tools["append_artifact_rows"].invoke({"artifact_id": created["id"], "expected_revision": 1,
        "rows": [{"amount": "0.10", "index": n} for n in range(750, 1500)]})["artifact"]
    result = tools["calculate_artifact_data"].invoke({"expression": "sum([decimal(r['amount']) for r in rows])",
        "input_refs": {"rows": {"artifact_id": revised["id"], "path": "rows"}}})
    assert result["data"]["value"] == "150.00"
    page = tools["read_artifact"].invoke({"artifact_id": revised["id"], "path": "rows", "offset": 1450})["data"]
    assert len(page["value"]) == 50 and page["total"] == 1500 and page["next_offset"] is None
    prefixed = tools["read_artifact"].invoke({"artifact_id": revised["id"], "path": "data.rows", "offset": 1450})["data"]
    assert prefixed == page
    assert tools['read_artifact'].invoke({'artifact_id': revised['id'], 'path': 'value.rows', 'offset': 1450})['data'] == page
    first = tools['read_artifact'].invoke({'artifact_id': revised['id'], 'path': 'rows', 'offset': 1400})['data']
    assert tools['read_artifact'].invoke(first['next_read'])['data'] == page
    root = tools["read_artifact"].invoke({"artifact_id": revised["id"], "path": "data"})["data"]
    assert len(root['value']['rows']) == 1500
    missing = tools['read_artifact'].invoke({'artifact_id': revised['id'], 'path': 'missing'})
    assert missing['status'] == 'error' and 'Available root fields: rows' in missing['error']


def test_content_read_keeps_actionable_issues_without_repeating_verbose_audit_receipts(tools):
    saved = tools['create_artifact'].invoke({'kind': 'table', 'title': 'Synthetic review',
        'data': {'rows': [{'record': 'Complete source row'}]}})['artifact']
    saved['metadata']['claim_evidence']['saved_detail'] = 'Synthetic audit receipt. ' * 1000
    saved['metadata']['validation']['issues'] = ['Review the synthetic source quotation.']
    result = tools['read_artifact'].invoke({'artifact_id': saved['id'], 'path': 'rows'})['data']
    assert result['value'] == saved['data']['rows']
    assert 'Review the synthetic source quotation.' in result['metadata']['validation']['issues']
    assert 'claim_evidence' not in result['metadata']
    assert 'claim_evidence' in result['metadata_details']['omitted_fields']
    assert result['metadata']['completion_review']['status'] == 'not_recorded_in_artifact'
    assert 'does not mean the report passed' in result['metadata']['completion_review']['scope']
    complete = tools['read_artifact'].invoke(result['metadata_details']['read_full_metadata'])['data']
    assert complete['metadata']['claim_evidence']['saved_detail'] == saved['metadata']['claim_evidence']['saved_detail']


def test_report_section_can_be_read_by_its_stable_nested_id(tools):
    child = {'id': 'record-map', 'heading': 'Record map', 'content': 'Complete nested source comparison.'}
    saved = tools['create_artifact'].invoke({'kind': 'report', 'title': 'Synthetic report',
        'data': {'sections': [{'id': 'profile', 'heading': 'Profile', 'content': 'A synthetic profile.', 'children': [child]}]}})['artifact']
    result = tools['read_artifact'].invoke({'artifact_id': saved['id'], 'section_id': 'record-map'})
    assert result['status'] == 'success' and result['data']['value'] == child
    assert result['data']['section_id'] == 'record-map'
    missing = tools['read_artifact'].invoke({'artifact_id': saved['id'], 'section_id': 'missing'})
    assert missing['status'] == 'error' and "Section 'missing' is absent" in missing['error']
    conflict = tools['read_artifact'].invoke({'artifact_id': saved['id'], 'section_id': 'record-map', 'path': 'sections.0'})
    assert conflict['status'] == 'error' and 'not both' in conflict['error']


def test_missing_table_and_numeric_disagreement_cannot_pass_structural_checks():
    data = {"total": "27.00", "rows": [{"amount": "100.00"}, {"amount": "49.00"}],
            "numeric_checks": [{"rows_path": "rows", "column": "amount", "value_path": "total"}],
            "sections": [{"heading": "Consolidated table", "content": "The table will go here."}]}
    result = validate_artifact("report", data, ["Missing subject"])
    assert result["status"] == "needs_revision"
    assert len(result["issues"]) == 3


@pytest.mark.parametrize("expression", ["__import__('os')", "rows.__class__", "open('secret')", "2**999999999",
                                      "'a'*1000000000", "[r for r in rows for x in rows for y in rows]"])
def test_expression_workspace_cannot_escape_or_allocate_unbounded_work(expression):
    with pytest.raises(CalculationError):
        Workspace({"rows": list(range(100))}, max_steps=1000).run(expression)


def test_expression_reproducibility_and_no_source_mutation():
    data = {"rows": [{"amount": "10.12"}, {"amount": "2.05"}]}
    original = copy.deepcopy(data)
    first = calculate("sum([decimal(r['amount']) for r in rows])", data)
    assert first == calculate(first["expression"], data)
    assert first["value"] == "12.17" and data == original


def test_interactive_csp_precedes_untrusted_content():
    result = interactive_document('<script>fetch("https://example.invalid")</script>')
    assert '<script>' not in result
    assert "script-src 'none'" in result
    assert "form-action 'none'" in result


def test_declaring_coverage_is_not_the_same_as_delivering_it():
    result = validate_artifact("report", {"sections": [{"heading": "Overview", "content": "A short summary."}],
        "included_items": ["Missing subject"]}, ["Missing subject"])
    assert result["status"] == "needs_revision"


def test_invalid_revision_keeps_original():
    original = new_artifact("table", "Evidence", {"rows": [{"amount": 1}]})
    with pytest.raises(ValueError, match="changed"):
        revise_artifact(original, {"rows": []}, expected_revision=10)
    assert original["data"]["rows"] == [{"amount": 1}]
