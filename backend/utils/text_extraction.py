"""
Text extraction utility for extracting text from various file types.
"""

import re
from pathlib import Path
from typing import Optional


def _extract_html_text(raw: str) -> str:
    """Extract clean text from raw HTML string using lxml."""
    try:
        from lxml import html as lxml_html
        from lxml import etree

        doc = lxml_html.fromstring(raw)
        to_remove = list(doc.iter("script", "style", "noscript", "head"))
        to_remove.extend(doc.iter(etree.Comment))
        for el in to_remove:
            if el.getparent() is not None:
                el.getparent().remove(el)
        text = doc.text_content()
    except Exception:
        # Fallback: strip tags with regex
        text = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<noscript[^>]*>.*?</noscript>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def _extract_markdown_text(raw: str) -> str:
    """Extract clean text from raw Markdown string."""
    try:
        from markdown_it import MarkdownIt
        md = MarkdownIt()
        html = md.render(raw)
        text = re.sub(r"<[^>]+>", "", html)
    except ImportError:
        # Fallback: strip common markdown syntax
        text = raw
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
        text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = re.sub(r"```[^\n]*\n", "", text)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def extract_text_from_file(file_path: Path) -> Optional[str]:
    """
    Extract text from a file based on its extension.

    Args:
        file_path: Path to the file

    Returns:
        Extracted text or None if extraction fails
    """
    if not file_path.exists():
        return None

    extension = file_path.suffix.lower()

    try:
        if extension == '.txt':
            # Plain text file
            try:
                return file_path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                return file_path.read_text(encoding='latin-1')

        elif extension == '.pdf':
            # PDF file
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(file_path))
                chunks = []
                for i, page in enumerate(reader.pages):
                    page_text = page.extract_text() or ""
                    if page_text.strip():
                        chunks.append(page_text)
                return "\n\n".join(chunks)
            except ImportError:
                print("[Text Extraction] pypdf not available for PDF extraction")
                return None
            except Exception as e:
                print(f"[Text Extraction] Failed to extract PDF text: {e}")
                return None

        elif extension in ['.doc', '.docx']:
            # Word document
            try:
                from docx import Document
                doc = Document(str(file_path))
                return "\n".join([para.text for para in doc.paragraphs])
            except ImportError:
                print("[Text Extraction] python-docx not available for Word extraction")
                return None
            except Exception as e:
                print(f"[Text Extraction] Failed to extract Word text: {e}")
                return None

        elif extension in ['.html', '.htm']:
            # HTML file
            try:
                try:
                    raw = file_path.read_text(encoding='utf-8')
                except UnicodeDecodeError:
                    raw = file_path.read_text(encoding='latin-1')
                return _extract_html_text(raw) or None
            except Exception as e:
                print(f"[Text Extraction] Failed to extract HTML text: {e}")
                return None

        elif extension == '.md':
            # Markdown file
            try:
                try:
                    raw = file_path.read_text(encoding='utf-8')
                except UnicodeDecodeError:
                    raw = file_path.read_text(encoding='latin-1')
                return _extract_markdown_text(raw) or None
            except Exception as e:
                print(f"[Text Extraction] Failed to extract Markdown text: {e}")
                return None

        else:
            # Try to read as text for other file types
            try:
                return file_path.read_text(encoding='utf-8')
            except (UnicodeDecodeError, Exception):
                return None

    except Exception as e:
        print(f"[Text Extraction] Error extracting text from {file_path}: {e}")
        return None
