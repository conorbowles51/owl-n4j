"""Acceptance checks on exported bytes: complete datasets, actual visuals, safe portable output."""
import io
import zipfile
from types import SimpleNamespace

import pytest

from services.agent.exports import render_artifact_export,render_report_pdf,render_report_docx
from services.agent.export_documents import document_html,offline_fetcher


def artifact(kind,payload,title='Synthetic investigation'):
    return SimpleNamespace(type=kind,title=title,payload=payload,extra_metadata={})


def report_fixture(count=1500):
    rows=[{'record':f'RECORD-{i:04d}','date':'2026-11-11','party':f'Synthetic party {i%25:02d}',
           'amount':i+0.25,'source':f'Synthetic source page {i//20+1}'} for i in range(count)]
    return {'title':'Synthetic investigation review','purpose':'A complete review of the synthetic evidence register.',
            'document_metadata':{'case_label':'Synthetic case','classification':'Test fixture','version':'1'},
            'sections':[{'heading':'Scope and method','content':'This report contains invented evidence only. No client records are used.'},
                {'heading':'Financial exhibit','content':'The chart and its source values agree.', 'embeds':[{'type':'chart','title':'Category comparison','data':{'chart_type':'bar','x_key':'category','y_keys':['amount'],'rows':[{'category':'Services','amount':45},{'category':'Supplies','amount':60}]}}]},
                {'heading':'Relationships','content':'The network records explicit synthetic links.', 'embeds':[{'type':'graph','title':'Entity network','data':{'nodes':[{'id':'a','name':'Synthetic Person','type':'Person'},{'id':'b','name':'Synthetic Company','type':'Organization'}],'links':[{'source':'a','target':'b','type':'DIRECTOR_OF'}]}}]},
                {'heading':'Complete record appendix','content':'All records follow, including the final record.', 'embeds':[{'type':'table','title':'Evidence register','data':{'rows':rows}}]}],
            'sources':[{'label':'Synthetic source record','url':'doc://synthetic/1','locator':'Page 1'}]}


def test_saved_source_handles_become_readable_citations_without_rewriting_the_report():
    from uuid import uuid4
    from services.agent.source_presentation import present_sources
    identity, handle = str(uuid4()), 'res_synthetic_source'
    payload = {'sections': [{'heading': 'Summary', 'content': 'Synthetic observations.'}],
               'sources': [handle, 'Investigator interview', {'label': 'Authored reference', 'url': 'https://example.test/source'}]}
    results = {handle: {'evidence_id': identity, 'document_name': 'Synthetic source.pdf', 'pages': [
        {'page_number': n, 'location_kind': 'source_page'} for n in (1, 2, 4)]}}
    view = present_sources(payload, results)
    assert view['sources'][0] == {'result_id': handle, 'label': 'Synthetic source.pdf',
        'url': f'doc://{identity}', 'locator': 'Pages 1–2, 4'}
    assert view['sources'][1:] == payload['sources'][1:]
    record = artifact('report', payload)
    record.run = SimpleNamespace(extra_metadata={'execution_checkpoint': {'result_store': results}})
    html = render_artifact_export(record, 'html').content.decode()
    assert 'Synthetic source.pdf' in html and f'doc://{identity}' in html and 'Pages 1–2, 4' in html
    assert handle not in html and payload['sources'][0] == handle
    with zipfile.ZipFile(io.BytesIO(render_artifact_export(record, 'docx').content)) as archive:
        xml = archive.read('word/document.xml').decode()
        assert 'Synthetic source.pdf' in xml and handle not in xml


def test_missing_source_handles_stay_visible_and_text_parts_are_not_called_pages():
    from uuid import uuid4
    from services.agent.source_presentation import present_sources
    payload = {'sources': ['res_missing', {'result_id': 'res_parts', 'label': 'Investigator label'}]}
    result = present_sources(payload, {'res_parts': {'evidence_id': str(uuid4()), 'document_name': 'Notes.docx',
        'pages': [{'page_number': 2, 'location_kind': 'text_part'}]}})
    assert result['sources'][0]['label'] == 'Source reference unavailable'
    assert 'confirm its citation' in result['sources'][0]['locator']
    assert result['sources'][1]['label'] == 'Investigator label'
    assert result['sources'][1]['locator'] == 'Text part 2'


