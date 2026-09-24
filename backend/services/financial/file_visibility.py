"""Case-wide financial file-list choices, retaining the underlying evidence."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile, IngestionLog
from postgres.models.financial import FinancialSourceDocument, FinancialStatementPeriod, FinancialTransaction
from services.financial.pdf_candidates import PdfMappingError


def financial_file_visibility(file):
    value = (getattr(file, "metadata_", None) or {}).get('financial_file_visibility') or {}
    return dict(financial_imports_removed=bool((getattr(file, 'metadata_', None) or {}).get('financial_import_removal')),
                financial_removed=value.get('removed') is True,
                financial_visibility_revision=value.get('revision', 'initial'))


def require_financial_file(file):
    if financial_file_visibility(file)['financial_removed']:
        raise PdfMappingError('This file was removed from Financial. Restore it from Removed files in Statements & accounts before reviewing or importing it.', 409)


def set_financial_file_visibility(session, *, case_id, evidence_file_id, removed, expected_revision, actor):
    # Use the same lock order as statement confirmation, so removal cannot race
    # an import and leave newly imported payments behind an absent file.
    session.execute(select(Case.id).where(Case.id == case_id).with_for_update()).all()
    file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_file_id,
        EvidenceFile.case_id == case_id).with_for_update().execution_options(populate_existing=True))
    if file is None:
        raise PdfMappingError('File not found in this case.', 404)
    if not removed and (file.metadata_ or {}).get('financial_import_removal'):
        raise PdfMappingError('These imports were removed. Use Process PDF afresh to start without the old readings or reviews.', 409)
    current = financial_file_visibility(file)
    if current['financial_removed'] == removed:
        return dict(case_id=str(case_id), evidence_file_id=str(file.id), **current)
    if current['financial_visibility_revision'] != expected_revision:
        raise PdfMappingError('Another user changed this file. Refresh files before changing it again.', 409)
    if removed:
        sources = select(FinancialSourceDocument.id).where(FinancialSourceDocument.case_id == case_id,
            FinancialSourceDocument.evidence_file_id == file.id)
        has_period = session.scalar(select(FinancialStatementPeriod.id).where(
            FinancialStatementPeriod.source_document_id.in_(sources)).limit(1))
        has_payment = session.scalar(select(FinancialTransaction.id).where(
            FinancialTransaction.source_document_id.in_(sources)).limit(1))
        if has_period or has_payment:
            raise PdfMappingError('This file already has imported financial records. Open its transactions or statement review to correct or exclude them; it cannot be removed from this list.', 409)
    revision = str(uuid4())
    changed_at = datetime.now(timezone.utc).isoformat()
    actor_data = dict(user_id=str(actor.user_id), name=actor.name, email=actor.email)
    file.metadata_ = {**(file.metadata_ or {}), 'financial_file_visibility': dict(
        removed=removed, revision=revision, changed_at=changed_at, actor=actor_data)}
    session.add(IngestionLog(case_id=case_id, evidence_file_id=file.id,
        filename=file.original_filename, level='info',
        message='Removed file from Financial; original retained in Evidence.' if removed else 'Restored file to Financial.',
        extra=dict(action='financial_file_visibility', removed=removed, revision=revision, actor=actor_data)))
    session.commit()
    return dict(case_id=str(case_id), evidence_file_id=str(file.id),
        **financial_file_visibility(file))
