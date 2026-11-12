import copy

import pytest

from services.agent.deliverables import new_artifact, revise_artifact, edit_sections, detect_dependencies, dependency_metadata


def report():
    return new_artifact('report','Nested report',{'sections':[
        {'id':'a','heading':'Parent A','content':'Parent prose','sections':[
            {'id':'a1','heading':'First child','content':'Original child','embeds':[{'artifact_id':'source','type':'table','data':{'rows':[{'value':1}]}}]},
            {'id':'a2','heading':'Second child','content':'Keep this child'}]},
        {'id':'b','heading':'Parent B','content':'Keep this parent','children':[{'id':'b1','heading':'Other child','content':'Other prose'}]}],
        'references':[{'section_id':'a1','label':'Cross-reference stays stable'}]})


def test_nested_replace_append_move_remove_preserve_ids_siblings_and_references():
    original=report(); snapshot=copy.deepcopy(original)
    revised=edit_sections(original,expected_revision=1,operations=[
        {'action':'replace','section_id':'a1','section':{'heading':'First child revised','content':'Corrected prose'}},
        {'action':'append','parent_section_id':'a','section':{'id':'a3','heading':'New child','content':'Added'}},
        {'action':'move','section_id':'a3','target_parent_section_id':'b','index':1},
        {'action':'remove','section_id':'a2'}])
    data=revised['data']
    assert data['sections'][0]['content']=='Parent prose'
    assert data['sections'][0]['sections'][0]['id']=='a1'
    assert data['sections'][0]['sections'][0]['embeds']==snapshot['data']['sections'][0]['sections'][0]['embeds']
    assert [s['id'] for s in data['sections'][1]['children']]==['b1','a3']
    assert data['sections'][1]['content']=='Keep this parent'
    assert data['references']==snapshot['data']['references']
    assert len(data['embedded_artifacts'])==1
    assert original==snapshot


def test_incremental_evidence_and_document_fields_preserve_all_chapters_and_other_claims():
    from services.agent.claim_validation import apply_claim_validation
    original = new_artifact('report', 'Long source review', {'sections': [
        {'id': 'a', 'heading': 'Subject A', 'content': 'The witness described the warehouse.'},
        {'id': 'b', 'heading': 'Subject B', 'content': 'The meeting was held on Tuesday.'}]},
        requirements=['Witness account'])
    sources = {'source': {'text': 'The witness described the warehouse. The meeting was held on Tuesday.'}}
    first = edit_sections(original, expected_revision=1, operations=[
        {'action': 'set_document', 'fields': {'purpose': 'Synthetic source review', 'document_layout': {'cover': 'inline', 'contents': False}}},
        {'action': 'add_evidence', 'claim_bindings': [{'id': 'a-source', 'section_id': 'a',
            'claim_text': 'The witness described the warehouse.', 'quote': 'The witness described the warehouse.', 'source': {'result_id': 'source'}}],
         'coverage': [{'item': 'Witness account', 'status': 'fulfilled', 'section_id': 'a', 'claim_ids': ['a-source']}]}])
    apply_claim_validation(first, sources, {})
    assert first['metadata']['validation']['issues'] == []
    second = edit_sections(first, expected_revision=2, operations=[{'action': 'add_evidence', 'claim_bindings': [
        {'id': 'b-source', 'section_id': 'b', 'claim_text': 'The meeting was held on Tuesday.', 'quote': 'The meeting was held on Tuesday.',
         'source': {'result_id': 'source'}}]}])
    apply_claim_validation(second, sources, {})
    assert second['metadata']['validation']['issues'] == []
    assert second['data']['sections'] == original['data']['sections']
    assert len(second['data']['claim_bindings']) == 2
    assert len(second['data']['coverage']) == 1
    assert 'coverage' not in original['data']


def test_evidence_record_update_is_stable_and_invalid_document_update_is_atomic():
    original = report()
    first = edit_sections(original, expected_revision=1, operations=[{'action': 'add_evidence', 'coverage': [
        {'item': 'Account', 'status': 'unresolved', 'reason': 'Not read yet'}]}])
    revised = edit_sections(first, expected_revision=2, operations=[{'action': 'add_evidence', 'coverage': [
        {'item': 'Account', 'status': 'fulfilled', 'section_id': 'a1', 'excerpt': 'Original child'}]}])
    assert len(revised['data']['coverage']) == 1
    assert revised['data']['coverage'][0]['status'] == 'fulfilled'
    with pytest.raises(ValueError, match='Document fields'):
        edit_sections(original, expected_revision=1, operations=[{'action': 'set_document', 'fields': {'sections': []}}])