def test_pdf_preserves_1500_records_and_renders_paged_brand():
    import fitz
    pdf=render_report_pdf(title='Synthetic report',payload=report_fixture())
    with fitz.open(stream=pdf.content,filetype='pdf') as doc:
        text='\n'.join(p.get_text() for p in doc)
        assert len(doc)>=40
        for i in range(1500):assert f'RECORD-{i:04d}' in text
        assert 'Synthetic source record' in text
        assert 'Synthetic case' in text
        assert len(doc.get_toc())>=4
        assert all(p.rect.contains(b[:4]) for p in doc for b in p.get_text('blocks') if b[4].strip())


def test_authored_record_lines_remain_separate_in_pdf_and_word():
    import fitz
    from docx import Document
    payload = {'document_layout': {'cover': 'inline', 'contents': False},
        'sections': [{'heading': 'Source records', 'content': 'RECORD-A First observation.\nRECORD-B Second observation.'}]}
    pdf = render_report_pdf(title='Synthetic record register', payload=payload)
    with fitz.open(stream=pdf.content, filetype='pdf') as doc:
        positions = {word[4]: word[1] for page in doc for word in page.get_text('words')}
        assert positions['RECORD-B'] > positions['RECORD-A'] + 5
    word = Document(io.BytesIO(render_report_docx(title='Synthetic record register', payload=payload).content))
    assert any('RECORD-A First observation.\nRECORD-B Second observation.' in p.text for p in word.paragraphs)


def test_docx_preserves_all_columns_citations_visuals_and_embedded_fonts():
    payload=report_fixture(45)
    payload['sections'][-1]['embeds'][0]['data']['rows'][0].update({f'column_{i}':f'VALUE-{i}' for i in range(12)})
    payload['sections'][0]['content']='A **supported** statement [Source](doc://fixture/19).'
    docx=render_report_docx(title='Report',payload=payload)
    with zipfile.ZipFile(io.BytesIO(docx.content)) as z:
        xml=z.read('word/document.xml').decode()
        for i in range(45):assert f'RECORD-{i:04d}' in xml
        for i in range(12):assert f'VALUE-{i}' in xml
        assert len([n for n in z.namelist() if n.startswith('word/media/')])>=3
        assert len([n for n in z.namelist() if n.endswith('.odttf')])==3
        assert 'doc://fixture/19' in z.read('word/_rels/document.xml.rels').decode()
        assert '<w:tblHeader' in xml


def test_unavailable_exhibit_fails_instead_of_claiming_a_complete_report():
    payload={'sections':[{'heading':'Missing','content':'A missing exhibit','embeds':[{'type':'table','title':'Required table','available':False}]}]}
    with pytest.raises(ValueError,match='unavailable'):render_report_pdf(title='Report',payload=payload)


def test_no_network_or_file_fetch_in_pdf_renderer():
    for url in ('https://example.test/private','file:///etc/passwd'):
        with pytest.raises(ValueError):offline_fetcher(url)
    page=document_html('Report',{'sections':[{'heading':'Safe','content':'<script>alert(1)</script> ![bad](file:///secret) [bad](javascript:alert(1))'}]})
    assert '<script>alert' not in page
    assert 'src="file:' not in page
    assert 'href="javascript:' not in page


@pytest.mark.parametrize('kind,data',[
    ('graph',{'nodes':[{'id':'a','name':'A'},{'id':'b','name':'B'}],'links':[{'source':'a','target':'b'}]}),
    ('diagram',{'nodes':[{'id':'a','name':'A'}]}),
    ('map',{'locations':[{'latitude':53.3,'longitude':-6.2,'name':'Synthetic place'}]}),
    ('chart',{'chart_type':'line','x_key':'period','y_keys':['amount'],'rows':[{'period':'A','amount':1},{'period':'B','amount':3}]}),
])
def test_real_vector_and_raster_exports(kind,data):
    svg=render_artifact_export(artifact(kind,data),'svg')
    png=render_artifact_export(artifact(kind,data),'png')
    assert b'<svg' in svg.content
    assert png.content.startswith(b'\x89PNG')


def test_workbook_preserves_sheet_data_and_explicit_formulas():
    from openpyxl import load_workbook
    payload={'sheets':[{'name':'Source','rows':[{'label':'=1+2','amount':12},{'label':'B','amount':9}]},
                       {'name':'Calculation','rows':[{'description':'Total','value':None}], 'formulas':[{'cell':'B2','formula':"=SUM(Source!B2:B3)"}]}]}
    result=render_artifact_export(artifact('workbook',payload),'xlsx')
    wb=load_workbook(io.BytesIO(result.content),data_only=False)
    assert wb['Source']['A2'].value=='=1+2'
    assert wb['Source']['A2'].data_type=='s'
    assert wb['Calculation']['B2'].value=='=SUM(Source!B2:B3)'
    assert wb['Source'].max_row==3


