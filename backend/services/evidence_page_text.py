"""A document's extracted text by page, and a passage of it kept as a citation (lx-textbench).

The workbench shows a page of the original beside the text Loupe holds for it, so the text is shown exactly as stored,
with what read it. A reading is never presented as more than it is: each page names its reader, and a reader that is
software or a model is marked ``machine_read``; a page with no text says why instead of showing blank (02 rule 1).

``source_locations`` hold each section's character range in the stored text. A PDF has one range per page; other files
have sheets, tables or one body, split here into parts of at most ``PART_CHARACTERS`` so a long transcript still pages.

A passage (``evidence_passage`` link target) is one range of the stored text of one document:
``<file id>:<text version>:<start>:<end>``. Its anchor is written by the server from the stored text (``passage_anchor``),
so a quote cannot differ from what the document held when it was taken and always carries its reader's label. Text is
replaced when a document is read again, so ``locate_passage`` says whether the quote is still there.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from postgres.models.evidence import EvidenceDocumentText, EvidenceFile

PART_CHARACTERS = 20_000
MAX_PAGE_LIMIT = 50
QUOTE_MAX_CHARACTERS = 5_000
VERSION_CHARACTERS = 16
# location kinds that hold text the file itself carries (evidence-engine build_canonical_document_text)
FILE_TEXT_KINDS = ("body", "table", "sheet", "text", "html", "markdown", "eml")
OCR_TIMEOUT_STATUS = "timeout"  # evidence-engine pdf_extraction.OCR_TIMEOUT_STATUS
_LONG = re.compile(r"[^\s]{0,40}\s+$")


class PassageError(ValueError):
    """A passage was refused; the message is written for the person who selected it."""


def reader_of(location: dict[str, Any] | None) -> dict[str, Any]:
    """What read this section: ``kind``, plain ``words``, whether software or a model read it, and its confidence."""
    location = location or {}
    kind = location.get("kind")
    method = location.get("extraction_method")
    origin = location.get("text_origin")
    confidence = location.get("ocr_confidence")
    confidence = float(confidence) if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) else None
    if kind in ("audio", "video", "audio_turn"):
        model = location.get("reader_model")
        words = (f"Transcript by a speech model ({model}), not confirmed by a person" if model
                 else "Transcript by a speech model (which one was not recorded), not confirmed by a person")
        return dict(kind="model", words=words, machine_read=True, model=model, confidence=None, low_confidence=False)
    if kind == "image":
        provider, model = location.get("reader_provider"), location.get("reader_model")
        if provider == "openai_vision":
            return dict(kind="model", words=f"Described by an image model ({model or 'not recorded'}), not confirmed by a person",
                        machine_read=True, model=model, confidence=None, low_confidence=False)
        if provider:
            return dict(kind="ocr", words="Read by OCR software (Tesseract), not confirmed by a person",
                        machine_read=True, model=None, confidence=None, low_confidence=False)
        return dict(kind="unrecorded", words="Read from the image by software or a model (which one was not recorded), "
                    "not confirmed by a person", machine_read=True, model=None, confidence=None, low_confidence=False)
    if kind == "phone_record":
        return dict(kind="phone", words="Written from the phone's records", machine_read=False, model=None,
                    confidence=None, low_confidence=False)
    if kind in FILE_TEXT_KINDS:
        return dict(kind="file_text", words="The file's own text", machine_read=False, model=None, confidence=None,
                    low_confidence=False)
    if method == "vision_model":  # a wordless scanned page read by a picture-reading model (page_image_reading)
        reading = location.get("page_image_reading") or {}
        model = reading.get("model") or (location.get("model_origin") or {}).get("model_id")
        return dict(kind="model", words=f"Read from the page image by a picture-reading model ({model or 'not recorded'}) "
                    "after OCR found no words, not confirmed by a person", machine_read=True, model=model,
                    confidence=None, low_confidence=False)
    if method == "tesseract_ocr":
        return dict(kind="ocr", words="Read from the page image by OCR software (Tesseract), not confirmed by a person",
                    machine_read=True, model=None, confidence=confidence,
                    low_confidence=bool(location.get("ocr_low_confidence")))
    if origin == "digital_text_layer":
        return dict(kind="text_layer", words="The PDF's own text layer", machine_read=False, model=None, confidence=None,
                    low_confidence=False)
    if origin == "recognised_glyphs":
        return dict(kind="recognised_layer", words="A text layer recognised from a scan before the file reached Loupe, "
                    "not confirmed by a person", machine_read=True, model=None, confidence=None, low_confidence=False)
    if method == "native":
        return dict(kind="file_layer", words="The PDF's stored text (whether typed or scanned was not recorded)",
                    machine_read=True, model=None, confidence=None, low_confidence=False)
    return dict(kind="unrecorded", words="What read this text was not recorded", machine_read=True, model=None,
                confidence=None, low_confidence=False)


def _sections(locations: list[Any] | None, length: int) -> list[dict[str, Any]]:
    """The document's numbered pages: a PDF's own, or its sections split into parts."""
    usable = [item for item in locations or [] if isinstance(item, dict)
              and isinstance(item.get("start_char"), int) and isinstance(item.get("end_char"), int)]
    paged: dict[int, dict[str, Any]] = {}
    for item in usable:
        number = item.get("page_number")
        if item.get("kind") == "page" and type(number) is int and number >= 1:
            paged.setdefault(number, item)
    if paged:
        return [{"page_number": number, "label": item.get("label") or f"Page {number}", "location": item,
                 "start_char": max(0, min(item["start_char"], length)),
                 "end_char": max(0, min(item["end_char"], length))} for number, item in sorted(paged.items())]
    whole = [item for item in usable if item.get("kind") in FILE_TEXT_KINDS + ("audio", "video", "image")]
    if not whole:  # a phone thread document, or text with no locations: the stored text as one section
        kinds = [item for item in usable if item.get("kind") == "phone_record"]
        whole = [{"kind": kinds[0]["kind"] if kinds else None, "label": "Document text", "start_char": 0,
                  "end_char": length}]
    out: list[dict[str, Any]] = []
    for item in sorted(whole, key=lambda value: value["start_char"]):
        start, end = max(0, item["start_char"]), min(item["end_char"], length)
        parts = max(1, -(-(end - start) // PART_CHARACTERS))
        for part in range(parts):
            part_start = start + part * PART_CHARACTERS
            label = item.get("label") or "Document text"
            out.append({"label": f"{label}, part {part + 1} of {parts}" if parts > 1 else label, "location": item,
                        "start_char": part_start, "end_char": min(end, part_start + PART_CHARACTERS)})
    for number, section in enumerate(out, start=1):
        section["page_number"] = number
    return out


def _pdf_pages(path: Path | None) -> int | None:
    """Pages of a PDF, counted from the file; None when it cannot be opened (the words then say so)."""
    if path is None or path.suffix.lower() != ".pdf":
        return None
    try:
        import fitz
        with fitz.open(path) as document:
            return document.page_count
    except Exception:  # noqa: BLE001 - no page images is reported, not raised
        return None


def absent_reason(record: EvidenceFile) -> str:
    """Why a document has no stored text, in words shown on the page. Never an empty panel."""
    if record.status == "unprocessed":
        if (record.last_error or "").startswith("Cancelled on request."):
            return "Processing this file was cancelled before its text was stored, so Loupe holds no text for it."
        return "This file has not been processed yet, so Loupe holds no text for it."
    if record.status == "failed":
        error = (record.last_error or "").strip()
        known = error.startswith(("Unsupported", "Batch task interrupted", "Batch task cancelled"))  # older rows keep it
        return "Reading this file failed, so Loupe holds no text for it." + (f" {error}" if known else "")
    if record.transcription:
        return "This recording's transcript is kept with the recording: open it from Evidence."
    return ("This file was processed but no text is stored for it. It may hold only pictures or sound, or it was "
            "processed before text was kept. Processing it again would read it.")


def page_image_failure(record: EvidenceFile) -> str | None:
    """The latest failed page-image reading of this file (services/financial/vision_reader), in its stored words."""
    from services.financial.vision_reader import METADATA_KEY
    failed = [value for value in ((record.metadata_ or {}).get(METADATA_KEY) or {}).values()
              if isinstance(value, dict) and value.get("status") == "failed"]
    if not failed:
        return None
    latest = max(failed, key=lambda value: str(value.get("at") or ""))
    day = str(latest.get("at") or "")[:10]
    return f"A page-image reading was tried{' on ' + day if day else ''} and failed: {latest.get('message') or 'no reason kept'}"


def _missing_words(section: dict[str, Any] | None, failure: str | None) -> str:
    location = (section or {}).get("location") or {}
    status = location.get("ocr_status")
    if section is None:
        why = "No text is stored for this page."
    elif status == OCR_TIMEOUT_STATUS or location.get("text_origin") == "unread":
        why = "OCR ran out of time on this page, so it was not read."
    elif status == "no_text":
        why = "OCR ran on this page and found no text. It may be blank or hold only a picture."
        reading = location.get("page_image_reading") or {}
        if reading.get("status") == "no_words":
            why += f" A picture-reading model ({reading.get('model') or 'not recorded'}) also found no words on it."
        elif reading.get("status") in ("failed", "not_read") and reading.get("message"):
            why += (" Reading it with a picture-reading model failed: " if reading["status"] == "failed" else " ") \
                + str(reading["message"]).rstrip(".") + "."
    elif location.get("extraction_method") == "native":
        why = "This page has no text layer and holds no text."
    else:
        why = "No text is stored for this page."
    return f"{why} {failure}" if failure else why


def _page_view(section: dict[str, Any] | None, number: int, text: str, failure: str | None) -> dict[str, Any]:
    location = (section or {}).get("location")
    return {
        "page_number": number,
        "label": (section or {}).get("label") or f"Page {number}",
        "start_char": (section or {}).get("start_char"),
        "end_char": (section or {}).get("end_char"),
        "text": text,
        "reader": reader_of(location) if section is not None else None,
        "text_missing": None if text.strip() else _missing_words(section, failure),
    }


def document_pages(db: Session, record: EvidenceFile, *, path: Path | None, page_offset: int,
                   page_limit: int) -> dict[str, Any]:
    """One window of a document's pages. Only the window's text is read from the database, so a 2,000-page document
    costs what a 5-page one does; ``page_count`` is the whole document. ``path``: the original on disk, when it is
    there. ``pages_in_step``: each text page is the same page of the file (false for a PDF whose stored text carries
    no page ranges, which is shown undivided); ``image_pages``: page images the file has."""
    row = db.execute(
        select(EvidenceDocumentText.content_sha256, EvidenceDocumentText.character_count,
               EvidenceDocumentText.source_locations, EvidenceDocumentText.extracted_at)
        .where(EvidenceDocumentText.evidence_file_id == record.id)
    ).one_or_none()
    name = record.original_filename or ""
    is_pdf = name.lower().endswith(".pdf") and path is not None
    out: dict[str, Any] = {
        "evidence_id": str(record.id), "case_id": str(record.case_id), "document_name": name,
        "source_type": record.source_type,
        "original_available": path is not None,
        "image_pages": 0, "pages_in_step": True,
        "text_version": None, "read_at": None, "character_count": 0,
        "text_absent": None, "page_count": 0, "page_offset": page_offset, "page_limit": page_limit,
        "has_more": False, "pages": [],
    }
    failure = page_image_failure(record)
    out["page_image_failure"] = failure
    if row is None:
        out["text_absent"] = " ".join(value for value in (absent_reason(record), failure) if value)
        count = _pdf_pages(path) or 0
        out["page_count"] = out["image_pages"] = count
        numbers = range(page_offset + 1, min(count, page_offset + page_limit) + 1)
        out["pages"] = [_page_view(None, number, "", failure) for number in numbers]
        out["has_more"] = page_offset + len(out["pages"]) < count
        return out

    out.update(text_version=row.content_sha256, character_count=row.character_count,
               read_at=row.extracted_at.isoformat() if row.extracted_at else None)
    sections = _sections(row.source_locations, row.character_count)
    by_number = {section["page_number"]: section for section in sections}
    paged = any((section["location"] or {}).get("kind") == "page" for section in sections)
    count = max(by_number, default=0)
    if is_pdf:
        out["image_pages"] = count if paged else _pdf_pages(path) or 0
        out["pages_in_step"] = paged
    numbers = list(range(page_offset + 1, min(count, page_offset + page_limit) + 1))
    held = [by_number[number] for number in numbers if number in by_number]
    window = ""
    first = 0
    if held:
        first = min(section["start_char"] for section in held)
        last = max(section["end_char"] for section in held)
        window = db.scalar(select(func.substr(EvidenceDocumentText.content, first + 1, last - first)).where(
            EvidenceDocumentText.evidence_file_id == record.id)) or ""
    for number in numbers:
        section = by_number.get(number)
        text = window[section["start_char"] - first:section["end_char"] - first] if section else ""
        out["pages"].append(_page_view(section, number, text, failure))
    out["page_count"] = count
    out["has_more"] = page_offset + len(numbers) < count
    return out


def page_at(db: Session, record: EvidenceFile, character: int) -> int | None:
    """The page or part of the document holding this character of its stored text; None past the end."""
    row = db.execute(select(EvidenceDocumentText.character_count, EvidenceDocumentText.source_locations)
                     .where(EvidenceDocumentText.evidence_file_id == record.id)).one_or_none()
    if row is None:
        return None
    sections = _sections(row.source_locations, row.character_count)
    return next((s["page_number"] for s in sections if s["start_char"] <= character < s["end_char"]), None)


def page_positions(path: Path, page_number: int, words: str) -> dict[str, Any]:
    """Where ``words`` sit on a PDF page, as fractions of the page as displayed (the page image's frame). Only a page
    with a text layer has positions; a page read by OCR has none and says so through ``available``."""
    import fitz
    with fitz.open(path) as document:
        if not 1 <= page_number <= document.page_count:
            return {"available": False, "rects": []}
        page = document[page_number - 1]
        if not page.get_text("text").strip():
            return {"available": False, "rects": []}
        matrix, frame = page.rotation_matrix, page.rect
        rects = []
        for found in page.search_for(words):
            rect = found * matrix
            rects.append({"x": rect.x0 / frame.width, "y": rect.y0 / frame.height,
                          "width": rect.width / frame.width, "height": rect.height / frame.height})
    return {"available": True, "rects": rects}


# ---- a passage as a link target ----------------------------------------------------------------------------------

def passage_id(evidence_id: Any, version: str, start: int, end: int) -> str:
    return f"{evidence_id}:{version[:VERSION_CHARACTERS]}:{start}:{end}"


def parse_passage(target_id: str) -> tuple[UUID, str, int, int]:
    try:
        file_id, version, start, end = str(target_id).split(":")
        parsed = UUID(file_id), version, int(start), int(end)
    except (TypeError, ValueError) as exc:
        raise PassageError("That selection could not be read as a passage of a document.") from exc
    if parsed[2] < 0 or parsed[3] <= parsed[2]:
        raise PassageError("That selection is empty.")
    return parsed


def _quote_label(quote: str, document: str, section: str) -> str:
    flat = " ".join(quote.split())
    short = flat if len(flat) <= 120 else _LONG.sub("", flat[:120] + " ") + "…"
    return f"“{short}”, {document or 'document'}, {section}"[:512]


def passage_anchor(db: Session, case_id: Any, target_id: str) -> tuple[str, dict[str, Any]]:
    """(label, source anchor) of a passage, written from the stored text and locations of the document as it is now.

    Refused, in words for the person, when the document is not in the case, was read again since the selection, the
    range runs past one page, or the selection is longer than a quote may be: a passage is stored whole or not at all."""
    file_id, version, start, end = parse_passage(target_id)
    case_uuid = case_id if isinstance(case_id, UUID) else UUID(str(case_id))
    record = db.get(EvidenceFile, file_id)
    if record is None or record.case_id != case_uuid or getattr(record, "deleted_at", None) is not None:
        raise PassageError(f"Evidence file {file_id} was not found in this case")
    if end - start > QUOTE_MAX_CHARACTERS:
        raise PassageError(f"A quote can be at most {QUOTE_MAX_CHARACTERS:,} characters; this selection has "
                           f"{end - start:,}. Nothing was added. Select less.")
    row = db.execute(select(EvidenceDocumentText.content_sha256, EvidenceDocumentText.source_locations,
                            EvidenceDocumentText.character_count,
                            func.substr(EvidenceDocumentText.content, start + 1, end - start).label("quote"))
                     .where(EvidenceDocumentText.evidence_file_id == file_id)).one_or_none()
    if row is None or row.content_sha256[:VERSION_CHARACTERS] != version:
        raise PassageError("This document was read again since this text was shown. Nothing was added. "
                           "Reload the page and select the words again.")
    if end > row.character_count:
        raise PassageError("That selection runs past the end of the document's text.")
    sections = _sections(row.source_locations, row.character_count)
    section = next((s for s in sections if s["start_char"] <= start and end <= s["end_char"]), None)
    if section is None:
        raise PassageError("A quote must sit on one page. Nothing was added. Select the words on each page separately.")
    numbered = (section["location"] or {}).get("kind") == "page"
    reader = reader_of(section["location"])
    anchor = {
        "kind": "text_passage", "evidence_file_id": str(file_id), "document_name": record.original_filename,
        "page_number": section["page_number"], "page_label": section["label"],
        **({"page": section["page_number"]} if numbered else {}),
        "quote": row.quote, "start_char": start, "end_char": end, "text_version": row.content_sha256,
        "reader": reader, "taken_at": datetime.now(timezone.utc).isoformat(),
    }
    label = _quote_label(row.quote, record.original_filename, section["label"])
    if reader["machine_read"]:
        label = f"{label[:512 - len(reader['words']) - 3]} · {reader['words']}"
    return label, anchor


def passage_state(anchor: dict[str, Any], current_version: str | None, extracted_at: datetime | None) -> str | None:
    """Link-state words for a passage: None while the document still holds the text it was taken from."""
    if current_version is None:
        return "This document's text is no longer held, so the quote can only be read here."
    if current_version == anchor.get("text_version"):
        return None
    day = extracted_at.astimezone(timezone.utc).strftime("%-d %B %Y") if extracted_at else "an unknown date"
    return f"This document was read again after this quote was taken, on {day}. The quote keeps the words as taken."


def kept_passage_anchor(db: Session, record: EvidenceFile, target_id: str) -> dict[str, Any] | None:
    """The stored anchor of a passage kept on some finding, note or dossier of this document's case."""
    from postgres.models.dossier import DossierLink
    from postgres.models.workspace_entry import WorkspaceEntryLink
    if not str(target_id).startswith(f"{record.id}:"):
        return None
    for model in (WorkspaceEntryLink, DossierLink):
        anchor = db.scalar(select(model.source_anchor).where(
            model.case_id == record.case_id, model.target_type == "evidence_passage", model.target_id == target_id,
        ).limit(1))
        if anchor:
            return dict(anchor)
    return None


def locate_passage(db: Session, record: EvidenceFile, anchor: dict[str, Any]) -> dict[str, Any]:
    """Where a kept quote is in the document now: at its place, found elsewhere, or no longer in the text."""
    row = db.execute(select(EvidenceDocumentText.content_sha256, EvidenceDocumentText.character_count,
                            EvidenceDocumentText.source_locations, EvidenceDocumentText.extracted_at)
                     .where(EvidenceDocumentText.evidence_file_id == record.id)).one_or_none()
    quote = anchor.get("quote") or ""
    start, end = anchor.get("start_char"), anchor.get("end_char")
    words = passage_state(anchor, row.content_sha256 if row else None, row.extracted_at if row else None)
    base = {"quote": quote, "reader": anchor.get("reader"), "taken_page": anchor.get("page_number"),
            "taken_version": anchor.get("text_version"), "current_version": row.content_sha256 if row else None,
            "start_char": None, "end_char": None, "page_number": None}
    if row is None:
        return {**base, "state": "text_gone", "words": words}
    sections = _sections(row.source_locations, row.character_count)
    if row.content_sha256 == anchor.get("text_version"):
        return {**base, "state": "unchanged", "words": None, "start_char": start, "end_char": end,
                "page_number": anchor.get("page_number")}
    content = db.scalar(select(EvidenceDocumentText.content).where(
        EvidenceDocumentText.evidence_file_id == record.id)) or ""
    found = content.find(quote) if quote else -1
    if found < 0:
        return {**base, "state": "not_found",
                "words": f"{words} Those words are not in the new reading, so the page is the one the quote came from."}
    section = next((s for s in sections if s["start_char"] <= found < s["end_char"]), None)
    return {**base, "state": "moved", "start_char": found, "end_char": found + len(quote),
            "page_number": section["page_number"] if section else anchor.get("page_number"),
            "words": f"{words} The same words are in the new reading."}
