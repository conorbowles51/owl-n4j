"""Bind proposed PDF rows to stored grid positions, never amount-text searches.

Canonical PDF text can be column-major or omit table-cell spacing. This adapter
retains the stored cell text without inventing character offsets. It is read-only;
column meanings remain proposals and every resulting row remains pending.
"""
import hashlib
import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator, model_serializer
from sqlalchemy import select

from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceTableGeometry
from services.financial.amount_assessment import source_span_origin
from services.financial.locators import Locator, LocatorError
from services.financial.pdf_candidates import (
    _Contract, _Digest, _Index, _digest, PdfMappingError, PdfContextProposal,
)
from services.financial.pdf_tables import GeometrySource, TableSource
from services.financial.suspect_amounts import TextOrigin
from services.financial.table_geometry import CELL_OVERFLOW_TOLERANCE_MILLIPOINTS


class PdfGridColumn(_Contract):
    column_index: _Index
    meaning: Literal["unknown", "date", "amount", "debit", "credit", "booking_date",
                     "value_date", "transaction_date", "description", "reference", "balance",
                     "account", "currency", "direction"] = "unknown"


class PdfGridCell(_Contract):
    column_index: _Index
    expected_text: Annotated[str, Field(strict=True, min_length=1, max_length=4096)]


class PdfGridRow(_Contract):
    row_index: _Index
    cells: Annotated[tuple[PdfGridCell, ...], Field(min_length=1, max_length=64)]


class PdfGridMapping(_Contract):
    schema_version: Literal["pdf-grid-mapping-v1"] = "pdf-grid-mapping-v1"
    case_id: UUID
    evidence_file_id: UUID
    source_revision: _Digest
    page_number: Annotated[int, Field(strict=True, ge=1)]
    table_index: _Index
    columns: Annotated[tuple[PdfGridColumn, ...], Field(min_length=1, max_length=64)]
    rows: Annotated[tuple[PdfGridRow, ...], Field(min_length=1, max_length=1000)]
    context: PdfContextProposal = Field(default_factory=PdfContextProposal)
    nomination_id: UUID | None = None

    @model_serializer(mode="wrap")
    def retain_legacy_shape(self, handler):
        data=handler(self)
        if self.nomination_id is None:data.pop('nomination_id',None)
        return data

    @model_validator(mode="after")
    def ordered_unique_grid(self):
        columns = [c.column_index for c in self.columns]
        rows = [r.row_index for r in self.rows]
        if columns != sorted(set(columns)) or rows != sorted(set(rows)):
            raise ValueError("Rows and columns must be unique and in stored grid order.")
        for row in self.rows:
            indices = [c.column_index for c in row.cells]
            if indices != sorted(set(indices)) or not set(indices) <= set(columns):
                raise ValueError("Cells must use unique, ordered, declared columns.")
        return self


class PdfGridBoundCell(_Contract):
    column_index: _Index
    proposed_meaning: str
    text: str
    locator: Locator
    origin: TextOrigin


class PdfGridCandidate(_Contract):
    candidate_key: _Digest
    row_index: _Index
    cells: tuple[PdfGridBoundCell, ...]
    status: Literal["pending"] = "pending"


class PdfGridBoundMapping(_Contract):
    proposal: PdfGridMapping
    mapping_revision: _Digest
    file_sha256: _Digest
    content_sha256: _Digest
    table_source: TableSource
    geometry_source: GeometrySource
    table_locator: Locator
    candidates: tuple[PdfGridCandidate, ...]
    nomination_snapshot: dict | None = None
    processing_manifest: dict | None = None

    @model_serializer(mode="wrap")
    def retain_legacy_shape(self, handler):
        data=handler(self)
        if self.nomination_snapshot is None:data.pop('nomination_snapshot',None)
        if self.processing_manifest is None:data.pop('processing_manifest',None)
        return data

    file_bytes_verified: Literal[False] = False
    applied: Literal[False] = False


