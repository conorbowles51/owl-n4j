"""Assess saved original cells against a fresh source binding, without writes."""
from uuid import UUID
from pydantic import ValidationError
from sqlalchemy import select

from postgres.models.financial_candidates import FinancialCandidateMapping, FinancialExtractionCandidate
from services.financial.candidate_store import CandidateStoreError, read_candidate_mapping
from services.financial.money import MoneyError, get_currency
from services.financial.pdf_candidates import PdfMappingError, _digest, bind_pdf_mapping
from services.financial.pdf_geometry_candidates import bind_pdf_grid_mapping
from services.financial.suspect_amounts import TextOrigin, read_amount


def current_candidate_original(session, *, case_id, candidate_id):
    """Return a saved original only if it still binds to the current source.

This is read-only. A future review writer must hold source and candidate locks
through this check and its commit, rather than treating this result as a permit.
"""
    with session.no_autoflush:
        mapping_id = session.scalar(select(FinancialCandidateMapping.id)
            .join(FinancialExtractionCandidate, FinancialExtractionCandidate.mapping_id == FinancialCandidateMapping.id)
            .where(FinancialExtractionCandidate.id == candidate_id, FinancialCandidateMapping.case_id == case_id))
        if mapping_id is None:
            raise CandidateStoreError("Candidate not found in this case.", 404)
        saved = read_candidate_mapping(session, case_id=case_id, mapping_id=mapping_id)
        proposal = saved["original"].get("proposal")
        try:
            if not isinstance(proposal, dict):
                raise ValueError("Missing original mapping proposal.")
            grid = proposal.get("schema_version") == "pdf-grid-mapping-v1"
            bound = (bind_pdf_grid_mapping if grid else bind_pdf_mapping)(session, case_id=case_id, proposal=proposal)
            original = bound.model_dump(mode="json")
            candidates = original.pop("candidates")
            if original != saved["original"] or candidates != [c["original"] for c in saved["candidates"]]:
                raise ValueError("Saved originals differ from the current source binding.")
        except PdfMappingError as exc:
            raise CandidateStoreError(str(exc), exc.status_code) from exc
        except (ValidationError, ValueError, TypeError, KeyError) as exc:
            raise CandidateStoreError("Saved candidate mapping is inconsistent. Rebuild it.") from exc
    candidate = next(c for c in saved["candidates"] if c["id"] == str(candidate_id))
    return saved, candidate, bound


def assess_candidate_amounts(session, *, case_id, candidate_id, currency):
    """Assess amount-like columns as proposals, preserving every uncertainty.

Currency is explicit caller context, not an inferred source fact. Columns of
unknown meaning are not classified as amounts. Even a certain numeric reading
does not resolve account, date, currency context, direction or admission.
"""
    # Check case scope before reporting anything about the saved source.
    saved, candidate, bound = current_candidate_original(session, case_id=case_id, candidate_id=candidate_id)
    try:
        get_currency(currency)
    except (MoneyError, TypeError, AttributeError) as exc:
        raise CandidateStoreError("Supply a supported currency code for this assessment.", 422) from exc
    amounts, unclassified = [], []
    grid = saved["original"]["proposal"]["schema_version"] == "pdf-grid-mapping-v1"
    typed = next(c for c in bound.candidates if c.candidate_key == candidate["candidate_key"])
    for cell in typed.cells:
        if cell.proposed_meaning not in ("amount", "debit", "credit", "balance"):
            if cell.proposed_meaning == "unknown":
                unclassified.append(cell.column_index)
            continue
        raw = cell.text if grid else cell.source.text
        source = ({"locator": cell.locator.to_json(), "text": raw} if grid else
                  {"text": raw, "start_char": cell.source.start_char, "end_char": cell.source.end_char,
                   "page_number": cell.page_number, "offset_unit": "unicode_code_points"})
        try:
            reading = read_amount(raw, currency, TextOrigin(cell.origin)).to_json()
        except MoneyError as exc:
            # Preserve an unassessable cell in the result instead of dropping it.
            amounts.append(dict(column_index=cell.column_index, proposed_meaning=cell.proposed_meaning,
                source=source, assessment=None, error=str(exc)))
            continue
        if "minor_units" in reading:
            reading["minor_units"] = str(reading["minor_units"])
        for proposal in reading.get("proposals", []):
            proposal["minor_units"] = str(proposal["minor_units"])
        amounts.append(dict(column_index=cell.column_index, proposed_meaning=cell.proposed_meaning,
                            source=source, assessment=reading, error=None))
    payload = dict(case_id=str(case_id), candidate_id=str(candidate_id), mapping_id=saved["id"],
        mapping_revision=saved["mapping_revision"], candidate_key=candidate["candidate_key"],
        currency=currency, currency_source="caller_supplied", source_context=saved["original"]["proposal"]["context"],
        amount_cells=amounts, unclassified_columns=unclassified, status=candidate["status"],
        review_revision=candidate["review_revision"], applied=False,
        limitation="Original numeric readings only; this assessment does not itself resolve a review or admit a transaction.")
    # Binds the exact displayed proposals, including currency, for a future review.
    payload["assessment_revision"] = _digest(payload)
    return payload


