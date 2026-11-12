"""Synthetic claims must resolve to real full sources and reproducible results."""
import copy
import uuid
from types import SimpleNamespace

import pytest

from services.agent.calculation_workspace import calculate
from services.agent.claim_validation import validate_claims, fingerprint
from services.agent.deliverable_tools import make_deliverable_tools


@pytest.fixture
def sources():
    rows = [{"record": f"S{i:04d}", "amount": "0.10"} for i in range(1500)]
    results = {"evidence": {"rows": rows, "text": "Source statement at the end: the payment was received."}}
    calculation = calculate("sum([decimal(r['amount']) for r in rows])", {"rows": rows})
    calculation.update(input_refs={"rows": {"result_id": "evidence", "path": "rows"}}, assumptions={})
    results["calculation"] = calculation
    return results


def numeric_data(value="150.00"):
    claim = f"The total is {value}."
    return {"sections": [{"id": "total", "heading": "Totals", "content": claim}],
            "claim_bindings": [{"id": "total-claim", "section_id": "total", "claim_text": claim,
                                "source": {"result_id": "calculation"},
                                "numeric": {"value_path": "value", "rendered_value": value, "decimals": 2}}],
            "numeric_claims": [{"section_id": "total", "claim_text": claim, "binding_id": "total-claim"}],
            "coverage": [{"item": "Totals", "status": "fulfilled", "section_id": "total", "claim_ids": ["total-claim"]}]}


def validate(data, sources, **kwargs):
    return validate_claims(data, result_store=sources, artifact_store={}, **kwargs)


def test_full_1500_row_numeric_claim_reproduces_and_persists_source_hashes(sources):
    checked = validate(numeric_data(), sources, required_items=["Totals"], source_result_ids=["evidence"])
    assert checked["issues"] == []
    receipt = checked["bindings"][0]
    assert receipt["expected_value"] == "150.00"
    assert receipt["calculation"]["input_sources"]["rows"]["source_sha256"] == fingerprint(sources["evidence"])
    assert receipt["source"]["source_sha256"] == fingerprint(sources["calculation"])
    assert checked["coverage"][0]["status"] == "content_located"
    assert "source truth" in checked["scope"]


@pytest.mark.parametrize("mutation", ["missing_source", "wrong_number", "modified_inputs", "missing_binding", "invented_value", "missing_quote"])
def test_invalid_declared_claim_cannot_pass(sources, mutation):
    data = numeric_data()
    if mutation == "missing_source":
        data["claim_bindings"][0]["source"]["result_id"] = "nonexistent"
    elif mutation == "wrong_number":
        data = numeric_data("149.00")
    elif mutation == "modified_inputs":
        sources["evidence"]["rows"][-1]["amount"] = "100.00"
    elif mutation == "missing_binding":
        data["claim_bindings"] = []
    elif mutation == "invented_value":
        sources["calculation"]["value"] = "999.00"
        data = numeric_data("999.00")
    else:
        data["claim_bindings"][0]["quote"] = "This quotation never occurred."
    result = validate(data, sources, required_items=["Totals"])
    assert result["issues"]
    assert result["coverage"][0]["status"] == "unresolved"


def test_quote_checked_against_full_selected_source_and_rendered_text(sources):
    quote = "the payment was received."
    data = {"sections": [{"id": "q", "content": quote}], "claim_bindings": [
        {"id": "q1", "section_id": "q", "claim_text": quote, "quote": quote, "source": {"result_id": "evidence", "path": "text"}}]}
    result = validate(data, sources)
    assert result["issues"] == []
    assert result["bindings"][0]["quote_sha256"] == fingerprint(quote)
    data["sections"][0]["content"] = "A different paraphrase."
    data["claim_bindings"][0]["claim_text"] = "A different paraphrase."
    assert validate(data, sources)["issues"]


def test_calculated_numeric_cell_can_be_bound_without_converting_the_dataset_to_prose(sources):
    data = {'rows': [{'amount': 150}], 'claim_bindings': [{'id': 'sum', 'content_path': 'rows.0.amount',
        'claim_text': '150', 'source': {'result_id': 'calculation'},
        'numeric': {'value_path': 'value', 'rendered_value': '150'}}]}
    assert not validate(data, sources)['issues']
    data['rows'][0]['amount'] = 149
    assert validate(data, sources)['issues']


