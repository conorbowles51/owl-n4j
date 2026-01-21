"""
Word Ingestion module - handles .docx file ingestion.

Uses python-docx to extract text from Word documents, then passes
it to the core ingestion logic.
"""

from pathlib import Path
from typing import Dict, Optional, Callable, Tuple

from docx import Document

from ingestion import ingest_document
from logging_utils import log_progress, log_error, log_warning


def extract_text_from_docx(path: Path) -> Tuple[str, int]:
    """
    Extract text from a Word .docx file.

    Concatenates non-empty paragraph text with newlines.

    Args:
        path: Path to the .docx file

    Returns:
        Tuple of (extracted text, paragraph count)
    """
    document = Document(str(path))
    paragraphs = document.paragraphs
    chunks = [p.text for p in paragraphs if p.text and p.text.strip()]
    return "\n".join(chunks), len(paragraphs)


def ingest_word_file(
    path: Path,
    case_id: str,
    log_callback: Optional[Callable[[str], None]] = None,
    profile_name: Optional[str] = None,
) -> Dict:
    """
    Ingest a single .docx file into the knowledge graph.

    Args:
        path: Path to the .docx file
        case_id: REQUIRED - The case ID to associate with all created entities/relationships
        log_callback: Optional callback function(message: str) to log progress messages
        profile_name: Name of the profile to use (e.g., 'fraud', 'generic')

    Returns:
        Ingestion result dict

    Raises:
        ValueError: If case_id is not provided
    """
    if not case_id:
        raise ValueError("case_id is required for Word file ingestion")

    doc_name = path.name

    log_progress(f"Extracting text from Word document: {path}", log_callback)

    try:
        text, paragraph_count = extract_text_from_docx(path)
    except Exception as e:
        log_error(f"Failed to extract text from Word document: {e}", log_callback)
        return {"status": "error", "reason": str(e), "file": str(path)}

    if not text.strip():
        log_warning(f"No text extracted from Word document, skipping: {path}", log_callback)
        return {"status": "skipped", "reason": "no_text", "file": str(path)}

    doc_metadata = {
        "filename": path.name,
        "full_path": str(path.resolve()),
        "source_type": "word",
        "paragraph_count": paragraph_count,
    }

    return ingest_document(
        text=text,
        doc_name=doc_name,
        case_id=case_id,
        doc_metadata=doc_metadata,
        log_callback=log_callback,
        profile_name=profile_name,
    )
