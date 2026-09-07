"""Source-bound, pending PDF mappings. No ledger writes or inferred readings.

This first contract binds nominated text regions, not detected table geometry.
Column meanings and context are proposals even when their text is digital.
Every candidate still requires review. A later writer must reload and rebind
under its transaction; a digest is a revision marker, not an authorization token.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from postgres.models.evidence import EvidenceDocumentText, EvidenceFile
from services.financial.amount_assessment import source_span_origin
from services.financial.suspect_amounts import TextOrigin


class PdfMappingError(ValueError):
    def __init__(self, message, status_code=422):
        super().__init__(message)
        self.status_code = status_code


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


_Index = Annotated[int, Field(strict=True, ge=0)]
_Digest = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]


class PdfTextSpan(_Contract):
    start_char: _Index
    end_char: _Index
    text: Annotated[str, Field(strict=True, min_length=1, max_length=4096)]

    @model_validator(mode="after")
    def exact_length(self):
        if self.end_char - self.start_char != len(self.text):
            raise ValueError("Span length must match the exact Unicode code-point text length.")
        return self


class PdfColumnProposal(_Contract):
    column_index: _Index
    meaning: Literal["unknown", "amount", "debit", "credit", "booking_date",
                     "value_date", "transaction_date", "description", "reference", "balance",
                     "account", "currency", "direction"] = "unknown"
    header: Optional[PdfTextSpan] = None


class PdfCellProposal(_Contract):
    column_index: _Index
    source: PdfTextSpan


class PdfRowProposal(_Contract):
    row_index: _Index
    cells: Annotated[tuple[PdfCellProposal, ...], Field(min_length=1, max_length=64)]


class PdfContextProposal(_Contract):
    # Text evidence only: no normalized account, date, currency or direction yet.
    account: Optional[PdfTextSpan] = None
    currency: Optional[PdfTextSpan] = None
    period: Optional[PdfTextSpan] = None
    direction_convention: Optional[PdfTextSpan] = None


class PdfMappingProposal(_Contract):
    schema_version: Literal["pdf-text-mapping-v1"] = "pdf-text-mapping-v1"
    case_id: UUID
    evidence_file_id: UUID
    source_revision: _Digest
    table_id: UUID
    # A caller-nominated text region, not proof that a table was detected.
    start_char: _Index
    end_char: _Index
    columns: Annotated[tuple[PdfColumnProposal, ...], Field(min_length=1, max_length=64)]
    rows: Annotated[tuple[PdfRowProposal, ...], Field(min_length=1, max_length=1000)]
    context: PdfContextProposal = Field(default_factory=PdfContextProposal)

    @model_validator(mode="after")
    def coherent_grid(self):
        if self.end_char <= self.start_char:
            raise ValueError("Table text region must be nonempty.")
        columns = [column.column_index for column in self.columns]
        if columns != sorted(set(columns)):
            raise ValueError("Columns must be unique and in source column order.")
        rows = [row.row_index for row in self.rows]
        if rows != sorted(set(rows)):
            raise ValueError("Rows must be unique and in source row order.")
        occupied = []
        previous_end = -1
        for row in self.rows:
            indices = [cell.column_index for cell in row.cells]
            if indices != sorted(set(indices)) or not set(indices) <= set(columns):
                raise ValueError("Each row must use unique, ordered, declared columns.")
            first = min(cell.source.start_char for cell in row.cells)
            if first < previous_end:
                raise ValueError("Row order must agree with canonical text order.")
            previous_end = max(cell.source.end_char for cell in row.cells)
            for cell in row.cells:
                span = cell.source
                if not self.start_char <= span.start_char < span.end_char <= self.end_char:
                    raise ValueError("Cells must lie inside their nominated table region.")
                occupied.append((span.start_char, span.end_char))
        occupied.sort()
        if any(left[1] > right[0] for left, right in zip(occupied, occupied[1:])):
            raise ValueError("Candidate cells must not reuse or overlap source characters.")
        for column in self.columns:
            if column.header is not None and not (
                self.start_char <= column.header.start_char < column.header.end_char <= self.end_char
            ):
                raise ValueError("Column headers must lie inside their table region.")
        return self


class PdfBoundCell(_Contract):
    column_index: _Index
    proposed_meaning: str
    source: PdfTextSpan
    origin: TextOrigin
    page_number: Optional[Annotated[int, Field(strict=True, ge=1)]]
    # No rectangle is asserted by this canonical-text mapping.


class PdfPendingCandidate(_Contract):
    # Identifies this mapping snapshot, not a cross-revision ingestion dedupe key.
    candidate_key: _Digest
    mapping_revision: _Digest
    row_index: _Index
    cells: tuple[PdfBoundCell, ...]
    status: Literal["pending"] = "pending"


class PdfBoundMapping(_Contract):
    proposal: PdfMappingProposal
    mapping_revision: _Digest
    file_sha256: _Digest
    content_sha256: _Digest
    candidates: tuple[PdfPendingCandidate, ...]
    file_bytes_verified: Literal[False] = False
    applied: Literal[False] = False


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _source(session, case_id, evidence_file_id):
    # One case-scoped snapshot includes provenance: text alone is not a revision.
    with session.no_autoflush:
        row = session.execute(select(
            EvidenceFile.sha256, EvidenceDocumentText.content,
            EvidenceDocumentText.content_sha256, EvidenceDocumentText.source_locations,
            EvidenceDocumentText.engine_job_id,
        ).join(EvidenceDocumentText, EvidenceFile.id == EvidenceDocumentText.evidence_file_id)
          .where(EvidenceFile.id == evidence_file_id, EvidenceFile.case_id == case_id)).one_or_none()
    if row is None:
        raise PdfMappingError("Source text not found in this case.", 404)
    file_hash, content, text_hash, locations, job_id = row
    if not isinstance(file_hash, str) or re.fullmatch(r"[0-9a-f]{64}", file_hash) is None:
        raise PdfMappingError("Source file has no valid recorded digest.", 409)
    if hashlib.sha256(content.encode("utf-8")).hexdigest() != text_hash:
        raise PdfMappingError("Stored source text digest is inconsistent.", 409)
    revision = _digest({"case_id": str(case_id), "evidence_file_id": str(evidence_file_id),
                        "file_sha256": file_hash, "content_sha256": text_hash,
                        "source_locations": locations, "engine_job_id": str(job_id) if job_id else None})
    return content, locations, file_hash, text_hash, revision


def pdf_mapping_source_revision(session, *, case_id, evidence_file_id):
    """Read the revision against which a mapping may be proposed (no writes)."""
    return _source(session, case_id, evidence_file_id)[4]


def bind_pdf_mapping(session, *, case_id, proposal):
    """Validate exact source bindings; return immutable pending candidates only.

    The caller must independently authorize case access. No proposed column meaning
    is promoted to a fact; even a complete mapping has no amount_minor or RowReading.
    """
    proposal = PdfMappingProposal.model_validate(proposal)
    if proposal.case_id != case_id:
        raise PdfMappingError("Mapping does not belong to this case.", 404)
    content, locations, file_hash, text_hash, revision = _source(
        session, case_id, proposal.evidence_file_id)
    if proposal.source_revision != revision:
        raise PdfMappingError("Source or provenance changed. Rebuild the mapping.", 409)
    if proposal.end_char > len(content):
        raise PdfMappingError("Table region extends beyond source text.", 409)
    spans = [cell.source for row in proposal.rows for cell in row.cells]
    spans += [column.header for column in proposal.columns if column.header is not None]
    spans += [getattr(proposal.context, field) for field in type(proposal.context).model_fields
              if getattr(proposal.context, field) is not None]
    for span in spans:
        if span.end_char > len(content) or content[span.start_char:span.end_char] != span.text:
            raise PdfMappingError("Mapped text does not match its exact source offsets.", 409)
    mapping_revision = _digest(proposal.model_dump(mode="json"))
    meanings = {column.column_index: column.meaning for column in proposal.columns}
    candidates = []
    for row in proposal.rows:
        cells = []
        for cell in row.cells:
            origin, page = source_span_origin(content, locations,
                                              cell.source.start_char, cell.source.end_char)
            cells.append(PdfBoundCell(column_index=cell.column_index,
                proposed_meaning=meanings[cell.column_index], source=cell.source,
                origin=origin, page_number=page))
        candidates.append(PdfPendingCandidate(
            candidate_key=_digest({"mapping_revision": mapping_revision, "row_index": row.row_index}),
            mapping_revision=mapping_revision, row_index=row.row_index, cells=tuple(cells)))
    return PdfBoundMapping(proposal=proposal, mapping_revision=mapping_revision,
        file_sha256=file_hash, content_sha256=text_hash, candidates=tuple(candidates))
