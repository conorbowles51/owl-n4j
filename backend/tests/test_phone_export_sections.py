"""The Phone summary's PDF document: no database, so it runs where the phone template does not."""


def test_a_document_of_sections_builds_with_its_page_count():
    from services.phone.exports import pdf
    doc, missing = pdf.build_sections_html(title="Phone summary", case_name="C", generated="now", export_id="e",
                                           sections=[("Calls", ["one line"])])
    assert "one line" in doc and 'counter(pages)' in doc and not missing
