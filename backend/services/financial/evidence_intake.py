"""Select financial sources in any format; prepare PDFs with the statement reader."""
from uuid import NAMESPACE_URL, UUID, uuid5
from sqlalchemy import select, or_, exists
from postgres.models.evidence import EvidenceFile, EvidenceFolder, EvidenceDocumentText, EvidenceTableGeometry
from services.financial.pdf_candidates import PdfMappingError
from services.financial.file_visibility import financial_file_visibility, set_financial_file_visibility, require_financial_file
from services.financial.statement_reprocessing import create_statement_version


def resolve_financial_selection(session, *, case_id, file_ids, folder_ids, include_other_formats=False):
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
    from services.financial.source_lineage import select_current_files, lineage_id
    eligible = files if include_other_formats else pdfs
    current = select_current_files(session, case_id, eligible)
    return dict(case_id=str(case_id), skipped_non_pdf=0 if include_other_formats else len(files)-len(pdfs), files=[dict(
        id=str(file.id), original_filename=file.original_filename, status=file.status,
        root_file_id=lineage_id(file),
        **financial_file_visibility(file)) for file in current], grouped_readings=len(eligible)-len(current))


def include_financial_sources(session, *, case_id, selections, actor):
    """Record the investigator's financial selection, without reading or importing.

    No format allow-list: a missing reader is not evidence of non-financial content.
    Check the complete preview before any writes. Retries are idempotent, and
    a removal after the preview must not be silently undone.
    """
    from datetime import datetime, timezone
    from uuid import uuid4
    from postgres.models.case import Case
    from postgres.models.evidence import IngestionLog
    from services.financial.file_scope import mark_financial_workspace, SCHEMA
    session.execute(select(Case.id).where(Case.id == case_id).with_for_update()).all()
    files = list(session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id,
        EvidenceFile.id.in_([item.evidence_file_id for item in selections]))
        .with_for_update().execution_options(populate_existing=True)))
    by_id = {file.id: file for file in files}
    if len(by_id) != len(selections):
        raise PdfMappingError('A selected file is no longer available in this case, or was selected twice. Refresh the selection.', 404)
    for item in selections:
        file = by_id[item.evidence_file_id]
        current = financial_file_visibility(file)
        enrolled = ((file.metadata_ or {}).get('financial_workspace') or {}).get('schema') == SCHEMA
        if (file.metadata_ or {}).get('financial_import_removal'):
            raise PdfMappingError('This file has removed imports. Use its recovery action in Financial before adding it again.', 409)
        if current['financial_visibility_revision'] != item.expected_revision and (current['financial_removed'] or not enrolled):
            raise PdfMappingError('A selected file changed after the preview. Review the selection again.', 409)
    for file in files:
        current = financial_file_visibility(file)
        enrolled = ((file.metadata_ or {}).get('financial_workspace') or {}).get('schema') == SCHEMA
        if enrolled and not current['financial_removed']:
            continue
        mark_financial_workspace(file, user_id=actor.user_id)
        actor_data = dict(user_id=str(actor.user_id), name=actor.name, email=actor.email)
        if current['financial_removed']:
            file.metadata_ = {**file.metadata_, 'financial_file_visibility': dict(
                removed=False, revision=str(uuid4()), changed_at=datetime.now(timezone.utc).isoformat(), actor=actor_data)}
        session.add(IngestionLog(case_id=case_id, evidence_file_id=file.id,
            filename=file.original_filename, level='info',
            message='Selected existing evidence for Financial review; no processing or import started.',
            extra=dict(action='financial_source_selected', actor=actor_data)))
    session.commit()
    return dict(case_id=str(case_id), file_ids=[str(item.evidence_file_id) for item in selections])


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
        from services.financial.reading_recovery import retry_reference_problem
        problem = retry_reference_problem(session, case_id=case_id, source_id=file.id, source=file)
        if problem:
            raise PdfMappingError(problem['message'], 409)
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
            from services.financial.file_scope import mark_financial_workspace
            mark_financial_workspace(file, user_id=actor.user_id)
            session.commit()
            return dict(case_id=str(case_id), source_file_id=str(file.id), evidence_file_id=str(file.id), outcome='ready')
        if file.status == 'processed':
            if (file.metadata_ or {}).get('statement_version_request'):
                from postgres.models.financial import FinancialSourceDocument
                if session.scalar(select(FinancialSourceDocument.id).where(FinancialSourceDocument.case_id == case_id,
                        FinancialSourceDocument.evidence_file_id == file.id).limit(1)):
                    raise PdfMappingError('This saved reading has no usable PDF geometry. Open its statement history and choose Read the statement again; its saved payments are retained.', 409)
                # A prior preparation without usable geometry resumes the same
                # internal reading; it must not manufacture another PDF copy.
                target = file
            else:
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
