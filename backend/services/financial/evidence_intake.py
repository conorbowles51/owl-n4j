"""Resolve case folders and reuse or prepare existing PDFs for financial review."""
from uuid import NAMESPACE_URL, UUID, uuid5
from sqlalchemy import select, or_, exists
from postgres.models.evidence import EvidenceFile, EvidenceFolder, EvidenceDocumentText, EvidenceTableGeometry
from services.financial.pdf_candidates import PdfMappingError
from services.financial.file_visibility import financial_file_visibility, set_financial_file_visibility, require_financial_file
from services.financial.statement_reprocessing import create_statement_version


def resolve_financial_selection(session, *, case_id, file_ids, folder_ids):
    file_ids, folder_ids = set(file_ids), set(folder_ids)
    if not file_ids and not folder_ids:
        raise PdfMappingError('Select files or folders first.', 422)
    for model, identifiers in ((EvidenceFile, file_ids), (EvidenceFolder, folder_ids)):
        found = set(session.scalars(select(model.id).where(model.case_id == case_id, model.id.in_(identifiers)))) if identifiers else set()
        if found != identifiers:
            raise PdfMappingError('A selected file or folder is no longer available in this case. Refresh the folder list.', 404)
    descendants = select(EvidenceFolder.id).where(EvidenceFolder.case_id == case_id,
        EvidenceFolder.id.in_(folder_ids)).cte('financial_folders', recursive=True)
    descendants = descendants.union(select(EvidenceFolder.id).join(descendants,
        EvidenceFolder.parent_id == descendants.c.id).where(EvidenceFolder.case_id == case_id))
    files = list(session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id,
        or_(EvidenceFile.id.in_(file_ids), EvidenceFile.folder_id.in_(select(descendants.c.id))))
        .order_by(EvidenceFile.original_filename, EvidenceFile.id).limit(10001)))
    if len(files) > 10000:
        raise PdfMappingError('This selection contains more than 10,000 files. Select fewer folders and send them in separate groups. Nothing has been sent.', 422)
    pdfs = [file for file in files if file.original_filename.lower().endswith('.pdf')]
    return dict(case_id=str(case_id), skipped_non_pdf=len(files)-len(pdfs), files=[dict(
        id=str(file.id), original_filename=file.original_filename, status=file.status,
        **financial_file_visibility(file)) for file in pdfs])


def has_financial_reading(session, file):
    return bool(session.scalar(select(exists().where(EvidenceDocumentText.evidence_file_id == file.id)))) and bool(
        session.scalar(select(exists().where(EvidenceTableGeometry.evidence_file_id == file.id))))


async def prepare_existing_financial_file(session, *, case_id, evidence_file_id, expected_revision,
                                         actor, resolve_path, process_files):
    file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_file_id, EvidenceFile.case_id == case_id))
    if file is None:
        raise PdfMappingError('File not found in this case.', 404)
    if not file.original_filename.lower().endswith('.pdf'):
        raise PdfMappingError('Financial statement review accepts PDFs. The file remains in Evidence.', 422)
    reset = (file.metadata_ or {}).get('financial_import_removal')
    target = file
    if reset:
        if financial_file_visibility(file)['financial_visibility_revision'] != expected_revision:
            raise PdfMappingError('The removal changed. Refresh files before preparing them again.', 409)
        target = create_statement_version(session, case_id=case_id,
            evidence_file_id=UUID(reset['restart_file_id']),
            request_id=uuid5(NAMESPACE_URL, f"loupe-financial-reset:{case_id}:{reset['id']}:{file.sha256}"),
            reset_revision=reset['id'], actor=actor, resolve_path=resolve_path)
    else:
        # Explicitly sending a hidden, unimported file restores its file-list choice.
        set_financial_file_visibility(session, case_id=case_id, evidence_file_id=file.id,
            removed=False, expected_revision=expected_revision, actor=actor)
        if file.status == 'processed' and has_financial_reading(session, file):
            return dict(case_id=str(case_id), source_file_id=str(file.id), evidence_file_id=str(file.id), outcome='ready')
        if file.status == 'processed':
            target = create_statement_version(session, case_id=case_id, evidence_file_id=file.id,
                request_id=uuid5(NAMESPACE_URL, f'loupe-financial-intake:{case_id}:{file.id}'),
                actor=actor, resolve_path=resolve_path)
    require_financial_file(target)
    if target.status == 'processed' and has_financial_reading(session, target):
        return dict(case_id=str(case_id), source_file_id=str(file.id), evidence_file_id=str(target.id), outcome='ready')
    if target.status == 'processing':
        return dict(case_id=str(case_id), source_file_id=str(file.id), evidence_file_id=str(target.id), outcome='processing')
    result = await process_files(session, case_id=case_id, file_ids=[target.id], preparation_mode='pdf_review',
        force_reprocess=target.status == 'processed', requested_by_user_id=actor.user_id)
    if len(result.get('job_ids', [])) != 1:
        raise PdfMappingError('A financial reading job could not be confirmed. Refresh files before trying again. The file remains in Evidence.', 409)
    return dict(case_id=str(case_id), source_file_id=str(file.id), evidence_file_id=str(target.id), outcome='queued')
