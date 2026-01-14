"""
PDF Ingestion module - handles .pdf file ingestion.

Uses pypdf to extract text from PDF files, then passes
to the core ingestion logic.
"""

from pathlib import Path
from typing import Dict, Optional, Callable

from pypdf import PdfReader

from ingestion import ingest_document
from logging_utils import log_progress, log_error, log_warning


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


def ingest_pdf_file(
    path: Path,
    case_id: str,
    log_callback: Optional[Callable[[str], None]] = None,
    profile_name: Optional[str] = None,
) -> Dict:
    """
    Ingest a single .pdf file into the knowledge graph.

    Args:
        path: Path to the .pdf file
        case_id: REQUIRED - The case ID to associate with all created entities/relationships
        log_callback: Optional callback function(message: str) to log progress messages
        profile_name: Name of the profile to use (e.g., 'fraud', 'generic')

    Returns:
        Ingestion result dict

    Raises:
        ValueError: If case_id is not provided
    """
    if not case_id:
        raise ValueError("case_id is required for PDF file ingestion")

    doc_name = path.name

    log_progress(f"Extracting text from PDF: {path}", log_callback)

    try:
        text = extract_text_from_pdf(path)
    except Exception as e:
        log_error(f"Failed to extract text from PDF: {e}", log_callback)
        return {"status": "error", "reason": str(e), "file": str(path)}

    if not text.strip():
        log_warning(f"No text extracted from PDF, skipping: {path}", log_callback)
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
        case_id=case_id,
        doc_metadata=doc_metadata,
        log_callback=log_callback,
        profile_name=profile_name,
    )
