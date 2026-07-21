from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import EvidenceDocumentText
from app.pipeline.extract_text import ExtractedDocument


@dataclass(frozen=True)
class CanonicalDocumentText:
    content: str
    content_sha256: str
    character_count: int
    source_locations: list[dict[str, Any]]


def _append_section(
    sections: list[str],
    locations: list[dict[str, Any]],
    text: str,
    *,
    kind: str,
    label: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not text:
        return
    separator = "\n\n" if sections else ""
    start = sum(len(part) for part in sections) + len(separator)
    sections.extend([separator, text] if separator else [text])
    location = {
        "kind": kind,
        "label": label,
        "start_char": start,
        "end_char": start + len(text),
    }
    if metadata:
        location.update(metadata)
    locations.append(location)


def build_canonical_document_text(doc: ExtractedDocument) -> CanonicalDocumentText:
    file_type = str(doc.metadata.get("file_type") or "text").lower()
    sections: list[str] = []
    locations: list[dict[str, Any]] = []

    if file_type == "pdf":
        content = doc.text or ""
        for span in doc.metadata.get("page_spans") or []:
            page = span.get("page")
            location = {
                "kind": "page",
                "label": f"Page {page}",
                "page_number": page,
                "start_char": int(span.get("start_char", 0)),
                "end_char": min(int(span.get("end_char", 0)), len(content)),
            }
            for key in (
                "extraction_method",
                "detection_reason",
                "ocr_status",
                "ocr_confidence",
                "ocr_low_confidence",
                "ocr_dpi",
                "ocr_language",
            ):
                if key in span:
                    location[key] = span[key]
            locations.append(location)
    elif file_type == "docx":
        _append_section(
            sections,
            locations,
            doc.text or "",
            kind="body",
            label="Document body",
        )
        for index, table in enumerate(doc.tables or [], start=1):
            _append_section(
                sections,
                locations,
                table,
                kind="table",
                label=f"Table {index}",
                metadata={"table_number": index},
            )
        content = "".join(sections)
    elif file_type in {"xlsx", "xls", "csv"}:
        for index, table in enumerate(doc.tables or [], start=1):
            sheet_match = re.match(r"^\[Sheet: (.+?)\]\n", table)
            sheet_name = sheet_match.group(1) if sheet_match else None
            label = f"Sheet {sheet_name}" if sheet_name else f"Table {index}"
            metadata: dict[str, Any] = {"table_number": index}
            if sheet_name:
                metadata["sheet_name"] = sheet_name
            _append_section(
                sections,
                locations,
                table,
                kind="sheet" if sheet_name else "table",
                label=label,
                metadata=metadata,
            )
        content = "".join(sections)
    else:
        content = doc.text or ""
        if content:
            label_by_type = {
                "audio": "Transcript",
                "video": "Transcript",
                "image": "OCR text",
            }
            locations.append(
                {
                    "kind": file_type,
                    "label": label_by_type.get(file_type, "Document text"),
                    "start_char": 0,
                    "end_char": len(content),
                }
            )

    return CanonicalDocumentText(
        content=content,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        character_count=len(content),
        source_locations=locations,
    )


async def upsert_evidence_document_text(
    db: AsyncSession,
    *,
    evidence_file_id: uuid.UUID | str,
    engine_job_id: uuid.UUID | str | None,
    doc: ExtractedDocument,
) -> CanonicalDocumentText:
    canonical = build_canonical_document_text(doc)
    evidence_uuid = uuid.UUID(str(evidence_file_id))
    job_uuid = uuid.UUID(str(engine_job_id)) if engine_job_id else None
    statement = insert(EvidenceDocumentText).values(
        evidence_file_id=evidence_uuid,
        engine_job_id=job_uuid,
        content=canonical.content,
        content_sha256=canonical.content_sha256,
        character_count=canonical.character_count,
        source_locations=canonical.source_locations,
    )
    await db.execute(
        statement.on_conflict_do_update(
            index_elements=[EvidenceDocumentText.evidence_file_id],
            set_={
                "engine_job_id": statement.excluded.engine_job_id,
                "content": statement.excluded.content,
                "content_sha256": statement.excluded.content_sha256,
                "character_count": statement.excluded.character_count,
                "source_locations": statement.excluded.source_locations,
                "extracted_at": func.now(),
            },
        )
    )
    await db.commit()
    return canonical