def test_replacing_parent_prose_keeps_unmentioned_descendants():
    original=report()
    revised=edit_sections(original,expected_revision=1,operations=[{'action':'replace','section_id':'a','section':{'heading':'A','content':'Updated parent'}}])
    assert revised['data']['sections'][0]['sections']==original['data']['sections'][0]['sections']


def test_move_nested_section_to_root_and_same_parent_end():
    original=report()
    revised=edit_sections(original,expected_revision=1,operations=[
        {'action':'move','section_id':'a1','index':1},
        {'action':'move','section_id':'a2','target_parent_section_id':None,'index':2}])
    assert [s['id'] for s in revised['data']['sections']]==['a','b','a2']
    assert [s['id'] for s in revised['data']['sections'][0]['sections']]==['a1']


@pytest.mark.parametrize('operation',[
    {'action':'move','section_id':'a','target_parent_section_id':'a1','index':0},
    {'action':'move','section_id':'a','target_parent_section_id':'a','index':0},
    {'action':'append','parent_section_id':'missing','section':{'content':'Missing parent'}},
    {'action':'append','section':{'id':'a1','content':'Duplicate child ID'}},
])
def test_invalid_nested_edit_is_atomic(operation):
    original=report();snapshot=copy.deepcopy(original)
    with pytest.raises(ValueError):
        edit_sections(original,expected_revision=1,operations=[{'action':'replace','section_id':'a1','section':{'content':'Earlier operation'}},operation])
    assert original==snapshot


def test_child_alias_receives_stable_ids_on_creation():
    original=new_artifact('report','Aliases',{'sections':[{'heading':'A','children':[{'heading':'B','content':'Nested'}]}]})
    child_id=original['data']['sections'][0]['children'][0]['id']
    revised=edit_sections(original,expected_revision=1,operations=[{'action':'replace','section_id':child_id,'section':{'heading':'B','content':'Revised'}}])
    assert revised['data']['sections'][0]['children'][0]['id']==child_id


def test_explicit_empty_children_removes_descendants_and_empty_alias_does_not_hide_append():
    original=report()
    original['data']['sections'][1]['sections']=[]
    revised=edit_sections(original,expected_revision=1,operations=[
        {'action':'append','parent_section_id':'b','section':{'id':'b2','content':'Appended'}},
        {'action':'replace','section_id':'a','section':{'heading':'A','content':'No descendants','sections':[]}}])
    assert revised['data']['sections'][0]['sections']==[]
    assert [s['id'] for s in revised['data']['sections'][1]['children']]==['b1','b2']
    assert revised['metadata']['validation']['issues']==[]


def test_newer_dependency_flags_review_without_changing_pin_or_saved_metadata():
    source=new_artifact('table','Evidence register',{'rows':[{'value':1}]})
    data={'sections':[{'id':'s','heading':'Evidence','embeds':[{'artifact_id':source['id'],'type':'table','title':source['title'],
          'data':copy.deepcopy(source['data']),'metadata':copy.deepcopy(source['metadata'])}]}]}
    saved=new_artifact('report','Pinned report',data);snapshot=copy.deepcopy(saved)
    newer=revise_artifact(source,{'rows':[{'value':2}]},expected_revision=1)
    store={source['id']:source,newer['id']:newer,saved['id']:saved}
    metadata=dependency_metadata(saved,store)
    assert metadata['validation']['status']=='needs_revision'
    item=metadata['dependency_review']['items'][0]
    assert item['artifact_id']==source['id'] and item['latest_artifact_id']==newer['id']
    assert item['status']=='newer_revision_available'
    assert saved==snapshot
    kept=copy.deepcopy(data)
    kept['sections'][0]['embeds'][0]['dependency_review']={'decision':'retain_pinned','latest_artifact_id':newer['id'],'reason':'The report covers the earlier review date.'}
    revision=revise_artifact(saved,kept,expected_revision=1)
    assert detect_dependencies(revision,store)['items'][0]['status']=='retained_after_review'
    newest=revise_artifact(newer,{'rows':[{'value':3}]},expected_revision=2)
    store[newest['id']]=newest
    assert detect_dependencies(revision,store)['status']=='review_needed'