def test_workbook_external_formula_is_refused():
    with pytest.raises(ValueError,match='External'):
        render_artifact_export(artifact('workbook',{'sheets':[{'name':'Unsafe','formulas':[{'cell':'A1','formula':'=WEBSERVICE("https://example.test")'}]}]}),'xlsx')


def test_presentation_retains_content_and_visuals():
    from pptx import Presentation
    payload={'slides':[{'title':'Evidence','content':'FIRST '+('Complete synthetic analysis. '*150)+' LAST',
                       'embeds':[report_fixture(1)['sections'][1]['embeds'][0]]}]}
    result=render_artifact_export(artifact('presentation',payload),'pptx')
    prs=Presentation(io.BytesIO(result.content))
    text=' '.join(shape.text for slide in prs.slides for shape in slide.shapes if shape.has_text_frame)
    assert 'FIRST' in text and 'LAST' in text
    assert len(prs.slides)>3
    assert any(shape.shape_type==13 for slide in prs.slides for shape in slide.shapes)


def test_interactive_download_is_offline_and_isolated():
    result=render_artifact_export(artifact('interactive',{'html':'<button onclick="this.textContent=42">Compute</button><script>fetch("https://example.test")</script>','static_content':'A scenario tool.'}),'html')
    text=result.content.decode()
    assert 'sandbox=""' in text
    assert 'allow-same-origin' not in text
    assert "connect-src &#x27;none&#x27;" in text
    assert 'srcdoc=' in text


def test_interactive_fragment_cannot_navigate_or_run_its_own_code():
    import html,re
    malicious='<meta http-equiv="refresh" content="0;url=https://example.test"><img src=x onerror="location.href=\'https://example.test\'"><a href="https://example.test">Go</a><script>location="https://example.test"</script>'
    text=render_artifact_export(artifact('interactive',{'html':malicious}),'html').content.decode()
    source=html.unescape(re.search(r'srcdoc="([^"]*)"',text).group(1))
    assert '<script' not in source and 'onerror' not in source and 'refresh' not in source
    assert 'href="https://example.test"' not in source


def test_scenario_static_and_dynamic_views_share_saved_inputs():
    from services.agent.export_office import scenario_values
    payload={'interactions':{'inputs':[{'key':'amount','label':'Amount','value':100},{'key':'fraction','label':'Share','value':0.25}],
                             'calculations':[{'key':'total','label':'Total','expression':'amount * (1 - fraction)'}]}}
    assert scenario_values(payload)[0]['value']==75
    page=render_artifact_export(artifact('interactive',payload),'html').content.decode()
    assert 'nonce="loupe-controls"' in page and 'eval(' not in page
    pdf=render_artifact_export(artifact('interactive',payload),'pdf')
    import pymupdf
    with pymupdf.open(stream=pdf.content,filetype='pdf') as doc:
        text=''.join(p.get_text() for p in doc)
        assert '75' in text and 'Saved assumptions' in text


def test_scenario_rejects_code_and_unknown_inputs():
    from services.agent.export_office import scenario_values
    for expression in ['__import__("os").getcwd()','value.x','2 ** 1000000','unknown + 2']:
        with pytest.raises(ValueError):scenario_values({'interactions':{'calculations':[{'expression':expression}]}})


def test_nested_report_sections_are_not_dropped():
    payload={'sections':[{'heading':'Parent','content':'Top','children':[{'heading':'Child','content':'NESTED-MARKER'}]}]}
    assert 'NESTED-MARKER' in document_html('Nested',payload)


def test_presentation_pdf_uses_same_four_slide_composition_and_widescreen_dimensions():
    import pymupdf
    from pptx import Presentation
    payload={'purpose':'Synthetic investigator briefing.','presentation_layout':{'cover':True},'slides':[
        {'title':'Findings','content':'UNIQUE-NARRATIVE: the invented evidence supports further review.'},
        {'title':'Evidence','content':'The source values follow.','embeds':[report_fixture(1)['sections'][1]['embeds'][0]]}]}
    pptx=render_artifact_export(artifact('presentation',payload),'pptx')
    pdf=render_artifact_export(artifact('presentation',payload),'pdf')
    prs=Presentation(io.BytesIO(pptx.content))
    with pymupdf.open(stream=pdf.content,filetype='pdf') as doc:
        assert len(doc)==len(prs.slides)==4
        assert all(abs(p.rect.width/p.rect.height-16/9)<.001 for p in doc)
        assert 'UNIQUE-NARRATIVE' in ''.join(p.get_text() for p in doc)
        assert 'Category comparison' in doc[3].get_text()
        assert len(doc[3].get_images())>=2  # Brand and actual chart.
        assert all(p.rect.contains(b[:4]) for p in doc for b in p.get_text('blocks') if b[4].strip())