def test_coverage_declaration_or_title_cannot_replace_content_evidence(sources):
    data = {"sections": [{"id": "s", "heading": "Totals", "content": "No calculations supplied."}],
            "coverage": [{"item": "Totals", "section_id": "s", "status": "fulfilled", "excerpt": "Totals"}]}
    assert validate(data, sources, required_items=["Totals"])["issues"]
    data["coverage"][0]["excerpt"] = "No calculations supplied."
    assert validate(data, sources, required_items=["Totals"])["issues"] == []


def test_numeric_token_cannot_match_prefix_of_different_value(sources):
    data = numeric_data("150.00")
    data["sections"][0]["content"] = data["claim_bindings"][0]["claim_text"] = "The total is 150.001."
    assert validate(data, sources)["issues"]


def test_self_certified_metadata_and_invisible_paths_are_rejected(sources):
    data = numeric_data()
    binding = data["claim_bindings"][0]
    binding.pop("section_id")
    data["invisible"] = binding["claim_text"]
    binding["content_path"] = "invisible"
    assert validate(data, sources)["issues"]
    binding["content_path"] = "claim_bindings.0.claim_text"
    assert validate(data, sources)["issues"]


def test_corrected_revision_rechecks_and_repairs_status_preserving_original(sources):
    context = SimpleNamespace(result_store=sources, artifact_store={})
    def result(name, data, *, summary, artifact=None, status="success", error=None):
        identity = str(uuid.uuid4())
        context.result_store[identity] = data
        if artifact:
            context.artifact_store[artifact["id"]] = artifact
        return {"result_id": identity, "data": data, "artifact": artifact, "status": status}
    context.result = result
    tools = {t.name: t for t in make_deliverable_tools(context)}
    wrong = tools["create_artifact"].invoke({"kind": "report", "title": "Totals", "data": numeric_data("149.00"), "required_items": ["Totals"]})["artifact"]
    original = copy.deepcopy(wrong)
    assert wrong["metadata"]["validation"]["status"] == "needs_revision"
    corrected = tools["revise_artifact"].invoke({"artifact_id": wrong["id"], "expected_revision": 1, "data": numeric_data()})["artifact"]
    assert corrected["metadata"]["revision"] == 2
    assert corrected["metadata"]["validation"]["issues"] == []
    assert corrected["metadata"]["validation"]["source_review"] == "declared_bindings_checked"
    assert corrected["metadata"]["validation"]["source_truth"] == "not_established"
    assert wrong == original


def test_artifact_source_binding_records_exact_revision(sources):
    source = {"id": "a", "data": {"text": "Known phrase"}, "metadata": {"revision": 3}}
    data = {"sections": [{"id": "q", "content": "Known phrase"}], "claim_bindings": [
        {"id": "q1", "section_id": "q", "claim_text": "Known phrase", "quote": "Known phrase", "source": {"artifact_id": "a"}}]}
    result = validate_claims(data, result_store=sources, artifact_store={"a": source})
    assert result["issues"] == []
    assert result["bindings"][0]["source"]["revision"] == 3


def test_undeclared_narrative_monetary_total_cannot_avoid_numeric_gate(sources):
    data={"sections":[{"id":"s","content":"The combined exposure total is £149.00.","embeds":[
        {"type":"table","data":{"rows":[{"amount":"100.00"},{"amount":"50.00"}]}}]}]}
    checked=validate(data,sources)
    assert checked["issues"]
    assert checked["detected_totals"][0]["status"]=="unbound"
    data=numeric_data()
    data.pop("numeric_claims")
    assert validate(data,sources)["issues"]==[]


def test_reported_verbatim_total_needs_both_source_quote_and_explicit_prose_label(sources):
    sources['statement']={'text':'The total was £149.00.'}
    data={'sections':[{'id':'s','content':'The statement reported: The total was £149.00.'}],
          'claim_bindings':[{'id':'reported','section_id':'s','claim_text':'The statement reported: The total was £149.00.',
                             'quote':'The total was £149.00.','reported_figure':True,'source':{'result_id':'statement'}}]}
    assert validate(data,sources)['issues']==[]
    data['claim_bindings'][0].pop('reported_figure')
    assert validate(data,sources)['issues']
