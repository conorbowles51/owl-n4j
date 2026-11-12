"""Bounded local extraction of an investigator's report brief or reference document."""
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, BadZipFile

MAX_BRIEF_BYTES = 10 * 1024 * 1024
MAX_BRIEF_CHARACTERS = 250000


def preview_brief(filename: str, content: bytes) -> dict:
    if len(content) > MAX_BRIEF_BYTES:
        raise ValueError("The brief exceeds 10 MiB. Select a smaller reference or read it from Evidence.")
    suffix = Path(filename).suffix.lower()
    warnings = []
    try:
        if suffix in {".txt", ".md"}:
            text = content.decode("utf-8-sig")
        elif suffix == ".docx":
            with ZipFile(BytesIO(content)) as package:
                if sum(info.file_size for info in package.infolist()) > 50 * 1024 * 1024:
                    raise ValueError("The document expands beyond the reference limit. Select a smaller reference.")
                if len(package.infolist()) > 3000:
                    raise ValueError("The document contains too many embedded parts.")
            from docx import Document
            from docx.oxml.ns import qn
            from docx.table import Table
            from docx.text.paragraph import Paragraph
            document = Document(BytesIO(content))
            parts = []
            for item in document.element.body:
                if item.tag == qn("w:p"):
                    paragraph = Paragraph(item, document)
                    style = paragraph.style.name if paragraph.style else ""
                    prefix = ""
                    if style.startswith("Heading ") and style[-1:].isdigit():
                        prefix = "#" * min(6, int(style[-1])) + " "
                    parts.append(prefix + paragraph.text)
                elif item.tag == qn("w:tbl"):
                    table = Table(item, document)
                    parts.extend(" | ".join(cell.text for cell in row.cells) for row in table.rows)
            text = "\n\n".join(parts)
            warnings.append("Paragraphs, headings and tables are included. Review image-only content and page layout in the original.")
        elif suffix == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                raise ValueError("Open an unencrypted copy of this reference first.")
            if len(reader.pages) > 500:
                raise ValueError("This reference exceeds 500 pages. Read the complete source through Evidence instead.")
            parts = [page.extract_text() or "" for page in reader.pages]
            if any(not part.strip() for part in parts):
                raise ValueError("At least one page has no readable text. Add the PDF to Evidence for reading before using it as a complete brief.")
            text = "\n\n".join(f"[Reference page {index + 1}]\n{part}" for index, part in enumerate(parts))
            warnings.append("This preview contains extracted text. Review figures and visual layout in the original PDF.")
        else:
            raise ValueError("Choose a TXT, Markdown, DOCX or text-readable PDF brief.")
    except (UnicodeError, BadZipFile) as exc:
        raise ValueError("The file could not be read as the selected document format.") from exc
    if not text.strip():
        raise ValueError("The reference has no readable text. Nothing was attached.")
    if len(text) > MAX_BRIEF_CHARACTERS:
        raise ValueError("The complete reference exceeds 250,000 characters. Read it through Evidence; no text was shortened or attached.")
    return {"filename": Path(filename).name, "text": text, "format": suffix.lstrip("."),
            "characters": len(text), "warnings": warnings}