def _snapshot(session, case_id, evidence_file_id, page_number):
    if type(page_number) is not int or page_number < 1:
        raise PdfMappingError("Page must be a positive integer.")
    with session.no_autoflush:
        row = session.execute(select(
            EvidenceFile.sha256, EvidenceDocumentText.content,
            EvidenceDocumentText.content_sha256, EvidenceDocumentText.source_locations,
            EvidenceDocumentText.engine_job_id, EvidenceTableGeometry.engine_job_id,
            EvidenceTableGeometry.payload, EvidenceDocumentText.processing_manifest,
        ).join(EvidenceDocumentText, EvidenceDocumentText.evidence_file_id == EvidenceFile.id)
          .join(EvidenceTableGeometry, EvidenceTableGeometry.evidence_file_id == EvidenceFile.id)
          .where(EvidenceFile.id == evidence_file_id, EvidenceFile.case_id == case_id,
                 EvidenceTableGeometry.page_number == page_number)).one_or_none()
    if row is None:
        raise PdfMappingError("Stored table source not found in this case.", 404)
    file_hash, content, text_hash, locations, text_job, geometry_job, payload, manifest = row
    if not isinstance(file_hash, str) or re.fullmatch(r"[0-9a-f]{64}", file_hash) is None:
        raise PdfMappingError("Source file has no valid recorded digest.", 409)
    if hashlib.sha256(content.encode("utf-8")).hexdigest() != text_hash:
        raise PdfMappingError("Stored source text digest is inconsistent.", 409)
    if text_job is None or geometry_job != text_job:
        raise PdfMappingError("Text and table geometry are not bound to the same extraction job.", 409)
    if not isinstance(payload, list):
        raise PdfMappingError("Stored table geometry is malformed.", 409)
    try:
        from services.financial.pdf_processing_manifest import validate_pdf_processing_manifest
        manifest = validate_pdf_processing_manifest(manifest)
        revision = _digest(dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id),
            file_sha256=file_hash, content_sha256=text_hash, source_locations=locations,
            engine_job_id=str(text_job), page_number=page_number, geometry=payload,
            **({"processing_manifest":manifest} if manifest is not None else {})))
    except (ValueError, TypeError) as exc:
        raise PdfMappingError("Stored table provenance is malformed.", 409) from exc
    return content, locations, file_hash, text_hash, payload, revision, manifest


def pdf_grid_source_revision(session, *, case_id, evidence_file_id, page_number):
    return _snapshot(session, case_id, evidence_file_id, page_number)[5]


def _locator(raw, page):
    if not isinstance(raw, dict):
        raise ValueError("Missing stored locator.")
    if "page" in raw and (type(raw["page"]) is not int or raw["page"] != page):
        raise ValueError("Locator disagrees with stored page.")
    locator = Locator.from_json(raw)
    if locator.kind.value == "not_positional":
        raise ValueError("A PDF cell cannot claim a non-positional source.")
    return locator


def _table(payload, index, page):
    try:
        entry = payload[index]
        table_source = TableSource(entry["table_source"])
        geometry_source = GeometrySource(entry["geometry_source"])
        table = entry["table"]
        if type(table["page"]) is not int or table["page"] != page:
            raise ValueError("Table disagrees with stored page.")
        table_locator = _locator(table["table"], page)
        values = table["values"]
        if not isinstance(values, list):
            raise ValueError("Missing stored cells.")
        cells = {}
        rectangles = []
        for cell in values:
            row, column, text = cell["row"], cell["column"], cell["text"]
            if type(row) is not int or type(column) is not int or min(row, column) < 0:
                raise ValueError("Invalid stored grid coordinates.")
            if not isinstance(text, str) or (row, column) in cells:
                raise ValueError("Invalid text or duplicate stored cell.")
            locator = _locator(cell["locator"], page)
            rect, outer = locator.rectangle, table_locator.rectangle
            if rect is not None:
                if geometry_source is not GeometrySource.cell_rectangles:
                    raise ValueError("Cell rectangle contradicts recorded geometry source.")
                tolerance = CELL_OVERFLOW_TOLERANCE_MILLIPOINTS
                if outer is None or (rect.page_width, rect.page_height) != (outer.page_width, outer.page_height):
                    raise ValueError("Cell dimensions disagree with table.")
                if (rect.x0 < outer.x0 - tolerance or rect.y0 < outer.y0 - tolerance
                        or rect.x1 > outer.x1 + tolerance or rect.y1 > outer.y1 + tolerance):
                    raise ValueError("Cell lies outside its table.")
                rectangles.append(rect)
            cells[row, column] = (text, locator)
        rectangles.sort(key=lambda r: r.x0)
        for i, left in enumerate(rectangles):
            for right in rectangles[i + 1:]:
                if right.x0 >= left.x1:
                    break
                if left.y0 < right.y1 and right.y0 < left.y1:
                    raise ValueError("Stored cells overlap; their source locations are ambiguous.")
        return table_source, geometry_source, table_locator, cells
    except (IndexError, KeyError, TypeError, ValueError, LocatorError) as exc:
        raise PdfMappingError("Stored table or cell geometry is missing or inconsistent.", 409) from exc


