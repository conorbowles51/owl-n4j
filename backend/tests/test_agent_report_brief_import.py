from io import BytesIO

import pytest

from services.agent.report_brief_import import preview_brief


def test_docx_reference_preserves_heading_table_and_final_paragraph():
    from docx import Document
    document = Document()
    document.add_heading("Requested subjects", level=1)
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Source"
    table.cell(0, 1).text = "Required analysis"
    document.add_paragraph("Retain this final instruction.")
    output = BytesIO()
    document.save(output)
    result = preview_brief("reference.docx", output.getvalue())
    assert "# Requested subjects" in result["text"]
    assert "Source | Required analysis" in result["text"]
    assert result["text"].endswith("Retain this final instruction.")
    assert result["warnings"]


def test_oversized_brief_refuses_instead_of_truncating():
    with pytest.raises(ValueError, match="no text was shortened"):
        preview_brief("brief.txt", b"x" * 250001)


def test_blank_pdf_page_is_not_silently_omitted():
    from pypdf import PdfWriter
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(output)
    with pytest.raises(ValueError, match="At least one page"):
        preview_brief("brief.pdf", output.getvalue())
