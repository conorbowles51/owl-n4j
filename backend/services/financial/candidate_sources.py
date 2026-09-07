"""Read verified stored PDF grids for deliberate candidate nomination.

No detection, normalization or ledger writes happen here. A table may contain a
letter or disclosure; its presence is never a transaction classification.
"""
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile, EvidenceDocumentText, EvidenceTableGeometry
from services.financial.pdf_candidates import PdfMappingError
from services.financial.pdf_geometry_candidates import _snapshot, _table


def list_candidate_sources(session, *, case_id, limit=25, offset=0):
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
        raise PdfMappingError("Invalid source page limits.", 422)
    rows = list(session.execute(select(EvidenceFile.id, EvidenceFile.original_filename,
        EvidenceTableGeometry.page_number)
        .join(EvidenceTableGeometry, EvidenceTableGeometry.evidence_file_id == EvidenceFile.id)
        .join(EvidenceDocumentText, EvidenceDocumentText.evidence_file_id == EvidenceFile.id)
        .where(EvidenceFile.case_id == case_id)
        .order_by(EvidenceFile.id, EvidenceTableGeometry.page_number).offset(offset).limit(limit + 1)))
    return dict(case_id=str(case_id), offset=offset, has_more=len(rows) > limit,
        items=[dict(evidence_file_id=str(row[0]), filename=row[1], page_number=row[2]) for row in rows[:limit]])


def read_candidate_source(session, *, case_id, evidence_file_id, page_number, table_index=0):
    if type(table_index) is not int or table_index < 0:
        raise PdfMappingError("Table index must be a nonnegative integer.", 422)
    _, _, _, _, payload, revision = _snapshot(session, case_id, evidence_file_id, page_number)
    if table_index >= len(payload):
        raise PdfMappingError("No stored table at this position.", 404)
    source, geometry, locator, cells = _table(payload, table_index, page_number)
    rows = {}
    columns = set()
    for (row, column), (text, cell_locator) in sorted(cells.items()):
        if not text:
            continue
        if len(text) > 4096:
            raise PdfMappingError("A stored cell is too long for candidate review; no text was truncated.", 422)
        columns.add(column)
        rows.setdefault(row, []).append(dict(column_index=column, expected_text=text,
                                             locator=cell_locator.to_json()))
    if len(columns) > 64 or len(rows) > 1000:
        raise PdfMappingError("Stored table exceeds candidate review limits; no rows were truncated.", 422)
    return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), page_number=page_number,
        table_index=table_index, table_count=len(payload), source_revision=revision,
        table_source=source.value, geometry_source=geometry.value, locator=locator.to_json(),
        columns=sorted(columns), rows=[dict(row_index=row, cells=values) for row, values in rows.items()],
        applied=False)
