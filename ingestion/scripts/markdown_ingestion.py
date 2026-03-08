"""
Markdown Ingestion module - handles .md file ingestion.

Uses markdown-it-py to parse Markdown and extract clean text content,
stripping markdown syntax while preserving document structure.
"""

import re
from pathlib import Path
from typing import Dict, Optional, Callable

from ingestion import ingest_document
from logging_utils import log_progress, log_warning


def extract_text_from_markdown(path: Path) -> str:
    """
    Extract clean text from a Markdown file using markdown-it-py.

    Parses markdown to HTML, then strips HTML tags to produce
    clean text. Preserves document structure (paragraphs, headings)
    as plain text with natural line breaks.

    Args:
        path: Path to the Markdown file

    Returns:
        Extracted plain text string
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = path.read_text(encoding="latin-1")

    if not raw.strip():
        return ""

    try:
        from markdown_it import MarkdownIt

        md = MarkdownIt()
        # Render markdown to HTML, then strip tags
        html = md.render(raw)

        # Strip HTML tags to get plain text
        text = re.sub(r"<[^>]+>", "", html)
    except ImportError:
        # Fallback: strip common markdown syntax manually
        text = raw
        # Remove header markers
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        # Remove bold/italic markers
        text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
        text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
        # Convert links to just text: [text](url) -> text
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        # Remove image markers: ![alt](url) -> alt
        text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
        # Remove inline code backticks
        text = re.sub(r"`([^`]+)`", r"\1", text)
        # Remove code block markers
        text = re.sub(r"```[^\n]*\n", "", text)
        # Remove horizontal rules
        text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
        # Remove blockquote markers
        text = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)

    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def ingest_markdown_file(
    path: Path,
    case_id: str,
    log_callback: Optional[Callable[[str], None]] = None,
    profile_name: Optional[str] = None,
) -> Dict:
    """
    Ingest a single .md file into the knowledge graph.

    Args:
        path: Path to the Markdown file
        case_id: REQUIRED - The case ID to associate with all created entities/relationships
        log_callback: Optional callback function(message: str) to log progress messages
        profile_name: Name of the profile to use (e.g., 'fraud', 'generic')

    Returns:
        Ingestion result dict

    Raises:
        ValueError: If case_id is not provided
    """
    if not case_id:
        raise ValueError("case_id is required for Markdown file ingestion")

    doc_name = path.name

    log_progress(f"Reading Markdown file: {path}", log_callback)

    text = extract_text_from_markdown(path)

    if not text.strip():
        log_warning(f"Markdown file is empty or contains no text content, skipping: {path}", log_callback)
        return {"status": "skipped", "reason": "empty", "file": str(path)}

    log_progress(f"Extracted {len(text):,} characters from Markdown", log_callback)

    doc_metadata = {
        "filename": path.name,
        "full_path": str(path.resolve()),
        "source_type": "markdown",
    }

    return ingest_document(
        text=text,
        doc_name=doc_name,
        case_id=case_id,
        doc_metadata=doc_metadata,
        log_callback=log_callback,
        profile_name=profile_name,
    )
