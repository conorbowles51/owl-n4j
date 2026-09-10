"""Document-wide saved review progress. Selection is never completeness proof."""
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile, EvidenceDocumentText, EvidenceTableGeometry
from postgres.models.financial_candidates import FinancialCandidateMapping
from services.financial.candidate_store import CandidateStoreError, read_candidate_mapping

MAX_PROGRESS_PAGES = 2000
MAX_PROGRESS_MAPPINGS = 100
MAX_PROGRESS_READINGS = 1000


def candidate_document_progress(session, *, case_id, evidence_file_id):
    file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_file_id, EvidenceFile.case_id == case_id))
    if file is None:
        raise CandidateStoreError('Source file not found in this case.', 404)
    text = session.get(EvidenceDocumentText, evidence_file_id)
    if text is None:
        raise CandidateStoreError('PDF text preparation is not available.', 409)
    locations = text.source_locations
    if not isinstance(locations, list):
        raise CandidateStoreError('Stored page locations are invalid.', 409)
    page_numbers = {loc.get('page_number') for loc in locations if isinstance(loc, dict) and loc.get('kind') == 'page'}
    if not page_numbers or any(type(p) is not int or p < 1 for p in page_numbers):
        raise CandidateStoreError('Stored page coverage is unknown.', 409)
    if max(page_numbers) > MAX_PROGRESS_PAGES:
        raise CandidateStoreError('Document exceeds the 2,000-page progress limit; no partial overview was calculated.', 422)
    # Show internal missing page records explicitly; the final source page count is
    # not independently verified by extraction metadata.
    geometry = dict(session.execute(select(EvidenceTableGeometry.page_number, EvidenceTableGeometry.engine_job_id)
        .where(EvidenceTableGeometry.evidence_file_id == evidence_file_id)).all())
    mappings = list(session.scalars(select(FinancialCandidateMapping).where(
        FinancialCandidateMapping.case_id == case_id, FinancialCandidateMapping.evidence_file_id == evidence_file_id)
        .order_by(FinancialCandidateMapping.created_at, FinancialCandidateMapping.id).limit(MAX_PROGRESS_MAPPINGS + 1)))
    if len(mappings) > MAX_PROGRESS_MAPPINGS or sum(m.candidate_count for m in mappings) > MAX_PROGRESS_READINGS:
        raise CandidateStoreError('Document exceeds 100 batches or 1,000 readings; no partial overview was calculated.', 422)
    counts = dict(pending=0, resolved=0, rejected=0)
    pages = {p: dict(page_number=p, prepared=p in page_numbers and text.engine_job_id is not None and geometry.get(p) == text.engine_job_id,
        counts=dict(counts), batches=[]) for p in range(1, max(page_numbers) + 1)}
    unlocated = 0
    for mapping in mappings:
        saved = read_candidate_mapping(session, case_id=case_id, mapping_id=mapping.id)
        proposal = saved['original']['proposal']
        by_page = {}
        for row in saved['candidates']:
            counts[row['status']] += 1
            if proposal.get('schema_version') == 'pdf-grid-mapping-v1':
                row_pages = {proposal.get('page_number')}
            else:
                row_pages = {cell.get('page_number') for cell in row['original']['cells']}
            if len(row_pages) != 1 or next(iter(row_pages), None) not in pages:
                unlocated += 1
                continue
            page = next(iter(row_pages))
            pages[page]['counts'][row['status']] += 1
            entry = by_page.setdefault(page, dict(mapping_id=saved['id'], pending=0, resolved=0, rejected=0, next_pending_candidate_id=None))
            entry[row['status']] += 1
            if row['status'] == 'pending' and entry['next_pending_candidate_id'] is None:
                entry['next_pending_candidate_id'] = row['id']
        for page, entry in by_page.items():
            pages[page]['batches'].append(entry)
    return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), filename=file.original_filename,
        pages=list(pages.values()), counts=counts, unlocated_readings=unlocated, applied=False,
        limitation='Saved selections and decisions only. A page with no selected rows may contain transactions, fees or interest. Resolved rows do not establish complete extraction. Page coverage comes from stored extraction metadata; missing final pages cannot be ruled out.')