def assess_candidate_dates(session, *, case_id, candidate_id):
    """Fresh source-bound date proposals; no locale/year guesses or writes."""
    from services.financial.source_dates import assess_date_text
    saved, candidate, bound = current_candidate_original(session, case_id=case_id, candidate_id=candidate_id)
    grid = saved["original"]["proposal"]["schema_version"] == "pdf-grid-mapping-v1"
    typed = next(c for c in bound.candidates if c.candidate_key == candidate["candidate_key"])
    cells, unknown = [], []
    for cell in typed.cells:
        if cell.proposed_meaning not in ("date", "booking_date", "value_date", "transaction_date"):
            if cell.proposed_meaning == "unknown":
                unknown.append(cell.column_index)
            continue
        raw = cell.text if grid else cell.source.text
        source = ({"locator": cell.locator.to_json(), "text": raw} if grid else
                  {"text": raw, "start_char": cell.source.start_char, "end_char": cell.source.end_char,
                   "page_number": cell.page_number, "offset_unit": "unicode_code_points"})
        cells.append(dict(column_index=cell.column_index, proposed_meaning=cell.proposed_meaning,
            source=source, assessment=assess_date_text(raw, cell.origin)))
    payload = dict(case_id=str(case_id), candidate_id=str(candidate_id), mapping_id=saved["id"],
        review_revision=candidate["review_revision"], date_cells=cells, unclassified_columns=unknown,
        applied=False, limitation="Calendar proposals only. No date is selected, corrected or admitted by this assessment.")
    payload["assessment_revision"] = _digest(payload)
    return payload


def candidate_source_readings(session, *, case_id, candidate_id):
    """Fresh source-bound cells for review, independent of any amount/date guess."""
    saved, candidate, bound = current_candidate_original(session, case_id=case_id, candidate_id=candidate_id)
    grid = saved['original']['proposal']['schema_version'] == 'pdf-grid-mapping-v1'
    typed = next(c for c in bound.candidates if c.candidate_key == candidate['candidate_key'])
    cells = []
    for cell in typed.cells:
        raw = cell.text if grid else cell.source.text
        locator = cell.locator.to_json() if grid else ({'kind': 'page_only', 'page': cell.page_number}
            if cell.page_number else {'kind': 'unlocated'})
        cells.append(dict(column_index=cell.column_index, proposed_meaning=cell.proposed_meaning,
            text=raw, locator=locator))
    layout = None
    if grid:
        from services.financial.candidate_sources import read_candidate_source
        proposal = saved['original']['proposal']
        try:
            source = read_candidate_source(session, case_id=case_id, evidence_file_id=UUID(saved['evidence_file_id']),
                page_number=proposal['page_number'], table_index=proposal['table_index'])
        except PdfMappingError as exc:
            raise CandidateStoreError(str(exc), exc.status_code) from exc
        if source['source_revision'] != proposal['source_revision']:
            raise CandidateStoreError('Source changed while reading statement context. Reload the review.', 409)
        layout = source.get('layout_context')
        if layout:
            layout = {**layout, 'rows': [row for row in layout['rows'] if row['row_index'] == typed.row_index]}
            if not layout['rows']:
                layout = None
    return dict(case_id=str(case_id), candidate_id=str(candidate_id), mapping_id=saved['id'],
        evidence_file_id=saved['evidence_file_id'], review_revision=candidate['review_revision'],
        cells=cells, layout_context=layout, applied=False)
