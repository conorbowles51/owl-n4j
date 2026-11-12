import copy
import uuid
from types import SimpleNamespace

import pytest

from services.agent.deliverable_tools import make_deliverable_tools


@pytest.fixture
def workspace():
    context=SimpleNamespace(result_store={'source':{'rows':[{'record':f'R{i:04d}','amount':'0.10'} for i in range(1500)]}},artifact_store={})
    def result(name,data,*,summary,artifact=None,status='success',error=None):
        identity=str(uuid.uuid4());context.result_store[identity]=data
        if artifact:context.artifact_store[artifact['id']]=artifact
        return {'result_id':identity,'data':data,'artifact':artifact,'status':status,'error':error}
    context.result=result
    return context,{tool.name:tool for tool in make_deliverable_tools(context)}


def test_complete_calculation_result_copies_to_workbook_without_row_rewriting(workspace):
    context,tools=workspace
    calculated=tools['calculate_artifact_data'].invoke({'expression':"[{'record':r['record'],'amount':decimal(r['amount'])*2} for r in rows]",
                  'input_refs':{'rows':{'result_id':'source','path':'rows'}}})
    created=tools['create_artifact'].invoke({'kind':'workbook','title':'Complete workbook','data':{'sheets':[{'name':'Calculated'}]},
        'data_refs':{'sheets.0.rows':{'result_id':calculated['result_id'],'path':'value'}}})['artifact']
    assert len(created['data']['sheets'][0]['rows'])==1500
    assert created['data']['sheets'][0]['rows'][-1]=={'record':'R1499','amount':'0.20'}
    receipt=created['metadata']['input_receipts'][0]
    assert receipt['target_path']=='sheets.0.rows' and receipt['applied_in_revision']==1
    assert len(receipt['source_sha256'])==64 and len(receipt['selected_sha256'])==64
    context.result_store[calculated['result_id']]['value'][0]['amount']='changed'
    assert created['data']['sheets'][0]['rows'][0]['amount']=='0.20'


@pytest.mark.parametrize('kind,path,initial', [('workbook', 'sheets.0.rows', {'sheets': [{'name': 'Dataset', 'rows': []}]}),
                                             ('interactive', 'rows', {'rows': [], 'static_content': 'Synthetic rows'})])
def test_payload_nested_data_refs_are_resolved_before_saving_and_exporting(workspace, kind, path, initial):
    from services.agent.exports import render_artifact_export
    from openpyxl import load_workbook
    import io
    context, tools = workspace
    created = tools['create_artifact'].invoke({'kind': kind, 'title': 'Complete data',
        'data': {**initial, 'data_refs': {path: {'result_id': 'source', 'path': 'rows'}}}})['artifact']
    assert 'data_refs' not in created['data']
    assert not created['metadata']['validation']['issues']
    record = SimpleNamespace(type=kind, title=created['title'], payload=created['data'], extra_metadata=created['metadata'])
    workbook = load_workbook(io.BytesIO(render_artifact_export(record, 'xlsx').content))
    assert workbook.active.max_row == 1501
    assert workbook.active['A1501'].value == 'R1499'


def test_unresolved_references_or_empty_requested_sheets_cannot_pass_structural_checks():
    from services.agent.deliverables import new_artifact
    bad = new_artifact('workbook', 'Missing data', {'sheets': [{'name': 'Dataset', 'rows': []}],
        'data_refs': {'sheets.0.rows': {'result_id': 'unresolved'}}})
    assert bad['metadata']['validation']['status'] == 'needs_revision'
    assert len(bad['metadata']['validation']['issues']) == 2
    template = new_artifact('workbook', 'Blank template', {'sheets': [{'name': 'Empty by request', 'rows': [], 'empty_template': True}]})
    assert not template['metadata']['validation']['issues']


def test_conflicting_nested_and_top_level_references_never_save(workspace):
    context, tools = workspace
    result = tools['create_artifact'].invoke({'kind': 'table', 'title': 'Conflicting references',
        'data': {'data_refs': {'rows': {'result_id': 'source', 'path': 'rows'}}},
        'data_refs': {'rows': {'result_id': 'unavailable'}}})
    assert result['status'] == 'error' and not context.artifact_store


