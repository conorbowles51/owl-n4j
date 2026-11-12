from services.agent.render_checks import inspect_export


def fixture():
    return {"id": "synthetic", "type": "report", "title": "Synthetic inspection", "metadata": {"revision": 2}, "data": {
        "sections": [{"id": "s", "heading": "Evidence", "content": "Complete **synthetic** records.", "embeds": [{
            "type": "table", "title": "Register", "data": {"rows": [{"record": f"RECORD-{i:04d}", "literal": "*Keep* [brackets] <angles>"} for i in range(35)]}}]}]}}


def test_inspection_reads_actual_export_and_all_source_values():
    checked = inspect_export(fixture(), min_pages=1, max_pages=15)
    assert checked["status"] == "render_checks_passed"
    assert checked["revision"] == 2
    assert checked["page_count"] >= 1 and checked["text_character_count"] > 100
    assert checked["data_coverage"]["source_rows"] == 35
    assert checked["data_coverage"]["source_cells"] == 70
    assert checked["data_coverage"]["missing_cells"] == 0
    assert checked["out_of_bounds_count"] == 0
    assert checked["visual_review"] == "not_established"


def test_requested_page_count_mismatch_requires_revision():
    checked = inspect_export(fixture(), min_pages=40)
    assert checked["status"] == "needs_revision"
    assert "minimum is 40" in checked["issues"][0]


def test_long_prose_matches_across_repeated_page_headers_and_footers():
    report = fixture()
    report["data"]["document_metadata"] = {"case_label": "Synthetic header", "classification": "Synthetic footer"}
    report["data"]["sections"][0]["content"] = "A continuous synthetic paragraph with every word retained. " * 400
    result = inspect_export(report)
    assert result["page_count"] > 3
    assert result["missing_content_locations"] == []


def test_markdown_table_continues_across_repeated_headers_without_false_missing_content():
    report = fixture()
    report['data']['sections'][0].pop('embeds')
    report['data']['sections'][0]['content'] = ('Records in source order.\n\n| Record | Detail |\n|---|---|\n' +
        '\n'.join(f'| SYNTHETIC-{i:04d} | Unique observation {i} retained in full. |' for i in range(160)) +
        '\n\n1. Retain the source.\n2. Verify the account.\n\nEnd of register.')
    checked = inspect_export(report)
    assert checked['page_count'] > 3
    assert checked['missing_content_locations'] == []


def test_missing_markdown_table_row_is_still_detected(monkeypatch):
    from copy import deepcopy
    from services.agent import exports
    from types import SimpleNamespace
    report = fixture()
    report['data']['sections'][0].pop('embeds')
    report['data']['sections'][0]['content'] = '| Record | Detail |\n|---|---|\n| SYNTHETIC-001 | First |\n| SYNTHETIC-002 | Second |'
    omitted = deepcopy(report)
    omitted['data']['sections'][0]['content'] = omitted['data']['sections'][0]['content'].replace('| SYNTHETIC-002 | Second |', '')
    output = exports.render_artifact_export(SimpleNamespace(type='report', title=report['title'],
        payload=omitted['data'], extra_metadata={}), 'pdf')
    monkeypatch.setattr(exports, 'render_artifact_export', lambda *args, **kwargs: output)
    checked = inspect_export(report)
    assert checked['status'] == 'needs_revision'
    assert checked['missing_content_locations'] == ['sections.0.content']
    assert 'SYNTHETIC-002' in checked['missing_content_examples'][0]['text']


def test_one_page_brief_keeps_five_requested_sections_without_forced_cover_or_contents():
    from services.agent.export_documents import document_docx, document_html
    from docx import Document
    import io
    report = fixture()
    report['title'] = 'Synthetic interview brief'
    report['data'] = {'document_layout': {'cover': 'inline', 'contents': False, 'density': 'compact'},
        'purpose': 'A concise, synthetic preparation note.',
        'sections': [{'id': f's{i}', 'heading': topic, 'content': 'Review the source record and ask the witness to explain the discrepancy. Preserve both accounts until corroborated.'}
                     for i, topic in enumerate(['Identity', 'Chronology', 'Connections', 'Conflicts', 'Questions'])]}
    result = inspect_export(report, min_pages=1, max_pages=1)
    assert result['status'] == 'render_checks_passed', result['issues']
    assert result['page_count'] == 1
    html = document_html(report['title'], report['data'])
    assert 'class="toc"' not in html and 'class="cover long"' not in html
    doc = Document(io.BytesIO(document_docx(report['title'], report['data'])))
    assert not any(p.text == 'Contents' for p in doc.paragraphs)
    assert all(any(p.text == s['heading'] for p in doc.paragraphs) for s in report['data']['sections'])


def test_letter_landscape_layout_applies_to_actual_pdf_and_word_page_dimensions():
    from services.agent.export_documents import document_docx
    from services.agent.exports import render_report_pdf
    from pypdf import PdfReader
    from docx import Document
    import io
    report = fixture()
    report['data']['document_layout'] = {'page_size': 'Letter', 'orientation': 'landscape'}
    pdf = PdfReader(io.BytesIO(render_report_pdf(title=report['title'], payload=report['data']).content))
    assert tuple(round(float(v)) for v in (pdf.pages[0].mediabox.width, pdf.pages[0].mediabox.height)) == (792, 612)
    doc = Document(io.BytesIO(document_docx(report['title'], report['data'])))
    assert round(doc.sections[0].page_width.inches) == 11
    assert abs(doc.sections[0].page_height.inches - 8.5) < .01
