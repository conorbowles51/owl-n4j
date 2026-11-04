from __future__ import annotations

import logging
import re
import time
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceFolder

logger = logging.getLogger(__name__)
PREVIEW_MATCH_LIMIT = 3
SNIPPET_CONTEXT_CHARACTERS = 90


def _escaped_like_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _literal_occurrences(content: str, query: str) -> list[tuple[int, int]]:
    return [
        (match.start(), match.end())
        for match in re.finditer(re.escape(query), content, flags=re.IGNORECASE)
    ]


def _clean_boundary(content: str, proposed: int, *, left: bool) -> int:
    if proposed <= 0:
        return 0
    if proposed >= len(content):
        return len(content)
    if content[proposed].isspace() or content[proposed - 1].isspace():
        return proposed
    if left:
        following_space = re.search(r"\s", content[proposed:])
        return proposed + following_space.end() if following_space else proposed
    preceding_space = list(re.finditer(r"\s", content[:proposed]))
    return preceding_space[-1].start() if preceding_space else proposed


def _snippet(content: str, match_start: int, match_end: int,
             context: int = SNIPPET_CONTEXT_CHARACTERS) -> tuple[str, int, int]:
    snippet_start = _clean_boundary(
        content,
        max(0, match_start - context),
        left=True,
    )
    snippet_end = _clean_boundary(
        content,
        min(len(content), match_end + context),
        left=False,
    )
    snippet_start = min(snippet_start, match_start)
    snippet_end = max(snippet_end, match_end)

    prefix = re.sub(r"\s+", " ", content[snippet_start:match_start])
    highlighted = re.sub(r"\s+", " ", content[match_start:match_end])
    suffix = re.sub(r"\s+", " ", content[match_end:snippet_end])
    body = prefix + highlighted + suffix
    removed_left = len(body) - len(body.lstrip())
    body = body.strip()
    highlight_start = max(0, len(prefix) - removed_left)
    highlight_end = highlight_start + len(highlighted)

    leading = "… " if snippet_start > 0 else ""
    trailing = " …" if snippet_end < len(content) else ""
    return (
        leading + body + trailing,
        len(leading) + highlight_start,
        len(leading) + highlight_end,
    )


def _location_for_match(
    locations: list[dict[str, Any]] | None,
    match_start: int,
) -> dict[str, Any] | None:
    """The narrowest location holding the match: a phone message line holds its attachments' spans, and a hit on an
    attachment names the attachment's own record. Equal widths keep the first."""
    best = None
    for location in locations or []:
        start, end = int(location.get("start_char", 0)), int(location.get("end_char", 0))
        if start <= match_start < end and (best is None or end - start < best[0]):
            best = (end - start, location)
    return best[1] if best else None


def _hit(
    evidence_id: UUID,
    content: str,
    locations: list[dict[str, Any]] | None,
    start: int,
    end: int,
    context: int = SNIPPET_CONTEXT_CHARACTERS,
) -> dict[str, Any]:
    snippet, highlight_start, highlight_end = _snippet(content, start, end, context)
    location = _location_for_match(locations, start)
    return {
        "id": f"{evidence_id}:{start}:{end}",
        "start_char": start,
        "end_char": end,
        "snippet": snippet,
        "highlight_start": highlight_start,
        "highlight_end": highlight_end,
        "page_number": location.get("page_number") if location else None,
        "location_label": location.get("label") if location else None,
        # a phone thread document's line names its record, so the hit opens the record (02 section 9.7)
        "location_kind": location.get("kind") if location else None,
        "record_uid": location.get("record_uid") if location else None,
        "extraction_id": location.get("extraction_id") if location else None,
    }


def _folder_paths(db: Session, case_id: UUID) -> dict[UUID, str]:
    folders = db.execute(
        select(EvidenceFolder.id, EvidenceFolder.parent_id, EvidenceFolder.name).where(
            EvidenceFolder.case_id == case_id
        )
    ).all()
    folder_by_id = {row.id: row for row in folders}
    paths: dict[UUID, str] = {}

    def resolve(folder_id: UUID, seen: set[UUID] | None = None) -> str:
        if folder_id in paths:
            return paths[folder_id]
        seen = set(seen or ())
        if folder_id in seen or folder_id not in folder_by_id:
            return "Root"
        seen.add(folder_id)
        folder = folder_by_id[folder_id]
        parent = resolve(folder.parent_id, seen) if folder.parent_id else "Root"
        paths[folder_id] = f"{parent} / {folder.name}"
        return paths[folder_id]

    for folder_id in folder_by_id:
        resolve(folder_id)
    return paths