def test_presentation_pdf_preserves_long_table_cells_with_matching_slide_pagination():
    import pymupdf
    from pptx import Presentation
    rows=[{'record':f'ROW-{i:03d}','description':'Complete synthetic evidence detail. '*14} for i in range(20)]
    payload={'slides':[{'title':'Register','embeds':[{'type':'table','data':{'rows':rows}}]}]}
    deck=render_artifact_export(artifact('presentation',payload),'pptx')
    pdf=render_artifact_export(artifact('presentation',payload),'pdf')
    with pymupdf.open(stream=pdf.content,filetype='pdf') as doc:
        text=''.join(p.get_text() for p in doc)
        assert len(doc)==len(Presentation(io.BytesIO(deck.content)).slides)
        assert all(f'ROW-{i:03d}' in text for i in range(20))


def test_export_rejects_unavailable_glyphs_instead_of_silent_boxes():
    for kind,extension,payload in [('report','pdf',{'sections':[{'heading':'Text','content':'Unsupported \U0001f9ec'}]}),
                                 ('report','docx',{'sections':[{'heading':'Text','content':'Unsupported \U0001f9ec'}]}),
                                 ('presentation','pptx',{'slides':[{'title':'Unsupported \U0001f9ec'}]})]:
        with pytest.raises(ValueError,match='lack characters'):
            render_artifact_export(artifact(kind,payload),extension)


@pytest.mark.parametrize('extension',['pdf','docx','html','pptx'])
def test_unfetched_markdown_images_are_not_silently_omitted(extension):
    payload={'sections':[{'heading':'Image','content':'![Required photograph](https://example.test/evidence.png)'}]}
    with pytest.raises(ValueError,match='image resources'):
        render_artifact_export(artifact('report',payload),extension)
def test_model_map_points_render_export_and_preserve_assumption_note():
    from services.agent.deliverables import validate_artifact
    from services.agent.export_visuals import visual_svg
    from services.agent.exports import _rows_for_artifact
    payload = {'points': [{'label': 'Synthetic A', 'lat': 53.3, 'lng': -6.2},
                          {'label': 'Synthetic B', 'lat': 53.4, 'lng': -6.3}],
               'note': 'Illustrative assumptions only; these are not source observations.'}
    assert validate_artifact('map', payload)['issues'] == []
    svg = visual_svg('map', payload, 'Synthetic locations')
    assert 'Synthetic A' in svg and 'Illustrative assumptions' in svg
    rows = _rows_for_artifact('map', payload)
    assert [(r['latitude'], r['longitude']) for r in rows] == [(53.3, -6.2), (53.4, -6.3)]
    assert validate_artifact('map', {})['issues']
    payload['points'][0]['lat'] = 120
    assert validate_artifact('map', payload)['issues']


def test_four_authored_slides_export_as_four_slides_without_an_unrequested_cover():
    from pptx import Presentation
    import pymupdf
    payload = {'slides': [{'title': title, 'content': 'Synthetic acceptance detail.'}
                         for title in ('Dataset', 'Method', 'Result', 'Limits')]}
    deck = render_artifact_export(artifact('presentation', payload), 'pptx')
    pdf = render_artifact_export(artifact('presentation', payload), 'pdf')
    assert len(Presentation(io.BytesIO(deck.content)).slides) == 4
    with pymupdf.open(stream=pdf.content, filetype='pdf') as document:
        assert len(document) == 4
        assert all(title in document[i].get_text() for i, title in enumerate(('Dataset', 'Method', 'Result', 'Limits')))


def test_readable_interactive_alternative_does_not_print_html_paragraph_wrappers():
    from services.agent.export_office import interactive_html
    payload = {'static_content': '<p>Synthetic assumptions only.</p>',
               'interactions': {'inputs': [{'key': 'quantity', 'value': 2}],
                                'calculations': [{'key': 'total', 'expression': 'quantity * 3'}]}}
    rendered = interactive_html('Example', payload)
    assert 'Synthetic assumptions only.' in rendered
    assert '&lt;p&gt;Synthetic' not in rendered
    assert 'quantity * 3' in rendered
