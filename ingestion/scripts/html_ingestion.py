"""
HTML Ingestion module - handles .html and .htm file ingestion.

Uses lxml to parse HTML and extract clean text content,
stripping scripts, styles, and HTML tags before ingestion.
"""

import re
from pathlib import Path
from typing import Dict, Optional, Callable

from ingestion import ingest_document
from logging_utils import log_progress, log_warning


def extract_text_from_html(path: Path) -> str:
    """
    Extract clean text from an HTML file using lxml.

    Strips <script>, <style>, and <noscript> elements,
    then extracts visible text content.

    Args:
        path: Path to the HTML file

    Returns:
        Extracted plain text string
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = path.read_text(encoding="latin-1")

    if not raw.strip():
        return ""

    text = _extract_html_text(raw)
    return text


def _extract_html_text(raw: str) -> str:
    """Extract clean text from a raw HTML string."""
    try:
        from lxml import html as lxml_html
        from lxml import etree

        doc = lxml_html.fromstring(raw)

        # Collect elements to remove first, then remove
        # (can't modify tree while iterating)
        to_remove = list(doc.iter("script", "style", "noscript", "head"))
        to_remove.extend(doc.iter(etree.Comment))
        for el in to_remove:
            if el.getparent() is not None:
                el.getparent().remove(el)

        text = doc.text_content()
    except Exception:
        # Fallback: strip tags with regex if lxml parsing fails
        text = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<noscript[^>]*>.*?</noscript>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)

    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def ingest_html_file(
    path: Path,
    case_id: str,
    log_callback: Optional[Callable[[str], None]] = None,
    profile_name: Optional[str] = None,
) -> Dict:
    """
    Ingest a single .html/.htm file into the knowledge graph.

    Args:
        path: Path to the HTML file
        case_id: REQUIRED - The case ID to associate with all created entities/relationships
        log_callback: Optional callback function(message: str) to log progress messages
        profile_name: Name of the profile to use (e.g., 'fraud', 'generic')

    Returns:
        Ingestion result dict

    Raises:
        ValueError: If case_id is not provided
    """
    if not case_id:
        raise ValueError("case_id is required for HTML file ingestion")

    doc_name = path.name

    log_progress(f"Reading HTML file: {path}", log_callback)

    text = extract_text_from_html(path)

    if not text.strip():
        log_warning(f"HTML file is empty or contains no text content, skipping: {path}", log_callback)
        return {"status": "skipped", "reason": "empty", "file": str(path)}

    log_progress(f"Extracted {len(text):,} characters from HTML", log_callback)

    doc_metadata = {
        "filename": path.name,
        "full_path": str(path.resolve()),
        "source_type": "html",
    }

    return ingest_document(
        text=text,
        doc_name=doc_name,
        case_id=case_id,
        doc_metadata=doc_metadata,
        log_callback=log_callback,
        profile_name=profile_name,
    )