def search_case_text(
    db: Session,
    *,
    case_id: UUID,
    query: str,
    document_limit: int,
    document_offset: int,
    snippet_context: int = SNIPPET_CONTEXT_CHARACTERS,
    evidence_ids: list[UUID] | None = None,
) -> dict[str, Any]:
    """Every document of the case whose text holds ``query`` literally (case-insensitive), paged by document.
    ``snippet_context``: characters of text kept either side of each hit (the meaning-search fallback asks for more,
    so an answer can be written from the hit). ``evidence_ids``: only these documents are read (the meaning-search
    fallback ranks with ``matching_documents`` first and reads only the page it returns)."""
    started = time.perf_counter()
    lowered_query = query.lower()
    like_pattern = f"%{_escaped_like_value(lowered_query)}%"

    case_documents = db.scalar(
        select(func.count()).select_from(EvidenceFile).where(
            EvidenceFile.case_id == case_id, EvidenceFile.source_type.is_distinct_from("phone_text"))
    ) or 0  # thread documents are text written from phone records, not documents in the case (02 section 9.7)
    searchable_documents = db.scalar(
        select(func.count())
        .select_from(EvidenceDocumentText)
        .join(EvidenceFile, EvidenceFile.id == EvidenceDocumentText.evidence_file_id)
        .where(EvidenceFile.case_id == case_id, EvidenceFile.source_type.is_distinct_from("phone_text"))
    ) or 0  # counted like case_documents, so searchable never exceeds the case's documents

    rows = db.execute(
        select(
            EvidenceFile.id,
            EvidenceFile.original_filename,
            EvidenceFile.folder_id,
            EvidenceFile.source_type,
            EvidenceDocumentText.content,
            EvidenceDocumentText.source_locations,
        )
        .join(EvidenceDocumentText, EvidenceDocumentText.evidence_file_id == EvidenceFile.id)
        .where(
            EvidenceFile.case_id == case_id,
            func.lower(EvidenceDocumentText.content).like(like_pattern, escape="\\"),
            *([EvidenceFile.id.in_(list(evidence_ids))] if evidence_ids is not None else []),
        )
        .order_by(func.lower(EvidenceFile.original_filename), EvidenceFile.id)
    ).all()

    folder_paths = _folder_paths(db, case_id)
    matched_documents: list[dict[str, Any]] = []
    total_matches = 0
    for row in rows:
        occurrences = _literal_occurrences(row.content, query)
        if not occurrences:
            continue
        total_matches += len(occurrences)
        preview = occurrences[:PREVIEW_MATCH_LIMIT]
        matched_documents.append(
            {
                "evidence_id": str(row.id),
                "document_name": row.original_filename,
                "source_type": row.source_type,
                "folder_path": "Phone conversations" if row.source_type == "phone_text"
                else folder_paths.get(row.folder_id, "Root"),
                "total_matches": len(occurrences),
                "shown_matches": len(preview),
                "matches_truncated": len(occurrences) > len(preview),
                "matches": [
                    _hit(row.id, row.content, row.source_locations, start, end, snippet_context)
                    for start, end in preview
                ],
            }
        )

    total_documents = len(matched_documents)
    page = matched_documents[document_offset : document_offset + document_limit]
    result = {
        "query": query,
        "total_matches": total_matches,
        "total_documents": total_documents,
        "case_documents": case_documents,
        "searchable_documents": searchable_documents,
        "document_limit": document_limit,
        "document_offset": document_offset,
        "returned_documents": len(page),
        "has_more_documents": document_offset + len(page) < total_documents,
        "documents": page,
    }
    logger.info(
        "Evidence text search completed duration_ms=%.1f query_length=%d case_id=%s "
        "total_matches=%d total_documents=%d returned_documents=%d",
        (time.perf_counter() - started) * 1000,
        len(query),
        case_id,
        total_matches,
        total_documents,
        len(page),
    )
    return result


def matching_documents(db: Session, *, case_id: UUID, query: str) -> list[tuple[UUID, str, int]]:
    """(id, file name, literal occurrences) of every case document whose text holds ``query``, counted in the
    database: no document text is loaded (on live BNB2, 3,239 texts / 58.6 M characters: 4 s for a term held by
    2,358 documents, against 80 s loading them)."""
    lowered_query = query.lower()
    like_pattern = f"%{_escaped_like_value(lowered_query)}%"
    lowered = func.lower(EvidenceDocumentText.content)
    occurrences = (func.length(lowered) - func.length(func.replace(lowered, lowered_query, ""))) / max(
        1, len(lowered_query))
    return [(row[0], row[1], int(row[2] or 0)) for row in db.execute(
        select(EvidenceFile.id, EvidenceFile.original_filename, occurrences)
        .join(EvidenceDocumentText, EvidenceDocumentText.evidence_file_id == EvidenceFile.id)
        .where(EvidenceFile.case_id == case_id, lowered.like(like_pattern, escape="\\"))
    ).all()]


def search_document_text(
    db: Session,
    *,
    evidence_id: UUID,
    query: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    row = db.execute(
        select(
            EvidenceDocumentText.content,
            EvidenceDocumentText.source_locations,
            EvidenceFile.case_id,
        )
        .join(EvidenceFile, EvidenceFile.id == EvidenceDocumentText.evidence_file_id)
        .where(EvidenceFile.id == evidence_id)
    ).one_or_none()
    occurrences = _literal_occurrences(row.content, query) if row else []
    selected = occurrences[offset : offset + limit]
    result = {
        "query": query,
        "evidence_id": str(evidence_id),
        "total_matches": len(occurrences),
        "returned_matches": len(selected),
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(selected) < len(occurrences),
        "matches": [
            _hit(evidence_id, row.content, row.source_locations, start, end)
            for start, end in selected
        ] if row else [],
    }
    logger.info(
        "Evidence document text search completed duration_ms=%.1f query_length=%d "
        "case_id=%s evidence_id=%s total_matches=%d returned_matches=%d",
        (time.perf_counter() - started) * 1000,
        len(query),
        row.case_id if row else None,
        evidence_id,
        len(occurrences),
        len(selected),
    )
    return result
