"""Case-wide draft progress, separate from evidence readings and ledger imports."""
from datetime import datetime, timezone
from copy import deepcopy
from uuid import UUID
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile
from services.financial.pdf_candidates import PdfMappingError, _digest
from services.financial.statement_import import read_statement_import
from services.financial.review_arithmetic import check_proposed_rows


def review_progress(file, statement_id):
    return (file.metadata_ or {}).get('financial_review_progress', {}).get(statement_id or '', None)


def previous_review_progress(session, file, statement_id):
    """Reuse only the explicitly related period, never guess among accounts."""
    parent = (file.metadata_ or {}).get('statement_parent_evidence_id')
    if not parent:
        return None
    parent_file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == UUID(parent),
        EvidenceFile.case_id == file.case_id))
    if parent_file is None:
        return None
    saved = review_progress(parent_file, statement_id)
    return {**saved, 'evidence_file_id': str(parent_file.id), 'filename': parent_file.original_filename} if saved else None


def save_progress(session, *, case_id, evidence_file_id, request, expected_review_revision, actor):
    # The evidence-row lock serialises first saves and edits to different
    # periods in this file, so updating metadata cannot lose another period.
    file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_file_id,
        EvidenceFile.case_id == case_id).with_for_update().execution_options(populate_existing=True))
    if file is None:
        raise PdfMappingError('Statement not found in this case.', 404)
    previous = review_progress(file, request.statement_id)
    revision = previous['review_revision'] if previous else 'initial'
    if revision != expected_review_revision:
        raise PdfMappingError('Another reviewer saved this statement. Your changes have not overwritten theirs. Reopen the statement to compare the saved review.', 409)
    proposal = read_statement_import(session, case_id=case_id, evidence_file_id=evidence_file_id,
        currency=request.currency, statement_id=request.statement_id, _include_period_checks=False)
    if proposal['revision'] != request.expected_revision:
        raise PdfMappingError('The statement reading changed. Reopen it before saving. Your earlier saved review is retained.', 409)
    if (proposal.get('current_import') or {}).get('evidence_file_id') == str(evidence_file_id):
        raise PdfMappingError('This statement is imported. Open its transactions to record further corrections.', 409)
    check_proposed_rows(proposal, [r.model_dump() for r in request.rows])
    payload = request.model_dump(mode='json')
    saved = dict(request=payload, review_revision=_digest(payload), saved_at=datetime.now(timezone.utc).isoformat(),
                 saved_by=dict(user_id=str(actor.user_id), name=actor.name))
    metadata = deepcopy(file.metadata_ or {})
    if previous and previous['request']['expected_revision'] != request.expected_revision:
        # Retain old corrections if the extraction changed underneath a draft.
        metadata.setdefault('financial_review_history', []).append(previous)
    metadata.setdefault('financial_review_progress', {})[request.statement_id or ''] = saved
    file.metadata_ = metadata
    session.commit()
    return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), **saved)
