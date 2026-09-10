"""Read verified stored PDF grids for deliberate candidate nomination.

No detection, normalization or ledger writes happen here. A table may contain a
letter or disclosure; its presence is never a transaction classification.
"""
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile, EvidenceDocumentText, EvidenceTableGeometry
from services.financial.pdf_candidates import PdfMappingError
from services.financial.pdf_geometry_candidates import _snapshot, _table, _page_origin


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
    content, locations, _, _, payload, revision, manifest = _snapshot(session, case_id, evidence_file_id, page_number)
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
    from services.financial.statement_layout_context import statement_layout_context
    source_rows = [dict(row_index=row, cells=values) for row, values in rows.items()]
    return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), page_number=page_number,
        table_index=table_index, table_count=len(payload), source_revision=revision,
        table_source=source.value, geometry_source=geometry.value, locator=locator.to_json(),
        text_origin=_page_origin(content, locations, page_number).value,
        columns=sorted(columns), rows=source_rows,
        layout_context=statement_layout_context(source_rows),
        processing_manifest=manifest, applied=False)


def suggest_candidate_rows(session, *, case_id, evidence_file_id, page_number,
                           table_index, expected_revision, date_column, amount_column, currency):
    """Find review candidates using two investigator-nominated columns, never admit rows."""
    from services.financial.source_dates import assess_date_text
    from services.financial.suspect_amounts import read_amount, TextOrigin
    from services.financial.money import get_currency, MoneyError
    source = read_candidate_source(session, case_id=case_id, evidence_file_id=evidence_file_id,
                                   page_number=page_number, table_index=table_index)
    if expected_revision != source['source_revision']:
        raise PdfMappingError('Stored source changed. Reload the table before suggesting rows.', 409)
    if (type(date_column) is not int or type(amount_column) is not int or date_column == amount_column
            or date_column not in source['columns'] or amount_column not in source['columns']):
        raise PdfMappingError('Choose distinct stored date and amount columns.', 422)
    try:
        currency = get_currency(currency).code
    except MoneyError as exc:
        raise PdfMappingError(str(exc), 422) from exc
    rows = []
    for row in source['rows']:
        cells = {c['column_index']: c for c in row['cells']}
        date_cell, amount_cell = cells.get(date_column), cells.get(amount_column)
        date_reading = assess_date_text(date_cell['expected_text'], 'unknown') if date_cell else None
        amount_reading, error = None, None
        if amount_cell:
            try:
                amount_reading = read_amount(amount_cell['expected_text'], currency, TextOrigin.unknown).to_json()
                if 'minor_units' in amount_reading:
                    amount_reading['minor_units'] = str(amount_reading['minor_units'])
                for proposal in amount_reading.get('proposals', []):
                    proposal['minor_units'] = str(proposal['minor_units'])
            except MoneyError as exc:
                error = str(exc)
        possible_date = bool(date_reading and date_reading['proposals'])
        possible_amount = bool(amount_reading and (
            'minor_units' in amount_reading or amount_reading.get('proposals')))
        rows.append(dict(row_index=row['row_index'], suggested=possible_date and possible_amount,
            date_source=date_cell, amount_source=amount_cell, date_assessment=date_reading,
            amount_assessment=amount_reading, amount_error=error,
            reason=('Date and amount each have a possible reading; inspect whether this is a transaction.'
                    if possible_date and possible_amount else
                    'No date-and-amount proposal under these columns. This does not rule out a transaction.')))
    return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), page_number=page_number,
        table_index=table_index, source_revision=source['source_revision'], date_column=date_column,
        amount_column=amount_column, currency=currency, currency_source='caller_supplied',
        checked_rows=len(rows), suggested_rows=sum(r['suggested'] for r in rows), rows=rows,
        applied=False, requires_source_review=True,
        limitation='Shape-based review suggestions only. Columns and currency are caller-supplied. Glyph origin is treated as unknown. No identity, date role, transaction classification, complete coverage or ledger admission is established; unselected rows may still contain transactions.')
