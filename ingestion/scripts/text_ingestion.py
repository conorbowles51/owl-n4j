"""
Text Ingestion module - handles .txt file ingestion.

Provides a simple wrapper around the core ingestion logic
specifically for plain text files.
"""

from pathlib import Path
from typing import Dict, Optional, Callable

from ingestion import ingest_document
from logging_utils import log_progress, log_warning


def ingest_text_file(
    path: Path,
    log_callback: Optional[Callable[[str], None]] = None,
    profile_name: Optional[str] = None,
) -> Dict:
    """
    Ingest a single .txt file into the knowledge graph.

    Args:
        path: Path to the .txt file
        log_callback: Optional callback function(message: str) to log progress messages
        profile_name: Name of the profile to use (e.g., 'fraud', 'generic')

    Returns:
        Ingestion result dict
    """
    doc_name = path.name

    log_progress(f"Reading text file: {path}", log_callback)

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Try with latin-1 as fallback
        text = path.read_text(encoding="latin-1")

    if not text.strip():
        log_warning(f"Text file is empty, skipping: {path}", log_callback)
        return {"status": "skipped", "reason": "empty", "file": str(path)}

    doc_metadata = {
        "filename": path.name,
        "full_path": str(path.resolve()),
        "source_type": "text",
    }

    return ingest_document(
        text=text,
        doc_name=doc_name,
        doc_metadata=doc_metadata,
        log_callback=log_callback,
        profile_name=profile_name,
    )