def test_revision_and_append_resolve_full_artifact_or_result_batches(workspace):
    context,tools=workspace
    table=tools['create_artifact'].invoke({'kind':'table','title':'All rows','data':{},'data_refs':{'rows':{'result_id':'source','path':'rows'}}})['artifact']
    original=copy.deepcopy(table)
    revised=tools['revise_artifact'].invoke({'artifact_id':table['id'],'expected_revision':1,'data':{},
        'data_refs':{'rows':{'artifact_id':table['id'],'path':'rows'}}})['artifact']
    appended=tools['append_artifact_rows'].invoke({'artifact_id':revised['id'],'expected_revision':2,
        'rows_ref':{'result_id':'source','path':'rows'}})['artifact']
    assert len(appended['data']['rows'])==3000
    assert appended['metadata']['input_receipts'][-1]['start_index']==1500
    assert appended['metadata']['input_receipts'][-1]['row_count']==1500
    assert appended['metadata']['input_receipts'][-1]['applied_in_revision']==3
    assert table==original


@pytest.mark.parametrize('reference',[{'result_id':'unavailable'},{'artifact_id':'outside-conversation'},
                                    {'result_id':'source','artifact_id':'ambiguous'},{'result_id':'source','path':'missing'}])
def test_unavailable_or_ambiguous_references_never_save(workspace,reference):
    context,tools=workspace
    result=tools['create_artifact'].invoke({'kind':'table','title':'Unavailable','data':{},'data_refs':{'rows':reference}})
    assert result['status']=='error' and context.artifact_store=={}


def test_append_requires_exactly_one_full_batch_source(workspace):
    context,tools=workspace
    table=tools['create_artifact'].invoke({'kind':'table','title':'Rows','data':{'rows':[{'value':1}]}})['artifact']
    for supplied in ({},{'rows':[],'rows_ref':{'result_id':'source','path':'rows'}}):
        result=tools['append_artifact_rows'].invoke({'artifact_id':table['id'],'expected_revision':1,**supplied})
        assert result['status']=='error'
    assert len(context.artifact_store)==1


@pytest.mark.parametrize('calculated', [False, True])
def test_copied_or_calculated_data_requires_review_when_its_artifact_input_changes(workspace, calculated):
    from services.agent.deliverables import dependency_metadata
    context, tools = workspace
    source = tools['create_artifact'].invoke({'kind': 'table', 'title': 'Source population',
        'data': {'rows': [{'amount': 2}]}})['artifact']
    reference = {'artifact_id': source['id'], 'path': 'rows'}
    if calculated:
        result = tools['calculate_artifact_data'].invoke({'expression': "[{'amount': row['amount'] * 2} for row in rows]",
            'input_refs': {'rows': reference}})
        reference = {'result_id': result['result_id'], 'path': 'value'}
    target = tools['create_artifact'].invoke({'kind': 'workbook', 'title': 'Derived workbook',
        'data': {'sheets': [{'name': 'Data'}]}, 'data_refs': {'sheets.0.rows': reference}})['artifact']
    revised = tools['revise_artifact'].invoke({'artifact_id': source['id'], 'expected_revision': 1,
        'data': {'rows': [{'amount': 3}]}})['artifact']
    review = dependency_metadata(target, context.artifact_store)
    assert review['validation']['status'] == 'needs_revision'
    item = review['dependency_review']['items'][0]
    assert item['dependency_kind'] == 'copied_input' and item['latest_artifact_id'] == revised['id']
    assert target['data']['sheets'][0]['rows'] == [{'amount': 4 if calculated else 2}]
    retained_data = copy.deepcopy(target['data'])
    retained_data['source_dependency_reviews'] = {source['id']: {'artifact_id': source['id'], 'dependency_review': {
        'decision': 'retain_pinned', 'latest_artifact_id': revised['id'], 'reason': 'Keep the original as-of population.'}}}
    retained = tools['revise_artifact'].invoke({'artifact_id': target['id'], 'expected_revision': 1,
        'data': retained_data})['artifact']
    assert dependency_metadata(retained, context.artifact_store)['dependency_review']['status'] == 'current'
    tools['revise_artifact'].invoke({'artifact_id': revised['id'], 'expected_revision': 2,
        'data': {'rows': [{'amount': 5}]}})
    assert dependency_metadata(retained, context.artifact_store)['validation']['status'] == 'needs_revision'