def _page_origin(content, locations, page_number):
    origin = TextOrigin.unknown
    pages = [p for p in locations if isinstance(p, dict) and p.get("kind") == "page"
             and type(p.get("page_number")) is int and p["page_number"] == page_number
             and type(p.get("start_char")) is int and type(p.get("end_char")) is int
             and 0 <= p["start_char"] < p["end_char"] <= len(content)] if isinstance(locations, list) else []
    if len(pages) == 1:
        origin, _ = source_span_origin(content, locations, pages[0]["start_char"], pages[0]["end_char"])
    return origin


def bind_pdf_grid_mapping(session, *, case_id, proposal):
    """Bind stored cell coordinates without reconstructing canonical text offsets."""
    proposal = PdfGridMapping.model_validate(proposal)
    if proposal.case_id != case_id:
        raise PdfMappingError("Mapping does not belong to this case.", 404)
    content, locations, file_hash, text_hash, payload, revision, manifest = _snapshot(
        session, case_id, proposal.evidence_file_id, proposal.page_number)
    if proposal.source_revision != revision:
        raise PdfMappingError("Source or geometry changed. Rebuild the mapping.", 409)
    table_source, geometry_source, table_locator, cells = _table(
        payload, proposal.table_index, proposal.page_number)
    for field in type(proposal.context).model_fields:
        span = getattr(proposal.context, field)
        if span is not None and content[span.start_char:span.end_char] != span.text:
            raise PdfMappingError("Context text does not match its source offsets.", 409)
    origin = _page_origin(content, locations, proposal.page_number)
    mapping_revision = _digest(proposal.model_dump(mode="json"))
    meanings = {c.column_index: c.meaning for c in proposal.columns}
    candidates = []
    for row in proposal.rows:
        bound_cells = []
        for cell in row.cells:
            stored = cells.get((row.row_index, cell.column_index))
            if stored is None or stored[0] != cell.expected_text:
                raise PdfMappingError("Mapped cell does not match its stored grid position and text.", 409)
            bound_cells.append(PdfGridBoundCell(column_index=cell.column_index,
                proposed_meaning=meanings[cell.column_index], text=stored[0], locator=stored[1], origin=origin))
        candidates.append(PdfGridCandidate(row_index=row.row_index, cells=tuple(bound_cells),
            candidate_key=_digest(dict(mapping_revision=mapping_revision, row_index=row.row_index))))
    nomination = None
    if proposal.nomination_id is not None:
        from services.financial.model_pdf_nomination import nomination_snapshot_for_mapping
        nomination=nomination_snapshot_for_mapping(session,case_id=case_id,proposal=proposal)
    return PdfGridBoundMapping(proposal=proposal, mapping_revision=mapping_revision,nomination_snapshot=nomination,processing_manifest=manifest,
        file_sha256=file_hash, content_sha256=text_hash, table_source=table_source,
        geometry_source=geometry_source, table_locator=table_locator, candidates=tuple(candidates))
