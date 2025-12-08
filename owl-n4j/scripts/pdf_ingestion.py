"""
PDF Ingestion module - handles .pdf file ingestion.

Uses pypdf to extract text from PDF files, then passes
to the core ingestion logic.
"""

from pathlib import Path
from typing import Dict

from pypdf import PdfReader

from ingestion import ingest_document


def extract_text_from_pdf(path: Path) -> str:
    """
    Extract text from a PDF file.

    Concatenates text from all pages with page separators.

    Args:
        path: Path to the PDF file

    Returns:
        Extracted text content
    """
    reader = PdfReader(str(path))
    chunks = []

    for i, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""
        if page_text.strip():
            chunks.append(f"--- Page {i + 1} ---\n{page_text}")

    return "\n\n".join(chunks)


def ingest_pdf_file(path: Path) -> Dict:
    """
    Ingest a single .pdf file into the knowledge graph.

    Args:
        path: Path to the .pdf file

    Returns:
        Ingestion result dict
    """
    doc_name = path.name

    print(f"Extracting text from PDF: {path}")

    try:
        text = extract_text_from_pdf(path)
    except Exception as e:
        print(f"ERROR: Failed to extract text from PDF: {e}")
        return {"status": "error", "reason": str(e), "file": str(path)}

    if not text.strip():
        print(f"WARNING: No text extracted from PDF, skipping: {path}")
        return {"status": "skipped", "reason": "no_text", "file": str(path)}

    doc_metadata = {
        "filename": path.name,
        "full_path": str(path.resolve()),
        "source_type": "pdf",
        "page_count": len(PdfReader(str(path)).pages),
    }

    return ingest_document(
        text=text,
        doc_name=doc_name,
        doc_metadata=doc_metadata,
    )
